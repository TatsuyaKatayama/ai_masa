import unittest
from unittest.mock import patch, MagicMock, ANY
import json
import subprocess

# テスト対象のクラスとモジュールをインポート
from ai_masa.base_agent import BaseAgent
from ai_masa.models.message import Message

class TestBaseAgent(unittest.TestCase):

    @patch('subprocess.run')
    @patch('ai_masa.base_agent.RedisBroker')
    def test_think_and_respond_with_llm_command(self, MockRedisBroker, mock_subprocess_run):
        """
        メッセージ受信時にllm_commandを実行し、その標準出力(JSON)に基づいて応答を送信するかのテスト
        """
        # --- Arrange (準備) ---

        # RedisBrokerのモックを設定
        mock_broker_instance = MockRedisBroker.return_value
        mock_broker_instance.publish = MagicMock()

        # subprocess.runのモックを設定
        # LLMからの期待される応答を定義
        llm_response_content = "私の名前はTestAgentです。"
        llm_response_json = json.dumps({
            "to_agent": "User",
            "content": llm_response_content
        })
        # CalledProcessErrorを発生させないように、CompletedProcessのインスタンスを返す
        mock_subprocess_run.return_value = subprocess.CompletedProcess(
            args='gemini',
            returncode=0,
            stdout=llm_response_json,
            stderr=''
        )

        # テスト対象のエージェントを初期化
        agent = BaseAgent(
            name="TestAgent",
            role_prompt="あなたはテスト用のエージェントです。",
            language='ja',
            llm_command="gemini" # llm_commandを指定
        )

        # トリガーとなるメッセージを作成
        trigger_message = Message(
            from_agent="User",
            to_agent="TestAgent",
            content="あなたの名前は？"
        )
        trigger_message_json = trigger_message.to_json()

        # --- Act (実行) ---
        
        # メッセージ受信処理を直接呼び出す
        agent._on_message_received(trigger_message_json)

        # --- Assert (検証) ---

        # 1. subprocess.run が1回呼び出されたことを確認
        mock_subprocess_run.assert_called_once()
        
        # 呼び出し引数を取得
        args, kwargs = mock_subprocess_run.call_args
        
        # 2. 意図したコマンドが実行されたかを確認
        self.assertEqual(args[0], 'gemini')
        
        # 3. プロンプトに重要な情報が含まれているかを確認
        prompt = kwargs['input']
        self.assertIn("あなたの名前は「TestAgent」です。", prompt)
        self.assertIn("From: User", prompt)
        self.assertIn("Content: あなたの名前は？", prompt)
        
        # 4. RedisBroker.publish が1回呼び出されたことを確認
        mock_broker_instance.publish.assert_called_once()
        
        # 5. publishされたメッセージの内容がLLMの応答と一致することを確認
        published_json = mock_broker_instance.publish.call_args[0][0]
        published_data = json.loads(published_json)
        
        self.assertEqual(published_data['from_agent'], 'TestAgent')
        self.assertEqual(published_data['to_agent'], 'User')
        self.assertEqual(published_data['content'], llm_response_content)

if __name__ == '__main__':
    unittest.main()
