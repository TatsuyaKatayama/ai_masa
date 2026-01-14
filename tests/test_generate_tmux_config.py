import unittest
import os
import yaml
import tempfile
import shutil
import shlex
from tools.generate_tmux_config import generate_config

class TestGenerateTmuxConfig(unittest.TestCase):

    def setUp(self):
        # Create a temporary directory to store mock config files
        self.test_dir = tempfile.mkdtemp()
        self.project_root = self.test_dir
        self.config_dir = os.path.join(self.test_dir, 'config')
        self.templates_dir = os.path.join(self.config_dir, 'templates')
        os.makedirs(self.templates_dir)

        # Mock agent_library.yml
        self.agent_library_path = os.path.join(self.config_dir, 'agent_library.yml')
        with open(self.agent_library_path, 'w') as f:
            yaml.dump({
                'user_proxy': {
                    'name': 'UserProxy',
                    'type': 'user_input_agent.UserInputAgent'
                },
                'coder': {
                    'name': 'Coder',
                    'type': 'role_based_gemini_cli_agent.RoleBasedGeminiCliAgent',
                    'user_lang': 'Japanese',
                    'role_prompt': 'You are a professional programmer.',
                    'working_dir': 'works/Coder/{project_name}',
                    'redis_db': 3
                },
                'foamer': {
                    'name': 'Foamer',
                    'type': 'role_based_gemini_cli_agent.RoleBasedGeminiCliAgent',
                    'user_lang': 'English',
                    'role_prompt': 'You are an expert OpenFOAM user.',
                    'llm_command': 'gemini -y --resume {session_id} --output-format json',
                    'working_dir': 'works/Foamer/{project_name}',
                    'redis_db': 1
                }
            }, f)

        # Mock team_library.yml
        self.team_library_path = os.path.join(self.config_dir, 'team_library.yml')
        with open(self.team_library_path, 'w') as f:
            yaml.dump({
                'test_team': ['user_proxy', 'coder', 'foamer']
            }, f)

        # Mock orchestration.yml.template
        self.template_path = os.path.join(self.templates_dir, 'orchestration.yml.template')
        with open(self.template_path, 'w') as f:
            f.write("name: ai_masa_orchestration\n")
            f.write("root: __PROJECT_ROOT__\n")
            f.write("windows:\n")
            f.write("  - agents:\n")
            f.write("      layout: tiled\n")
            f.write("      panes:\n")
            f.write("__USER_INPUT_LOGGING_PANES__\n")
            f.write("__SHELL_PANE__\n")
            f.write("__OTHER_AGENT_PANES__\n")
            
        # Mock venv path
        self.venv_path = os.path.join(self.test_dir, '.venv', 'bin', 'activate')
        os.makedirs(os.path.dirname(self.venv_path))
        with open(self.venv_path, 'w') as f:
            f.write("# mock venv activate\n")
            
        # Output path for the generated config
        self.output_path = os.path.join(self.test_dir, 'generated_config.yml')

    def tearDown(self):
        # Clean up the temporary directory
        shutil.rmtree(self.test_dir)

    def test_generate_config(self):
        # Run the config generation
        generate_config(
            team_name='test_team',
            ai_masa_project_root=self.project_root,
            tmuxinator_memory_root=self.project_root,
            venv_activate_path=self.venv_path,
            template_path=self.template_path,
            output_path=self.output_path,
            project_name='test_project',
            logging_level='INFO'
        )

        # Verify the output file exists
        self.assertTrue(os.path.exists(self.output_path))

        # Verify the content of the generated file
        with open(self.output_path, 'r') as f:
            content = f.read()

        # Check project root replacement
        self.assertIn(f"root: {self.project_root}", content)
        
        # Check for user_proxy pane
        self.assertIn("- user_proxy:", content)
        expected_user_proxy_command = shlex.join([
            "python", "-m", "ai_masa.agents.user_input_agent",
            "UserProxy",
            f"--memory_id", "UserProxy:test_project",
            f"--redis_db", "0",
            f"--working_dir", "works/UserProxy/test_project",
            f"--default_target_agent", "Coder",
            f"--logging_level", "INFO"
        ])
        self.assertIn(expected_user_proxy_command, content)

        # Check for coder pane (and its command details)
        self.assertIn("- coder:", content)
        expected_coder_command = shlex.join([
            "python", "-m", "ai_masa.agents.role_based_gemini_cli_agent",
            "Coder",
            "You are a professional programmer.", # Positional arg
            f"--memory_id", "Coder:test_project",
            f"--redis_db", "3",
            f"--working_dir", "works/Coder/test_project",
            f"--user_lang", "Japanese",
            f"--logging_level", "INFO", # Moved here
            f"--role_prompt", "You are a professional programmer."
        ])
        self.assertIn(expected_coder_command, content)

        # Check for foamer pane (and its command details including llm_command)
        self.assertIn("- foamer:", content)
        expected_foamer_command = shlex.join([
            "python", "-m", "ai_masa.agents.role_based_gemini_cli_agent",
            "Foamer",
            "You are an expert OpenFOAM user.", # Positional arg
            f"--memory_id", "Foamer:test_project",
            f"--redis_db", "1",
            f"--working_dir", "works/Foamer/test_project",
            f"--user_lang", "English",
            f"--logging_level", "INFO", # Moved here
            f"--role_prompt", "You are an expert OpenFOAM user.",
            f"--llm_command", "gemini -y --resume {session_id} --output-format json"
        ])
        self.assertIn(expected_foamer_command, content)


if __name__ == '__main__':
    unittest.main()
