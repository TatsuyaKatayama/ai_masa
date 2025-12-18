import unittest
import os
import sys
import json
import yaml
import tempfile
import shutil
import shlex
from unittest.mock import patch, MagicMock, call

# Add the ai_masa directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ai_masa.agents.base_agent import BaseAgent
from ai_masa.agents.gemini_cli_agent import GeminiCliAgent
from ai_masa.agents.role_based_gemini_cli_agent import RoleBasedGeminiCliAgent
from ai_masa.models.message import Message

class TestFoamerAgentResponse(unittest.TestCase):

    def setUp(self):
        # Create a temporary directory for WM_PROJECT_DIR
        self.temp_wm_project_dir = tempfile.mkdtemp()
        os.environ['WM_PROJECT_DIR'] = self.temp_wm_project_dir

        # Create a dummy OpenFOAM tutorial directory inside temp_wm_project_dir
        # This is to ensure that the include-directories flag has a valid path to include
        self.dummy_tutorial_path = os.path.join(self.temp_wm_project_dir, 'tutorials', 'incompressible', 'simpleFoam', 'cavity')
        os.makedirs(self.dummy_tutorial_path, exist_ok=True)
        os.makedirs(os.path.join(self.dummy_tutorial_path, '0'), exist_ok=True) # Create '0' directory
        with open(os.path.join(self.dummy_tutorial_path, '0/U'), 'w') as f:
            f.write('FoamFile { version 2.0; format ascii; class volVectorField; object U; } dimensions [0 1 -1 0 0 0 0]; boundaryField {};')

        # Load agent library configuration
        config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'config', 'agent_library.yml.default'))
        with open(config_path, 'r') as f:
            self.agent_configs = yaml.safe_load(f)

        # datetime.now()をモックして、プロンプト内のタイムスタンプを固定する
        self.mock_datetime_patcher = patch('datetime.datetime')
        mock_dt = self.mock_datetime_patcher.start()
        mock_dt.now.return_value.isoformat.return_value = "2025-12-04T00:00:00.000000"

    def tearDown(self):
        # Clean up the temporary directory
        if os.path.exists(self.temp_wm_project_dir):
            shutil.rmtree(self.temp_wm_project_dir)
        del os.environ['WM_PROJECT_DIR']
        self.mock_datetime_patcher.stop()

    @patch('subprocess.run')
    @patch('ai_masa.agents.base_agent.RedisBroker')
    def test_foamer_agent_session_and_response(self, MockRedisBroker, mock_subprocess_run):
        mock_broker_instance = MockRedisBroker.return_value

        # Mock subprocess.run for session creation and LLM invocation
        session_create_output = "session-12345"
        llm_response_content = "As an OpenFOAM expert, I confirm that a+b=3. I have checked the cavity tutorial."
        llm_json_response = json.dumps({"to_agent": "User", "content": llm_response_content})

        mock_subprocess_run.side_effect = [
            # First call: gemini --list-sessions
            MagicMock(args=unittest.mock.ANY, returncode=0, stdout="No sessions found.\n", stderr=""),
            # Second call: _create_llm_session for foamer (gemini {role_prompt})
            MagicMock(args=unittest.mock.ANY, returncode=0, stdout="", stderr=""),
            # Third call: _invoke_llm (gemini -y --resume {session_id} ...)
            MagicMock(args=unittest.mock.ANY, returncode=0, stdout=llm_json_response, stderr="")
        ]

        # Get foamer agent config
        foamer_config = self.agent_configs['foamer']
        agent_type = foamer_config.pop('type').split('.')[-1]
        
        # Dynamically get the agent class (RoleBasedGeminiCliAgent)
        agent_class = globals()[agent_type]

        # Instantiate the agent
        foamer_agent = agent_class(
            **foamer_config,
            start_heartbeat=False,
            redis_host='localhost', # Default redis host for testing
            working_dir=self.temp_wm_project_dir # Pass the temporary directory
        )
        
        # Simulate an incoming message for the agent
        trigger_message = Message(from_agent="User", to_agent="Foamer", content="If a=1 and b=2, what is a+b? Check the cavity tutorial.", job_id="job-foamer-1")
        foamer_agent._on_message_received(trigger_message.to_json())

        # Assertions
        # 1. subprocess.run was called for session creation (once for _create_llm_session, once for _invoke_llm)
        self.assertEqual(mock_subprocess_run.call_count, 3)

        # Check the call for session creation (second call in side_effect)
        create_session_call_args = mock_subprocess_run.call_args_list[1].args[0]
        self.assertIn('gemini', create_session_call_args)
        self.assertNotIn('--resume', create_session_call_args) # Should not have --resume for new session creation
        self.assertIn(shlex.quote(foamer_agent.role_prompt), create_session_call_args) # Role prompt should be present
        self.assertIn(f"--include-directories {self.temp_wm_project_dir}", create_session_call_args) # Check WM_PROJECT_DIR

        # Check the call for LLM invocation (third call in side_effect)
        llm_invoke_call_args = mock_subprocess_run.call_args_list[2].args[0]
        self.assertIn('gemini', llm_invoke_call_args)
        self.assertIn('--resume 1', llm_invoke_call_args) # Should use --resume 1 (first session)
        self.assertIn(f"--include-directories {self.temp_wm_project_dir}", llm_invoke_call_args) # Check WM_PROJECT_DIR
        self.assertIn('--output-format json', llm_invoke_call_args)

        # 2. Agent registered the session ID
        self.assertIn('job-foamer-1', foamer_agent.job_sessions)
        self.assertEqual(foamer_agent.job_sessions['job-foamer-1'], '1') # Expecting session index 1

        # 3. Agent published a response
        mock_broker_instance.publish.assert_called_once()
        published_message = Message.from_json(mock_broker_instance.publish.call_args[0][0])
        self.assertEqual(published_message.from_agent, foamer_agent.name)
        self.assertEqual(published_message.to_agent, "User")
        self.assertIn("3", published_message.content) # Check if the content contains the expected result
        self.assertIn("cavity tutorial", published_message.content) # Ensure content from included dir is conceptually present

if __name__ == '__main__':
    unittest.main()