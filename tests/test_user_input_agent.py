import unittest
from unittest.mock import MagicMock, patch, call
import sys
from io import StringIO

from ai_masa.agents.user_input_agent import UserInputAgent
from ai_masa.models.message import Message

class TestUserInputAgent(unittest.TestCase):

    def setUp(self):
        """各テストの前に実行されるセットアップ"""
        # UserInputAgentのstart_interactionが自動で呼ばれるのを防ぐ
        self.start_interaction_patcher = patch('ai_masa.agents.user_input_agent.UserInputAgent.start_interaction', MagicMock())
        self.start_interaction_patcher.start()

        # RedisBrokerのモック (BaseAgent内)
        self.broker_patcher = patch('ai_masa.agents.base_agent.RedisBroker')
        MockRedisBroker = self.broker_patcher.start()
        self.mock_broker = MagicMock()
        MockRedisBroker.return_value = self.mock_broker

        # 標準入力と出力をモック
        self.mock_stdin = StringIO()
        self.mock_stdout = StringIO()
        sys.stdin = self.mock_stdin
        sys.stdout = self.mock_stdout

        # エージェントを初期化
        self.agent = UserInputAgent(name="TestUser", default_target_agent="TestTarget")
        # BaseAgentのbroadcastメソッドをモックして、呼び出しを検証できるようにする
        self.agent.broadcast = MagicMock()
        self.mock_broker.connect.assert_called_once() # connectが呼ばれることを確認

    def tearDown(self):
        """各テストの後に実行されるクリーンアップ"""
        self.broker_patcher.stop()
        self.start_interaction_patcher.stop()
        sys.stdin = sys.__stdin__
        sys.stdout = sys.__stdout__

    def test_initialization(self):
        """エージェントが正しく初期化されるかテスト"""
        self.assertEqual(self.agent.name, "TestUser")
        self.assertEqual(self.agent.default_target_agent, "TestTarget")
        output = self.mock_stdout.getvalue()
        self.assertIn("[TestUser] Initialized.", output)

    @patch('uuid.uuid4')
    def test_broadcast_user_input(self, mock_uuid):
        """ユーザー入力が正しくブロードキャストされるかテスト"""
        with patch.object(self.agent, 'response_received_event') as mock_event:
            mock_uuid.return_value = "test-job-id-123"
            
            # ユーザー入力を設定
            self.mock_stdin.write("Hello Agent!\n")
            self.mock_stdin.write("quit\n")
            self.mock_stdin.seek(0)

            # テスト対象のメソッドを実行
            self.agent._input_loop()

            # broadcastが正しい引数で呼ばれたか検証
            self.agent.broadcast.assert_called_once_with(
                target="TestTarget",
                content="Hello Agent!",
                job_id="test-job-id-123"
            )
            
            # response_received_eventの状態が適切に操作されているか確認
            self.assertEqual(mock_event.wait.call_count, 2)
            mock_event.clear.assert_called_once()
            
            # プロンプトや待機メッセージが出力されているか確認
            output = self.mock_stdout.getvalue()
            self.assertIn("Enter your message", output)
            self.assertIn("Waiting for a response...", output)

    def test_receive_message(self):
        """エージェントがメッセージを正しく受信し、イベントをセットするかテスト"""
        test_msg = Message("OtherAgent", "TestUser", "This is a test message.", job_id="job-456")
        
        # イベントがクリアされている状態をシミュレート
        self.agent.response_received_event.clear()
        self.assertFalse(self.agent.response_received_event.is_set())

        # _on_message_receivedを直接呼び出す
        self.agent._on_message_received(test_msg.to_json())
        
        output = self.mock_stdout.getvalue()
        self.assertIn("[TestUser][job-456] 📨 Received from OtherAgent: This is a test message.", output)
        
        # イベントがセットされたことを確認
        self.assertTrue(self.agent.response_received_event.is_set())

    def test_receive_cc_message(self):
        """エージェントがCCメッセージを正しく受信し、イベントは変更しないかテスト"""
        test_msg = Message("Sender", "PrimaryRecipient", "CC message", cc_agents=["TestUser"], job_id="job-789")

        # イベントがクリアされている状態をシミュレート
        self.agent.response_received_event.clear()
        self.assertFalse(self.agent.response_received_event.is_set())

        self.agent._on_message_received(test_msg.to_json())

        output = self.mock_stdout.getvalue()
        self.assertIn("[TestUser][job-789] 👀 (CC) Saw message from Sender to PrimaryRecipient: CC message", output)
        
        # CC受信ではイベントがセットされない（ブロックが解除されない）ことを確認
        self.assertFalse(self.agent.response_received_event.is_set())

    @patch('uuid.uuid4')
    def test_newjob_command(self, mock_uuid):
        """'newjob'コマンドでjob_idが更新され、broadcastが呼ばれないことをテスト"""
        with patch.object(self.agent, 'response_received_event') as mock_event:
            mock_uuid.side_effect = ["job-id-1", "job-id-2"]
            
            # 入力シーケンス: newjob -> メッセージ -> quit
            self.mock_stdin.write("newjob\n")
            self.mock_stdin.write("Second message\n")
            self.mock_stdin.write("quit\n")
            self.mock_stdin.seek(0)
            
            self.agent._input_loop()
            
            # broadcastは1回だけ呼ばれていることを確認
            self.agent.broadcast.assert_called_once_with(
                target="TestTarget",
                content="Second message",
                job_id="job-id-2" # newjobで生成された新しいID
            )

            # コンソール出力の確認
            output = self.mock_stdout.getvalue()
            self.assertIn("A new job has started. Job ID: job-id-1", output) # 初期ID
            self.assertIn("A new job has started. Job ID: job-id-2", output) # newjobコマンドによるID
            
            # waitが3回呼ばれていることを確認 (newjob, メッセージ入力, quit の各ループの開始時)
            self.assertEqual(mock_event.wait.call_count, 3)

if __name__ == '__main__':
    unittest.main()
