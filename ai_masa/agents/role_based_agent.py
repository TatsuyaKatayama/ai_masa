from typing import Optional, List, Dict, Any
from .base_agent import BaseAgent

class RoleBasedAgent(BaseAgent):
    """
    A general-purpose agent whose behavior is primarily defined by the 
    'role_prompt' provided in the configuration.
    
    This class serves as a base for more specific role-based agents.
    """
    def __init__(self, name: str = "RoleBasedAgent", description: Optional[str] = None,
                 user_lang: str = 'Japanese', memory_id: str = "role_based_memory",
                 redis_host: str = 'localhost', redis_port: int = 6379, redis_db: int = 0,
                 role_prompt: Optional[str] = None, **kwargs):
        
        final_description = description if description is not None else (role_prompt if role_prompt else "A role-based agent.")

        super().__init__(
            name=name,
            description=final_description,
            user_lang=user_lang,
            memory_id=memory_id,
            redis_host=redis_host,
            redis_port=redis_port,
            redis_db=redis_db,
            **kwargs
        )
        self.role_prompt_content = role_prompt # Save role_prompt explicitly if needed later
