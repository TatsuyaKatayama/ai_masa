
import unittest
from unittest.mock import patch, MagicMock
import subprocess
import yaml
import os

# Make sure to adjust the path to import the agent
from ai_masa.agents.role_based_gemini_cli_agent import RoleBasedGeminiCliAgent
from ai_masa.models.message import Message

class TestFoamerAgent(unittest.TestCase):

    def setUp(self):
        # Load agent configuration from YAML
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'agent_library.yml')
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        self.foamer_config = self.config['foamer']
        self.foamer_config['name'] = 'FoamerTestAgent' # Use a different name for testing to avoid conflicts
        # Remove the 'type' key as it's not expected by the agent's constructor
        del self.foamer_config['type']

    @patch('ai_masa.comms.redis_broker.RedisBroker')
    def test_foamer_initial_session_timeout(self, MockRedisBroker):
        """
        Tests if the foamer agent's initial session creation times out,
        as described in the problem.
        """
        # Instantiate the agent with the loaded config
        agent = RoleBasedGeminiCliAgent(**self.foamer_config)
        agent.shutdown_event.set() # Prevent heartbeat threads

        # Mock subprocess.run to simulate a timeout on the specific command
        # that _create_llm_session in GeminiCliAgent runs.
        original_subprocess_run = subprocess.run

        def mock_subprocess_run(*args, **kwargs):
            command = args[0]
            if "gemini --resume" in command and agent.description in command:
                # This is the initial session creation command. Simulate a timeout.
                raise subprocess.TimeoutExpired(cmd=command, timeout=80)
            return original_subprocess_run(*args, **kwargs)

        with patch('subprocess.run', side_effect=mock_subprocess_run) as mock_run:
            # This call will trigger _create_llm_session
            session_id = agent._create_llm_session(job_id="test_job_1")

            # Assert that a session was NOT created due to the timeout
            self.assertIsNone(session_id)

            # Verify that subprocess.run was called with the expected command structure
            self.assertTrue(any("gemini --resume" in call.args[0] for call in mock_run.call_args_list))


    @patch('ai_masa.comms.redis_broker.RedisBroker')
    def test_foamer_initial_session_live(self, MockRedisBroker):
        """
        This is a live test that attempts to reproduce the timeout without mocking subprocess.
        It may be slow and is expected to fail if the timeout issue exists.
        This test is marked as 'expectedFailure' to indicate the bug.
        """
        # Instantiate the agent
        agent = RoleBasedGeminiCliAgent(**self.foamer_config)
        agent.shutdown_event.set() # Prevent heartbeat threads

        # This call will trigger the actual subprocess command
        # If the bug exists, this will hang and then time out (returning None).
        # The original code has a timeout of 80 seconds.
        # We can add a shorter timeout here for the test if needed, but for now
        # we will rely on the agent's internal timeout.
        
        print(f"\n--- Running live test for {agent.name}. This may take over 80 seconds. ---")
        
        session_id = agent._create_llm_session(job_id="live_test_job")

        # If the command times out as per GeminiCliAgent, session_id will be None.
        if session_id is None:
            print(f"--- Live test for {agent.name} correctly resulted in a timeout (session_id is None). ---")
        else:
            print(f"--- Live test for {agent.name} did NOT time out. Session ID: {session_id} ---")

        # This assertion will fail if the timeout occurs, demonstrating the bug.
        # To make the test pass when the bug is present, we'd assert IsNone.
        self.assertIsNone(session_id, "Expected session creation to time out and return None, but it did not.")


if __name__ == '__main__':
    unittest.main()
