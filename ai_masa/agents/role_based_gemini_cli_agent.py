from .role_based_agent import RoleBasedAgent
from .gemini_cli_agent import GeminiCliAgent
import sys
import argparse

class RoleBasedGeminiCliAgent(RoleBasedAgent, GeminiCliAgent):
    """
    An agent that combines the role-based behavior of RoleBasedAgent
    with the Gemini CLI functionalities of GeminiCliAgent.
    """
    def __init__(self, name="RoleBasedGeminiCliAgent", redis_host='localhost', user_lang='Japanese', role_prompt=None, llm_command=None, **kwargs):
        if role_prompt and not llm_command:
            # Construct llm_command to include the role_prompt if it's provided and llm_command is not
            # This ensures that GeminiCliAgent's _create_llm_session can use it for initial command
            llm_command = f"gemini --resume {{session_id}} --output-format json"

        super().__init__(
            name=name,
            redis_host=redis_host,
            user_lang=user_lang,
            role_prompt=role_prompt,
            llm_command=llm_command, # Pass the constructed or existing llm_command
            **kwargs
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Launch a RoleBasedGeminiCliAgent.")
    parser.add_argument("name", type=str, help="The name of the agent.")
    parser.add_argument("user_lang", type=str, nargs='?', default='Japanese', help="The user language for the agent.")
    parser.add_argument("--role_prompt", type=str, help="The role prompt for the agent.")
    parser.add_argument('--llm_command', type=str, default=None, help='The command to execute for the LLM.')

    args = parser.parse_args()

    agent = RoleBasedGeminiCliAgent(
        name=args.name,
        user_lang=args.user_lang,
        role_prompt=args.role_prompt,
        llm_command=args.llm_command
    )
    try:
        agent.observe_loop()
    except KeyboardInterrupt:
        print(f"[{agent.name}] Shutting down.")
        agent.shutdown_event.set()