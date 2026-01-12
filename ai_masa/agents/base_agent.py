import sys
import json
import subprocess
import threading
import time
import os
import argparse
from typing import Optional, List, Dict, Any

from ..models.message import Message
from ..comms.redis_broker import RedisBroker
from ..comms.session_manager import SessionManager
from ..models.prompts import JSON_FORMAT_EXAMPLE, PROMPT_TEMPLATE, OBSERVER_INSTRUCTION

class BaseAgent:
    def __init__(self, name: str, description: str, user_lang: str = 'Japanese',
                 session_id: Optional[str] = None, session_manager: Optional[SessionManager] = None,
                 redis_host: str = 'localhost', redis_port: int = 6379, redis_db: int = 0,
                 llm_command: str = "echo '{\"to_agent\": \"dummy\", \"content\": \"dummy response\"}'",
                 llm_session_create_command: str = "echo 'new_session_id'",
                 working_dir: Optional[str] = None,
                 start_heartbeat: bool = True):
        self.name = name
        self.description = description
        self.user_lang = user_lang
        self.language = 'English' # LLM間の会話は英語に固定
        self.llm_command = llm_command
        self.llm_session_create_command = llm_session_create_command
        self.working_dir = working_dir

        if not session_id:
            raise ValueError("session_id must be provided for BaseAgent in individual session model.")
        self.session_id = session_id
        
        if session_manager:
            self.session_manager = session_manager
        else:
            self.session_manager = SessionManager(host=redis_host, port=redis_port, db=redis_db)
        
        print(f"[{self.name}] Using session ID: {self.session_id}")
        
        self.broker = RedisBroker(host=redis_host, port=redis_port, db=redis_db)
        self.broker.connect()
        
        self.role_prompt = self._generate_role_prompt()

        self.shutdown_event = threading.Event()
        self.heartbeat_timer = None
        if start_heartbeat:
            self._start_heartbeat()

    def shutdown(self):
        print(f"[{self.name}] Shutting down...")
        self.shutdown_event.set()
        if self.heartbeat_timer:
            self.heartbeat_timer.cancel()

    def _send_heartbeat(self):
        if self.shutdown_event.is_set():
            return
        self.broadcast(target=self.name, content="heartbeat", cc=["_broadcast_"], job_id="_system_")
        self.heartbeat_timer = threading.Timer(30, self._send_heartbeat)
        self.heartbeat_timer.start()

    def _start_heartbeat(self):
        print(f"[{self.name}] Starting heartbeat...")
        self._send_heartbeat()

    def _generate_role_prompt(self):
        return f"""Your name is {self.name}. {self.description}
When you send a message to the 'User' agent, please respond in {self.user_lang}.
Your response must be a JSON object that adheres to the following format.
IMPORTANT: The 'to_agent' field must be the 'from_agent' of the message you are replying to.
Example:
```json
{JSON_FORMAT_EXAMPLE}
```
""".strip()

    def observe_loop(self):
        print(f"[{self.name}] Listening on Redis...")
        self.broker.subscribe(self._on_message_received, shutdown_event=self.shutdown_event)

    def _is_message_for_me(self, msg: Message) -> bool:
        """Check if the message is relevant to this agent."""
        is_sender = msg.from_agent == self.name
        is_recipient = msg.to_agent == self.name
        is_cc = self.name in (msg.cc_agents or [])
        is_broadcast = "_broadcast_" in (msg.cc_agents or [])
        return is_sender or is_recipient or is_cc or is_broadcast

    def _on_message_received(self, message_json: str):
        try:
            msg = Message.from_json(message_json)
            job_id = msg.job_id or "default"

            # Check if this message is relevant before doing anything else
            if not self._is_message_for_me(msg):
                return
            
            # Save relevant message to my own history
            # Don't save my own sent messages here, it is handled in broadcast()
            if msg.from_agent != self.name:
                self.session_manager.add_message(self.session_id, json.loads(message_json))

            # Ignore heartbeat for console logging and response logic
            if msg.content == "heartbeat" and job_id == "_system_":
                return

            if msg.to_agent == self.name:
                print(f"[{self.name}][{job_id}] 📨 Received from {msg.from_agent}: {msg.content}")
                self.think_and_respond(msg, job_id)
            elif self.name in (msg.cc_agents or []):
                print(f"[{self.name}][{job_id}] 👀 (CC) Saw message from {msg.from_agent}")
                self.think_and_respond(msg, job_id, is_observer=True)

        except Exception as e:
            print(f"[{self.name}] Error in _on_message_received: {e}")

    def think_and_respond(self, trigger_msg: Message, job_id: str, is_observer: bool = False):
        agent_state = self.session_manager.get_agent_state(self.session_id, self.name) or {}
        llm_sessions = agent_state.get("llm_sessions", {})
        llm_session_id = llm_sessions.get(job_id)
        
        if not llm_session_id:
            print(f"[{self.name}][{job_id}] No LLM session found. Creating a new one...")
            llm_session_id = self._create_llm_session(job_id)
            if not llm_session_id:
                print(f"[{self.name}][{job_id}] Failed to create LLM session. Aborting.")
                return
            
            llm_sessions[job_id] = llm_session_id
            agent_state["llm_sessions"] = llm_sessions
            self.session_manager.update_agent_state(self.session_id, self.name, agent_state)
            print(f"[{self.name}][{job_id}] New LLM session created: {llm_session_id}")

        prompt = self._build_prompt(trigger_msg, job_id, is_observer)
        llm_response_json = self._invoke_llm(prompt, llm_session_id)
        
        if not llm_response_json:
            print(f"[{self.name}][{job_id}] Error: LLM did not return a response.")
            return

        try:
            response_data = json.loads(llm_response_json)
            self.broadcast(
                target=response_data.get("to_agent"),
                content=response_data.get("content"),
                cc=response_data.get("cc_agents"),
                job_id=job_id
            )
        except json.JSONDecodeError as e:
            print(f"[{self.name}][{job_id}] Error decoding LLM response: {e}\nReceived: {llm_response_json}")
        except Exception as e:
            print(f"[{self.name}][{job_id}] Error processing LLM response: {e}")

    def _create_llm_session(self, job_id: str) -> Optional[str]:
        print(f"[{self.name}][{job_id}] Initializing LLM session with role: {self.role_prompt}")
        try:
            process = subprocess.run(
                self.llm_session_create_command,
                input=self.role_prompt,
                capture_output=True, text=True, shell=True, check=True,
                cwd=self.working_dir
            )
            session_id = process.stdout.strip().split('\n')[-1]
            return session_id
        except subprocess.CalledProcessError as e:
            print(f"[{self.name}][{job_id}] Error executing LLM session creation command: {e}\nStderr: {e.stderr}")
            return None
        except FileNotFoundError:
            print(f"[{self.name}][{job_id}] Error: LLM command not found: '{self.llm_session_create_command}'")
            return None

    def _build_prompt(self, trigger_msg: Message, job_id: str, is_observer: bool = False) -> str:
        # Get all history relevant to this agent from its session
        full_history_list = self.session_manager.get_history(self.session_id, self.name) or []
        
        # CRITICAL: Filter history by the current job_id
        history_for_job = [msg for msg in full_history_list if msg.get("job_id") == job_id]
        
        history = "\n".join([f"- {msg.get('from_agent')}: {msg.get('content')}" for msg in history_for_job])
        
        observer_instructions = OBSERVER_INSTRUCTION if is_observer else ""
            
        return PROMPT_TEMPLATE.format(
            name=self.name, 
            role_prompt=self.role_prompt,
            history=history,
            from_agent=trigger_msg.from_agent, 
            content=trigger_msg.content,
            observer_instructions=observer_instructions
        )

    def _invoke_llm(self, prompt: str, llm_session_id: str) -> Optional[str]:
        print(f"[{self.name}][{llm_session_id}] 🧠 Thinking...")
        command_to_run = os.path.expandvars(self.llm_command.format(session_id=llm_session_id))
        
        try:
            process = subprocess.run(
                command_to_run,
                input=prompt, capture_output=True, text=True, shell=True, check=True,
                cwd=self.working_dir
            )
            raw_stdout = process.stdout
            try:
                outer_response = json.loads(raw_stdout)
                if "response" in outer_response:
                    content_str = outer_response["response"]
                    if content_str.strip().startswith("```json"):
                        json_start = content_str.find("{")
                        json_end = content_str.rfind("}") + 1
                        if json_start != -1 and json_end != -1:
                            return json.dumps(json.loads(content_str[json_start:json_end]))
                return raw_stdout
            except json.JSONDecodeError:
                return raw_stdout
        except subprocess.CalledProcessError as e:
            print(f"[{self.name}] Error executing LLM command: {e}\nStderr: {e.stderr}")
            return None
        except FileNotFoundError:
            print(f"[{self.name}] Error: LLM command not found: '{command_to_run}'")
            return None

    def broadcast(self, target: str, content: str, cc: Optional[List[str]] = None, job_id: str = "default"):
        if not target or (not content and content != "heartbeat"):
            print(f"[{self.name}][{job_id}] ⚠️ Missing target or content. Aborting broadcast.")
            return

        msg = Message(self.name, target, content, cc_agents=cc, job_id=job_id)
        msg_json = msg.to_json()
        
        # Save my own message to my history before sending
        self.session_manager.add_message(self.session_id, json.loads(msg_json))
        
        # Publish to all agents
        self.broker.publish(msg_json)
        
        if not (content == "heartbeat" and job_id == "_system_"):
            print(f"[{self.name}][{job_id}] 🚀 Sent to {target}: {content}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run a BaseAgent.")
    parser.add_argument("name", type=str, help="Name of the agent")
    parser.add_argument("description", type=str, help="Description of the agent")
    parser.add_argument("--user_lang", type=str, default="Japanese", help="Language for user interaction")
    parser.add_argument("--session_id", type=str, required=True, help="Session ID for the agent's history")
    parser.add_argument("--redis_host", type=str, default="localhost", help="Redis host")
    parser.add_argument("--redis_port", type=int, default=6379, help="Redis port")
    parser.add_argument("--redis_db", type=int, default=0, help="Redis DB")
    parser.add_argument("--llm_command", type=str, default="echo '{\"to_agent\": \"dummy\", \"content\": \"dummy response\"}'", help="Command to invoke LLM")
    parser.add_argument("--llm_session_create_command", type=str, default="echo 'new_session_id'", help="Command to create LLM session")
    
    args = parser.parse_args()

    agent = BaseAgent(
        name=args.name,
        description=args.description,
        user_lang=args.user_lang,
        session_id=args.session_id,
        redis_host=args.redis_host,
        redis_port=args.redis_port,
        redis_db=args.redis_db,
        llm_command=args.llm_command,
        llm_session_create_command=args.llm_session_create_command
    )
    agent.observe_loop()
