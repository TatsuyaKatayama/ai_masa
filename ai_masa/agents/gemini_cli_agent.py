import sys
import subprocess
import shlex
import os
import argparse
from typing import Optional
from .base_agent import BaseAgent

class GeminiCliAgent(BaseAgent):
    """
    外部のGemini CLIコマンドをLLMとして利用するエージェント。
    """
    def __init__(self, name: str = "GeminiCliAgent", description: Optional[str] = None,
                 user_lang: str = 'Japanese', session_id: str = "gemini_cli_session",
                 redis_host: str = 'localhost', redis_port: int = 6379, redis_db: int = 0,
                 llm_command: Optional[str] = None,
                 llm_session_create_command: Optional[str] = None,
                 working_dir: Optional[str] = None, **kwargs):
        
        final_description = description if description is not None else \
            "You are an intelligent AI assistant equipped with the Gemini CLI. Your task is to understand user messages and generate concise and accurate responses using the Gemini CLI tool."

        final_llm_command = llm_command
        if final_llm_command is None:
            final_llm_command = "gemini --resume {session_id} --output-format json"

        final_llm_session_create_command = llm_session_create_command or "echo 'new_session_id'"

        super().__init__(
            name=name,
            description=final_description,
            user_lang=user_lang,
            session_id=session_id,
            redis_host=redis_host,
            redis_port=redis_port,
            redis_db=redis_db,
            llm_command=final_llm_command,
            llm_session_create_command=final_llm_session_create_command,
            working_dir=working_dir,
            **kwargs
        )

        self.parsed_llm_args = []
        expanded_llm_command = os.path.expandvars(self.llm_command)
        llm_command_parts = shlex.split(expanded_llm_command)
        i = 0
        while i < len(llm_command_parts):
            part = llm_command_parts[i]
            if part in ('-y', '--yolo', '--include-directories', '-I'):
                self.parsed_llm_args.append(part)
                if part in ('--include-directories', '-I') and i + 1 < len(llm_command_parts) and not llm_command_parts[i+1].startswith('-'):
                    self.parsed_llm_args.append(llm_command_parts[i+1])
                    i += 1
            i += 1
        
        if self.working_dir:
            gemini_dir = os.path.join(self.working_dir, '.gemini')
            settings_path = os.path.join(gemini_dir, 'settings.json')
            os.makedirs(gemini_dir, exist_ok=True)
            if not os.path.exists(settings_path):
                with open(settings_path, 'w') as f:
                    f.write('{}')
                print(f"[{self.name}] Created {settings_path}")

    def _create_llm_session(self, job_id: str) -> Optional[str]:
        """
        Creates a new Gemini CLI session by running a one-shot command and returns the next available session index.
        It checks both stdout and stderr for the session list, as gemini CLI's output stream may vary.
        """
        import re
        session_index = 0
        try:
            result = subprocess.run(
                "gemini --list-sessions",
                shell=True, capture_output=True, text=True, check=False,
                cwd=self.working_dir
            )
            # The command might not raise an error even if it fails, so we check stderr.
            # The output might be in stdout or stderr.
            output = result.stdout.strip() or result.stderr.strip()

            if "No previous sessions found for this project." in output or "No sessions found." in output:
                session_index = 1
            else:
                # Try to find "Available sessions for this project (X):"
                match = re.search(r"Available sessions for this project \((\d+)\):", output)
                if match:
                    session_count = int(match.group(1))
                    session_index = session_count + 1
                else:
                    # Fallback to counting lines if the header is not found
                    session_lines = [line for line in output.split('\n') if line.strip() and line.strip()[0].isdigit() and '.' in line]
                    if session_lines:
                        session_index = len(session_lines) + 1
                    else:
                        # If we have output but can't parse it, it's safer to abort.
                        print(f"[{self.name}][{job_id}] CRITICAL: Could not determine session count from gemini output.", file=sys.stderr)
                        print(f"[{self.name}][{job_id}] Output was: {output}", file=sys.stderr)
                        return None
            
            if session_index == 0: # Should not happen if logic is correct
                print(f"[{self.name}][{job_id}] CRITICAL: Calculated session_index is 0. Aborting.", file=sys.stderr)
                return None

        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"[{self.name}][{job_id}] CRITICAL: Failed to execute 'gemini --list-sessions': {e}", file=sys.stderr)
            return None

        try:
            init_command = f"gemini {' '.join(self.parsed_llm_args)} {shlex.quote(self.role_prompt)}"
            subprocess.run(
                init_command, shell=True, check=True,
                capture_output=True, text=True, timeout=80,
                cwd=self.working_dir
            )
        except subprocess.CalledProcessError as e:
            print(f"[{self.name}][{job_id}] Info: Initial gemini command for session creation finished with code {e.returncode}. This is often expected.")
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            print(f"[{self.name}][{job_id}] Error during Gemini session initialization: {e}", file=sys.stderr)
            return None
        
        print(f"[{self.name}][{job_id}] New session will use index: {session_index}")
        return str(session_index)



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Launch a GeminiCliAgent.")
    parser.add_argument("name", type=str, help="The name of the agent.")
    parser.add_argument("description", type=str, nargs='?', default=None, help="The description of the agent.")
    parser.add_argument("--user_lang", type=str, default="Japanese", help="Language for user interaction.")
    parser.add_argument("--session_id", type=str, required=True, help="Session ID for the agent's history.")
    parser.add_argument("--redis_host", type=str, default="localhost", help="Redis host.")
    parser.add_argument("--redis_port", type=int, default=6379, help="Redis port.")
    parser.add_argument("--redis_db", type=int, default=0, help="Redis DB.")
    parser.add_argument('--llm_command', type=str, default=None, help='The command to execute for the LLM.')
    parser.add_argument('--llm_session_create_command', type=str, default=None, help='The command to create LLM session.')
    parser.add_argument('--working_dir', type=str, default=None, help='Working directory for LLM commands.')

    args = parser.parse_args()

    agent = GeminiCliAgent(
        name=args.name,
        description=args.description,
        user_lang=args.user_lang,
        session_id=args.session_id,
        redis_host=args.redis_host,
        redis_port=args.redis_port,
        redis_db=args.redis_db,
        llm_command=args.llm_command,
        llm_session_create_command=args.llm_session_create_command,
        working_dir=args.working_dir
    )
    try:
        agent.observe_loop()
    except KeyboardInterrupt:
        print(f"[{agent.name}] Shutting down.")
    finally:
        agent.shutdown()
