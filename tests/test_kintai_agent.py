import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta

from ai_masa.agents.kintai_agent import KintaiAgent
from ai_masa.models.message import Message

class TestKintaiAgent(unittest.TestCase):

    def setUp(self):
        """Set up for each test case."""
        with patch('ai_masa.comms.redis_broker.RedisBroker'):
            self.agent = KintaiAgent(name="TestKintaiAgent", heartbeat_timeout=10)
            self.agent.broadcast = MagicMock()

    def test_initialization(self):
        """Test that the agent initializes correctly."""
        self.assertEqual(self.agent.name, "TestKintaiAgent")
        self.assertEqual(self.agent.heartbeat_timeout, timedelta(seconds=10))
        self.assertEqual(self.agent.active_agents, {})

    def test_handle_heartbeat_message(self):
        """Test that the agent correctly processes a heartbeat message."""
        # 正しいハートビートメッセージの形式に変更
        heartbeat_msg = Message(
            from_agent="Agent1", 
            to_agent="Agent1",  # to_agentは送信元自身
            content="heartbeat",
            cc_agents=["_broadcast_"]
        )
        
        mock_now = datetime(2025, 1, 1, 12, 0, 0)
        with patch('ai_masa.agents.kintai_agent.datetime') as mock_datetime:
            mock_datetime.now.return_value = mock_now
            
            self.agent._handle_message(heartbeat_msg)
            
            self.assertIn("Agent1", self.agent.active_agents)
            self.assertEqual(self.agent.active_agents["Agent1"], mock_now)

    def test_respond_to_any_message(self):
        """Test that the agent responds correctly to any message addressed to it."""
        self.agent.active_agents = {
            "Agent1": datetime(2025, 1, 1, 12, 0, 0),
            "Agent2": datetime(2025, 1, 1, 12, 0, 1)
        }
        
        query_msg = Message(from_agent="User", to_agent="TestKintaiAgent", content="Just a random message.")
        
        mock_now = datetime(2025, 1, 1, 12, 0, 10)
        with patch('ai_masa.agents.kintai_agent.datetime') as mock_datetime:
            mock_datetime.now.return_value = mock_now
            self.agent._handle_message(query_msg)
        
        self.agent.broadcast.assert_called_once()
        sent_args = self.agent.broadcast.call_args.kwargs
        
        self.assertEqual(sent_args['target'], "User")
        
        expected_agents = sorted(["Agent1", "Agent2", "TestKintaiAgent"])
        expected_content = f"I am {self.agent.name}, a bot. The following agents are currently active:\n- " + "\n- ".join(expected_agents)
        self.assertEqual(sent_args['content'], expected_content)

    def test_cleanup_inactive_agents(self):
        """Test that inactive agents are correctly removed from the list."""
        mock_now = datetime(2025, 1, 1, 12, 0, 15)
        
        with patch('ai_masa.agents.kintai_agent.datetime') as mock_datetime:
            mock_datetime.now.return_value = mock_now
            
            self.agent.active_agents = {
                "ActiveAgent": datetime(2025, 1, 1, 12, 0, 10),
                "InactiveAgent": datetime(2025, 1, 1, 12, 0, 0),
                self.agent.name: datetime(2025, 1, 1, 12, 0, 0)
            }
            
            self.agent._cleanup_inactive_agents()
            
            self.assertIn("ActiveAgent", self.agent.active_agents)
            self.assertIn(self.agent.name, self.agent.active_agents)
            self.assertNotIn("InactiveAgent", self.agent.active_agents)

if __name__ == '__main__':
    unittest.main()