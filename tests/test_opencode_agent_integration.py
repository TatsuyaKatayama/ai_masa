import logging
import unittest
import time
import json
import threading
from unittest.mock import patch, MagicMock
import subprocess
import os
import redis
import sys # Add this line

from ai_masa.agents.opencode_agent import OpencodeAgent
from ai_masa.comms.redis_broker import RedisBroker
from ai_masa.models.message import Message

# Get API key from environment to determine if tests should be skipped

API_KEY_CONFIGURED = bool(os.environ.get("GOOGLE_GENERATIVE_AI_API_KEY"))



@unittest.skipIf(not API_KEY_CONFIGURED, "GOOGLE_GENERATIVE_AI_API_KEY environment variable not set.")

class TestOpencodeAgentIntegration(unittest.TestCase):



    @classmethod

    def setUpClass(cls):

        """Starts the Docker Compose services before any tests are run."""

        logging.basicConfig(level=logging.DEBUG, stream=sys.stdout, format='[%(name)s][%(levelname)s] %(message)s')

        

        print("\nStarting Docker Compose services for OpencodeAgent integration tests...")

        compose_file_path = os.path.join(os.path.dirname(__file__), '..', 'docker-compose.yml')

        if not os.path.exists(compose_file_path):

            raise FileNotFoundError(f"docker-compose.yml not found at {compose_file_path}")



        try:

            # Ensure containers are down before starting to avoid stale state

            subprocess.run(["docker", "compose", "-f", compose_file_path, "down"], capture_output=True)

            subprocess.run(

                ["docker", "compose", "-f", compose_file_path, "up", "-d"],

                check=True, capture_output=True

            )

            cls.wait_for_redis()

            cls.wait_for_opencode()

        except (subprocess.CalledProcessError, FileNotFoundError) as e:

            print("Error starting Docker Compose services. Is Docker running?")

            print(f"Stderr: {e.stderr if hasattr(e, 'stderr') else 'N/A'}")

            raise



    @classmethod

    def tearDownClass(cls):

        """Stops the Docker Compose services after all tests are done."""

        print("\nStopping Docker Compose services for OpencodeAgent integration tests...")

        compose_file_path = os.path.join(os.path.dirname(__file__), '..', 'docker-compose.yml')

        subprocess.run(["docker", "compose", "-f", compose_file_path, "down"], capture_output=True)



    @classmethod

    def wait_for_redis(cls, retries=10, delay=2):

        print("Waiting for Redis to be ready...")

        for i in range(retries):

            try:

                r = redis.Redis(host='localhost', port=6379, db=0)

                if r.ping():

                    print("Redis is ready.")

                    return

            except redis.exceptions.ConnectionError:

                time.sleep(delay)

        raise ConnectionError("Could not connect to Redis container after multiple retries.")

    

    @classmethod

    def wait_for_opencode(cls, retries=10, delay=2):

        print("Waiting for opencode-cli container to be ready...")

        for i in range(retries):

            try:

                result = subprocess.run(

                    ["docker", "exec", "opencode-cli", "opencode", "--version"],

                    check=True, capture_output=True, text=True

                )

                if result.returncode == 0:

                    print(f"opencode-cli is ready. Version: {result.stdout.strip()}")

                    return

            except (subprocess.CalledProcessError, FileNotFoundError):

                time.sleep(delay)

        raise ConnectionError("Could not connect to opencode-cli container after multiple retries.")





    def setUp(self):

        self.agent_name = "TestOpencodeAgent_Integration"

        self.memory_id = "integration_test_session"

        self.redis_host = 'localhost'

        self.redis_port = 6379

        self.test_channel = "ai_masa_channel"

        

        self.redis_client = redis.Redis(host=self.redis_host, port=self.redis_port, db=0, decode_responses=True)

        self.redis_client.flushdb()

        self.pubsub = self.redis_client.pubsub()



        # Initialize the agent to run against the real container

        self.agent = OpencodeAgent(

            name=self.agent_name, memory_id=self.memory_id, redis_host=self.redis_host, redis_port=self.redis_port, start_heartbeat=False

        )

        self.agent.broker.channel = self.test_channel



        self.agent_thread = threading.Thread(target=self.agent.observe_loop, daemon=True)

        self.agent_thread.start()

        time.sleep(1)



    def tearDown(self):

        if self.agent:

            self.agent.shutdown()

        if self.agent_thread and self.agent_thread.is_alive():

            self.agent_thread.join(timeout=5)

        if self.pubsub:

            self.pubsub.unsubscribe()

            self.pubsub.close()

        if self.redis_client:

            self.redis_client.close()



    def _send_message_and_get_reply(self, job_id: str, content: str, expected_substring: str, timeout: int = 45):

        print(f"\n[Test] Sending message for job '{job_id}': {content}")



        trigger_message = Message(from_agent="TestUser", to_agent=self.agent_name, content=content, job_id=job_id)

        self.redis_client.publish(self.test_channel, trigger_message.to_json())



        start_time = time.time()

        response_msg = None

        self.pubsub.subscribe(self.test_channel)

        for message in self.pubsub.listen():

            if time.time() - start_time > timeout:

                break

            if message['type'] == 'message':

                try:

                    msg = Message.from_json(message['data'])

                    if msg.from_agent == self.agent_name and msg.to_agent == "TestUser" and msg.job_id == job_id:

                        response_msg = msg

                        print(f"[Test] Received reply for '{job_id}': {msg.content}")

                        break

                except (json.JSONDecodeError, TypeError):

                    continue

        self.pubsub.unsubscribe(self.test_channel)



        self.assertIsNotNone(response_msg, f"No reply received for job '{job_id}' within {timeout}s.")

        self.assertEqual(response_msg.to_agent, "TestUser")

        self.assertIn(expected_substring.lower(), response_msg.content.lower())

        return response_msg



    def test_simple_interaction(self):

        self._send_message_and_get_reply(

            job_id="JobSimple",

            content="What is the capital of France?",

            expected_substring="Paris"

        )



    def test_memory_management_with_multiple_jobs(self):

        # Job00's first interaction

        self._send_message_and_get_reply(

            job_id="Job00",

            content="For the following calculations, assume a=2 and b=1. What is a+b?",

            expected_substring="3"

        )

        time.sleep(5)

        

        # Job01's interaction

        self._send_message_and_get_reply(

            job_id="Job01",

            content="For the following calculations, assume a=10 and b=5. What is a+b?",

            expected_substring="15"

        )

        time.sleep(5)



        # Return to Job00 to check context is maintained

        self._send_message_and_get_reply(

            job_id="Job00",

            content="Now, what is a*b?",

            expected_substring="2"

        )


