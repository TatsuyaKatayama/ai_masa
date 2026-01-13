import unittest
from unittest.mock import patch
import sys
from io import StringIO
import json

from ai_masa.agents.logging_agent import LoggingAgent
from ai_masa.models.message import Message

class TestLoggingAgent(unittest.TestCase):

    def setUp(self):
        """Set up mocks and agent instance for each test case."""
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
            memory_id="project-TestLogger", # 必須となったmemory_idを渡す
            memory_manager=self.mock_memory_manager_instance # モックを渡す
        )

    def tearDown(self):
        """Stop all patchers."""
        self.mock_broker_patcher.stop()
        self.mock_memory_manager_patcher.stop()
        self.mock_base_agent_start_heartbeat_patcher.stop()
        self.mock_stdout_patcher.stop()
        sys.stdout = sys.__stdout__ # stdoutを元に戻す

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
