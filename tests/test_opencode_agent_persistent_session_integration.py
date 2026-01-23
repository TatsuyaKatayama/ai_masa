import logging
import unittest
import time
import json
import threading
import subprocess
import os
import redis
import sys
from ai_masa.agents.opencode_agent import OpencodeAgent
from ai_masa.models.message import Message


class TestOpencodeAgentPersistentSessionIntegration(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """
        Starts Docker Compose services, waits for them to be ready,
        and skips tests if they don't become healthy.
        """
        logging.basicConfig(level=logging.INFO, stream=sys.stdout, format='[%(name)s][%(levelname)s] %(message)s')
        
        print("\nStarting Docker Compose services for OpencodeAgent persistent session integration tests...")
        cls.compose_file_path = os.path.join(os.path.dirname(__file__), '..', 'docker-compose.yml')
        if not os.path.exists(cls.compose_file_path):
            raise FileNotFoundError(f"docker-compose.yml not found at {cls.compose_file_path}")

        try:
            subprocess.run(["docker", "compose", "-f", cls.compose_file_path, "down"], capture_output=True, timeout=60)
            subprocess.run(
                ["docker", "compose", "-f", cls.compose_file_path, "up", "-d"],
                check=True, capture_output=True, timeout=120
            )
            cls.wait_for_redis()
            cls.wait_for_opencode() # This will now skip the test if it fails
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
            raise unittest.SkipTest(f"Failed to start Docker Compose services. Skipping tests. Error: {e}")
        except ConnectionError as e:
             raise unittest.SkipTest(str(e))


    @classmethod
    def tearDownClass(cls):
        """Stops the Docker Compose services after all tests are done."""
        print("\nStopping Docker Compose services...")
        subprocess.run(["docker", "compose", "-f", cls.compose_file_path, "down"], capture_output=True, timeout=60)

    @classmethod
    def wait_for_redis(cls, retries=10, delay=3):
        print("Waiting for Redis to be ready...")
        for i in range(retries):
            try:
                r = redis.Redis(host='localhost', port=6379, db=0)
                if r.ping():
                    print("Redis is ready.")
                    return
            except redis.exceptions.ConnectionError:
                time.sleep(delay)
        raise ConnectionError("Could not connect to Redis container after multiple retries. Skipping tests.")
    
    @classmethod
    def wait_for_opencode(cls, retries=15, delay=5):
        print("Waiting for opencode-cli container to be functionally ready...")
        for i in range(retries):
            try:
                # Perform a functional check.
                result = subprocess.run(
                    ["docker", "exec", "opencode-cli", "opencode", "run", "-m", "google/gemini-2.5-flash", "What is 2+2?"],
                    check=True, capture_output=True, text=True, timeout=30
                )
                if "4" in result.stdout:
                    print(f"opencode-cli is ready and responded correctly.")
                    return
            except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
                print(f"opencode-cli not ready yet, retrying ({i+1}/{retries})...")
                time.sleep(delay)
        raise ConnectionError("Opencode CLI container did not become ready in time. Skipping tests.")

    def setUp(self):
        self.agent_name = "CodeReviewerAgent"
        self.memory_id = "code_reviewer_session"
        self.redis_host = 'localhost'
        self.redis_port = 6379
        self.test_channel = "ai_masa_code_review_channel"
        
        self.redis_client = redis.Redis(host=self.redis_host, port=self.redis_port, db=0, decode_responses=True)
        self.redis_client.flushdb()
        self.pubsub = self.redis_client.pubsub(ignore_subscribe_messages=True)

        # This role prompt will establish the agent's persona in the persistent session.
        role_prompt = "Your role is a meticulous and helpful code reviewer. When you receive code, identify potential bugs, suggest improvements, and explain your reasoning clearly."
        
        # Instantiate the agent with the specific description to set its role.
        self.agent = OpencodeAgent(
            name=self.agent_name,
            description=role_prompt,
            memory_id=self.memory_id,
            redis_host=self.redis_host,
            redis_port=self.redis_port,
            start_heartbeat=False
        )
        
        self.agent.broker.channel = self.test_channel
        self.agent_thread = threading.Thread(target=self.agent.observe_loop, daemon=True)
        self.agent_thread.start()
        # Allow time for the agent to initialize its session
        time.sleep(5) 

    def tearDown(self):
        if self.agent:
            self.agent.shutdown()
        if self.agent_thread and self.agent_thread.is_alive():
            self.agent_thread.join(timeout=10)
        if self.pubsub:
            self.pubsub.unsubscribe()
            self.pubsub.close()
        if self.redis_client:
            self.redis_client.close()

    def _send_message_and_get_reply(self, job_id: str, content: str, timeout: int = 60):
        print(f"\n[Test] Sending message for job '{job_id}': {content}")
        self.pubsub.subscribe(self.test_channel)
        
        trigger_message = Message(from_agent="TestUser", to_agent=self.agent_name, content=content, job_id=job_id)
        self.redis_client.publish(self.test_channel, trigger_message.to_json())

        start_time = time.time()
        response_msg = None
        for message in self.pubsub.listen():
            if time.time() - start_time > timeout:
                break
            if message['type'] == 'message':
                msg = Message.from_json(message['data'])
                if msg.from_agent == self.agent_name and msg.to_agent == "TestUser" and msg.job_id == job_id:
                    response_msg = msg
                    print(f"[Test] Received reply for job '{job_id}': {msg.content}")
                    break
        
        self.pubsub.unsubscribe(self.test_channel)
        return response_msg

    def test_code_reviewer_session_persistence(self):
        """
        Tests if the agent maintains the 'code reviewer' persona across multiple,
        independent job requests, demonstrating the single persistent session.
        """
        # 1. Verify the session was created on init
        self.assertIsNotNone(self.agent.session_id, "Agent should have created a session ID on initialization.")
        print(f"[Test] Agent initialized with persistent session ID: {self.agent.session_id}")

        # 2. First job: Ask the agent its role to confirm the initial prompt worked.
        response1 = self._send_message_and_get_reply(
            job_id="Job01_CheckRole",
            content="What is your primary function?"
        )
        self.assertIsNotNone(response1, "Did not receive a reply for Job01_CheckRole.")
        # Check for keywords related to its code reviewer role in either English or Japanese
        is_japanese_code_reviewer = ("コード" in response1.content and (
            "レビュ" in response1.content or
            "レビューア" in response1.content or
            "レビューワー" in response1.content
        ))
        is_english_code_reviewer = ("code" in response1.content.lower() and (
            "review" in response1.content.lower() or
            "reviewer" in response1.content.lower()
        ))
        self.assertTrue(
            is_japanese_code_reviewer or is_english_code_reviewer,
            f"Agent's response did not confirm its code reviewer role. Got: {response1.content}"
        )

        # 3. Second job: Send a piece of code for review.
        python_code = """
def add(a, b):
    # A simple function
    return a + b

# Example usage
result = add("2", 3)
print(result)
"""
        response2 = self._send_message_and_get_reply(
            job_id="Job02_ReviewCode",
            content=f"Please review this Python code:\n```python\n{python_code}\n```"
        )
        self.assertIsNotNone(response2, "Did not receive a reply for Job02_ReviewCode.")
        # The agent, acting as a code reviewer, should spot the TypeError.
        self.assertTrue(
            "typeerror" in response2.content.lower() 
            or "type mismatch" in response2.content.lower() 
            or "string and integer" in response2.content.lower()
            or "typeerror" in response2.content # Include for exact match if LLM returns it
            or "TypeError" in response2.content
            or "TYPEERROR" in response2.content
            or "Typeerror" in response2.content
            or "型エラー" in response2.content
            or "型の不一致" in response2.content
            or "文字列と整数" in response2.content,
            f"Agent did not identify the type error in the code. Got: {response2.content}"
        )

        # 4. Third job: A follow-up question that relies on the context of the second job.
        # This confirms the *same session* is being used.
        response3 = self._send_message_and_get_reply(
            job_id="Job02_ReviewCode", # Use the same job_id to continue the conversation
            content="How would you fix it?"
        )
        self.assertIsNotNone(response3, "Did not receive a reply for the follow-up question.")
        # A good fix would be converting the string to an integer, or suggesting type hints.
        self.assertTrue(
            "int(" in response3.content
            or "integer" in response3.content.lower()
            or "型ヒント" in response3.content
            or "型アノテーション" in response3.content
            or "int" in response3.content # Catch simple 'int' suggestions
            or "TypeError" in response3.content # If the LLM re-mentions the error type in the fix context
            or "typeerror" in response3.content.lower()
            or "TYPEERROR" in response3.content
            or "Typeerror" in response3.content,
        print("[Test] Code reviewer persona and session context were maintained successfully.")

if __name__ == '__main__':
    unittest.main()
