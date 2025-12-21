import unittest
import redis
import uuid
import json # To verify JSON directly from Redis

from ai_masa.comms.session_manager import SessionManager

class TestSessionManager(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Connect to Redis once for all tests in this class."""
        cls.redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        try:
            cls.redis_client.ping()
        except redis.exceptions.ConnectionError as e:
            raise unittest.SkipTest(f"Could not connect to Redis: {e}")

    def setUp(self):
        """Set up a fresh SessionManager instance for each test."""
        self.redis_client.flushdb() # Clean DB before each test
        self.session_manager = SessionManager(host='localhost', port=6379, db=0)
        self.session_manager.redis_client = self.redis_client # Ensure it uses the class client

    def tearDown(self):
        """Clean up DB after each test is handled by setUp. Close client is handled by tearDownClass"""
        pass # setUp takes care of flushdb

    @classmethod
    def tearDownClass(cls):
        """Close Redis connection after all tests in this class."""
        cls.redis_client.close()


    def test_init(self):
        """Test that SessionManager initializes the Redis client correctly."""
        # Already tested by setUpClass and setUp implicitly, but can add explicit check if needed.
        self.assertEqual(self.session_manager.redis_client.connection_pool.connection_kwargs['host'], 'localhost')
        self.assertEqual(self.session_manager.redis_client.connection_pool.connection_kwargs['port'], 6379)
        self.assertEqual(self.session_manager.redis_client.connection_pool.connection_kwargs['db'], 0)


    def test_create_session(self):
        """Test the creation of a new session."""
        session_id = self.session_manager.create_session()

        self.assertTrue(session_id.startswith("session:"))
        
        # raw_data is already a Python object (list in this case) because decode_responses=True
        raw_data = self.redis_client.execute_command('JSON.GET', session_id, '$')
        session_data = raw_data[0] # Get the actual dictionary from the list

        self.assertIsNotNone(session_data)
        self.assertEqual(session_data['session_id'], session_id)
        self.assertEqual(session_data['history'], [])
        self.assertEqual(session_data['agent_states'], {})

    def test_get_session_nonexistent(self):
        """Test retrieving a non-existent session."""
        session_id = "session:nonexistent"
        retrieved_session = self.session_manager.get_session(session_id)
        self.assertIsNone(retrieved_session)

    def test_add_and_get_history(self):
        """Test adding messages to history and retrieving them."""
        session_id = self.session_manager.create_session()
        message1 = {"role": "user", "content": "First message"}
        message2 = {"role": "assistant", "content": "Second message"}

        self.session_manager.add_message(session_id, message1)
        self.session_manager.add_message(session_id, message2)

        history = self.session_manager.get_history(session_id)
        self.assertEqual(history, [message1, message2])

        # raw_data is already a Python object (list in this case) because decode_responses=True
        raw_data = self.redis_client.execute_command('JSON.GET', session_id, '$.history')
        direct_history = raw_data[0] # Get the actual list from the list
        self.assertEqual(direct_history, [message1, message2])

    def test_get_history_empty_or_nonexistent(self):
        """Test retrieving history when it's empty or the session doesn't exist."""
        session_id = self.session_manager.create_session()
        history = self.session_manager.get_history(session_id)
        self.assertEqual(history, [])

        non_existent_session_id = "session:totally_fake"
        history = self.session_manager.get_history(non_existent_session_id)
        self.assertIsNone(history)

    def test_delete_session(self):
        """Test deleting a session."""
        session_id = self.session_manager.create_session()
        self.assertEqual(self.redis_client.exists(session_id), 1)

        self.session_manager.delete_session(session_id)

        self.assertEqual(self.redis_client.exists(session_id), 0)

    def test_update_and_get_agent_state(self):
        """Test updating and retrieving an agent's state."""
        session_id = self.session_manager.create_session()
        agent_name = "test_agent"
        state1 = {"status": "processing", "step": 1}
        state2 = {"status": "done", "step": 2}

        self.session_manager.update_agent_state(session_id, agent_name, state1)
        retrieved_state = self.session_manager.get_agent_state(session_id, agent_name)
        self.assertEqual(retrieved_state, state1)

        # raw_data is already a Python object (list in this case) because decode_responses=True
        raw_data = self.redis_client.execute_command('JSON.GET', session_id, f'$.agent_states.{agent_name}')
        direct_state = raw_data[0] # Get the actual dictionary from the list
        self.assertEqual(direct_state, state1)

        self.session_manager.update_agent_state(session_id, agent_name, state2)
        retrieved_state_updated = self.session_manager.get_agent_state(session_id, agent_name)
        self.assertEqual(retrieved_state_updated, state2)

    def test_get_agent_state_nonexistent(self):
        """Test retrieving a non-existent agent state."""
        session_id = self.session_manager.create_session()
        
        state = self.session_manager.get_agent_state(session_id, "nonexistent_agent")
        
        self.assertIsNone(state)
