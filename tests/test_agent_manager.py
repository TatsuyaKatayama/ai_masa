import unittest
from unittest.mock import MagicMock, patch, call
import time
import sys
from io import StringIO

# ai_masaモジュールをインポート可能にする
sys.path.insert(0, '.')

from ai_masa.agents.base_agent import BaseAgent
from ai_masa.agents.agent_manager import AgentManager
from ai_masa.models.message import Message

class TestAgentManagerAndHeartbeat(unittest.TestCase):

    def setUp(self):
        # 標準出力をモック
        self.mock_stdout = StringIO()
        sys.stdout = self.mock_stdout

        # AgentManagerが監視スレッドを自動で開始しないようにモック化
        patcher = patch('ai_masa.agents.agent_manager.AgentManager._start_monitoring')
        self.mock_start_monitoring = patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        # テストで使用したエージェントをシャットダウンする
        if hasattr(self, 'agent') and self.agent:
            self.agent.shutdown()
        if hasattr(self, 'manager') and self.manager:
            self.manager.shutdown()
        sys.stdout = sys.__stdout__

    @patch('ai_masa.agents.base_agent.RedisBroker')
    @patch('threading.Timer')
    def test_base_agent_heartbeat(self, MockTimer, MockRedisBroker):
        """BaseAgentが定期的にハートビートを送信するかテスト"""
        mock_broker_instance = MockRedisBroker.return_value
        
        self.agent = BaseAgent(name="TestAgent", description="A test agent")
        
        # _send_heartbeatが一度すぐに呼ばれることを確認
        time.sleep(0.1) # ハートビートが非同期で呼ばれるのを少し待つ
        mock_broker_instance.publish.assert_called()
        
        # publishされたメッセージがハートビートメッセージであることを確認
        last_call_args = mock_broker_instance.publish.call_args[0][0]
        msg = Message.from_json(last_call_args)
        self.assertEqual(msg.from_agent, "TestAgent")
        self.assertEqual(msg.to_agent, "TestAgent")
        self.assertEqual(msg.content, "heartbeat")
        self.assertIn("_broadcast_", msg.cc_agents)
        
        # Timerが30秒後に_send_heartbeatを再度呼び出すようにスケジュールされることを確認
        MockTimer.assert_called_with(30, self.agent._send_heartbeat)

    @patch('ai_masa.agents.base_agent.RedisBroker')
    def test_agent_manager_detects_new_agent(self, MockRedisBroker):
        """AgentManagerが新しいエージェントを検出するかテスト"""
        self.manager = AgentManager()
        
        heartbeat_msg = Message(
            from_agent="NewAgent", 
            to_agent="NewAgent", 
            content="heartbeat", 
            cc_agents=["_broadcast_"]
        ).to_json()
        
        # マネージャーにハートビートメッセージを直接渡す
        self.manager._on_message_received(heartbeat_msg)
        
        self.assertIn("NewAgent", self.manager.active_agents)
        output = self.mock_stdout.getvalue()
        self.assertIn("✅ New agent detected: NewAgent", output)

    @patch('ai_masa.agents.base_agent.RedisBroker')
    @patch('time.time')
    def test_agent_manager_removes_timed_out_agent(self, mock_time, MockRedisBroker):
        """AgentManagerがタイムアウトしたエージェントを削除するかテスト"""
        self.manager = AgentManager(timeout_seconds=30)
        
        # 1. エージェントをアクティブリストに追加
        mock_time.return_value = 1000.0
        self.manager.active_agents["OldAgent"] = 1000.0
        self.assertIn("OldAgent", self.manager.active_agents)
        
        # 2. 時間をタイムアウト後まで進める
        mock_time.return_value = 1031.0
        
        # 3. モニタリングループの1サイクルを手動で実行
        self.manager._monitor_loop(_run_once=True) 

        self.assertNotIn("OldAgent", self.manager.active_agents)
        output = self.mock_stdout.getvalue()
        self.assertIn("❌ Agent timed out and removed: OldAgent", output)
        self.assertIn("No active agents detected.", output) # ステータスレポートも確認

    @patch('ai_masa.agents.base_agent.RedisBroker')
    def test_agent_manager_status_query(self, MockRedisBroker):
        """AgentManagerがステータス問い合わせに応答するかテスト"""
        mock_broker_instance = MockRedisBroker.return_value
        self.manager = AgentManager()
        self.manager.active_agents["AgentOne"] = time.time() - 10
        self.manager.active_agents["AgentTwo"] = time.time() - 20
        
        query_msg = Message(
            from_agent="User", 
            to_agent="AgentManager", 
            content="What is the status?",
            job_id="query-123"
        ).to_json()
        
        # 問い合わせメッセージを処理
        self.manager._on_message_received(query_msg)
        
        # broadcastが呼ばれ、ステータスレポートが送信されたか確認
        mock_broker_instance.publish.assert_called()
        last_call_args = mock_broker_instance.publish.call_args[0][0]
        response_msg = Message.from_json(last_call_args)
        
        self.assertEqual(response_msg.to_agent, "User")
        self.assertIn("Active agents:", response_msg.content)
        self.assertIn("AgentOne", response_msg.content)
        self.assertIn("AgentTwo", response_msg.content)

if __name__ == '__main__':
    unittest.main()
