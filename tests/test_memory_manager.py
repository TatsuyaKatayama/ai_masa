import unittest
import redis
import uuid
import json
import time
import subprocess
import os

from ai_masa.comms.memory_manager import MemoryManager

# Configuration for test Redis instance
TEST_REDIS_HOST = 'localhost'
TEST_REDIS_PORT = 6379
TEST_REDIS_DB = 1 # Use a dedicated DB for testing

class TestMemoryManager(unittest.TestCase):
    """Tests for the SessionManager class using a real Redis instance."""

    @classmethod
    def setUpClass(cls):
        """Starts the Redis container before any tests are run."""
        print("\n[Memory Manager Test] Starting Redis container...")
        compose_file_path = os.path.join(os.path.dirname(__file__), '..', 'docker-compose.yml')
        if not os.path.exists(compose_file_path):
            raise FileNotFoundError(f"docker-compose.yml not found at {compose_file_path}")
        
        try:
            subprocess.run(["docker", "compose", "-f", compose_file_path, "up", "-d"], check=True, capture_output=True)
            cls.wait_for_redis()
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print("Error starting Redis container. Is Docker running?", file=sys.stderr)
            if hasattr(e, 'stderr'):
                print(f"Stderr: {e.stderr.decode()}", file=sys.stderr)
            raise

    @classmethod
    def tearDownClass(cls):
        """Stops the Redis container after all tests are done."""
        print("\n[Memory Manager Test] Stopping Redis container...")
        compose_file_path = os.path.join(os.path.dirname(__file__), '..', 'docker-compose.yml')
        subprocess.run(["docker", "compose", "-f", compose_file_path, "down"], capture_output=True)
        if hasattr(cls, 'sm') and cls.sm.redis_client:
            cls.sm.redis_client.close()

    @classmethod
    def wait_for_redis(cls, retries=10, delay=2):
        """Waits for the Redis container to become available."""
        for i in range(retries):
            try:
                r = redis.Redis(host=TEST_REDIS_HOST, port=TEST_REDIS_PORT, db=TEST_REDIS_DB)
                if r.ping():
                    print("[Memory Manager Test] Redis is ready.")
                    cls.sm = MemoryManager(host=TEST_REDIS_HOST, port=TEST_REDIS_PORT, db=TEST_REDIS_DB)
                    return
            except redis.exceptions.ConnectionError:
                time.sleep(delay)
        raise ConnectionError("Could not connect to Redis container after multiple retries.")

    def setUp(self):
        """Initialize list to track session IDs for cleanup."""
        self.sm.redis_client.flushdb()
        self._memories_to_clean = []

    def tearDown(self):
        """Clean up any memories created by the test."""
        # This is redundant if setUp flushes, but good practice for clarity
        for memory_id in self._memories_to_clean:
            self.sm.delete_memory(memory_id)

    def _generate_and_track_memory_id(self):
        """Helper to generate a memory ID and add it to the cleanup list."""
        memory_id = f"memory:{uuid.uuid4()}"
        self._memories_to_clean.append(memory_id)
        return memory_id

    def test_create_memory(self):
        """Test memory creation and initial data."""
        memory_id = self.sm.create_memory()
        self._memories_to_clean.append(memory_id) # Track for cleanup

        self.assertIsNotNone(memory_id)
        self.assertTrue(memory_id.startswith("memory:"))

        retrieved_data = self.sm.get_memory(memory_id)
        self.assertIsNotNone(retrieved_data)
        self.assertEqual(retrieved_data["memory_id"], memory_id)
        self.assertEqual(retrieved_data["history"], [])
        self.assertEqual(retrieved_data["agent_states"], {})

    def test_get_memory(self):
        """Test retrieving an existing memory."""
        memory_id = self.sm.create_memory()
        self._memories_to_clean.append(memory_id)

        retrieved_data = self.sm.get_memory(memory_id)
        self.assertIsNotNone(retrieved_data)
        self.assertEqual(retrieved_data["memory_id"], memory_id)

    def test_get_memory_not_found(self):
        """Test retrieving a non-existent memory."""
        memory_id = self._generate_and_track_memory_id() # Generate but don't create in Redis
        retrieved_data = self.sm.get_memory(memory_id)
        self.assertIsNone(retrieved_data)

    def test_add_message_to_existing_memory(self):
        """Test adding a message to an existing memory."""
        memory_id = self.sm.create_memory()
        self._memories_to_clean.append(memory_id)

        message1 = {"from_agent": "user", "to_agent": "assistant", "content": "Hello"}
        self.sm.add_message(memory_id, message1)

        history = self.sm.get_history(memory_id, "user")
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0], message1)

        message2 = {"from_agent": "assistant", "to_agent": "user", "content": "Hi there!"}
        self.sm.add_message(memory_id, message2)
        history = self.sm.get_history(memory_id, "user")
        self.assertEqual(len(history), 2)
        self.assertEqual(history[1], message2)

    def test_add_message_creates_memory_if_not_exists(self):
        """Test that add_message creates a memory if it doesn't exist."""
        memory_id = self._generate_and_track_memory_id() # Generate but don't create initially
        message = {"from_agent": "user", "to_agent": "system", "content": "First message"}
        self.sm.add_message(memory_id, message)

        retrieved_data = self.sm.get_memory(memory_id)
        self.assertIsNotNone(retrieved_data)
        self.assertEqual(retrieved_data["memory_id"], memory_id)
        
        history = self.sm.get_history(memory_id, "user")
        self.assertEqual(history, [message])
        self.assertEqual(retrieved_data["agent_states"], {})

    def test_get_history_with_filtering(self):
        """Test retrieving message history with agent-specific filtering."""
        memory_id = self.sm.create_memory()
        self._memories_to_clean.append(memory_id)

        # Define agents and messages
        agent_a, agent_b, agent_c = "agent_a", "agent_b", "agent_c"
        
        msg1 = {"from_agent": agent_a, "to_agent": agent_b, "content": "Hi B"}
        msg2 = {"from_agent": agent_b, "to_agent": agent_a, "content": "Hi A"}
        msg3 = {"from_agent": agent_c, "to_agent": agent_a, "cc_agents": [agent_b], "content": "Hi A and B"}
        msg4 = {"from_agent": agent_a, "to_agent": agent_c, "content": "Hi C"}
        
        # Add messages to history
        self.sm.add_message(memory_id, msg1)
        self.sm.add_message(memory_id, msg2)
        self.sm.add_message(memory_id, msg3)
        self.sm.add_message(memory_id, msg4)

        # Test history for agent_a (should see all messages)
        history_a = self.sm.get_history(memory_id, agent_a)
        self.assertEqual(len(history_a), 4)

        # Test history for agent_b (should see msg1, msg2, msg3)
        history_b = self.sm.get_history(memory_id, agent_b)
        self.assertEqual(len(history_b), 3)

        # Test history for agent_c (should see msg3, msg4)
        history_c = self.sm.get_history(memory_id, agent_c)
        self.assertEqual(len(history_c), 2)
        
        # Test for an agent not involved in any message
        history_d = self.sm.get_history(memory_id, "agent_d")
        self.assertEqual(history_d, [])

    def test_get_history_empty_memory(self):
        """Test retrieving history from a memory with no messages."""
        memory_id = self.sm.create_memory()
        self._memories_to_clean.append(memory_id)

        history = self.sm.get_history(memory_id, "any_agent")
        self.assertEqual(history, [])

    def test_get_history_no_memory(self):
        """Test retrieving history from a non-existent memory."""
        memory_id = self._generate_and_track_memory_id() # Generate but don't create
        history = self.sm.get_history(memory_id, "any_agent")
        self.assertIsNone(history)

    def test_delete_memory(self):
        """Test deleting a memory."""
        memory_id = self.sm.create_memory()
        self.assertIsNotNone(self.sm.get_memory(memory_id))
        self.sm.delete_memory(memory_id)
        self.assertIsNone(self.sm.get_memory(memory_id))

    def test_update_agent_state(self):
        """Test updating an agent's state within a memory."""
        memory_id = self.sm.create_memory()
        self._memories_to_clean.append(memory_id)

        agent_name = "test_agent"
        state1 = {"status": "running", "step": 1}
        self.sm.update_agent_state(memory_id, agent_name, state1)
        retrieved_state = self.sm.get_agent_state(memory_id, agent_name)
        self.assertEqual(retrieved_state, state1)

    def test_get_agent_state(self):
        """Test retrieving an agent's state."""
        memory_id = self.sm.create_memory()
        self._memories_to_clean.append(memory_id)

        agent_name = "another_agent"
        state = {"task": "processing", "progress": "50%"}
        self.sm.update_agent_state(memory_id, agent_name, state)
        retrieved_state = self.sm.get_agent_state(memory_id, agent_name)
        self.assertEqual(retrieved_state, state)

    def test_get_agent_state_not_found(self):
        """Test retrieving state for a non-existent agent or memory."""
        memory_id = self.sm.create_memory()
        self._memories_to_clean.append(memory_id)
        retrieved_state = self.sm.get_agent_state(memory_id, "non_existent_agent")
        self.assertIsNone(retrieved_state)

    def test_export_and_import_memory(self):
        """Test exporting a memory and importing it as a new one."""
        original_memory_id = self.sm.create_memory()
        self._memories_to_clean.append(original_memory_id)
        msg1 = {"from_agent": "agent1", "to_agent": "agent2", "content": "Hello"}
        self.sm.add_message(original_memory_id, msg1)
        state1 = {"status": "running"}
        self.sm.update_agent_state(original_memory_id, "agent1", state1)

        exported_json = self.sm.export_memory(original_memory_id)
        self.assertIsNotNone(exported_json)

        new_memory_id = self.sm.import_memory(exported_json)
        self._memories_to_clean.append(new_memory_id)
        self.assertNotEqual(new_memory_id, original_memory_id)

        imported_data = self.sm.get_memory(new_memory_id)
        self.assertEqual(imported_data['history'][0], msg1)
        self.assertEqual(imported_data['agent_states']['agent1'], state1)

    def test_export_non_existent_memory(self):
        """Test that exporting a non-existent memory returns None."""
        non_existent_id = self._generate_and_track_memory_id()
        self.assertIsNone(self.sm.export_memory(non_existent_id))

    def test_list_memories_with_digest(self):
        """Test listing all memories with a digest of their first message."""
        m1_id = self.sm.create_memory()
        self._memories_to_clean.append(m1_id)
        msg1_m1 = {"from_agent": "a1", "to_agent": "b1", "content": "First", "timestamp": "T1"}
        self.sm.add_message(m1_id, msg1_m1)

        m2_id = self.sm.create_memory()
        self._memories_to_clean.append(m2_id)

        summaries = self.sm.list_memories_with_digest()
        self.assertEqual(len(summaries), 2)
        
        summaries_dict = {s["memory_id"]: s for s in summaries}
        
        self.assertEqual(summaries_dict[m1_id]["from_agent"], "a1")
        self.assertEqual(summaries_dict[m2_id]["content_preview"], "No messages yet.")

if __name__ == '__main__':
    unittest.main()