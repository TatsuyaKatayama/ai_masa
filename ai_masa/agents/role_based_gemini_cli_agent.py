from typing import Optional
from .role_based_agent import RoleBasedAgent
from .gemini_cli_agent import GeminiCliAgent
import sys
import argparse
import logging

class RoleBasedGeminiCliAgent(GeminiCliAgent, RoleBasedAgent):
    """
    An agent that combines the role-based behavior of RoleBasedAgent
    with the Gemini CLI functionalities of GeminiCliAgent.
    The order of inheritance is important: GeminiCliAgent's methods (like _create_llm_session)
    should take precedence over BaseAgent's, and RoleBasedAgent's __init__ logic is layered on top.
    """
    def __init__(self, name: str = "RoleBasedGeminiCliAgent", description: Optional[str] = None,
                 user_lang: str = 'Japanese', memory_id: str = "rb_gemini_memory",
                 redis_host: str = 'localhost', redis_port: int = 6379, redis_db: int = 0,
                 role_prompt: Optional[str] = None, llm_command: Optional[str] = None, **kwargs):

        # RoleBasedAgent's logic: use role_prompt as description if description is not provided
        final_description = description if description is not None else (role_prompt if role_prompt else "A role-based Gemini CLI agent.")

        # GeminiCliAgent's logic for default llm_command
        final_llm_command = llm_command
        if final_llm_command is None:
            final_llm_command = "gemini --resume {session_id} --output-format json"
        
        # MRO: RoleBasedGeminiCliAgent -> GeminiCliAgent -> RoleBasedAgent -> BaseAgent
        # We call super() which will eventually call BaseAgent.__init__ with all necessary arguments.
        super().__init__(
            name=name,
            description=final_description,
            user_lang=user_lang,
            memory_id=memory_id,
            redis_host=redis_host,
            redis_port=redis_port,
            redis_db=redis_db,
            role_prompt=role_prompt, # RoleBasedAgentの__init__に渡される
            llm_command=final_llm_command, # GeminiCliAgentの__init__に渡される
            **kwargs
        )

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Launch a RoleBasedGeminiCliAgent.")
    parser.add_argument("name", type=str, help="The name of the agent.")
    parser.add_argument("description", type=str, nargs='?', default=None, help="The description of the agent. If not provided, role_prompt will be used.")
    parser.add_argument("--user_lang", type=str, default="Japanese", help="The user language for the agent.")
    parser.add_argument("--memory_id", type=str, required=True, help="Memory ID for the agent's history.")
    parser.add_argument("--redis_host", type=str, default="localhost", help="Redis host.")
    parser.add_argument("--redis_port", type=int, default=6379, help="Redis port.")
    parser.add_argument("--redis_db", type=int, default=0, help="Redis DB.")
    parser.add_argument("--role_prompt", type=str, help="The role prompt for the agent. Used as description if --description is not set.")
    parser.add_argument('--llm_command', type=str, default=None, help='The command to execute for the LLM.')
    parser.add_argument('--working_dir', type=str, default=None, help='Working directory for LLM commands.')
    parser.add_argument("--logging_level", type=str, default="INFO", help="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)")
    
    args = parser.parse_args()

    # Configure logging
    log_level = getattr(logging, args.logging_level.upper(), logging.INFO)
    logging.basicConfig(level=log_level, stream=sys.stdout, format='[%(name)s][%(levelname)s] %(message)s')

    agent = RoleBasedGeminiCliAgent(
        name=args.name,
        description=args.description,
        user_lang=args.user_lang,
        memory_id=args.memory_id,
        redis_host=args.redis_host,
        redis_port=args.redis_port,
        redis_db=args.redis_db,
        role_prompt=args.role_prompt,
        llm_command=args.llm_command,
        working_dir=args.working_dir
    )
    try:
        agent.observe_loop()
    except KeyboardInterrupt:
        print(f"[{agent.name}] Shutting down.")
    finally:
        agent.shutdown()
