import unittest
from unittest.mock import MagicMock, patch

from ai_masa.agents.role_based_agent import RoleBasedAgent

class TestRoleBasedAgent(unittest.TestCase):

    def setUp(self):
        """Set up mocks and agent instance for each test case."""
        self.mock_broker_patcher = patch('ai_masa.agents.base_agent.RedisBroker')
        self.mock_memory_manager_patcher = patch('ai_masa.agents.base_agent.MemoryManager')
        self.mock_base_agent_start_heartbeat_patcher = patch('ai_masa.agents.base_agent.BaseAgent._start_heartbeat')

        self.MockRedisBroker = self.mock_broker_patcher.start()
        self.MockMemoryManager = self.mock_memory_manager_patcher.start()
        self.mock_base_agent_start_heartbeat = self.mock_base_agent_start_heartbeat_patcher.start()

        self.mock_broker_instance = self.MockRedisBroker.return_value
        self.mock_memory_manager_instance = self.MockMemoryManager.return_value

    def tearDown(self):
        """Stop all patchers."""
        self.mock_broker_patcher.stop()
        self.mock_memory_manager_patcher.stop()
        self.mock_base_agent_start_heartbeat_patcher.stop()

    def test_instantiation_with_role_prompt_and_description(self):
        """
        Test that when both description and role_prompt are provided,
        description takes precedence for the base prompt, but role_prompt is still stored.
        """
        agent_name = "TestRoleAgent"
        description_text = "Specific description"
        role_prompt_text = "You are a test agent."
        memory_id = f"{agent_name}:test_project"
        
        agent = RoleBasedAgent(
            name=agent_name,
            description=description_text,
            role_prompt=role_prompt_text,
            memory_id=memory_id,
            memory_manager=self.mock_memory_manager_instance
        )
        
        self.assertEqual(agent.name, agent_name)
        
        # BaseAgentのdescriptionには、明示的に渡したdescriptionが使われることを確認
        self.assertEqual(agent.description, description_text)
        
        # BaseAgentの_generate_role_promptが作るプロンプトに、description_textが含まれることを確認
        self.assertIn(description_text, agent.role_prompt)
        # 逆に、role_prompt_textは含まれないことを確認
        self.assertNotIn(role_prompt_text, agent.role_prompt)

        # role_prompt_contentにはrole_promptが正しく保存されていることを確認
        self.assertEqual(agent.role_prompt_content, role_prompt_text)

    def test_instantiation_without_explicit_description_uses_role_prompt_as_description(self):
        """
        Test that if no explicit description is given, role_prompt is used as description.
        """
        agent_name = "TestRoleAgent2"
        role_prompt_text = "Another test role."
        memory_id = f"{agent_name}:test_project"

        agent = RoleBasedAgent(
            name=agent_name,
            role_prompt=role_prompt_text,
            memory_id=memory_id,
            memory_manager=self.mock_memory_manager_instance
        )

        self.assertEqual(agent.description, role_prompt_text)
        self.assertEqual(agent.role_prompt_content, role_prompt_text)

    def test_instantiation_without_role_prompt_uses_default_description(self):
        """
        Test that if neither description nor role_prompt is given, a default description is used.
        """
        agent_name = "TestRoleAgent3"
        memory_id = f"{agent_name}:test_project"

        agent = RoleBasedAgent(
            name=agent_name,
            memory_id=memory_id,
            memory_manager=self.mock_memory_manager_instance
        )

        self.assertEqual(agent.description, "A role-based agent.")
        self.assertIsNone(agent.role_prompt_content)

if __name__ == '__main__':
    unittest.main()
