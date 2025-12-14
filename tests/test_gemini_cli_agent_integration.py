import unittest
import os
import redis
import threading
import time
import json
import sys
import tempfile
import shutil

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
        self.temp_dir = tempfile.mkdtemp()

        # テスト対象のエージェントをインスタンス化
        self.agent = GeminiCliAgent(name=self.agent_name, user_lang='English', working_dir=self.temp_dir)
        self.agent.broker.channel = self.test_channel

        # 別スレッドでエージェントのリスナーを起動
        self.agent_thread = threading.Thread(target=self.agent.observe_loop)
        self.agent_thread.start()
        
        time.sleep(2) # エージェントスレッドがRedisに接続するのを待つ

    def _send_message_and_get_reply(self, job_id, content, expected_substring, timeout=45):
        """Helper to send a message and wait for a single reply on the main test channel."""
        print(f"[Test] Sending message for job {job_id}: {content}")
        trigger_message = Message(
            from_agent="TestUser",
            to_agent=self.agent_name,
            content=content,
            job_id=job_id
        )
        self.redis_client.publish(self.test_channel, trigger_message.to_json())

        start_time = time.time()
        response_msg = None

        # メインチャネルを購読し、目的のメッセージを待つ
        self.pubsub.subscribe(self.test_channel)
        for message in self.pubsub.listen():
            if time.time() - start_time > timeout:
                break
            if message['type'] == 'message':
                try:
                    msg = Message.from_json(message['data'])
                    # エージェントからの、現在のjob_idに対する応答をフィルタリング
                    if msg.from_agent == self.agent_name and msg.to_agent == "TestUser" and msg.job_id == job_id:
                        response_msg = msg
                        print(f"[Test] Received reply for {job_id}: {response_msg.content}")
                        break
                except json.JSONDecodeError:
                    continue # JSONではないメッセージはスキップ
            time.sleep(0.1) # 短時間待機してCPUを解放
        
        self.pubsub.unsubscribe(self.test_channel) # メッセージ受信後、購読解除

        self.assertIsNotNone(response_msg, f"No reply received for job {job_id} within timeout.")
        self.assertEqual(response_msg.from_agent, self.agent_name)
        self.assertEqual(response_msg.to_agent, "TestUser")
        self.assertIn(expected_substring.lower(), response_msg.content.lower(), 
                      f"Response for job {job_id} should contain '{expected_substring}'. Got: {response_msg.content}")
        return response_msg

    def test_session_management_with_multiple_jobs(self):
        """
        GeminiCliAgentが複数のジョブIDでセッションを正しく管理することを確認する。
        """
        print("\n[Test] Starting session management test with multiple jobs...")

        # Job00の最初のやり取り
        self._send_message_and_get_reply(
            job_id="Job00",
            content="If a=2 and b=1, what is a+b?",
            expected_substring="3"
        )
        time.sleep(5) # エージェントが次のメッセージを処理するのを待つ

        # Job01のやり取り
        self._send_message_and_get_reply(
            job_id="Job01",
            content="If a=10 and b=5, what is a+b?",
            expected_substring="15"
        )
        time.sleep(5) # エージェントが次のメッセージを処理するのを待つ

        # Job00に戻って別の質問をする (セッションが維持されているか確認)
        self._send_message_and_get_reply(
            job_id="Job00",
            content="What is a*b?",
            expected_substring="2"
        )
        time.sleep(5) # エージェントが次のメッセージを処理するのを待つ

    def test_real_gemini_cli_interaction(self):
        """
        エージェントにメッセージを送り、Gemini CLI経由での応答を待つ
        """
        print(f"\n[Test] Sending message to '{self.agent_name}'...")
        self._send_message_and_get_reply(
            job_id="integration-test-1",
            content="What is the capital of France?",
            expected_substring="Paris"
        )
        time.sleep(5) # エージェントが次のメッセージを処理するのを待つ

    def tearDown(self):
        print("\n[Test] Tearing down...")
        # エージェントのシャットダウンをトリガー
        self.agent.shutdown()

        # スレッドが終了するのを待つ
        if self.agent_thread and self.agent_thread.is_alive():
            self.agent_thread.join()

        # 一時ディレクトリをクリーンアップ
        if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

        # クリーンアップ
        self.pubsub.unsubscribe()
        self.pubsub.close()
        self.agent.broker.disconnect()
        print("[Test] Cleaned up resources.")

if __name__ == '__main__':
    unittest.main()
