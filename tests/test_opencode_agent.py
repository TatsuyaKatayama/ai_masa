import unittest
from unittest.mock import patch, MagicMock, call
import subprocess
import json
import logging
import os

# Mute the agent's own logging to keep test output clean
logging.getLogger('ai_masa.agents.opencode_agent').setLevel(logging.CRITICAL)

from ai_masa.agents.opencode_agent import OpencodeAgent
from ai_masa.models.message import Message

class TestOpencodeAgentNew(unittest.TestCase):

    def setUp(self):
        # Patch dependencies that are not the focus of this test
        patcher_redis = patch('ai_masa.agents.base_agent.RedisBroker')
        patcher_heartbeat = patch('ai_masa.agents.base_agent.BaseAgent._start_heartbeat')
        
        self.mock_redis_broker = patcher_redis.start()
        self.mock_start_heartbeat = patcher_heartbeat.start()
        
        self.addCleanup(patcher_redis.stop)
        self.addCleanup(patcher_heartbeat.stop)

    @patch('ai_masa.agents.opencode_agent.load_env_file')
    def test_env_file_loaded_on_init(self, mock_load_env_file):
        # Arrange: Mock a successful _initialize_session to allow OpencodeAgent to instantiate
        # Patch subprocess.run that is called inside _initialize_session
        with patch('subprocess.run') as mock_subprocess_run:
            mock_subprocess_run.return_value = MagicMock(
                spec=subprocess.CompletedProcess,
                stdout=json.dumps({"sessionID": "ses_mock_id", "response": "Hello"}),
                stderr="",
                returncode=0
            )

            # Act
            agent = OpencodeAgent(name="TestAgent", memory_id="test_mem")

            # Assert that load_env_file was called
            mock_load_env_file.assert_called_once()

            # Assert that load_env_file was called with the correct path
            called_path = mock_load_env_file.call_args[0][0]
            path_parts = os.path.normpath(called_path).split(os.sep)
            self.assertEqual(path_parts[-2:], ['ai_masa', '.env.example'])

    @patch('subprocess.run')
    def test_initialize_session_success(self, mock_subprocess_run):
        # Arrange
        session_id = "ses_12345"
        mock_stdout = json.dumps({"sessionID": session_id, "response": "Hello"})
        mock_subprocess_run.return_value = MagicMock(
            spec=subprocess.CompletedProcess,
            stdout=mock_stdout,
            stderr="",
            returncode=0
        )

        # Act
        agent = OpencodeAgent(name="TestAgent", memory_id="test_mem", model="test/model")

        # Assert
        self.assertEqual(agent.session_id, session_id)
        self.assertEqual(agent.llm_command, f"opencode -m test/model run -s {session_id}")
        
        expected_command = "opencode -m test/model run --format json"
        mock_subprocess_run.assert_called_once()
        # Accessing the call arguments correctly
        called_args, called_kwargs = mock_subprocess_run.call_args
        self.assertEqual(called_args[0], expected_command)
        self.assertTrue(called_kwargs.get('shell'))


    @patch('subprocess.run')
    def test_initialize_session_no_session_id_in_output(self, mock_subprocess_run):
        # Arrange
        mock_stdout = json.dumps({"response": "Hello, this is not a session init response"})
        mock_subprocess_run.return_value = MagicMock(
            spec=subprocess.CompletedProcess,
            stdout=mock_stdout,
            stderr="",
            returncode=0
        )

        # Act & Assert
        with self.assertRaisesRegex(RuntimeError, "Failed to initialize Opencode session: sessionID not found."):
            OpencodeAgent(name="TestAgent", memory_id="test_mem")

    @patch('subprocess.run')
    def test_initialize_session_subprocess_error(self, mock_subprocess_run):
        # Arrange
        mock_subprocess_run.side_effect = subprocess.CalledProcessError(
            returncode=1, cmd="opencode run", stderr="Something went wrong"
        )

        # Act & Assert
        with self.assertRaisesRegex(RuntimeError, "Failed to initialize Opencode session"):
            OpencodeAgent(name="TestAgent", memory_id="test_mem")

    def test_think_and_respond_session_not_initialized(self):
        # Arrange
        # This test requires bypassing the __init__'s call to _initialize_session
        with patch.object(OpencodeAgent, '_initialize_session', return_value=None):
            agent = OpencodeAgent(name="TestAgent", memory_id="test_mem")
            agent.session_id = None # Ensure session is not set
            
            # Mock the logger to capture error messages
            with self.assertLogs('ai_masa.agents.opencode_agent', level='ERROR') as cm:
                # Act
                agent.think_and_respond(
                    trigger_msg=Message(from_agent="user", content="hello", job_id="test_job"),
                    job_id="test_job"
                )
                # Assert
                self.assertIn("Cannot handle message; persistent session not initialized. Aborting.", cm.output[0])

    @patch('subprocess.run')
    def test_invoke_llm_success(self, mock_subprocess_run):
        # Arrange
        # First, initialize the agent successfully to set up the llm_command
        init_session_id = "ses_init_123"
        mock_init_stdout = json.dumps({"sessionID": init_session_id})
        
        # Second, set up the mock for the _invoke_llm call
        llm_response = '{"to_agent": "user", "content": "This is the response."}'
        
        # The side_effect will apply to all calls to subprocess.run
        mock_subprocess_run.side_effect = [
            MagicMock(stdout=mock_init_stdout, returncode=0), # For _initialize_session
            MagicMock(stdout=llm_response, returncode=0)      # For _invoke_llm
        ]

        agent = OpencodeAgent(name="TestAgent", memory_id="test_mem", model="test/model")
        
        # Act
        response = agent._invoke_llm(prompt="User prompt", llm_session_id="ignored_id")

        # Assert
        self.assertEqual(response, llm_response)
        
        # Check the second call to subprocess.run which is the one from _invoke_llm
        self.assertEqual(mock_subprocess_run.call_count, 2)
        expected_llm_command = f"opencode -m test/model run -s {init_session_id}"
        invoked_command = mock_subprocess_run.call_args_list[1].args[0]
        self.assertEqual(invoked_command, expected_llm_command)

    @patch('subprocess.run')
    def test_invoke_llm_subprocess_error(self, mock_subprocess_run):
        # Arrange
        init_session_id = "ses_init_456"
        mock_init_stdout = json.dumps({"sessionID": init_session_id})
        
        mock_subprocess_run.side_effect = [
            MagicMock(stdout=mock_init_stdout, returncode=0),
            subprocess.CalledProcessError(1, "llm command failed", stderr="LLM Error")
        ]
        
        agent = OpencodeAgent(name="TestAgent", memory_id="test_mem")

        # Act
        response = agent._invoke_llm(prompt="User prompt", llm_session_id="ignored_id")

        # Assert
        self.assertIsNone(response)

if __name__ == "__main__":
    unittest.main()