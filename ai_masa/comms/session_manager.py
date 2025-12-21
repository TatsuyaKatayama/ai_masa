import redis
import uuid
from typing import List, Dict, Any, Optional

class SessionManager:
    """
    Manages agent sessions using RedisJSON.
    """
    def __init__(self, host='localhost', port=6379, db=0):
        """
        Initializes the SessionManager with a Redis connection.
        """
        self.redis_client = redis.Redis(host=host, port=port, db=db, decode_responses=True)

    def _generate_session_id(self) -> str:
        """Generates a unique session ID."""
        return f"session:{uuid.uuid4()}"

    def create_session(self) -> str:
        """
        Creates a new session in Redis and returns the session ID.
        """
        session_id = self._generate_session_id()
        initial_data = {
            "session_id": session_id,
            "history": [],
            "agent_states": {}
        }
        self.redis_client.json().set(session_id, '$', initial_data)
        return session_id

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves a session from Redis.

        Args:
            session_id: The ID of the session to retrieve.

        Returns:
            The session data as a dictionary, or None if not found.
        """
        return self.redis_client.json().get(session_id, '$')

    def add_message(self, session_id: str, message: Dict[str, str]):
        """
        Adds a message to the session's history.

        Args:
            session_id: The ID of the session.
            message: A dictionary with 'role' and 'content' keys.
        """
        self.redis_client.json().arrappend(session_id, '$.history', message)

    def get_history(self, session_id: str) -> Optional[List[Dict[str, str]]]:
        """
        Retrieves the message history for a session.

        Args:
            session_id: The ID of the session.

        Returns:
            A list of messages, or None if the session does not exist.
        """
        history = self.redis_client.json().get(session_id, '$.history')
        # The result from redis-py for a single path is a list containing the actual value
        return history[0] if history else None

    def delete_session(self, session_id: str):
        """
        Deletes a session from Redis.
        """
        self.redis_client.delete(session_id)

    def update_agent_state(self, session_id: str, agent_name: str, state: Dict[str, Any]):
        """
        Updates the state of a specific agent within a session.
        """
        path = f'$.agent_states.{agent_name}'
        self.redis_client.json().set(session_id, path, state)

    def get_agent_state(self, session_id: str, agent_name: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves the state of a specific agent within a session.
        """
        path = f'$.agent_states.{agent_name}'
        state = self.redis_client.json().get(session_id, path)
        return state[0] if state else None
