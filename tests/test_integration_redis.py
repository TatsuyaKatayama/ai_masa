import unittest
import subprocess
import time
import redis
import json
import os
from unittest.mock import patch

from ai_masa.agents.base_agent import BaseAgent
from ai_masa.models.message import Message
from ai_masa.comms.session_manager import SessionManager

# Configuration for test Redis instance (must match docker-compose.yml)
TEST_REDIS_HOST = 'localhost'
TEST_REDIS_PORT = 6379
TEST_REDIS_DB = 1 # Use a dedicated DB for integration testing to avoid conflicts

# Note: This test requires Docker and docker-compose to be installed and running.
class TestBaseAgentIntegration(unittest.TestCase):
    """
    Integration test for BaseAgent with a real Redis instance managed by Docker.
    """

    @classmethod
    def setUpClass(cls):
        """Starts the Redis container before any tests are run."""
        print("\nStarting Redis container for integration tests...")
        
        # We need to specify the path to the docker-compose file relative to the project root
        compose_file_path = os.path.join(os.path.dirname(__file__), '..', 'docker-compose.yml')
        if not os.path.exists(compose_file_path):
            raise FileNotFoundError(f"docker-compose.yml not found at {compose_file_path}")

        try:
            subprocess.run(
                ["docker", "compose", "-f", compose_file_path, "up", "-d"],
                check=True, capture_output=True
            )
            # Wait for Redis to be ready
            cls.wait_for_redis()
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print("Error starting Redis container. Is Docker running?")
            print(f"Stderr: {e.stderr if hasattr(e, 'stderr') else 'N/A'}")
            raise

    @classmethod
    def tearDownClass(cls):
        """Stops the Redis container after all tests are done."""
        print("\nStopping Redis container...")
        compose_file_path = os.path.join(os.path.dirname(__file__), '..', 'docker-compose.yml')
        subprocess.run(
            ["docker", "compose", "-f", compose_file_path, "down"],
            capture_output=True
        )

    @classmethod
    def wait_for_redis(cls, retries=10, delay=2):
        """Waits for the Redis container to become available."""
        print("Waiting for Redis to be ready...")
        for i in range(retries):
            try:
                r = redis.Redis(host=TEST_REDIS_HOST, port=TEST_REDIS_PORT, db=TEST_REDIS_DB)
                if r.ping():
                    print("Redis is ready.")
                    cls.redis_client = r
                    return
            except redis.exceptions.ConnectionError:
                time.sleep(delay)
        raise ConnectionError("Could not connect to Redis container after multiple retries.")

    def setUp(self):
        """Cleans the Redis database before each test."""
        self.assertTrue(self.redis_client.ping(), "Redis connection failed at setUp.")
        self.redis_client.flushdb()
        
        # We only mock the subprocess call to the LLM, everything else is real.
        self.mock_subprocess_patcher = patch('subprocess.run')
        self.mock_subprocess_run = self.mock_subprocess_patcher.start()

    def tearDown(self):
        """Stops the patcher."""
        self.mock_subprocess_patcher.stop()

    def test_full_scenario_integration(self):
        """
        Tests Scenario 1 and 2 in a single flow against a real Redis DB.
        """
        project_name = "integ-project"
        agent_name = "IntegAgent"
        session_id = f"{project_name}-{agent_name}"
        job_id = "job-integ-123"

        # Use the real SessionManager
        session_manager = SessionManager(host=TEST_REDIS_HOST, port=TEST_REDIS_PORT, db=TEST_REDIS_DB)

        agent = BaseAgent(
            name=agent_name,
            description="An integration test agent.",
            session_id=session_id,
            redis_host=TEST_REDIS_HOST,
            redis_port=TEST_REDIS_PORT,
            redis_db=TEST_REDIS_DB,
            llm_command="gemini -r {session_id}",
            llm_session_create_command="create_session_cmd",
            start_heartbeat=False
        )
        
        # --- SCENARIO 1: First message ---
        
        # Arrange (Scenario 1)
        trigger_message_1 = Message(from_agent="User", to_agent=agent_name, content="Hello", job_id=job_id)
        llm_response_1 = json.dumps({"to_agent": "User", "content": "Hi there!"})
        self.mock_subprocess_run.side_effect = [
            subprocess.CompletedProcess(args='create_session_cmd', returncode=0, stdout='llm-session-abc', stderr=''),
            subprocess.CompletedProcess(args='gemini', returncode=0, stdout=llm_response_1, stderr='')
        ]

        # Act (Scenario 1)
        agent._on_message_received(trigger_message_1.to_json())

        # Assert (Scenario 1) - Check Redis directly
        self.assertEqual(self.mock_subprocess_run.call_count, 2, "Expected LLM session creation and one LLM call.")
        
        history = session_manager.get_history(session_id, agent_name)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]['content'], "Hello")
        self.assertEqual(history[1]['content'], "Hi there!")

        agent_state = session_manager.get_agent_state(session_id, agent_name)
        self.assertEqual(agent_state['llm_sessions'][job_id], 'llm-session-abc')

        # --- SCENARIO 2: Second message ---

        # Arrange (Scenario 2)
        trigger_message_2 = Message(from_agent="User", to_agent=agent_name, content="How are you?", job_id=job_id)
        llm_response_2 = json.dumps({"to_agent": "User", "content": "I am fine."})
        # Reset mock for the second call - only one subprocess call is expected now
        self.mock_subprocess_run.reset_mock()
        self.mock_subprocess_run.side_effect = [
             subprocess.CompletedProcess(args='gemini', returncode=0, stdout=llm_response_2, stderr='')
        ]

        # Act (Scenario 2)
        agent._on_message_received(trigger_message_2.to_json())

        # Assert (Scenario 2)
        self.mock_subprocess_run.assert_called_once() # CRITICAL: No new LLM session was created
        
        history = session_manager.get_history(session_id, agent_name)
        self.assertEqual(len(history), 4) # 2 from previous, 2 from this turn
        self.assertEqual(history[2]['content'], "How are you?")
        self.assertEqual(history[3]['content'], "I am fine.")

if __name__ == '__main__':
    unittest.main()