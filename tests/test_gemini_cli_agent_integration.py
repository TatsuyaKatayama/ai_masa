import unittest
import os
import redis
import threading
import time
import json
import sys
import tempfile
import shutil
import subprocess # 追加

# パスを追加してモジュールをインポート可能にする
# sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from ai_masa.agents.gemini_cli_agent import GeminiCliAgent
from ai_masa.models.message import Message
from ai_masa.comms.redis_broker import RedisBroker
from ai_masa.comms.memory_manager import MemoryManager # MemoryManagerも必要

# 環境変数とRedis接続の確認
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

@unittest.skipIf(not GEMINI_API_KEY, "GEMINI_API_KEY environment variable not set.")
class TestGeminiCliAgentIntegration(unittest.TestCase):
    """
    GeminiCliAgentの実動作インテグレーションテスト。
    実際の`gemini`コマンドを実行し、Redisを介した応答を確認します。
    """
    @classmethod
    def setUpClass(cls):
        """Starts the Redis container before any tests are run."""
        print("\nStarting Redis container for GeminiCliAgent integration tests...")
        
        # docker-compose.ymlのパスをai_masaディレクトリの直下に設定
        compose_file_path = os.path.join(os.path.dirname(__file__), '..', 'docker-compose.yml')
        if not os.path.exists(compose_file_path):
            raise FileNotFoundError(f"docker-compose.yml not found at {compose_file_path}")

        try:
            subprocess.run(
                ["docker", "compose", "-f", compose_file_path, "up", "-d"],
                check=True, capture_output=True
            )
            # Wait for Redis to be ready
            cls.wait_for_redis()
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print("Error starting Redis container. Is Docker running?")
            print(f"Stderr: {e.stderr if hasattr(e, 'stderr') else 'N/A'}")
            raise

    @classmethod
    def tearDownClass(cls):
        """
        Stops the Redis container after all tests are done.
        Also cleans up any gemini CLI sessions created in temporary directories.
        """
        print("\nStopping Redis container for GeminiCliAgent integration tests...")
        compose_file_path = os.path.join(os.path.dirname(__file__), '..', 'docker-compose.yml')
        subprocess.run(
            ["docker", "compose", "-f", compose_file_path, "down"],
            capture_output=True
        )

    @classmethod
    def wait_for_redis(cls, retries=10, delay=2):
        """
        Waits for the Redis container to become available.
        This method is now always called, ensuring Redis is up.
        """
        print("Waiting for Redis to be ready...")
        for i in range(retries):
            try:
                r = redis.Redis(host='localhost', port=6379, db=1)
                if r.ping():
                    print("Redis is ready.")
                    return
            except redis.exceptions.ConnectionError:
                time.sleep(delay)
        raise ConnectionError("Could not connect to Redis container after multiple retries.")


    def setUp(self):
        self.agent_name = "RealGeminiAgent"
        self.test_channel = "ai_masa_test_channel"
        self.redis_client = redis.Redis(host='localhost', port=6379, db=1, decode_responses=True)
        self.redis_client.flushdb() # 各テスト前にDBをクリーンアップ
        self.pubsub = self.redis_client.pubsub()
        # Create a fresh temporary directory for each test
        self.temp_dir = tempfile.mkdtemp()

        # BaseAgentのmemory_idは必須なので、一意なIDを生成して渡す
        self.memory_id = f"integration-memory-{self.agent_name}-{os.getpid()}-{time.time_ns()}"

        # テスト対象のエージェントをインスタンス化
        self.agent = GeminiCliAgent(
            name=self.agent_name,
            description="An integration test agent for Gemini CLI.", # descriptionを追加
            user_lang='English',
            memory_id=self.memory_id, # memory_idを追加
            redis_host='localhost',
            redis_port=6379,
            redis_db=1, # テスト専用DBを指定
            working_dir=self.temp_dir,
            start_heartbeat=False # ハートビートはテストの邪魔になるのでオフ
        )
        self.agent.broker.channel = self.test_channel # Brokerのチャネルを設定

        # The default role_prompt in BaseAgent can confuse the LLM in a test environment.
        # We will add a stronger, explicit instruction for the test.
        self.agent.role_prompt += (
            "\n\n--- TEST INSTRUCTION OVERRIDE ---\n"
            "CRITICAL: The user you are interacting with in this test is named 'TestUser'.\n"
            "You MUST address all your responses to 'TestUser' by setting the 'to_agent' field in your JSON response to exactly 'TestUser'.\n"
            "--- END TEST INSTRUCTION OVERRIDE ---"
        )

        # 別スレッドでエージェントのリスナーを起動
        self.agent_thread = threading.Thread(target=self.agent.observe_loop, daemon=True)
        self.agent_thread.start()
        
        time.sleep(2) # エージェントスレッドがRedisに接続するのを待つ

    def _send_message_and_get_reply(self, job_id: str, content: str, expected_substring: str, timeout: int = 60):
        """Helper to send a message and wait for a single reply on the main test channel."""
        print(f"[Test] Sending message for job {job_id}: {content}")
        trigger_message = Message(
            from_agent="TestUser",
            to_agent=self.agent_name,
            content=content,
            job_id=job_id
        )
        self.redis_client.publish(self.agent.broker.channel, trigger_message.to_json()) # broker.channelを使用

        start_time = time.time()
        response_msg = None

        # メインチャネルを購読し、目的のメッセージを待つ
        self.pubsub.subscribe(self.agent.broker.channel) # broker.channelを使用
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
        
        self.pubsub.unsubscribe(self.agent.broker.channel) # メッセージ受信後、購読解除

        self.assertIsNotNone(response_msg, f"No reply received for job {job_id} within timeout.")
        self.assertEqual(response_msg.from_agent, self.agent_name)
        self.assertEqual(response_msg.to_agent, "TestUser")
        self.assertIn(expected_substring.lower(), response_msg.content.lower(), 
                      f"Response for job {job_id} should contain '{expected_substring}'. Got: {response_msg.content}")
        return response_msg

    def test_memory_management_with_multiple_jobs(self):
        """
        GeminiCliAgentが複数のジョブIDでセッションを正しく管理することを確認する。
        """
        print("\n[Test] Starting memory management test with multiple jobs...")

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
        # 1. Signal the agent thread to shut down
        if hasattr(self, 'agent'):
            self.agent.shutdown()

        # 2. Wait for the agent thread to terminate
        if hasattr(self, 'agent_thread') and self.agent_thread.is_alive():
            self.agent_thread.join(timeout=5) # Add a timeout
            if self.agent_thread.is_alive():
                print("Warning: Agent thread did not terminate within timeout.", file=sys.stderr)

        # 3. Clean up Redis resources (now that the thread is stopped)
        if hasattr(self, 'pubsub') and self.pubsub:
            try:
                self.pubsub.unsubscribe()
                self.pubsub.close()
            except Exception as e:
                print(f"Error during pubsub cleanup: {e}", file=sys.stderr)
        
        if hasattr(self, 'agent') and hasattr(self.agent, 'broker'):
             self.agent.broker.disconnect()
        
        if hasattr(self, 'redis_client'):
            self.redis_client.close()

        # 4. Clean up temporary directory, which contains the gemini sessions
        if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

        print("[Test] Cleaned up resources.")

if __name__ == '__main__':
    unittest.main()
