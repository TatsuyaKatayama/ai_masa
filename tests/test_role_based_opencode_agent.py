import unittest
from unittest.mock import patch, MagicMock
import json
import subprocess

from ai_masa.agents.role_based_opencode_agent import RoleBasedOpencodeAgent

class TestRoleBasedOpencodeAgent(unittest.TestCase):

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
        
        # Configure a default successful return for the session initialization
        self.mock_subprocess_run.return_value = MagicMock(
            stdout=json.dumps({"sessionID": "ses_test_12345", "response": "Initialization successful"}),
            stderr="",
            returncode=0
        )

    def tearDown(self):
        """Stop all patchers."""
        self.mock_broker_patcher.stop()
        self.mock_memory_manager_patcher.stop()
        self.mock_subprocess_patcher.stop()
        self.mock_base_agent_start_heartbeat_patcher.stop()

    def test_instantiation_with_role_prompt(self):
        """
        Test that RoleBasedOpencodeAgent can be instantiated with a role_prompt.
        """
        agent_name = "TestRoleOpencodeAgent"
        description_text = "A test opencode agent."
        role_prompt_text = "You are a test opencode agent."
        memory_id = f"{agent_name}:test_project"
        
        agent = RoleBasedOpencodeAgent(
            name=agent_name,
            description=description_text,
            role_prompt=role_prompt_text,
            memory_id=memory_id,
            start_heartbeat=False
        )
        
        self.assertEqual(agent.name, agent_name)
        self.assertEqual(agent.description, description_text)
        self.assertEqual(agent.role_prompt_content, role_prompt_text)
        self.assertIn(description_text, agent.role_prompt)
        self.assertNotIn(role_prompt_text, agent.role_prompt) # role_prompt is not in the final prompt
        self.assertIn("opencode", agent.llm_command)
        self.assertEqual(agent.memory_id, memory_id)
        self.assertIsNotNone(agent.session_id)

    def test_instantiation_with_custom_llm_command(self):
        """
        Test that RoleBasedOpencodeAgent can be instantiated with a custom llm_command.
        """
        agent_name = "TestCustomLlmOpencodeAgent"
        description_text = "An agent with a custom LLM command."
        role_prompt_text = "You are an agent with a custom LLM command."
        custom_llm_command = "my_custom_opencode_cli --model custom-model --param value"
        memory_id = f"{agent_name}:test_project"
        
        # We need to bypass the automatic session creation for this test
        with patch.object(RoleBasedOpencodeAgent, '_initialize_session', return_value=None) as mock_init:
            agent = RoleBasedOpencodeAgent(
                name=agent_name,
                description=description_text,
                role_prompt=role_prompt_text,
                llm_command=custom_llm_command,
                memory_id=memory_id,
                start_heartbeat=False
            )
            # The custom command is passed, but _initialize_session will not run to overwrite it.
            agent.llm_command = custom_llm_command
            
            mock_init.assert_called_once()
            self.assertEqual(agent.llm_command, custom_llm_command)


    def test_instantiation_without_explicit_description_uses_role_prompt(self):
        """
        Test that if no explicit description is given, role_prompt is used as description.
        """
        agent_name = "TestRoleOpencodeAgentNoDesc"
        role_prompt_text = "Only role prompt provided."
        memory_id = f"{agent_name}:test_project"

        agent = RoleBasedOpencodeAgent(
            name=agent_name,
            role_prompt=role_prompt_text,
            memory_id=memory_id,
            start_heartbeat=False
        )

        self.assertEqual(agent.description, role_prompt_text)
        self.assertIn(role_prompt_text, agent.role_prompt)
        self.assertEqual(agent.role_prompt_content, role_prompt_text)

    def test_instantiation_without_any_description_or_role_prompt_uses_default(self):
        """
        Test that if neither description nor role_prompt is given, a default is used.
        """
        agent_name = "TestRoleOpencodeAgentDefaultDesc"
        memory_id = f"{agent_name}:test_project"

        agent = RoleBasedOpencodeAgent(
            name=agent_name,
            memory_id=memory_id,
            start_heartbeat=False
        )

        self.assertEqual(agent.description, "A role-based Opencode agent.")
        self.assertIn("A role-based Opencode agent.", agent.role_prompt)
        self.assertIsNone(agent.role_prompt_content)

    def test_successful_initialization_sets_session_id_and_llm_command(self):
        """
        Test that a successful initialization call sets session_id and llm_command.
        """
        agent_name = "TestInitAgent"
        memory_id = f"{agent_name}:test"
        session_id = "ses_xyz_789"
        model = "google/test-model"

        self.mock_subprocess_run.return_value = MagicMock(
            stdout=json.dumps({"sessionID": session_id, "response": "Success"}),
            stderr="",
            returncode=0
        )

        agent = RoleBasedOpencodeAgent(
            name=agent_name,
            memory_id=memory_id,
            model=model,
            start_heartbeat=False
        )

        self.assertEqual(agent.session_id, session_id)
        self.assertEqual(agent.llm_command, f"opencode -m {model} run -s {session_id}")
        self.mock_subprocess_run.assert_called_once_with(
            f"opencode -m {model} run --format json",
            shell=True,
            check=True,
            input=agent.role_prompt,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=None
        )

if __name__ == '__main__':
    unittest.main()
