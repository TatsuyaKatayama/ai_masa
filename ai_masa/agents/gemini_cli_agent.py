import sys
import subprocess
import shlex
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

        final_description = description if description is not None else \
            "You are an intelligent AI assistant equipped with the Gemini CLI. Your task is to understand user messages and generate concise and accurate responses using the Gemini CLI tool."

        super().__init__(
            name=name,
            description=final_description,
            user_lang=user_lang,
            redis_host=redis_host,
            llm_command=llm_command,
            llm_session_create_command=llm_session_create_command,
            **kwargs # 残りのkwargsをBaseAgentに渡す
        )

    def _create_llm_session(self, job_id):
        """
        新しいGemini CLIセッションを作成し、そのセッションインデックスを返す。
        """
        session_index = 0
        try:
            # 既存のセッション数を数える
            result = subprocess.run(
                "gemini --list-sessions",
                shell=True, capture_output=True, text=True, check=False
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
            # 新しいセッションインデックスを使って初期化
            init_command = f"gemini --resume {session_index} {shlex.quote(self.role_prompt)}"
            subprocess.run(
                init_command, shell=True, check=True,
                capture_output=True, text=True, timeout=80
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
