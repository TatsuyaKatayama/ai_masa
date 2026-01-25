import unittest
from unittest.mock import patch
import sys
from io import StringIO
import json
import os
import shutil
import tempfile

from ai_masa.agents.logging_agent import LoggingAgent
from ai_masa.models.message import Message

class TestLoggingAgent(unittest.TestCase):

    def setUp(self):
        """Set up mocks and agent instance for each test case."""
        self.test_dir = tempfile.mkdtemp()
        self.mock_broker_patcher = patch('ai_masa.agents.base_agent.RedisBroker')
        self.mock_memory_manager_patcher = patch('ai_masa.agents.base_agent.MemoryManager')
        self.mock_base_agent_start_heartbeat_patcher = patch('ai_masa.agents.base_agent.BaseAgent._start_heartbeat')
        self.mock_stdout_patcher = patch('sys.stdout', new_callable=StringIO)

        self.MockRedisBroker = self.mock_broker_patcher.start()
        self.MockMemoryManager = self.mock_memory_manager_patcher.start()
        self.mock_base_agent_start_heartbeat = self.mock_base_agent_start_heartbeat_patcher.start()
        self.mock_stdout = self.mock_stdout_patcher.start()

        self.mock_broker_instance = self.MockRedisBroker.return_value
        self.mock_memory_manager_instance = self.MockMemoryManager.return_value

        self.agent = LoggingAgent(
            name="TestLogger",
            description="An agent that logs all messages.",
            memory_id="TestLogger:test_project", # 必須となったmemory_idを渡す
            memory_manager=self.mock_memory_manager_instance, # モックを渡す
            working_dir=self.test_dir
        )

    def tearDown(self):
        """Stop all patchers and clean up the test directory."""
        shutil.rmtree(self.test_dir)
        self.mock_broker_patcher.stop()
        self.mock_memory_manager_patcher.stop()
        self.mock_base_agent_start_heartbeat_patcher.stop()
        self.mock_stdout_patcher.stop()
        sys.stdout = sys.__stdout__ # stdoutを元に戻す

    def test_logs_to_file_correctly(self):
        """
        Test that a message is logged to a file in JSONL format correctly.
        """
        msg_dict = {
            "from_agent": "FileAgent",
            "to_agent": "FileTester",
            "content": "Log this to a file.",
            "job_id": "file-log-job-123"
        }
        msg = Message(**msg_dict)
        msg_json = msg.to_json()

        # Receive the message
        self.agent._on_message_received(msg_json)

        # Check if the log file was created and contains the correct content
        log_file_path = os.path.join(self.test_dir, "logs", f"{msg.job_id}.jsonl")
        self.assertTrue(os.path.exists(log_file_path))

        with open(log_file_path, 'r', encoding='utf-8') as f:
            line = f.readline()
            logged_msg_dict = json.loads(line)
            
            # Compare the relevant fields
            self.assertEqual(logged_msg_dict['from_agent'], msg_dict['from_agent'])
            self.assertEqual(logged_msg_dict['to_agent'], msg_dict['to_agent'])
            self.assertEqual(logged_msg_dict['content'], msg_dict['content'])
            self.assertEqual(logged_msg_dict['job_id'], msg_dict['job_id'])

    @patch('ai_masa.agents.logging_agent.datetime')
    def test_logs_standard_message(self, mock_datetime):
        """
        Test that a standard message is logged correctly.
        """
        # Clear stdout from setup
        self.mock_stdout.truncate(0)
        self.mock_stdout.seek(0)
        
        mock_datetime.now.return_value.strftime.return_value = "2025-01-01 12:00:00"
        
        msg = Message(
            from_agent="AgentA",
            to_agent="AgentB",
            content="Hello World",
            job_id="job-123"
        ).to_json()
        
        self.agent._on_message_received(msg)
        
        output = self.mock_stdout.getvalue()
        expected_log = "[2025-01-01 12:00:00][job-123] AgentA -> AgentB: Hello World\n"
        self.assertEqual(output, expected_log) # Use assertEqual for exact match

        # Message is not for the logger, so it should not be added to its memory history
        self.mock_memory_manager_instance.add_message.assert_not_called()


    @patch('ai_masa.agents.logging_agent.datetime')
    def test_logs_message_with_cc(self, mock_datetime):
        """
        Test that a message with CC is logged correctly.
        """
        # Clear stdout from setup
        self.mock_stdout.truncate(0)
        self.mock_stdout.seek(0)

        mock_datetime.now.return_value.strftime.return_value = "2025-01-01 12:01:00"
        
        msg = Message(
            from_agent="AgentA",
            to_agent="AgentB",
            content="FYI",
            job_id="job-456",
            cc_agents=["AgentC", "TestLogger"] # Logger自身をCCに含める
        ).to_json()
        
        self.agent._on_message_received(msg)
        
        output = self.mock_stdout.getvalue()
        expected_log = "[2025-01-01 12:01:00][job-456] AgentA -> AgentB (CC: AgentC, TestLogger): FYI\n"
        self.assertEqual(output, expected_log) # Use assertEqual for exact match
        
        # BaseAgentのロジックにより、CCされたメッセージは履歴に追加される
        self.mock_memory_manager_instance.add_message.assert_called_once()

    def test_ignores_heartbeat_message(self):
        """
        Test that heartbeat messages are not logged.
        """
        # Clear stdout from setup
        self.mock_stdout.truncate(0)
        self.mock_stdout.seek(0)
        
        msg = Message(
            from_agent="AgentA",
            to_agent="AgentA",
            content="heartbeat",
            job_id="_system_",
            cc_agents=["_broadcast_", "TestLogger"]
        ).to_json()
        
        self.agent._on_message_received(msg)
        
        output = self.mock_stdout.getvalue()
        # 何もprintされないことを確認
        self.assertEqual(output.strip(), "")
        
        # BaseAgentのロジックにより、CCされたメッセージは履歴に追加される
        self.mock_memory_manager_instance.add_message.assert_called_once()


if __name__ == '__main__':
    unittest.main()
