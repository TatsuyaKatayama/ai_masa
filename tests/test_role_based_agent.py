import unittest
from ai_masa.agents.role_based_agent import RoleBasedAgent

class TestRoleBasedAgent(unittest.TestCase):

    def test_instantiation_with_role_prompt(self):
        """
        Test that RoleBasedAgent can be instantiated with a role_prompt,
        and that the prompt is correctly assigned to the agent's description.
        """
        agent_name = "TestRoleAgent"
        role_prompt_text = "You are a test agent."
        
        # Instantiate the agent
        agent = RoleBasedAgent(
            name=agent_name,
            role_prompt=role_prompt_text,
            start_heartbeat=False
        )
        
        # Check if the name is set correctly
        self.assertEqual(agent.name, agent_name)
        
        # Check if the original role_prompt_text is included in the full prompt
        self.assertIn(role_prompt_text, agent.role_prompt)

if __name__ == '__main__':
    unittest.main()
