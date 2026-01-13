import unittest
from unittest.mock import patch, MagicMock
import subprocess
import yaml
import os
import redis
import time

# Make sure to adjust the path to import the agent
from ai_masa.agents.role_based_gemini_cli_agent import RoleBasedGeminiCliAgent
from ai_masa.models.message import Message

class TestFoamerAgent(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Starts the Redis container before any tests are run."""
        print("\n[Foamer Test] Starting Redis container...")
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
        print("\n[Foamer Test] Stopping Redis container...")
        compose_file_path = os.path.join(os.path.dirname(__file__), '..', 'docker-compose.yml')
        subprocess.run(["docker", "compose", "-f", compose_file_path, "down"], capture_output=True)

    @classmethod
    def wait_for_redis(cls, retries=10, delay=2):
        """Waits for the Redis container to become available."""
        for i in range(retries):
            try:
                r = redis.Redis(host='localhost', port=6379, db=1)
                if r.ping():
                    print("[Foamer Test] Redis is ready.")
                    return
            except redis.exceptions.ConnectionError:
                time.sleep(delay)
        raise ConnectionError("Could not connect to Redis container after multiple retries.")

    def setUp(self):
        # Load agent configuration from the default YAML for testing purposes.
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'agent_library.yml.default')
        
        if not os.path.exists(config_path):
            self.fail(f"Required default agent config not found at {config_path}")

        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        self.foamer_config = self.config['foamer'].copy() # Use copy to avoid modifying class-level dict
        self.foamer_config['name'] = 'FoamerTestAgent' # Use a different name for testing to avoid conflicts
        self.foamer_config['memory_id'] = 'test-foamer-memory' # Add memory_id
        self.foamer_config['redis_db'] = 1 # Use test DB
        # Remove the 'type' key as it's not expected by the agent's constructor
        if 'type' in self.foamer_config:
            del self.foamer_config['type']

        # Patch RedisBroker here, so it's mocked during agent instantiation in tearDown.
        self.mock_broker_patcher = patch('ai_masa.comms.redis_broker.RedisBroker')
        self.MockRedisBroker = self.mock_broker_patcher.start()

        # Instantiate the agent, storing it for tearDown
        self.agent = RoleBasedGeminiCliAgent(**self.foamer_config, start_heartbeat=False)
        self.agent.shutdown_event.set() # Ensure heartbeats are not started


    def tearDown(self):
        """
        Clean up by shutting down the agent and stopping all patchers.
        """
        # Ensure the agent is shut down cleanly
        if hasattr(self, 'agent') and self.agent:
            self.agent.shutdown()
        self.mock_broker_patcher.stop()

    @patch('subprocess.run')
    def test_foamer_initial_session_timeout(self, mock_subprocess_run):
        """
        Tests if the foamer agent's initial session creation times out,
        as described in the problem.
        """
        # Mock subprocess.run to simulate a timeout on the specific command
        # that _create_llm_session in GeminiCliAgent runs.
        def mock_subprocess_run_side_effect(*args, **kwargs):
            command = args[0]
            if "gemini --list-sessions" in command:
                return MagicMock(returncode=0, stdout="", stderr="No previous sessions found for this project.")
            # If it's a gemini command but not list-sessions, it must be the init command.
            if "gemini" in command:
                raise subprocess.TimeoutExpired(cmd=command, timeout=80)
            # Fallback for any other command
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_subprocess_run.side_effect = mock_subprocess_run_side_effect

        # This call will trigger _create_llm_session
        session_id = self.agent._create_llm_session(job_id="test_job_1")

        # Assert that a session was NOT created due to the timeout
        self.assertIsNone(session_id)

        # Verify that subprocess.run was called for list-sessions and the init command
        self.assertEqual(mock_subprocess_run.call_count, 2)
        self.assertTrue(any("gemini --list-sessions" in call.args[0] for call in mock_subprocess_run.call_args_list))
        self.assertTrue(any("gemini" in call.args[0] and "list-sessions" not in call.args[0] for call in mock_subprocess_run.call_args_list))

if __name__ == '__main__':
    unittest.main()
