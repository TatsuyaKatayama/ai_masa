import unittest
from unittest.mock import patch, MagicMock, call
import subprocess
import json
from ai_masa.agents.opencode_agent import OpencodeAgent

class TestOpencodeAgent(unittest.TestCase):

    def setUp(self):
        # We patch 'subprocess.run' to mock shell command execution
        self.mock_subprocess_run = patch('subprocess.run').start()
        
        # We patch 'RedisBroker' to prevent actual network connections during unit tests
        self.mock_redis_broker = patch('ai_masa.agents.base_agent.RedisBroker').start()
        
        # We patch '_start_heartbeat' to prevent the background thread from starting
        self.mock_start_heartbeat = patch('ai_masa.agents.base_agent.BaseAgent._start_heartbeat').start()
        
        self.addCleanup(patch.stopall)

    def test_init_default_llm_command(self):
        agent = OpencodeAgent(name="TestAgent", memory_id="test_mem")
        expected_command = "docker exec opencode-cli opencode -m google/gemini-2.5-flash run --session {session_id}"
        self.assertEqual(agent.llm_command, expected_command)
        self.assertEqual(agent.model, "google/gemini-2.5-flash")

    def test_init_with_custom_model(self):
        agent = OpencodeAgent(name="TestAgent", memory_id="test_mem", model="google/gemini-pro")
        expected_command = "docker exec opencode-cli opencode -m google/gemini-pro run --session {session_id}"
        self.assertEqual(agent.llm_command, expected_command)
        self.assertEqual(agent.model, "google/gemini-pro")

    def test_init_with_model_and_spaces_quoted(self):
        # Although opencode models don't typically have spaces, testing shlex.quote
        agent = OpencodeAgent(name="TestAgent", memory_id="test_mem", model="a model/with spaces")
        expected_command = "docker exec opencode-cli opencode -m 'a model/with spaces' run --session {session_id}"
        self.assertEqual(agent.llm_command, expected_command)

    def test_create_llm_session_success(self):
        # Mock the two subprocess calls
        mock_init_run_result = MagicMock(spec=subprocess.CompletedProcess, returncode=0, stdout="", stderr="")
        mock_session_list_result = MagicMock(spec=subprocess.CompletedProcess, returncode=0)
        
        mock_sessions_output = json.dumps([
            {"id": "ses_newest_session", "title": "Initialize session", "updated": 1700000002},
            {"id": "ses_older_session", "title": "Some other task", "updated": 1700000001}
        ])
        mock_session_list_result.stdout = mock_sessions_output
        
        self.mock_subprocess_run.side_effect = [
            mock_init_run_result, # First call is the init run
            mock_session_list_result  # Second call is the session list
        ]

        agent = OpencodeAgent(name="TestAgent", memory_id="test_mem")
        session_id = agent._create_llm_session(job_id="test_job")

        # Verify the session ID is the first one from the list
        self.assertEqual(session_id, "ses_newest_session")

        # Verify the calls to subprocess.run
        self.assertEqual(self.mock_subprocess_run.call_count, 2)
        
        # Check the first call (init)
        expected_init_command_args = call(
            "docker exec opencode-cli opencode -m google/gemini-2.5-flash run 'Initialize session for ID retrieval'",
            shell=True, capture_output=True, text=True, check=True, timeout=80, cwd=None
        )
        self.assertEqual(self.mock_subprocess_run.call_args_list[0], expected_init_command_args)

        # Check the second call (session list)
        expected_session_list_command_args = call(
            "docker exec opencode-cli opencode session list --format json",
            shell=True, capture_output=True, text=True, check=True, cwd=None
        )
        self.assertEqual(self.mock_subprocess_run.call_args_list[1], expected_session_list_command_args)

    def test_create_llm_session_init_command_fails(self):
        # If the first command to create a session fails, the whole process should fail.
        self.mock_subprocess_run.side_effect = subprocess.CalledProcessError(1, "init command failed")

        agent = OpencodeAgent(name="TestAgent", memory_id="test_mem")
        session_id = agent._create_llm_session(job_id="test_job")
        
        self.assertIsNone(session_id)
        self.assertEqual(self.mock_subprocess_run.call_count, 1)

    def test_create_llm_session_list_command_fails(self):
        # If the session list command fails, the process should fail.
        self.mock_subprocess_run.side_effect = [
            MagicMock(spec=subprocess.CompletedProcess, returncode=0, stdout="", stderr=""), # Init command succeeds
            subprocess.CalledProcessError(1, "session list command failed")
        ]

        agent = OpencodeAgent(name="TestAgent", memory_id="test_mem")
        session_id = agent._create_llm_session(job_id="test_job")
        
        self.assertIsNone(session_id)
        self.assertEqual(self.mock_subprocess_run.call_count, 2)

    def test_create_llm_session_empty_list(self):
        # If session list returns an empty JSON array
        self.mock_subprocess_run.side_effect = [
            MagicMock(spec=subprocess.CompletedProcess, returncode=0, stdout="", stderr=""), # Init command succeeds
            MagicMock(spec=subprocess.CompletedProcess, returncode=0, stdout="[]")
        ]

        agent = OpencodeAgent(name="TestAgent", memory_id="test_mem")
        session_id = agent._create_llm_session(job_id="test_job")
        
        self.assertIsNone(session_id)
        self.assertEqual(self.mock_subprocess_run.call_count, 2)

    def test_create_llm_session_invalid_json(self):
        # If session list returns invalid JSON
        self.mock_subprocess_run.side_effect = [
            MagicMock(spec=subprocess.CompletedProcess, returncode=0, stdout="", stderr=""), # Init command succeeds
            MagicMock(spec=subprocess.CompletedProcess, returncode=0, stdout="invalid json")
        ]

        agent = OpencodeAgent(name="TestAgent", memory_id="test_mem")
        session_id = agent._create_llm_session(job_id="test_job")
        
        self.assertIsNone(session_id)
        self.assertEqual(self.mock_subprocess_run.call_count, 2)

    def test_create_llm_session_missing_id_in_first_session(self):
        # If the first session object in the list doesn't have an 'id' key
        self.mock_subprocess_run.side_effect = [
            MagicMock(spec=subprocess.CompletedProcess, returncode=0, stdout="", stderr=""), # Init command succeeds
            MagicMock(spec=subprocess.CompletedProcess, returncode=0, stdout=json.dumps([{"title": "No ID here"}]))
        ]

        agent = OpencodeAgent(name="TestAgent", memory_id="test_mem")
        session_id = agent._create_llm_session(job_id="test_job")
        
        self.assertIsNone(session_id)
        self.assertEqual(self.mock_subprocess_run.call_count, 2)