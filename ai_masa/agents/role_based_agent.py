from .base_agent import BaseAgent

class RoleBasedAgent(BaseAgent):
    """
    A general-purpose agent whose behavior is primarily defined by the 
    'role_prompt' provided in the configuration.
    
    This class serves as a base for more specific role-based agents.
    """
    def __init__(self, name="RoleBasedAgent", redis_host='localhost', user_lang='Japanese', role_prompt=None, **kwargs):
        super().__init__(
            name=name,
            redis_host=redis_host,
            user_lang=user_lang,
            description=role_prompt, # role_prompt is used as description for BaseAgent
            **kwargs
        )
