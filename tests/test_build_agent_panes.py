import unittest
import os
import yaml
import sys
from unittest.mock import patch, MagicMock

# Import the function to be tested
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'tools'))
from build_agent_panes import build_agent_panes

class TestBuildAgentPanes(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None  # Show full diff for assertion errors
        self.test_dir = os.path.join(os.path.dirname(__file__), 'test_data')
        os.makedirs(os.path.join(self.test_dir, 'config'), exist_ok=True)
        os.makedirs(os.path.join(self.test_dir, 'logs'), exist_ok=True)

        self.project_root = self.test_dir
        self.venv_activate_path = os.path.join(self.project_root, '.venv', 'bin', 'activate')

        # Mock agent_library.yml
        self.agent_library_path = os.path.join(self.project_root, 'config', 'agent_library.yml')
        self.agent_library_content = {
            'user_input': {'type': 'user_input_agent.UserInputAgent', 'name': 'User', 'user_lang': 'Japanese'},
            'gemini_cli': {'type': 'gemini_cli_agent.GeminiCliAgent', 'name': 'GeminiCliAgent', 'user_lang': 'English'},
            'team_manager': {'type': 'role_based_gemini_cli_agent.RoleBasedGeminiCliAgent', 'name': 'TeamManager', 'role_prompt': 'You are a manager.', 'user_lang': 'Japanese'},
            'calculator': {'type': 'role_based_gemini_cli_agent.RoleBasedGeminiCliAgent', 'name': 'Calculator', 'role_prompt': 'You are a calculator.', 'user_lang': 'English'},
        }
        with open(self.agent_library_path, 'w') as f:
            yaml.dump(self.agent_library_content, f)

        # Mock team_library.yml
        self.team_library_path = os.path.join(self.project_root, 'config', 'team_library.yml')
        self.team_library_content = {
            'default_team': ['user_input', 'gemini_cli'],
            'analysis_team': ['user_input', 'team_manager', 'calculator'],
        }
        with open(self.team_library_path, 'w') as f:
            yaml.dump(self.team_library_content, f)

    def tearDown(self):
        # Clean up created files and directories
        if os.path.exists(self.test_dir):
            import shutil
            shutil.rmtree(self.test_dir)

    def test_default_team_panes_generation(self):
        pass

    def test_analysis_team_panes_generation(self):
        expected_output = f"""        - shell:
            - source {self.venv_activate_path}
            - # Generic shell pane
        - user_input:
            - source {self.venv_activate_path}
            - python -m ai_masa.agents.user_input_agent User Japanese
        - team_manager:
            - source {self.venv_activate_path}
            - mkdir -p {os.path.join(self.project_root, 'logs')} && python -m ai_masa.agents.role_based_gemini_cli_agent TeamManager Japanese --role_prompt 'You are a manager.' > {os.path.join(self.project_root, 'logs', 'TeamManager.log')} 2>&1
        - calculator:
            - source {self.venv_activate_path}
            - mkdir -p {os.path.join(self.project_root, 'logs')} && python -m ai_masa.agents.role_based_gemini_cli_agent Calculator English --role_prompt 'You are a calculator.' > {os.path.join(self.project_root, 'logs', 'Calculator.log')} 2>&1"""
        result = build_agent_panes('analysis_team', self.project_root, self.venv_activate_path)
        self.assertEqual(result, expected_output)

    @patch('sys.exit')
    @patch('builtins.print')
    def test_unknown_team_name_error(self, mock_print, mock_exit):
        build_agent_panes('unknown_team', self.project_root, self.venv_activate_path)
        mock_exit.assert_called_with(1)
        mock_print.assert_any_call(unittest.mock.ANY, file=sys.stderr) # Check if error message is printed to stderr

    @patch('sys.exit')
    @patch('builtins.print')
    def test_unknown_agent_in_team_error(self, mock_print, mock_exit):
        # Temporarily modify team_library_content to include an unknown agent
        self.team_library_content['bad_team'] = ['user_input', 'non_existent_agent']
        with open(self.team_library_path, 'w') as f:
            yaml.dump(self.team_library_content, f)

        build_agent_panes('bad_team', self.project_root, self.venv_activate_path)
        mock_exit.assert_called_with(1)
        mock_print.assert_any_call(unittest.mock.ANY, file=sys.stderr) # Check if error message is printed to stderr

if __name__ == '__main__':
    unittest.main()
