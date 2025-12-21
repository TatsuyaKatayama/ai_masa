import unittest
import redis
import uuid
import json
import time # For potential small delays if needed for Redis operations

from ai_masa.comms.session_manager import SessionManager

# Configuration for test Redis instance
TEST_REDIS_HOST = 'localhost'
TEST_REDIS_PORT = 6379
TEST_REDIS_DB = 1 # Use a dedicated DB for testing

class TestSessionManager(unittest.TestCase):
    """Tests for the SessionManager class using a real Redis instance."""

    @classmethod
    def setUpClass(cls):
        """Set up a single SessionManager instance for all tests in this class."""
        cls.sm = SessionManager(host=TEST_REDIS_HOST, port=TEST_REDIS_PORT, db=TEST_REDIS_DB)
        # Ensure Redis is clean before any tests run
        cls.sm.redis_client.flushdb()

    @classmethod
    def tearDownClass(cls):
        """Clean up Redis after all tests in this class have run."""
        cls.sm.redis_client.flushdb()
        cls.sm.redis_client.close()

    def setUp(self):
        """Initialize list to track session IDs for cleanup."""
        self.sm.redis_client.flushdb()
        self._sessions_to_clean = []

    def tearDown(self):
        """Clean up any sessions created by the test."""
        # This is redundant if setUp flushes, but good practice for clarity
        for session_id in self._sessions_to_clean:
            self.sm.delete_session(session_id)

    def _generate_and_track_session_id(self):
        """Helper to generate a session ID and add it to the cleanup list."""
        session_id = f"session:{uuid.uuid4()}"
        self._sessions_to_clean.append(session_id)
        return session_id

    def test_create_session(self):
        """Test session creation and initial data."""
        session_id = self.sm.create_session()
        self._sessions_to_clean.append(session_id) # Track for cleanup

        self.assertIsNotNone(session_id)
        self.assertTrue(session_id.startswith("session:"))

        retrieved_data = self.sm.get_session(session_id)
        self.assertIsNotNone(retrieved_data)
        self.assertEqual(retrieved_data["session_id"], session_id)
        self.assertEqual(retrieved_data["history"], [])
        self.assertEqual(retrieved_data["agent_states"], {})

    def test_get_session(self):
        """Test retrieving an existing session."""
        session_id = self.sm.create_session()
        self._sessions_to_clean.append(session_id)

        retrieved_data = self.sm.get_session(session_id)
        self.assertIsNotNone(retrieved_data)
        self.assertEqual(retrieved_data["session_id"], session_id)

    def test_get_session_not_found(self):
        """Test retrieving a non-existent session."""
        session_id = self._generate_and_track_session_id() # Generate but don't create in Redis
        retrieved_data = self.sm.get_session(session_id)
        self.assertIsNone(retrieved_data)

    def test_add_message_to_existing_session(self):
        """Test adding a message to an existing session."""
        session_id = self.sm.create_session()
        self._sessions_to_clean.append(session_id)

        message1 = {"from_agent": "user", "to_agent": "assistant", "content": "Hello"}
        self.sm.add_message(session_id, message1)

        history = self.sm.get_history(session_id, "user")
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0], message1)

        message2 = {"from_agent": "assistant", "to_agent": "user", "content": "Hi there!"}
        self.sm.add_message(session_id, message2)
        history = self.sm.get_history(session_id, "user")
        self.assertEqual(len(history), 2)
        self.assertEqual(history[1], message2)

    def test_add_message_creates_session_if_not_exists(self):
        """Test that add_message creates a session if it doesn't exist."""
        session_id = self._generate_and_track_session_id() # Generate but don't create initially
        message = {"from_agent": "user", "to_agent": "system", "content": "First message"}
        self.sm.add_message(session_id, message)

        retrieved_data = self.sm.get_session(session_id)
        self.assertIsNotNone(retrieved_data)
        self.assertEqual(retrieved_data["session_id"], session_id)
        
        history = self.sm.get_history(session_id, "user")
        self.assertEqual(history, [message])
        self.assertEqual(retrieved_data["agent_states"], {})

    def test_get_history_with_filtering(self):
        """Test retrieving message history with agent-specific filtering."""
        session_id = self.sm.create_session()
        self._sessions_to_clean.append(session_id)

        # Define agents and messages
        agent_a, agent_b, agent_c = "agent_a", "agent_b", "agent_c"
        
        msg1 = {"from_agent": agent_a, "to_agent": agent_b, "content": "Hi B"}
        msg2 = {"from_agent": agent_b, "to_agent": agent_a, "content": "Hi A"}
        msg3 = {"from_agent": agent_c, "to_agent": agent_a, "cc_agents": [agent_b], "content": "Hi A and B"}
        msg4 = {"from_agent": agent_a, "to_agent": agent_c, "content": "Hi C"}
        
        # Add messages to history
        self.sm.add_message(session_id, msg1)
        self.sm.add_message(session_id, msg2)
        self.sm.add_message(session_id, msg3)
        self.sm.add_message(session_id, msg4)

        # Test history for agent_a (should see all messages)
        history_a = self.sm.get_history(session_id, agent_a)
        self.assertEqual(len(history_a), 4)

        # Test history for agent_b (should see msg1, msg2, msg3)
        history_b = self.sm.get_history(session_id, agent_b)
        self.assertEqual(len(history_b), 3)

        # Test history for agent_c (should see msg3, msg4)
        history_c = self.sm.get_history(session_id, agent_c)
        self.assertEqual(len(history_c), 2)
        
        # Test for an agent not involved in any message
        history_d = self.sm.get_history(session_id, "agent_d")
        self.assertEqual(history_d, [])

    def test_get_history_empty(self):
        """Test retrieving history from a session with no messages."""
        session_id = self.sm.create_session()
        self._sessions_to_clean.append(session_id)

        history = self.sm.get_history(session_id, "any_agent")
        self.assertEqual(history, [])

    def test_get_history_no_session(self):
        """Test retrieving history from a non-existent session."""
        session_id = self._generate_and_track_session_id() # Generate but don't create
        history = self.sm.get_history(session_id, "any_agent")
        self.assertIsNone(history)

    def test_delete_session(self):
        """Test deleting a session."""
        session_id = self.sm.create_session()
        self.assertIsNotNone(self.sm.get_session(session_id))
        self.sm.delete_session(session_id)
        self.assertIsNone(self.sm.get_session(session_id))

    def test_update_agent_state(self):
        """Test updating an agent's state within a session."""
        session_id = self.sm.create_session()
        self._sessions_to_clean.append(session_id)

        agent_name = "test_agent"
        state1 = {"status": "running", "step": 1}
        self.sm.update_agent_state(session_id, agent_name, state1)
        retrieved_state = self.sm.get_agent_state(session_id, agent_name)
        self.assertEqual(retrieved_state, state1)

    def test_get_agent_state(self):
        """Test retrieving an agent's state."""
        session_id = self.sm.create_session()
        self._sessions_to_clean.append(session_id)

        agent_name = "another_agent"
        state = {"task": "processing", "progress": "50%"}
        self.sm.update_agent_state(session_id, agent_name, state)
        retrieved_state = self.sm.get_agent_state(session_id, agent_name)
        self.assertEqual(retrieved_state, state)

    def test_get_agent_state_not_found(self):
        """Test retrieving state for a non-existent agent or session."""
        session_id = self.sm.create_session()
        self._sessions_to_clean.append(session_id)
        retrieved_state = self.sm.get_agent_state(session_id, "non_existent_agent")
        self.assertIsNone(retrieved_state)

    def test_export_and_import_session(self):
        """Test exporting a session and importing it as a new one."""
        original_session_id = self.sm.create_session()
        self._sessions_to_clean.append(original_session_id)
        msg1 = {"from_agent": "agent1", "to_agent": "agent2", "content": "Hello"}
        self.sm.add_message(original_session_id, msg1)
        state1 = {"status": "running"}
        self.sm.update_agent_state(original_session_id, "agent1", state1)

        exported_json = self.sm.export_session(original_session_id)
        self.assertIsNotNone(exported_json)

        new_session_id = self.sm.import_session(exported_json)
        self._sessions_to_clean.append(new_session_id)
        self.assertNotEqual(new_session_id, original_session_id)

        imported_data = self.sm.get_session(new_session_id)
        self.assertEqual(imported_data['history'][0], msg1)
        self.assertEqual(imported_data['agent_states']['agent1'], state1)

    def test_export_non_existent_session(self):
        """Test that exporting a non-existent session returns None."""
        non_existent_id = self._generate_and_track_session_id()
        self.assertIsNone(self.sm.export_session(non_existent_id))

    def test_list_sessions_with_digest(self):
        """Test listing all sessions with a digest of their first message."""
        s1_id = self.sm.create_session()
        self._sessions_to_clean.append(s1_id)
        msg1_s1 = {"from_agent": "a1", "to_agent": "b1", "content": "First", "timestamp": "T1"}
        self.sm.add_message(s1_id, msg1_s1)

        s2_id = self.sm.create_session()
        self._sessions_to_clean.append(s2_id)

        summaries = self.sm.list_sessions_with_digest()
        self.assertEqual(len(summaries), 2)
        
        summaries_dict = {s["session_id"]: s for s in summaries}
        
        self.assertEqual(summaries_dict[s1_id]["from_agent"], "a1")
        self.assertEqual(summaries_dict[s2_id]["content_preview"], "No messages yet.")

if __name__ == '__main__':
    unittest.main()