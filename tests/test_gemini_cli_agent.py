import unittest
from unittest.mock import patch, MagicMock, call
import json
import subprocess
import os
import shlex
import tempfile
import shutil

from ai_masa.agents.gemini_cli_agent import GeminiCliAgent
from ai_masa.models.message import Message

class TestGeminiCliAgent(unittest.TestCase):

    def setUp(self):
        """Set up mocks and agent instance for each test case."""
        self.mock_broker_patcher = patch('ai_masa.agents.base_agent.RedisBroker')
        self.mock_memory_manager_patcher = patch('ai_masa.agents.base_agent.MemoryManager')
        self.mock_subprocess_patcher = patch('subprocess.run')
        self.mock_base_agent_start_heartbeat_patcher = patch('ai_masa.agents.base_agent.BaseAgent._start_heartbeat')

        self.MockRedisBroker = self.mock_broker_patcher.start()
        self.MockMemoryManager = self.mock_memory_manager_patcher.start()
        self.mock_subprocess_run = self.mock_subprocess_patcher.start()
        self.mock_base_agent_start_heartbeat = self.mock_base_agent_start_heartbeat_patcher.start()

        self.mock_broker_instance = self.MockRedisBroker.return_value
        self.mock_memory_manager_instance = self.MockMemoryManager.return_value

        self.agent_name = "TestGeminiAgent"
        self.memory_id = f"project-{self.agent_name}"
        self.description = "You are an intelligent AI assistant equipped with the Gemini CLI."

        self.agent = GeminiCliAgent(
            name=self.agent_name,
            description=self.description,
            memory_id=self.memory_id,
            memory_manager=self.mock_memory_manager_instance,
            llm_command="gemini --resume {session_id} --output-format json",
            # _create_llm_session method is overridden, so this value is not directly used for session creation
            llm_session_create_command="echo 'new_llm_session_id'", 
            start_heartbeat=False
        )

    def tearDown(self):
        """Stop all patchers."""
        self.mock_broker_patcher.stop()
        self.mock_memory_manager_patcher.stop()
        self.mock_subprocess_patcher.stop()
        self.mock_base_agent_start_heartbeat_patcher.stop()

    def test_init_sets_correct_description_and_llm_command(self):
        """
        Test that __init__ correctly sets description and default llm_command.
        """
        self.assertEqual(self.agent.name, self.agent_name)
        self.assertEqual(self.agent.description, self.description)
        self.assertEqual(self.agent.llm_command, "gemini --resume {session_id} --output-format json")
        self.assertIn("--output-format json", self.agent.llm_command) # Should be part of actual llm_command
        self.assertEqual(self.agent.memory_id, self.memory_id)

    def test_create_llm_session_generates_new_session_index(self):
        """
        Test that _create_llm_session correctly generates a new Gemini CLI session index.
        """
        job_id = "job-create-new"
        # Mock gemini --list-sessions to return no sessions
        self.mock_subprocess_run.side_effect = [
            subprocess.CompletedProcess(args=["gemini", "--list-sessions"], returncode=0, stdout="No sessions found.", stderr=""),
            subprocess.CompletedProcess(args=unittest.mock.ANY, returncode=0, stdout="", stderr="") # For initial prompt call
        ]
        
        llm_session_index = self.agent._create_llm_session(job_id)
        
        self.assertEqual(llm_session_index, "1") # Expecting the first session to be index 1
        self.assertEqual(self.mock_subprocess_run.call_count, 2)
        self.assertIn("gemini --list-sessions", self.mock_subprocess_run.call_args_list[0].args[0])
        self.assertIn(shlex.quote(self.agent.role_prompt), self.mock_subprocess_run.call_args_list[1].args[0])

    def test_create_llm_session_uses_next_available_index(self):
        """
        Test that _create_llm_session uses the next available session index.
        """
        job_id = "job-create-next"
        # Mock gemini --list-sessions to return existing sessions in the expected format (e.g., "1. ...")
        self.mock_subprocess_run.side_effect = [
            subprocess.CompletedProcess(args=["gemini", "--list-sessions"], returncode=0, stdout="1. Memory A\n2. Memory B", stderr=""),
            subprocess.CompletedProcess(args=unittest.mock.ANY, returncode=0, stdout="", stderr="") # For initial prompt call
        ]
        
        llm_session_index = self.agent._create_llm_session(job_id)
        
        self.assertEqual(llm_session_index, "3") # Expecting next session to be index 3
        self.assertEqual(self.mock_subprocess_run.call_count, 2)

    def test_think_and_respond_creates_new_llm_session_and_responds(self):
        """
        Test Scenario 1: First message for a job creates LLM session and responds.
        """
        job_id = "job-first"
        trigger_message_json = Message("User", self.agent_name, "What is 1+1?", job_id=job_id).to_json()
        llm_response_content = {"to_agent": "User", "content": "The answer is 2."}
        llm_response_json = json.dumps(llm_response_content)

        self.mock_memory_manager_instance.get_agent_state.return_value = None
        self.mock_memory_manager_instance.get_history.return_value = []

        self.mock_subprocess_run.side_effect = [
            subprocess.CompletedProcess(args=["gemini", "--list-sessions"], returncode=0, stdout="No sessions found.", stderr=""), # _create_llm_session list
            subprocess.CompletedProcess(args=unittest.mock.ANY, returncode=0, stdout="", stderr=""), # _create_llm_session init prompt
            subprocess.CompletedProcess(args=unittest.mock.ANY, returncode=0, stdout=llm_response_json, stderr="") # _invoke_llm
        ]

        self.agent._on_message_received(trigger_message_json)

        self.assertEqual(self.mock_subprocess_run.call_count, 3) # list-sessions, init prompt, invoke LLM
        self.mock_memory_manager_instance.update_agent_state.assert_called_once()
        
        # Verify history saved for incoming and outgoing messages
        self.assertEqual(self.mock_memory_manager_instance.add_message.call_count, 2)
        self.mock_broker_instance.publish.assert_called_once()
        published_msg = json.loads(self.mock_broker_instance.publish.call_args[0][0])
        self.assertEqual(published_msg['content'], "The answer is 2.")


    def test_think_and_respond_uses_existing_llm_session(self):
        """
        Test Scenario 2: Subsequent message for a job uses existing LLM session.
        """
        job_id = "job-existing"
        trigger_message_json = Message("User", self.agent_name, "What is 2+2?", job_id=job_id).to_json()
        llm_response_content = {"to_agent": "User", "content": "The answer is 4."}
        llm_response_json = json.dumps(llm_response_content)

        existing_llm_session_id = "existing-llm-session-abc"
        existing_agent_state = {"llm_sessions": {job_id: existing_llm_session_id}}

        self.mock_memory_manager_instance.get_agent_state.return_value = existing_agent_state
        self.mock_memory_manager_instance.get_history.return_value = [
            {"from_agent": "User", "to_agent": self.agent_name, "content": "What is 1+1?", "job_id": job_id},
            {"from_agent": self.agent_name, "to_agent": "User", "content": "The answer is 2.", "job_id": job_id}
        ]

        self.mock_subprocess_run.return_value = subprocess.CompletedProcess(args=unittest.mock.ANY, returncode=0, stdout=llm_response_json, stderr="")

        self.agent._on_message_received(trigger_message_json)

        self.mock_memory_manager_instance.get_agent_state.assert_called_once_with(self.memory_id, self.agent_name)
        self.mock_memory_manager_instance.update_agent_state.assert_not_called() # No new LLM session created
        self.assertEqual(self.mock_subprocess_run.call_count, 1) # Only _invoke_llm called
        self.assertIn(f"gemini --resume {existing_llm_session_id}", self.mock_subprocess_run.call_args[0][0])

        # Verify history saved for incoming and outgoing messages
        # It was called for the incoming message by BaseAgent's _on_message_received,
        # and for the outgoing message by BaseAgent's broadcast.
        self.assertEqual(self.mock_memory_manager_instance.add_message.call_count, 2)
        self.mock_broker_instance.publish.assert_called_once()

    def test_gemini_config_file_creation(self):
        """
        Test that .gemini/settings.json is created if working_dir is set and it doesn't exist.
        """
        # Create a temporary working directory for this test
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = GeminiCliAgent(
                name="TempGeminiAgent",
                description="Temp agent.",
                memory_id="project-TempGeminiAgent",
                memory_manager=self.mock_memory_manager_instance,
                working_dir=tmpdir,
                start_heartbeat=False
            )
            settings_path = os.path.join(tmpdir, '.gemini', 'settings.json')
            self.assertTrue(os.path.exists(settings_path))
            with open(settings_path, 'r') as f:
                self.assertEqual(f.read(), '{}')

    def test_gemini_config_file_not_created_if_exists(self):
        """
        Test that .gemini/settings.json is not created if working_dir is set and it already exists.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, '.gemini'), exist_ok=True)
            with open(os.path.join(tmpdir, '.gemini', 'settings.json'), 'w') as f:
                f.write('{"api_key": "existing"}')

            agent = GeminiCliAgent(
                name="TempGeminiAgent2",
                description="Temp agent.",
                memory_id="project-TempGeminiAgent2",
                memory_manager=self.mock_memory_manager_instance,
                working_dir=tmpdir,
                start_heartbeat=False
            )
            settings_path = os.path.join(tmpdir, '.gemini', 'settings.json')
            self.assertTrue(os.path.exists(settings_path))
            with open(settings_path, 'r') as f:
                self.assertEqual(f.read(), '{"api_key": "existing"}')


if __name__ == '__main__':
    unittest.main()
