import unittest
from unittest.mock import patch, MagicMock
import json
import subprocess

from ai_masa.agents.role_based_gemini_cli_agent import RoleBasedGeminiCliAgent

class TestRoleBasedGeminiCliAgent(unittest.TestCase):

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
        
        # subprocess.runのデフォルトの戻り値を設定
        self.mock_subprocess_run.return_value = MagicMock(stdout="", stderr="", returncode=0)

    def tearDown(self):
        """Stop all patchers."""
        self.mock_broker_patcher.stop()
        self.mock_memory_manager_patcher.stop()
        self.mock_subprocess_patcher.stop()
        self.mock_base_agent_start_heartbeat_patcher.stop()

    def test_instantiation_with_role_prompt(self):
        """
        Test that RoleBasedGeminiCliAgent can be instantiated with a role_prompt.
        """
        agent_name = "TestRoleCliAgent"
        description_text = "A test CLI agent."
        role_prompt_text = "You are a test CLI agent." # This will be stored but not used in the main prompt
        memory_id = f"project-{agent_name}"
        
        agent = RoleBasedGeminiCliAgent(
            name=agent_name,
            description=description_text,
            role_prompt=role_prompt_text,
            memory_id=memory_id,
            memory_manager=self.mock_memory_manager_instance,
            start_heartbeat=False
        )
        
        self.assertEqual(agent.name, agent_name)
        self.assertEqual(agent.description, description_text) # description should be prioritized
        self.assertEqual(agent.role_prompt_content, role_prompt_text)
        self.assertIn(description_text, agent.role_prompt) # The final prompt should contain the description
        self.assertNotIn(role_prompt_text, agent.role_prompt) # but not the role_prompt text
        self.assertIn("gemini", agent.llm_command)
        self.assertEqual(agent.memory_id, memory_id)

    def test_instantiation_with_custom_llm_command(self):
        """
        Test that RoleBasedGeminiCliAgent can be instantiated with a custom llm_command.
        """
        agent_name = "TestCustomLlmAgent"
        description_text = "An agent with a custom LLM command."
        role_prompt_text = "You are an agent with a custom LLM command."
        custom_llm_command = "my_custom_llm_cli --model custom-model --param value"
        memory_id = f"project-{agent_name}"
        
        agent = RoleBasedGeminiCliAgent(
            name=agent_name,
            description=description_text,
            role_prompt=role_prompt_text,
            llm_command=custom_llm_command,
            memory_id=memory_id,
            memory_manager=self.mock_memory_manager_instance,
            start_heartbeat=False
        )

        self.assertEqual(agent.name, agent_name)
        self.assertEqual(agent.description, description_text)
        self.assertEqual(agent.role_prompt_content, role_prompt_text)
        self.assertIn(description_text, agent.role_prompt)
        self.assertNotIn(role_prompt_text, agent.role_prompt)
        self.assertEqual(agent.llm_command, custom_llm_command)
        self.assertEqual(agent.memory_id, memory_id)

    def test_instantiation_without_explicit_description_uses_role_prompt(self):
        """
        Test that if no explicit description is given, role_prompt is used as description.
        """
        agent_name = "TestRoleCliAgentNoDesc"
        role_prompt_text = "Only role prompt provided."
        memory_id = f"project-{agent_name}"

        agent = RoleBasedGeminiCliAgent(
            name=agent_name,
            role_prompt=role_prompt_text,
            memory_id=memory_id,
            memory_manager=self.mock_memory_manager_instance,
            start_heartbeat=False
        )

        self.assertEqual(agent.description, role_prompt_text)
        self.assertIn(role_prompt_text, agent.role_prompt)
        self.assertEqual(agent.role_prompt_content, role_prompt_text)

    def test_instantiation_without_any_description_or_role_prompt_uses_default(self):
        """
        Test that if neither description nor role_prompt is given, a default is used.
        """
        agent_name = "TestRoleCliAgentDefaultDesc"
        memory_id = f"project-{agent_name}"

        agent = RoleBasedGeminiCliAgent(
            name=agent_name,
            memory_id=memory_id,
            memory_manager=self.mock_memory_manager_instance,
            start_heartbeat=False
        )

        self.assertEqual(agent.description, "A role-based Gemini CLI agent.")
        self.assertIn("A role-based Gemini CLI agent.", agent.role_prompt)
        self.assertIsNone(agent.role_prompt_content)

if __name__ == '__main__':
    unittest.main()
