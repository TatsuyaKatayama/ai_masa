import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta
import json

from ai_masa.agents.kintai_agent import KintaiAgent
from ai_masa.models.message import Message

class TestKintaiAgent(unittest.TestCase):

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

        self.agent = KintaiAgent(
            name="TestKintaiAgent",
            description="An agent that tracks active agents via heartbeats.",
            memory_id="project-TestKintaiAgent", # 必須となったmemory_idを渡す
            memory_manager=self.mock_memory_manager_instance, # モックを渡す
            heartbeat_timeout=10
        )

    def tearDown(self):
        """Stop all patchers."""
        self.mock_broker_patcher.stop()
        self.mock_memory_manager_patcher.stop()
        self.mock_base_agent_start_heartbeat_patcher.stop()

    def test_initialization(self):
        """Test that the agent initializes correctly."""
        self.assertEqual(self.agent.name, "TestKintaiAgent")
        self.assertEqual(self.agent.heartbeat_timeout, timedelta(seconds=10))
        self.assertEqual(self.agent.active_agents, {})
        self.assertEqual(self.agent.memory_id, "project-TestKintaiAgent")

    @patch('ai_masa.agents.kintai_agent.datetime')
    def test_on_message_received_heartbeat_updates_active_agents(self, mock_datetime):
        """
        KintaiAgentがCCされたハートビートメッセージを受信した際、
        active_agentsリストを更新し、自身の履歴にメッセージを保存することを確認。
        """
        mock_now = datetime(2025, 1, 1, 12, 0, 0)
        mock_datetime.now.return_value = mock_now

        heartbeat_msg = Message(
            from_agent="Agent1", 
            to_agent="Agent1",
            content="heartbeat",
            cc_agents=["_broadcast_", "TestKintaiAgent"], # KintaiAgent自身もCCに含める
            job_id="_system_"
        ).to_json()
        
        self.agent._on_message_received(heartbeat_msg)
            
        self.assertIn("Agent1", self.agent.active_agents)
        self.assertEqual(self.agent.active_agents["Agent1"], mock_now)
        
        # BaseAgentの_on_message_receivedにより、CCされたメッセージは自身の履歴に追加される
        heartbeat_msg_dict = json.loads(heartbeat_msg)
        self.mock_memory_manager_instance.add_message.assert_called_once() # 受信したハートビート
        call_args = self.mock_memory_manager_instance.add_message.call_args[0]
        self.assertEqual(call_args[0], "project-TestKintaiAgent")
        # message_idとtimestampは動的に生成されるため、ANYでマッチさせる
        call_args[1].pop('message_id')
        call_args[1].pop('timestamp')
        heartbeat_msg_dict.pop('message_id')
        heartbeat_msg_dict.pop('timestamp')
        self.assertEqual(call_args[1], heartbeat_msg_dict)


    @patch('ai_masa.agents.kintai_agent.datetime')
    def test_on_message_received_query_responds(self, mock_datetime):
        """
        KintaiAgentが自分宛の問い合わせメッセージを受信した際に、
        active_agentsリストを送信することを確認。
        """
        mock_now = datetime(2025, 1, 1, 12, 0, 10)
        mock_datetime.now.return_value = mock_now
        
        self.agent.active_agents = {
            "Agent1": datetime(2025, 1, 1, 12, 0, 0),
            "Agent2": datetime(2025, 1, 1, 12, 0, 1)
        }
        
        query_msg = Message(from_agent="User", to_agent="TestKintaiAgent", content="Status request.", job_id="query-1").to_json()
        
        self.agent._on_message_received(query_msg)
        
        self.mock_broker_instance.publish.assert_called_once()
        sent_args_json = self.mock_broker_instance.publish.call_args[0][0]
        sent_msg = json.loads(sent_args_json)

        self.assertEqual(sent_msg['to_agent'], "User")
        
        expected_agents = sorted(["Agent1", "Agent2", "TestKintaiAgent"])
        expected_content = f"I am {self.agent.name}, a bot. The following agents are currently active:\n- " + "\n- ".join(expected_agents)
        self.assertEqual(sent_msg['content'], expected_content)

        # 受信した問い合わせメッセージが自身の履歴に追加されたことを確認
        query_msg_dict = json.loads(query_msg)
        self.mock_memory_manager_instance.add_message.assert_any_call("project-TestKintaiAgent", query_msg_dict)
        # 送信した応答メッセージも自身の履歴に追加されたことを確認
        self.mock_memory_manager_instance.add_message.assert_any_call(
            "project-TestKintaiAgent", 
            unittest.mock.ANY # ここは動的に生成されるメッセージなのでANYで対応
        )
        # add_messageが計2回呼ばれたことを確認 (受信と送信)
        self.assertEqual(self.mock_memory_manager_instance.add_message.call_count, 2)


    @patch('ai_masa.agents.kintai_agent.datetime')
    def test_cleanup_inactive_agents(self, mock_datetime):
        """
        Test that inactive agents are correctly removed from the list.
        """
        mock_now = datetime(2025, 1, 1, 12, 0, 15)
        mock_datetime.now.return_value = mock_now
            
        self.agent.active_agents = {
            "ActiveAgent": datetime(2025, 1, 1, 12, 0, 10),
            "InactiveAgent": datetime(2025, 1, 1, 12, 0, 0),
            self.agent.name: datetime(2025, 1, 1, 12, 0, 0) # KintaiAgent自身はタイムアウト対象外
        }
            
        self.agent._cleanup_inactive_agents()
            
        self.assertIn("ActiveAgent", self.agent.active_agents)
        self.assertIn(self.agent.name, self.agent.active_agents)
        self.assertNotIn("InactiveAgent", self.agent.active_agents)

    def test_on_message_received_ignores_irrelevant_messages(self):
        """
        KintaiAgentが自分宛でないメッセージを無視することを確認。
        """
        irrelevant_msg = Message("User", "AnotherAgent", "Irrelevant content.", job_id="irrelevant-1").to_json()
        self.agent._on_message_received(irrelevant_msg)
        
        # BaseAgentの_is_message_for_meでフィルタリングされるため、active_agentsは更新されない
        self.assertEqual(len(self.agent.active_agents), 0)
        # BaseAgentのadd_messageも呼ばれない
        self.mock_memory_manager_instance.add_message.assert_not_called()
        # broadcastも呼ばれない
        self.mock_broker_instance.publish.assert_not_called()


if __name__ == '__main__':
    unittest.main()
