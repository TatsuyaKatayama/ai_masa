import sys
import subprocess
import shlex
import os
import argparse
import logging
import json
from typing import Optional, List, Dict, Any

from .base_agent import BaseAgent
from ..models.message import Message

logger = logging.getLogger(__name__)

class OpencodeAgent(BaseAgent):
    """
    An agent that uses the external Opencode CLI command as an LLM.
    A single, persistent Opencode session is created upon initialization and reused
    for all subsequent interactions. The user is responsible for configuring the
    Opencode CLI backend (e.g., OpenAI, Anthropic) beforehand via
    `~/.config/opencode/config.json`.
    """
    def __init__(self, name: str = "OpencodeAgent", description: Optional[str] = None,
                 user_lang: str = 'Japanese', memory_id: str = "opencode_session",
                 redis_host: str = 'localhost', redis_port: int = 6379, redis_db: int = 0,
                 llm_command: Optional[str] = None,
                 working_dir: Optional[str] = None, 
                 model: str = "google/gemini-2.5-flash", **kwargs):
        
        final_description = description if description is not None else \
            "You are an intelligent AI assistant powered by the Opencode CLI. Your task is to understand user messages and generate concise and accurate responses using your configured LLM backend."

        super().__init__(
            name=name,
            description=final_description,
            user_lang=user_lang,
            memory_id=memory_id,
            redis_host=redis_host,
            redis_port=redis_port,
            redis_db=redis_db,
            llm_command="dummy",  # Placeholder, will be set in _initialize_session
            llm_session_create_command="dummy",  # BaseAgent's logic is bypassed
            working_dir=working_dir,
            **kwargs
        )

        self.model = model
        self.session_id: Optional[str] = None
        self._initialize_session()

    def _initialize_session(self) -> None:
        """
        Initializes a persistent Opencode session at agent startup.
        It sends the role_prompt to create a session, stores the session ID,
        and constructs the final `llm_command` for all subsequent interactions.
        """
        logger.debug(f"[{self.name}] Initializing persistent Opencode session.")
        try:
            model_flag = f"-m {shlex.quote(self.model)}" if self.model else ""
            init_command = f"docker exec -i opencode-cli opencode {model_flag} run --format json"
            prompt = self.role_prompt
            logger.debug(f"[{self.name}] Running session init command: {init_command}")

            process = subprocess.run(
                init_command, shell=True, check=True,
                input=prompt,
                capture_output=True, text=True, timeout=120,
                cwd=self.working_dir
            )

            output_lines = process.stdout.strip().split('\n')
            session_id = None
            for line in output_lines:
                try:
                    json_output = json.loads(line)
                    if "sessionID" in json_output:
                        session_id = json_output["sessionID"]
                        break
                except json.JSONDecodeError:
                    continue

            if session_id:
                self.session_id = session_id
                logger.info(f"[{self.name}] Persistent session ID retrieved: {self.session_id}")
                self.llm_command = f"docker exec -i opencode-cli opencode {model_flag} run -s {shlex.quote(self.session_id)}"
                logger.debug(f"[{self.name}] LLM command updated to: {self.llm_command}")
            else:
                logger.critical(f"[{self.name}] Could not find sessionID in the output. Full output: {process.stdout.strip()}")
                raise RuntimeError("Failed to initialize Opencode session: sessionID not found.")

        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
            stderr_output = e.stderr.strip() if hasattr(e, 'stderr') and e.stderr else 'N/A'
            logger.critical(f"[{self.name}] Failed to run command to create session: {e}. Stderr: {stderr_output}")
            raise RuntimeError(f"Failed to initialize Opencode session: {e}") from e

    def think_and_respond(self, trigger_msg: Message, job_id: str, is_observer: bool = False):
        """
        Handles incoming messages using the agent's single persistent Opencode session.
        Bypasses BaseAgent's job-specific session management.
        """
        if not self.session_id:
            logger.error(f"[{self.name}] Cannot handle message; persistent session not initialized. Aborting.")
            return

        logger.debug(f"[{self.name}][{job_id}] Starting OpencodeAgent's custom think_and_respond.")
        
        # Use the single, persistent session ID
        llm_session_id = self.session_id
        
        # Build prompt using BaseAgent's logic, but ensure history is correct.
        # The history management needs to be adapted for a single session if context is to be shared,
        # or kept job-specific if opencode itself handles session-level context.
        # For now, we assume opencode session itself maintains context per session, not per job_id here.
        # The memory_manager still stores history by job_id.
        prompt = self._build_prompt(trigger_msg, job_id, is_observer)
        logger.debug(f"[{self.name}][{job_id}] Built prompt:\n---PROMPT---\n{prompt}\n---END PROMPT---")

        llm_response_json = self._invoke_llm(prompt, llm_session_id)
        logger.debug(f"[{self.name}][{job_id}] Received raw response from _invoke_llm: '''{llm_response_json}'''")
        
        if not llm_response_json:
            logger.error(f"[{self.name}][{job_id}] Error: LLM did not return a response.")
            return

        try:
            # Extract JSON from markdown code block if present
            clean_json_str = llm_response_json
            if "```" in clean_json_str:
                json_start = clean_json_str.find('{')
                json_end = clean_json_str.rfind('}') + 1
                if json_start != -1 and json_end != 0:
                    clean_json_str = clean_json_str[json_start:json_end]
            
            response_data = json.loads(clean_json_str)
            self.broadcast(
                target=response_data.get("to_agent"),
                content=response_data.get("content"),
                cc=response_data.get("cc_agents"),
                job_id=job_id
            )
        except json.JSONDecodeError as e:
            logger.error(f"[{self.name}][{job_id}] Error decoding LLM response: {e}\nReceived: {llm_response_json}")
        except Exception as e:
            logger.error(f"[{self.name}][{job_id}] Error processing LLM response: {e}")

    def _invoke_llm(self, prompt: str, llm_session_id: str) -> Optional[str]:
        """
        Invokes the LLM with a prompt using the persistent session.
        The `llm_session_id` argument is received but the internal command
        already has the correct session ID from initialization.
        """
        if not self.session_id or self.llm_command == "dummy":
            logger.error(f"[{self.name}] LLM session is not initialized. Cannot invoke LLM.")
            return None

        logger.debug(f"[{self.name}][{self.session_id}] Starting OpencodeAgent's custom _invoke_llm.")
        logger.info(f"[{self.name}][{self.session_id}] 🧠 Thinking...")
        # The session_id is already correctly embedded in self.llm_command
        command_to_run = os.path.expandvars(self.llm_command)
        logger.debug(f"[{self.name}][{self.session_id}] Running LLM command: {command_to_run}")
        
        try:
            process = subprocess.run(
                command_to_run,
                input=prompt, capture_output=True, text=True, shell=True, check=True,
                cwd=self.working_dir
            )
            response_text = process.stdout.strip()
            logger.debug(f"[{self.name}][{self.session_id}] LLM raw stdout:\n{response_text}")
            
            return response_text
            
        except subprocess.CalledProcessError as e:
            logger.error(f"[{self.name}] Error executing LLM command: {e}\nStderr: {e.stderr}")
            return None
        except FileNotFoundError:
            logger.error(f"[{self.name}] Error: LLM command not found: '{command_to_run}'")
            return None

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, stream=sys.stdout, format='[%(levelname)s] %(message)s')

    parser = argparse.ArgumentParser(description="Launch an OpencodeAgent.")
    parser.add_argument("name", type=str, help="The name of the agent.")
    parser.add_argument("description", type=str, nargs='?', default=None, help="The description of the agent.")
    parser.add_argument("--user_lang", type=str, default="Japanese", help="Language for user interaction.")
    parser.add_argument("--memory_id", type=str, required=True, help="Session ID for the agent's history.")
    parser.add_argument("--redis_host", type=str, default="localhost", help="Redis host.")
    parser.add_argument("--redis_port", type=int, default=6379, help="Redis port.")
    parser.add_argument("--redis_db", type=int, default=0, help="Redis DB.")
    parser.add_argument('--llm_command', type=str, default=None, help='The command to execute for the LLM.')
    parser.add_argument('--working_dir', type=str, default=None, help='Working directory for LLM commands.')
    parser.add_argument('--model', type=str, default='google/gemini-2.5-flash', help='The opencode model to use (e.g., google/gemini-2.5-flash).')
    parser.add_argument("--logging_level", type=str, default="DEBUG", help="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)")

    args = parser.parse_args()

    log_level = getattr(logging, args.logging_level.upper(), logging.INFO)
    logging.basicConfig(level=log_level, stream=sys.stdout, format='[%(name)s][%(levelname)s] %(message)s')

    agent = OpencodeAgent(
        name=args.name,
        description=args.description,
        user_lang=args.user_lang,
        memory_id=args.memory_id,
        redis_host=args.redis_host,
        redis_port=args.redis_port,
        redis_db=args.redis_db,
        llm_command=args.llm_command,
        working_dir=args.working_dir,
        model=args.model
    )
    try:
        agent.observe_loop()
    except KeyboardInterrupt:
        logger.info(f"[{agent.name}] Shutting down.")
    finally:
        agent.shutdown()
