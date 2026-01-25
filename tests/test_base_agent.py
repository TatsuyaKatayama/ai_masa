import unittest
from unittest.mock import patch, MagicMock
import json
import subprocess

from ai_masa.agents.base_agent import BaseAgent
from ai_masa.models.message import Message
from ai_masa.models.prompts import OBSERVER_INSTRUCTION

class TestBaseAgent(unittest.TestCase):

    def setUp(self):
        """Set up mocks for each test."""
        self.mock_broker_patcher = patch('ai_masa.agents.base_agent.RedisBroker')
        self.mock_memory_manager_patcher = patch('ai_masa.agents.base_agent.MemoryManager')
        self.mock_subprocess_patcher = patch('subprocess.run')

        self.MockRedisBroker = self.mock_broker_patcher.start()
        self.MockMemoryManager = self.mock_memory_manager_patcher.start()
        self.mock_subprocess_run = self.mock_subprocess_patcher.start()

        self.mock_broker_instance = self.MockRedisBroker.return_value
        self.mock_memory_manager_instance = self.MockMemoryManager.return_value

        self.agent = BaseAgent(
            name="TestAgent",
            description="A test agent.",
            memory_id="TestAgent:test_project",
            memory_manager=self.mock_memory_manager_instance,
            llm_command="gemini -r {session_id}",
            llm_session_create_command="create_session_cmd",
            start_heartbeat=False
        )

    def tearDown(self):
        """Stop all patchers."""
        self.mock_broker_patcher.stop()
        self.mock_memory_manager_patcher.stop()
        self.mock_subprocess_patcher.stop()

    def test_scenario_1_first_message_received(self):
        """
        Tests agent's behavior on receiving the first message for a new job.
        """
        # --- Arrange ---
        job_id = "job-new"
        trigger_message = Message(from_agent="User", to_agent="TestAgent", content="Hello", job_id=job_id)
        trigger_message_json = trigger_message.to_json()
        
        llm_response_content = {"to_agent": "User", "content": "Hi there!"}
        llm_response_json = json.dumps(llm_response_content)

        self.mock_memory_manager_instance.get_agent_state.return_value = None
        self.mock_memory_manager_instance.get_history.return_value = []
        self.mock_subprocess_run.side_effect = [
            subprocess.CompletedProcess(args='create_session_cmd', returncode=0, stdout='new-llm-session-123', stderr=''),
            subprocess.CompletedProcess(args='gemini -r new-llm-session-123', returncode=0, stdout=llm_response_json, stderr='')
        ]

        # --- Act ---
        self.agent._on_message_received(trigger_message_json)

        # --- Assert ---
        self.mock_memory_manager_instance.add_message.assert_any_call("TestAgent:test_project", json.loads(trigger_message_json))
        self.mock_memory_manager_instance.get_agent_state.assert_called_once_with("TestAgent:test_project", "TestAgent")
        
        create_session_call = self.mock_subprocess_run.call_args_list[0]
        self.assertEqual(create_session_call.args[0], 'create_session_cmd')
        
        expected_state = {"llm_sessions": {job_id: "new-llm-session-123"}}
        self.mock_memory_manager_instance.update_agent_state.assert_called_once_with("TestAgent:test_project", "TestAgent", expected_state)

        self.mock_memory_manager_instance.get_history.assert_called_once_with("TestAgent:test_project", "TestAgent")
        invoke_llm_call = self.mock_subprocess_run.call_args_list[1]
        self.assertEqual(invoke_llm_call.args[0], 'gemini -r new-llm-session-123')
        
        self.assertEqual(self.mock_memory_manager_instance.add_message.call_count, 2)
        saved_response_dict = self.mock_memory_manager_instance.add_message.call_args.args[1]
        self.assertEqual(saved_response_dict['content'], "Hi there!")

        self.mock_broker_instance.publish.assert_called_once()
        published_data = json.loads(self.mock_broker_instance.publish.call_args[0][0])
        self.assertEqual(published_data['content'], "Hi there!")

    def test_scenario_2_second_message_uses_existing_state(self):
        """
        Tests agent's behavior on receiving a subsequent message for an existing job.
        """
        # --- Arrange ---
        job_id = "job-existing"
        trigger_message = Message(from_agent="User", to_agent="TestAgent", content="How are you?", job_id=job_id)
        trigger_message_json = trigger_message.to_json()

        llm_response_content = {"to_agent": "User", "content": "I am fine, thank you."}
        llm_response_json = json.dumps(llm_response_content)

        existing_state = {"llm_sessions": {job_id: "existing-llm-session-456"}}
        self.mock_memory_manager_instance.get_agent_state.return_value = existing_state
        
        previous_history = [{"from_agent": "User", "content": "Hello", "job_id": job_id}]
        self.mock_memory_manager_instance.get_history.return_value = previous_history

        self.mock_subprocess_run.return_value = subprocess.CompletedProcess(
            args='gemini -r existing-llm-session-456', returncode=0, stdout=llm_response_json, stderr=''
        )

        # --- Act ---
        self.agent._on_message_received(trigger_message_json)

        # --- Assert ---
        self.mock_memory_manager_instance.get_agent_state.assert_called_once_with("TestAgent:test_project", "TestAgent")
        self.mock_memory_manager_instance.update_agent_state.assert_not_called()
        self.mock_subprocess_run.assert_called_once()

        invoke_llm_call = self.mock_subprocess_run.call_args
        self.assertEqual(invoke_llm_call.args[0], 'gemini -r existing-llm-session-456')
        prompt = invoke_llm_call.kwargs['input']
        self.assertIn("- User: Hello", prompt)
        
        self.mock_broker_instance.publish.assert_called_once()

    def test_irrelevant_message_is_ignored(self):
        """An agent should not process messages not addressed to it."""
        trigger_message = Message("User", "AnotherAgent", "Hi there", job_id="job-1")
        self.agent._on_message_received(trigger_message.to_json())

        self.mock_memory_manager_instance.add_message.assert_not_called()
        self.mock_subprocess_run.assert_not_called()

    def test_cc_message_is_processed_as_observer(self):
        """A CC'd agent should save the message and act as an observer."""
        job_id = "job-cc"
        trigger_message = Message("User", "AnotherAgent", "FYI", job_id=job_id, cc_agents=["TestAgent"])
        llm_response_json = json.dumps({"to_agent": "", "content": ""})

        self.mock_memory_manager_instance.get_agent_state.return_value = {"llm_sessions": {job_id: "llm-session-cc"}}
        self.mock_memory_manager_instance.get_history.return_value = []
        self.mock_subprocess_run.return_value = subprocess.CompletedProcess(args='', returncode=0, stdout=llm_response_json, stderr='')

        self.agent._on_message_received(trigger_message.to_json())

        self.mock_memory_manager_instance.add_message.assert_called_once_with("TestAgent:test_project", json.loads(trigger_message.to_json()))
        self.mock_subprocess_run.assert_called_once()
        prompt = self.mock_subprocess_run.call_args.kwargs['input']
        self.assertIn(OBSERVER_INSTRUCTION, prompt)
        self.mock_broker_instance.publish.assert_not_called()

if __name__ == '__main__':
    unittest.main()
