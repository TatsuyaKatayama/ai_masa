import logging
import subprocess
import shlex
import os
from typing import Optional

from .opencode_agent import OpencodeAgent
from ..models.message import Message

logger = logging.getLogger(__name__)

class RoleBasedOpencodeAgent(OpencodeAgent):
    """
    A Role-Based Agent that uses the external Opencode CLI command as its LLM backend.
    It combines the role-based prompting capabilities with the Opencode CLI's multi-provider support.
    The user is responsible for configuring the Opencode CLI backend (e.g., OpenAI, Anthropic) beforehand.
    """
    def __init__(self, name: str, description: Optional[str] = None,
                 user_lang: str = 'Japanese', memory_id: str = "role_opencode_session",
                 redis_host: str = 'localhost', redis_port: int = 6379, redis_db: int = 0,
                 llm_command: Optional[str] = None,
                 llm_session_create_command: Optional[str] = None, # Not used, but required by BaseAgent
                 working_dir: Optional[str] = None,
                 role_prompt: str = "You are a helpful AI assistant.",
                 model: str = "google/gemini-2.5-flash", **kwargs):
        
        # OpencodeAgent.__init__ will set up llm_command and self.model
        super().__init__(
            name=name,
            description=description, 
            user_lang=user_lang,
            memory_id=memory_id,
            redis_host=redis_host,
            redis_port=redis_port,
            redis_db=redis_db,
            llm_command=llm_command,
            llm_session_create_command=llm_session_create_command, # Pass through, will be overwritten by _create_llm_session logic
            working_dir=working_dir,
            model=model, # Pass model to OpencodeAgent
            **kwargs
        )

        # Override role_prompt from OpencodeAgent's description-based prompt
        self.role_prompt = role_prompt
        self.description = description # Preserve original description

        logger.debug(f"[{self.name}] RoleBasedOpencodeAgent initialized with role_prompt: {self.role_prompt}")

    # No need to override _create_llm_session as OpencodeAgent's implementation is sufficient.
    # No need to override _invoke_llm as OpencodeAgent's overridden version is sufficient.
    # No need to override _process_llm_response as BaseAgent's implementation is sufficient.

if __name__ == "__main__":
    # This part will be implemented in a later step, similar to OpencodeAgent's main block.
    pass
