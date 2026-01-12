import unittest
from unittest.mock import MagicMock, patch, call
import sys
from io import StringIO
import json

from ai_masa.agents.user_input_agent import UserInputAgent
from ai_masa.models.message import Message

class TestUserInputAgent(unittest.TestCase):

    def setUp(self):
        """各テストの前に実行されるセットアップ"""
        # UserInputAgentのstart_interactionが自動で呼ばれるのを防ぐ
        self.start_interaction_patcher = patch('ai_masa.agents.user_input_agent.UserInputAgent.start_interaction', MagicMock())
        self.start_interaction_patcher.start()

        # 依存関係をモック化
        self.mock_broker_patcher = patch('ai_masa.agents.base_agent.RedisBroker')
        self.mock_session_manager_patcher = patch('ai_masa.agents.base_agent.SessionManager')
        self.mock_base_agent_start_heartbeat_patcher = patch('ai_masa.agents.base_agent.BaseAgent._start_heartbeat')

        self.MockRedisBroker = self.mock_broker_patcher.start()
        self.MockSessionManager = self.mock_session_manager_patcher.start()
        self.mock_base_agent_start_heartbeat = self.mock_base_agent_start_heartbeat_patcher.start()

        self.mock_broker_instance = self.MockRedisBroker.return_value
        self.mock_session_manager_instance = self.MockSessionManager.return_value

        # 標準入力と出力をモック
        self.mock_stdin = StringIO()
        self.mock_stdout = StringIO()
        sys.stdin = self.mock_stdin
        sys.stdout = self.mock_stdout

        # エージェントを初期化
        self.agent = UserInputAgent(
            name="TestUser",
            description="Handles user input for testing.", # descriptionを追加
            session_id="project-TestUser", # session_idを追加
            session_manager=self.mock_session_manager_instance, # モックを渡す
            default_target_agent="TestTarget"
        )
        # BaseAgentのbroadcastメソッドをモックして、呼び出しを検証できるようにする
        # BaseAgentのbroadcastはSessionManager.add_messageも呼ぶので、それを検証する
        self.agent.broadcast = MagicMock(side_effect=self.agent.broadcast) # 元のbroadcastも実行させる
        
        self.mock_broker_instance.connect.assert_called_once() # connectが呼ばれることを確認

    def tearDown(self):
        """各テストの後に実行されるクリーンアップ"""
        self.mock_broker_patcher.stop()
        self.mock_session_manager_patcher.stop()
        self.mock_base_agent_start_heartbeat_patcher.stop()
        self.start_interaction_patcher.stop()
        sys.stdin = sys.__stdin__
        sys.stdout = sys.__stdout__

    def test_initialization(self):
        """エージェントが正しく初期化されるかテスト"""
        self.assertEqual(self.agent.name, "TestUser")
        self.assertEqual(self.agent.description, "Handles user input for testing.")
        self.assertEqual(self.agent.session_id, "project-TestUser")
        self.assertEqual(self.agent.default_target_agent, "TestTarget")
        output = self.mock_stdout.getvalue()
        self.assertIn("[TestUser] Initialized. I will send messages to 'TestTarget'.", output)

    @patch('uuid.uuid4')
    def test_broadcast_user_input(self, mock_uuid):
        """
        ユーザー入力が正しくブロードキャストされ、自身の履歴に保存されるかテスト。
        """
        with patch.object(self.agent, 'response_received_event') as mock_event:
            mock_uuid.return_value = "test-job-id-123"
            
            # 標準入力の初期メッセージと終了メッセージ
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
            
            # broadcast内で自身のメッセージがSessionManagerに保存されることを検証
            # broadcastのside_effectを設定しているので、add_messageが呼ばれる
            self.mock_session_manager_instance.add_message.assert_called_once()
            saved_message = self.mock_session_manager_instance.add_message.call_args[0][1]
            self.assertEqual(saved_message['content'], "Hello Agent!")
            self.assertEqual(saved_message['from_agent'], "TestUser")
            self.assertEqual(saved_message['to_agent'], "TestTarget")
            
            # response_received_eventの状態が適切に操作されているか確認
            self.assertEqual(mock_event.wait.call_count, 2) # 入力待ち2回
            mock_event.clear.assert_called_once() # メッセージ送信時1回
            
            # プロンプトや待機メッセージが出力されているか確認
            output = self.mock_stdout.getvalue()
            self.assertIn("Enter your message", output)
            self.assertIn("Waiting for a response...", output)

    def test_receive_message(self):
        """
        エージェントが自分宛のメッセージを正しく受信し、イベントをセットし、自身の履歴に保存するかテスト。
        """
        test_msg = Message("OtherAgent", "TestUser", "This is a test message.", job_id="job-456")
        test_msg_json = test_msg.to_json()
        
        # イベントがクリアされている状態をシミュレート
        self.agent.response_received_event.clear()
        self.assertFalse(self.agent.response_received_event.is_set())

        # _on_message_receivedを直接呼び出す
        self.agent._on_message_received(test_msg_json)
        
        output = self.mock_stdout.getvalue()
        self.assertIn("📨 Received from OtherAgent: This is a test message.", output)
        
        # イベントがセットされたことを確認
        self.assertTrue(self.agent.response_received_event.is_set())

        # 受信メッセージがSessionManagerに保存されることを検証
        self.mock_session_manager_instance.add_message.assert_called_once_with("project-TestUser", json.loads(test_msg_json))

    def test_receive_cc_message(self):
        """
        エージェントがCCメッセージを正しく受信し、コンソールに表示し、イベントは変更せず、自身の履歴に保存するかテスト。
        """
        test_msg = Message("Sender", "PrimaryRecipient", "CC message", cc_agents=["TestUser"], job_id="job-789")
        test_msg_json = test_msg.to_json()

        # イベントがクリアされている状態をシミュレート
        self.agent.response_received_event.clear()
        self.assertFalse(self.agent.response_received_event.is_set())

        self.agent._on_message_received(test_msg_json)

        output = self.mock_stdout.getvalue()
        self.assertIn("👀 (CC) Saw message from Sender to PrimaryRecipient: CC message", output)
        
        # CC受信ではイベントがセットされない（ブロックが解除されない）ことを確認
        self.assertFalse(self.agent.response_received_event.is_set())

        # 受信メッセージがSessionManagerに保存されることを検証
        self.mock_session_manager_instance.add_message.assert_called_once_with("project-TestUser", json.loads(test_msg_json))

    @patch('uuid.uuid4')
    def test_newjob_command(self, mock_uuid):
        """
        'newjob'コマンドでjob_idが更新され、broadcastが呼ばれること、
        および自身の履歴にメッセージが保存されることをテスト。
        """
        with patch.object(self.agent, 'response_received_event') as mock_event:
            mock_uuid.side_effect = ["job-id-1", "job-id-2"]
            
            # 入力シーケンス: newjob -> メッセージ -> quit
            self.mock_stdin.write("newjob\n")
            self.mock_stdin.write("Second message\n")
            self.mock_stdin.write("quit\n")
            self.mock_stdin.seek(0)
            
            # broadcastメソッドをモックし、元のbroadcastメソッドも実行させる
            original_broadcast = self.agent.broadcast
            self.agent.broadcast = MagicMock(side_effect=original_broadcast)

            self.agent._input_loop()
                
            # broadcastは1回だけ呼ばれていることを確認 (newjobはbroadcastしない)
            self.agent.broadcast.assert_called_once_with(
                target="TestTarget",
                content="Second message",
                job_id="job-id-2" # newjobで生成された新しいID
            )

            # 送信したメッセージが履歴に保存されていることを検証
            self.assertEqual(self.mock_session_manager_instance.add_message.call_count, 1) # ユーザーからの入力メッセージのみ
            saved_message = self.mock_session_manager_instance.add_message.call_args[0][1]
            self.assertEqual(saved_message['content'], "Second message")
            
            # コンソール出力の確認
            output = self.mock_stdout.getvalue()
            self.assertIn("A new job has started. Job ID: job-id-1", output) # 初期ID
            self.assertIn("A new job has started. Job ID: job-id-2", output) # newjobコマンドによるID
            
            # waitが3回呼ばれていることを確認 (newjob, メッセージ入力, quit の各ループの開始時)
            self.assertEqual(mock_event.wait.call_count, 3)

    def test_no_default_target_agent_error(self):
        """
        default_target_agentが設定されていない場合にエラーメッセージが表示されることをテスト。
        """
        # default_target_agentがないエージェントを再初期化
        self.agent = UserInputAgent(
            name="TestUserNoTarget",
            description="Handles user input for testing.",
            session_id="project-TestUserNoTarget",
            session_manager=self.mock_session_manager_instance,
            default_target_agent=None # ここでNoneに設定
        )
        self.agent.broadcast = MagicMock()

        with patch.object(self.agent, 'response_received_event') as mock_event:
            # stderrもモックして出力をキャプチャ
            with patch('sys.stderr', new_callable=StringIO) as mock_stderr:
                self.mock_stdin.write("Hello without target!\n")
                self.mock_stdin.write("quit\n")
                self.mock_stdin.seek(0)

                self.agent._input_loop()

                stderr_output = mock_stderr.getvalue()
                self.assertIn("Error: No default target agent set. Cannot send message.", stderr_output)
                self.agent.broadcast.assert_not_called()
                # エラー後に入力が再度可能になることを確認
                # 初期化時のset()はモックの対象外なので、エラー発生後の1回のみ
                mock_event.set.assert_called_once()

if __name__ == '__main__':
    unittest.main()
