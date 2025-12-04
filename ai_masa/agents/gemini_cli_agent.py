import sys
from .base_agent import BaseAgent

class GeminiCliAgent(BaseAgent):
    """
    外部のGemini CLIコマンドをLLMとして利用するエージェント。
    """
    def __init__(self, name="GeminiCliAgent", redis_host='localhost', user_lang='Japanese'):
        llm_command = "gemini --output-format json"
        llm_session_create_command = "echo 'gemini-cli-session-active'"

        super().__init__(
            name=name,
            description="You are an intelligent AI assistant equipped with the Gemini CLI. Your task is to understand user messages and generate concise and accurate responses using the Gemini CLI tool.",
            user_lang=user_lang,
            redis_host=redis_host,
            llm_command=llm_command,
            llm_session_create_command=llm_session_create_command
        )

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: python -m ai_masa.agents.gemini_cli_agent <AgentName> [user_lang]")
        sys.exit(1)

    agent = GeminiCliAgent(
        name=sys.argv[1],
        user_lang=sys.argv[2] if len(sys.argv) > 2 else 'Japanese'
    )
    agent.observe_loop()
