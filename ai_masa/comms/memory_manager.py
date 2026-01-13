import redis
import uuid
from typing import List, Dict, Any, Optional

class MemoryManager:
    """
    Manages agent sessions using RedisJSON.
    """
    def __init__(self, host='localhost', port=6379, db=0):
        """
        Initializes the MemoryManager with a Redis connection.
        """
        self.redis_client = redis.Redis(host=host, port=port, db=db, decode_responses=True)

    def _generate_memory_id(self) -> str:
        """Generates a unique memory ID."""
        return f"memory:{uuid.uuid4()}"

    def create_memory(self) -> str:
        """
        Creates a new memory in Redis and returns the memory ID.
        """
        memory_id = self._generate_memory_id()
        initial_data = {
            "memory_id": memory_id,
            "history": [],
            "agent_states": {}
        }
        self.redis_client.json().set(memory_id, '$', initial_data)
        return memory_id

    def get_memory(self, memory_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves a memory from Redis.

        Args:
            memory_id: The ID of the memory to retrieve.

        Returns:
            The memory data as a dictionary, or None if not found.
        """
        memory = self.redis_client.json().get(memory_id, '$')
        return memory[0] if memory else None

    def add_message(self, memory_id: str, message: Dict[str, str]):
        """
        Adds a message to the memory's history.
        If the memory does not exist, it creates one before appending.
        """
        # Ensure the memory key exists before appending.
        if not self.redis_client.exists(memory_id):
            initial_data = {
                "memory_id": memory_id,
                "history": [],
                "agent_states": {}
            }
            self.redis_client.json().set(memory_id, '$', initial_data)
        
        self.redis_client.json().arrappend(memory_id, '$.history', message)

    def get_history(self, memory_id: str, agent_name: str) -> Optional[List[Dict[str, Any]]]:
        """
        Retrieves the message history for a memory, filtered for a specific agent.
        An agent sees a message if it is the sender, recipient, or in the CC list.

        Args:
            memory_id: The ID of the memory.
            agent_name: The name of the agent requesting the history.

        Returns:
            A filtered list of messages, or None if the memory does not exist.
        """
        full_history_list = self.redis_client.json().get(memory_id, '$.history')

        if full_history_list is None:
            return None  # Memory does not exist

        full_history = full_history_list[0]
        if not full_history:
            return []  # Memory exists but history is empty

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

    def delete_memory(self, memory_id: str):
        """
        Deletes a memory from Redis.
        """
        self.redis_client.delete(memory_id)

    def update_agent_state(self, memory_id: str, agent_name: str, state: Dict[str, Any]):
        """
        Updates the state of a specific agent within a memory.
        """
        path = f'$.agent_states.{agent_name}'
        self.redis_client.json().set(memory_id, path, state)

    def get_agent_state(self, memory_id: str, agent_name: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves the state of a specific agent within a memory.
        """
        path = f'$.agent_states.{agent_name}'
        state = self.redis_client.json().get(memory_id, path)
        return state[0] if state else None

    def export_memory(self, memory_id: str) -> Optional[str]:
        """
        Exports a full memory's data to a JSON string.

        Args:
            memory_id: The ID of the memory to export.

        Returns:
            A JSON string representing the memory, or None if not found.
        """
        memory_data = self.get_memory(memory_id)
        if not memory_data:
            return None
        import json
        return json.dumps(memory_data, indent=2)

    def import_memory(self, memory_data_json: str) -> str:
        """
        Imports a memory from a JSON string, creating a new memory.

        Args:
            memory_data_json: The JSON string of the memory data.

        Returns:
            The ID of the newly created memory.
        """
        import json
        data = json.loads(memory_data_json)
        
        # Create a new memory ID to avoid conflicts
        new_memory_id = self._generate_memory_id()
        data['memory_id'] = new_memory_id
        
        self.redis_client.json().set(new_memory_id, '$', data)
        return new_memory_id

    def list_memories_with_digest(self, content_preview_length: int = 50) -> list[dict[str, any]]:
        """
        Lists all active memories with a digest of their first message.

        Args:
            content_preview_length: The max length of the content preview.

        Returns:
            A list of dictionaries, each containing a memory's digest.
        """
        memory_ids = [key for key in self.redis_client.scan_iter("memory:*")]
        if not memory_ids:
            return []

        # Fetch the first message of all memories in one go for efficiency
        first_messages = self.redis_client.json().mget(memory_ids, '$.history[0]')
        
        summaries = []
        for memory_id, first_message_list in zip(memory_ids, first_messages):
            summary = {"memory_id": memory_id}
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
