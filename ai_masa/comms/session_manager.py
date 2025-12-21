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
        session = self.redis_client.json().get(session_id, '$')
        return session[0] if session else None

    def add_message(self, session_id: str, message: Dict[str, str]):
        """
        Adds a message to the session's history.
        If the session does not exist, it creates one before appending.
        """
        # Ensure the session key exists before appending.
        if not self.redis_client.exists(session_id):
            initial_data = {
                "session_id": session_id,
                "history": [],
                "agent_states": {}
            }
            self.redis_client.json().set(session_id, '$', initial_data)
        
        self.redis_client.json().arrappend(session_id, '$.history', message)

    def get_history(self, session_id: str, agent_name: str) -> Optional[List[Dict[str, Any]]]:
        """
        Retrieves the message history for a session, filtered for a specific agent.
        An agent sees a message if it is the sender, recipient, or in the CC list.

        Args:
            session_id: The ID of the session.
            agent_name: The name of the agent requesting the history.

        Returns:
            A filtered list of messages, or None if the session does not exist.
        """
        full_history_list = self.redis_client.json().get(session_id, '$.history')

        if full_history_list is None:
            return None  # Session does not exist

        full_history = full_history_list[0]
        if not full_history:
            return []  # Session exists but history is empty

        filtered_history = []
        for message in full_history:
            is_sender = message.get("from_agent") == agent_name
            is_recipient = message.get("to_agent") == agent_name
            
            # The 'cc_agents' field can be None or not exist
            cc_list = message.get("cc_agents") or []
            is_cc = agent_name in cc_list

            if is_sender or is_recipient or is_cc:
                filtered_history.append(message)
        
        return filtered_history

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

    def export_session(self, session_id: str) -> Optional[str]:
        """
        Exports a full session's data to a JSON string.

        Args:
            session_id: The ID of the session to export.

        Returns:
            A JSON string representing the session, or None if not found.
        """
        session_data = self.get_session(session_id)
        if not session_data:
            return None
        import json
        return json.dumps(session_data, indent=2)

    def import_session(self, session_data_json: str) -> str:
        """
        Imports a session from a JSON string, creating a new session.

        Args:
            session_data_json: The JSON string of the session data.

        Returns:
            The ID of the newly created session.
        """
        import json
        data = json.loads(session_data_json)
        
        # Create a new session ID to avoid conflicts
        new_session_id = self._generate_session_id()
        data['session_id'] = new_session_id
        
        self.redis_client.json().set(new_session_id, '$', data)
        return new_session_id

    def list_sessions_with_digest(self, content_preview_length: int = 50) -> list[dict[str, any]]:
        """
        Lists all active sessions with a digest of their first message.

        Args:
            content_preview_length: The max length of the content preview.

        Returns:
            A list of dictionaries, each containing a session's digest.
        """
        session_ids = [key for key in self.redis_client.scan_iter("session:*")]
        if not session_ids:
            return []

        # Fetch the first message of all sessions in one go for efficiency
        first_messages = self.redis_client.json().mget(session_ids, '$.history[0]')
        
        summaries = []
        for session_id, first_message_list in zip(session_ids, first_messages):
            summary = {"session_id": session_id}
            if first_message_list:
                # The result is a list containing the actual message dict
                first_message = first_message_list[0]
                summary["timestamp"] = first_message.get("timestamp", "N/A")
                summary["from_agent"] = first_message.get("from_agent", "N/A")
                summary["to_agent"] = first_message.get("to_agent", "N/A")
                content = first_message.get("content", "")
                summary["content_preview"] = (content[:content_preview_length] + '...') if len(content) > content_preview_length else content
            else:
                summary["timestamp"] = None
                summary["from_agent"] = None
                summary["to_agent"] = None
                summary["content_preview"] = "No messages yet."
            summaries.append(summary)
            
        return summaries
