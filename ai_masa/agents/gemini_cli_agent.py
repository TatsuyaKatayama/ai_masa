import sys
import subprocess
import shlex
import os
from .base_agent import BaseAgent

class GeminiCliAgent(BaseAgent):
    """
    外部のGemini CLIコマンドをLLMとして利用するエージェント。
    """
    def __init__(self, name="GeminiCliAgent", redis_host='localhost', user_lang='Japanese', description=None, **kwargs):
        llm_command = kwargs.pop('llm_command', None)
        if llm_command is None:
            llm_command = "gemini --resume {session_id} --output-format json"
        llm_session_create_command = kwargs.pop('llm_session_create_command', "")
        working_dir = kwargs.pop('working_dir', None)

        final_description = description if description is not None else \
            "You are an intelligent AI assistant equipped with the Gemini CLI. Your task is to understand user messages and generate concise and accurate responses using the Gemini CLI tool."

        super().__init__(
            name=name,
            description=final_description,
            user_lang=user_lang,
            redis_host=redis_host,
            llm_command=llm_command,
            llm_session_create_command=llm_session_create_command,
            working_dir=working_dir,
            **kwargs # 残りのkwargsをBaseAgentに渡す
        )

        # Parse llm_command to extract common arguments for session creation
        self.parsed_llm_args = []
        expanded_llm_command = os.path.expandvars(self.llm_command) # Expand environment variables
        llm_command_parts = shlex.split(expanded_llm_command)
        # Skip the 'gemini' command itself and placeholder arguments
        i = 0
        while i < len(llm_command_parts):
            part = llm_command_parts[i]
            if part == '-y' or part == '--yolo':
                self.parsed_llm_args.append(part)
            elif part == '--include-directories' or part == '-I':
                self.parsed_llm_args.append(part)
                if i + 1 < len(llm_command_parts) and not llm_command_parts[i+1].startswith('-'):
                    self.parsed_llm_args.append(llm_command_parts[i+1])
                    i += 1 # Consume the value
            elif part == '--output-format' or part == '-o':
                # This is typically only for _invoke_llm, but keep it in mind
                pass # We don't want output-format for session creation
            i += 1

        if self.working_dir:
            gemini_dir = os.path.join(self.working_dir, '.gemini')
            settings_path = os.path.join(gemini_dir, 'settings.json')
            os.makedirs(gemini_dir, exist_ok=True)
            if not os.path.exists(settings_path):
                with open(settings_path, 'w') as f:
                    f.write('{}')
                print(f"[{self.name}] Created {settings_path}")

    def _create_llm_session(self, job_id):
        """
        新しいGemini CLIセッションを作成し、そのセッションインデックスを返す。
        """
        session_index = 0
        try:
            # 既存のセッション数を数える
            result = subprocess.run(
                "gemini --list-sessions",
                shell=True, capture_output=True, text=True, check=False,
                cwd=self.working_dir
            )
            stdout = result.stdout.strip()
            # "No sessions found." が返ってくる場合も考慮
            if stdout and "No sessions found" not in stdout:
                session_index = len(stdout.split('\n')) + 1 # 1-based index
            else:
                session_index = 1 # 最初のセッションはインデックス1から始まる
        except FileNotFoundError:
            print(f"[{self.name}][{job_id}] Error: 'gemini' command not found.")
            return None
        except Exception as e:
            print(f"[{self.name}][{job_id}] Error counting sessions: {e}. Assuming 1 as starting index.")
            session_index = 1

        # 新しいセッションを開始するために、role_promptを使って簡単なコマンドを実行する
        try:
            # --resume を付けずにコマンドを実行し、新しいセッションを作成させる
            # parsed_llm_args を init_command に含める
            init_command = f"gemini {' '.join(self.parsed_llm_args)} {shlex.quote(self.role_prompt)}"
            subprocess.run(
                init_command, shell=True, check=True,
                capture_output=True, text=True, timeout=80,
                cwd=self.working_dir
            )
        except subprocess.CalledProcessError as e:
             # A one-shot command might return non-zero if it doesn't produce a "final answer"
             # in the expected format, but it still creates the session. So we log and continue.
            print(f"[{self.name}][{job_id}] Info: Initial gemini command finished with code {e.returncode}. This might be expected for a one-shot prompt that is just a role description. Stderr: {e.stderr}")
        except subprocess.TimeoutExpired:
            print(f"[{self.name}][{job_id}] Warning: Initial gemini command timed out. A session may not have been created.")
            return None
        except FileNotFoundError:
            print(f"[{self.name}][{job_id}] Error: 'gemini' command not found.")
            return None

        print(f"[{self.name}][{job_id}] New session will use index: {session_index}")
        return str(session_index)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: python -m ai_masa.agents.gemini_cli_agent <AgentName> [user_lang]")
        sys.exit(1)

    agent = GeminiCliAgent(
        name=sys.argv[1],
        user_lang=sys.argv[2] if len(sys.argv) > 2 else 'Japanese'
    )
    agent.observe_loop()
