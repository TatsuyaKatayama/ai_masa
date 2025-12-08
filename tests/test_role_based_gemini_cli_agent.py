import unittest
from unittest.mock import patch, MagicMock
from ai_masa.agents.role_based_gemini_cli_agent import RoleBasedGeminiCliAgent

class TestRoleBasedGeminiCliAgent(unittest.TestCase):

    @patch('subprocess.run') # Mock subprocess.run to prevent actual command execution
    def test_instantiation_with_role_prompt(self, mock_subprocess_run):
        """
        Test that RoleBasedGeminiCliAgent can be instantiated with a role_prompt,
        and that the prompt is correctly assigned and included in the agent's full role_prompt.
        """
        # Configure the mock to return a successful result for gemini --list-sessions etc.
        mock_subprocess_run.return_value = MagicMock(stdout="", stderr="", returncode=0)

        agent_name = "TestRoleCliAgent"
        role_prompt_text = "You are a test CLI agent."
        
        # Instantiate the agent, ensuring start_heartbeat is False for tests
        agent = RoleBasedGeminiCliAgent(
            name=agent_name,
            role_prompt=role_prompt_text,
            start_heartbeat=False
        )
        
        # Check if the name is set correctly
        self.assertEqual(agent.name, agent_name)
        
        # Check if the original role_prompt_text is included in the full prompt
        # (as BaseAgent modifies the description/role_prompt)
        self.assertIn(role_prompt_text, agent.role_prompt)
        
        # Verify that the llm_command is set by GeminiCliAgent's init
        self.assertIsNotNone(agent.llm_command)
        self.assertIn("gemini", agent.llm_command)

if __name__ == '__main__':
    unittest.main()
