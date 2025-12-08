from .role_based_agent import RoleBasedAgent
from .gemini_cli_agent import GeminiCliAgent
import sys
import argparse

class RoleBasedGeminiCliAgent(RoleBasedAgent, GeminiCliAgent):
    """
    An agent that combines the role-based behavior of RoleBasedAgent
    with the Gemini CLI functionalities of GeminiCliAgent.
    """
    def __init__(self, name="RoleBasedGeminiCliAgent", redis_host='localhost', user_lang='Japanese', role_prompt=None, **kwargs):
        super().__init__(
            name=name,
            redis_host=redis_host,
            user_lang=user_lang,
            role_prompt=role_prompt, # Pass role_prompt up the MRO
            **kwargs
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Launch a RoleBasedGeminiCliAgent.")
    parser.add_argument("name", type=str, help="The name of the agent.")
    parser.add_argument("user_lang", type=str, nargs='?', default='Japanese', help="The user language for the agent.")
    parser.add_argument("--role_prompt", type=str, help="The role prompt for the agent.")

    args = parser.parse_args()

    agent = RoleBasedGeminiCliAgent(
        name=args.name,
        user_lang=args.user_lang,
        role_prompt=args.role_prompt
    )
    try:
        agent.observe_loop()
    except KeyboardInterrupt:
        print(f"[{agent.name}] Shutting down.")
        agent.shutdown_event.set()