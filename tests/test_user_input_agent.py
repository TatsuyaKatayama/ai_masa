import unittest
from unittest.mock import MagicMock, patch, call
import sys
import threading
from io import StringIO

from ai_masa.agents.user_input_agent import UserInputAgent
from ai_masa.models.message import Message

from ai_masa.agents.user_input_agent import UserInputAgent
from ai_masa.models.message import Message

class TestUserInputAgent(unittest.TestCase):

    def setUp(self):
        """各テストの前に実行されるセットアップ"""
        # RedisBrokerのモック
        self.mock_broker = MagicMock()

        # UserInputAgentのインスタンスを作成する際に、BaseAgentがRedisBrokerを参照するパスをモック
        # ai_masa.agents.base_agent.RedisBroker が正しいパッチターゲット
        patcher = patch('ai_masa.agents.base_agent.RedisBroker')
        MockRedisBroker = patcher.start()
        MockRedisBroker.return_value = self.mock_broker

        # 標準入力と出力をモック (エージェント初期化前に設定)
        self.mock_stdin = StringIO()
        self.mock_stdout = StringIO()
        sys.stdin = self.mock_stdin
        sys.stdout = self.mock_stdout

        # エージェントを初期化
        self.agent = UserInputAgent(name="TestUser", default_target_agent="TestTarget")
        self.mock_broker.connect.assert_called_once() # connectが呼ばれることを確認
    def tearDown(self):
        """各テストの後に実行されるクリーンアップ"""
        sys.stdin = sys.__stdin__
        sys.stdout = sys.__stdout__

    def test_initialization(self):
        """エージェントが正しく初期化されるかテスト"""
        self.assertEqual(self.agent.name, "TestUser")
        self.assertEqual(self.agent.default_target_agent, "TestTarget")
        # self.mock_broker.connect.assert_called_once() # setUpで既に確認済み
        
        # 初期化メッセージの確認
        output = self.mock_stdout.getvalue()
        self.assertIn("[TestUser] Initialized.", output)

    @patch('uuid.uuid4')
    def test_broadcast_user_input(self, mock_uuid):
        """ユーザー入力が正しくブロードキャストされるかテスト"""
        # uuid.uuid4が固定の値を返すように設定
        mock_uuid.return_value = "test-job-id-123"
        
        # ユーザー入力を設定
        self.mock_stdin.write("Hello Agent!\n")
        self.mock_stdin.write("quit\n") # ループを抜けるため
        self.mock_stdin.seek(0)

        # テスト対象のメソッドを実行
        self.agent._input_loop()

        # broadcastが正しい引数で呼ばれたか検証
        self.mock_broker.publish.assert_called_once()
        actual_published_json = self.mock_broker.publish.call_args[0][0]
        actual_msg = Message.from_json(actual_published_json)

        expected_msg = Message(
            from_agent="TestUser",
            to_agent="TestTarget",
            content="Hello Agent!",
            job_id="test-job-id-123"
        )
        
        self.assertEqual(actual_msg.from_agent, expected_msg.from_agent)
        self.assertEqual(actual_msg.to_agent, expected_msg.to_agent)
        self.assertEqual(actual_msg.content, expected_msg.content)
        self.assertEqual(actual_msg.job_id, expected_msg.job_id)
        
        # 送信時のログが出力されているか確認
        output = self.mock_stdout.getvalue()
        self.assertIn("🚀 Sent to TestTarget: Hello Agent!", output)

    def test_receive_message(self):
        """エージェントがメッセージを正しく受信し表示するかテスト"""
        test_msg = Message("OtherAgent", "TestUser", "This is a test message.", job_id="job-456")
        
        # _on_message_receivedを直接呼び出す
        self.agent._on_message_received(test_msg.to_json())
        
        output = self.mock_stdout.getvalue()
        self.assertIn("[TestUser][job-456] 📨 Received from OtherAgent: This is a test message.", output)
        
    def test_receive_cc_message(self):
        """エージェントがCCメッセージを正しく受信し表示するかテスト"""
        test_msg = Message("Sender", "PrimaryRecipient", "CC message", cc_agents=["TestUser"], job_id="job-789")

        self.agent._on_message_received(test_msg.to_json())

        output = self.mock_stdout.getvalue()
        self.assertIn("[TestUser][job-789] 👀 (CC) Saw message from Sender to PrimaryRecipient: CC message", output)


    @patch('uuid.uuid4')
    def test_newjob_command(self, mock_uuid):
        """'newjob'コマンドでjob_idが更新されるかテスト"""
        # uuid.uuid4が呼ばれるたびに異なる値を返すように設定
        mock_uuid.side_effect = ["job-id-1", "job-id-2"]
        
        # 入力シーケンス: 最初のメッセージ -> newjob -> 2番目のメッセージ -> quit
        self.mock_stdin.write("First message\n")
        self.mock_stdin.write("newjob\n")
        self.mock_stdin.write("Second message\n")
        self.mock_stdin.write("quit\n")
        self.mock_stdin.seek(0)
        
        self.agent._input_loop()
        
        # publishが2回呼ばれていることを確認
        self.assertEqual(self.mock_broker.publish.call_count, 2)
        
        # 1回目の呼び出しが 'job-id-1' で行われたか
        first_call_args = self.mock_broker.publish.call_args_list[0]
        first_msg = Message.from_json(first_call_args[0][0])
        self.assertEqual(first_msg.job_id, "job-id-1")
        self.assertEqual(first_msg.content, "First message")

        # 2回目の呼び出しが 'job-id-2' で行われたか
        second_call_args = self.mock_broker.publish.call_args_list[1]
        second_msg = Message.from_json(second_call_args[0][0])
        self.assertEqual(second_msg.job_id, "job-id-2")
        self.assertEqual(second_msg.content, "Second message")

        # コンソール出力の確認
        output = self.mock_stdout.getvalue()
        self.assertIn("A new job has started. Job ID: job-id-1", output)
        self.assertIn("A new job has started. Job ID: job-id-2", output)

if __name__ == '__main__':
    unittest.main()
