import unittest
from unittest.mock import MagicMock, patch, call
import time
import sys
from io import StringIO
import json

# ai_masaモジュールをインポート可能にする
sys.path.insert(0, '.')

from ai_masa.agents.base_agent import BaseAgent
from ai_masa.agents.agent_manager import AgentManager
from ai_masa.models.message import Message

class TestAgentManager(unittest.TestCase):

    def setUp(self):
        # 標準出力をモック
        self.mock_stdout = StringIO()
        sys.stdout = self.mock_stdout

        # 依存関係をモック化
        self.mock_broker_patcher = patch('ai_masa.agents.base_agent.RedisBroker')
        self.mock_session_manager_patcher = patch('ai_masa.agents.base_agent.SessionManager')
        self.mock_base_agent_start_heartbeat_patcher = patch('ai_masa.agents.base_agent.BaseAgent._start_heartbeat')

        self.MockRedisBroker = self.mock_broker_patcher.start()
        self.MockSessionManager = self.mock_session_manager_patcher.start()
        self.mock_base_agent_start_heartbeat = self.mock_base_agent_start_heartbeat_patcher.start()

        self.mock_broker_instance = self.MockRedisBroker.return_value
        self.mock_session_manager_instance = self.MockSessionManager.return_value

        # AgentManagerが監視スレッドを自動で開始しないようにモック化
        self.mock_agent_manager_start_monitoring_patcher = patch('ai_masa.agents.agent_manager.AgentManager._start_monitoring')
        self.mock_agent_manager_start_monitoring = self.mock_agent_manager_start_monitoring_patcher.start()

        # AgentManagerインスタンスの生成
        self.manager = AgentManager(
            name="AgentManager",
            description="I am an agent manager, monitoring the status of other agents.",
            session_id="project-AgentManager", # 必須となったsession_idを渡す
            session_manager=self.mock_session_manager_instance # モックを渡す
        )

    def tearDown(self):
        # すべてのパッチを停止
        self.mock_broker_patcher.stop()
        self.mock_session_manager_patcher.stop()
        self.mock_base_agent_start_heartbeat_patcher.stop()
        self.mock_agent_manager_start_monitoring_patcher.stop()

        # 標準出力を元に戻す
        sys.stdout = sys.__stdout__

    @patch('time.time')
    def test_agent_manager_detects_new_agent(self, mock_time):
        """
        AgentManagerが新しいエージェントのハートビートを検出して記録するかテスト。
        BaseAgentの_on_message_receivedが呼ばれ、SessionManagerにメッセージが追加されることも確認。
        """
        mock_time.return_value = 1000.0
        
        heartbeat_msg = Message(
            from_agent="NewAgent", 
            to_agent="NewAgent", 
            content="heartbeat", 
            cc_agents=["_broadcast_", "AgentManager"], # AgentManager自身もCCに含める
            job_id="_system_"
        ).to_json()
        
        # マネージャーにハートビートメッセージを直接渡す
        self.manager._on_message_received(heartbeat_msg)
        
        self.assertIn("NewAgent", self.manager.active_agents)
        self.assertAlmostEqual(self.manager.active_agents["NewAgent"], 1000.0)
        output = self.mock_stdout.getvalue()
        self.assertIn("✅ New agent detected: NewAgent", output)

        # BaseAgentの_on_message_receivedにより、CCされたメッセージは自身の履歴に追加される
        # そのため、add_messageが呼ばれるのが正しい挙動
        heartbeat_msg_dict = json.loads(heartbeat_msg)
        # message_idとtimestampは動的に生成されるため、ANYでマッチさせる
        self.mock_session_manager_instance.add_message.assert_called_once()
        call_args = self.mock_session_manager_instance.add_message.call_args[0]
        self.assertEqual(call_args[0], "project-AgentManager")
        # message_id と timestamp を除外して比較
        call_args[1].pop('message_id')
        call_args[1].pop('timestamp')
        heartbeat_msg_dict.pop('message_id')
        heartbeat_msg_dict.pop('timestamp')
        self.assertEqual(call_args[1], heartbeat_msg_dict)

    @patch('time.time')
    def test_agent_manager_removes_timed_out_agent(self, mock_time):
        """
        AgentManagerがタイムアウトしたエージェントを削除するかテスト。
        """
        self.manager.timeout_seconds = 30
        
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
        # AgentManager自身はアクティブなので、ステータスレポートは"Active agents"を含むはず
        self.assertIn("Active agents:", output)
        self.assertIn("AgentManager", output)
        self.assertNotIn("No active agents detected.", output)

    @patch('time.time')
    def test_agent_manager_does_not_timeout_itself(self, mock_time):
        """
        AgentManagerが自分自身をタイムアウトさせないことをテスト。
        """
        self.manager.timeout_seconds = 30
        mock_time.return_value = 1000.0
        
        # マネージャー自身をアクティブリストに追加
        self.manager.active_agents["AgentManager"] = 950.0 # 50秒前に活動
        self.manager.active_agents["OtherAgent"] = 950.0
        
        # 時間を大幅に進める (AgentManagerもタイムアウトするはずの時間)
        mock_time.return_value = 1100.0 # 150秒後
        
        self.manager._monitor_loop(_run_once=True)

        self.assertIn("AgentManager", self.manager.active_agents)
        self.assertNotIn("OtherAgent", self.manager.active_agents) # OtherAgentはタイムアウトで削除される
        output = self.mock_stdout.getvalue()
        self.assertNotIn("❌ Agent timed out and removed: AgentManager", output)
        self.assertIn("❌ Agent timed out and removed: OtherAgent", output)


    def test_agent_manager_status_query(self):
        """
        AgentManagerがステータス問い合わせに応答し、BaseAgentのbroadcastを介して送信するかテスト。
        """
        # AgentManager自身をアクティブエージェントに追加
        self.manager.active_agents["AgentManager"] = time.time()
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
        self.mock_broker_instance.publish.assert_called_once()
        published_data = json.loads(self.mock_broker_instance.publish.call_args[0][0])
        
        self.assertEqual(published_data['to_agent'], "User")
        self.assertIn("Active agents:", published_data['content'])
        self.assertIn("AgentManager", published_data['content'])
        self.assertIn("AgentOne", published_data['content'])
        self.assertIn("AgentTwo", published_data['content'])

        # AgentManager自身のセッションにメッセージが追加されたことを確認
        self.mock_session_manager_instance.add_message.assert_called() # _on_message_receivedとbroadcastで計2回
        add_message_calls = self.mock_session_manager_instance.add_message.call_args_list
        self.assertEqual(len(add_message_calls), 2) # 受信メッセージと送信メッセージ
        
        # 受信メッセージの確認
        self.assertEqual(add_message_calls[0].args[1]['content'], "What is the status?")
        # 送信メッセージの確認
        self.assertIn("Active agents", add_message_calls[1].args[1]['content'])


if __name__ == '__main__':
    unittest.main()
