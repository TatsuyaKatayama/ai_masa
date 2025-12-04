import unittest
import os
import redis
import threading
import time
import json
import sys

# パスを追加してモジュールをインポート可能にする
# sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from ai_masa.agents.gemini_cli_agent import GeminiCliAgent
from ai_masa.models.message import Message

# 環境変数とRedis接続の確認
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
IS_REDIS_AVAILABLE = False
try:
    r = redis.Redis(decode_responses=True)
    r.ping()
    IS_REDIS_AVAILABLE = True
except redis.exceptions.ConnectionError:
    print("WARNING: Redis server not available at localhost:6379. Integration test will be skipped.", file=sys.stderr)

@unittest.skipIf(not GEMINI_API_KEY, "GEMINI_API_KEY environment variable not set.")
@unittest.skipIf(not IS_REDIS_AVAILABLE, "Redis server is not available.")
class TestGeminiCliAgentIntegration(unittest.TestCase):
    """
    GeminiCliAgentの実動作インテグレーションテスト。
    実際の`gemini`コマンドを実行し、Redisを介した応答を確認します。
    """
    def setUp(self):
        self.agent_name = "RealGeminiAgent"
        self.test_channel = "ai_masa_test_channel"
        self.redis_client = redis.Redis(decode_responses=True)
        self.pubsub = self.redis_client.pubsub()
        self.received_messages = []

        # テスト対象のエージェントをインスタンス化
        # BaseAgentのデフォルトチャネルではなく、テスト用チャネルを使うように調整
        self.agent = GeminiCliAgent(name=self.agent_name)
        self.agent.broker.channel = self.test_channel

        # 別スレッドでエージェントのリスナーを起動
        self.agent_thread = threading.Thread(target=self.agent.observe_loop, daemon=True)
        self.agent_thread.start()
        
        # 別スレッドでRedisからのメッセージを監視するリスナーを起動
        self.listener_thread = threading.Thread(target=self._listen_for_replies, daemon=True)
        self.listener_thread.start()
        
        time.sleep(2) # 各スレッドがRedisに接続するのを待つ

    def _listen_for_replies(self):
        """Redisチャネルを購読し、エージェントからの応答のみをリストに格納する"""
        self.pubsub.subscribe(self.test_channel)
        print("\n[Test Listener] Subscribed to test channel. Waiting for agent's reply...")
        for message in self.pubsub.listen():
            if message['type'] == 'message':
                # メッセージをパース
                msg = Message.from_json(message['data'])
                # テスト対象のエージェントからのメッセージのみを処理
                if msg.from_agent == self.agent_name:
                    self.received_messages.append(message['data'])
                    # 期待する応答を1つ受信したらループを抜ける
                    break

    def test_real_gemini_cli_interaction(self):
        """
        エージェントにメッセージを送り、Gemini CLI経由での応答を待つ
        """
        print(f"\n[Test] Sending message to '{self.agent_name}'...")
        # 1. テスト用のメッセージを作成してRedisに送信
        trigger_message = Message(
            from_agent="TestUser",
            to_agent=self.agent_name,
            content="フランスの首都はどこですか？",
            job_id="integration-test-1"
        )
        self.redis_client.publish(self.test_channel, trigger_message.to_json())

        # 2. Gemini APIからの応答を待つ (ネットワーク越しなので長めに設定)
        print("[Test] Waiting for response from agent via Gemini CLI...")
        time.sleep(15) 

        # 3. リスナーが応答を受信したか検証
        self.assertEqual(len(self.received_messages), 1, "Should have received exactly one reply from the agent.")
        
        # 4. 受信したメッセージの内容を検証
        response_json = self.received_messages[0]
        response_msg = Message.from_json(response_json)

        print(f"[Test] Received content: {response_msg.content}")
        self.assertEqual(response_msg.from_agent, self.agent_name)
        self.assertEqual(response_msg.to_agent, "TestUser")
        self.assertIn("パリ", response_msg.content, "The response content should contain 'パリ'.")
        
    def tearDown(self):
        # クリーンアップ
        self.pubsub.unsubscribe()
        self.pubsub.close()
        self.agent.broker.disconnect()
        print("[Test] Cleaned up resources.")

if __name__ == '__main__':
    unittest.main()
