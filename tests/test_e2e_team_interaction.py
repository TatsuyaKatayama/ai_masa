import os
import unittest
import threading
import time
import uuid
import json
import yaml
import redis
import subprocess

from ai_masa.agents.kintai_agent import KintaiAgent
from ai_masa.agents.role_based_gemini_cli_agent import RoleBasedGeminiCliAgent
from ai_masa.comms.redis_broker import RedisBroker
from ai_masa.models.message import Message

# Skip test if GEMINI_API_KEY is not set, as it's an E2E test
@unittest.skipIf(not os.environ.get("GEMINI_API_KEY"), "GEMINI_API_KEY environment variable not set.")
class TestE2ETeamInteraction(unittest.TestCase):
    """
    Tests a full end-to-end scenario involving multiple agents coordinating
    to answer a user's query, inspired by test_gemini_cli_agent_integration.
    """
    @classmethod
    def setUpClass(cls):
        """Starts the Redis container before any tests are run."""
        print("\n[E2E Test] Starting Redis container...")
        compose_file_path = os.path.join(os.path.dirname(__file__), '..', 'docker-compose.yml')
        if not os.path.exists(compose_file_path):
            raise FileNotFoundError(f"docker-compose.yml not found at {compose_file_path}")
        
        try:
            subprocess.run(["docker", "compose", "-f", compose_file_path, "up", "-d"], check=True, capture_output=True)
            cls.wait_for_redis()
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print("Error starting Redis container. Is Docker running?", file=sys.stderr)
            if hasattr(e, 'stderr'):
                print(f"Stderr: {e.stderr.decode()}", file=sys.stderr)
            raise

    @classmethod
    def tearDownClass(cls):
        """Stops the Redis container after all tests are done."""
        print("\n[E2E Test] Stopping Redis container...")
        compose_file_path = os.path.join(os.path.dirname(__file__), '..', 'docker-compose.yml')
        subprocess.run(["docker", "compose", "-f", compose_file_path, "down"], capture_output=True)

    @classmethod
    def wait_for_redis(cls, retries=10, delay=2):
        """Waits for the Redis container to become available."""
        for i in range(retries):
            try:
                # Use DB 1 for testing
                r = redis.Redis(host='localhost', port=6379, db=1)
                if r.ping():
                    print("[E2E Test] Redis is ready.")
                    return
            except redis.exceptions.ConnectionError:
                time.sleep(delay)
        raise ConnectionError("Could not connect to Redis container after multiple retries.")

    def setUp(self):
        """
        Set up the test environment by starting the necessary agents in
        separate threads.
        """
        self.job_id = str(uuid.uuid4())
        
        # Connect to the test DB
        self.redis_client = redis.Redis(host='localhost', port=6379, db=1, decode_responses=True)
        self.redis_client.flushdb()

        # Load agent configuration from the default file
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'agent_library.yml.default')
        if not os.path.exists(config_path):
            self.fail(f"Default agent config not found at {config_path}")
        with open(config_path, 'r') as f:
            full_config = yaml.safe_load(f)

        # Get configs for specific agents
        kintai_config = full_config['kintaikun'].copy()
        manager_config = full_config['team_manager'].copy()

        # Override names for test isolation
        self.kintai_agent_name = "Kintaikun_E2E"
        self.team_manager_name = "TeamManager_E2E"
        self.user_agent_name = "User_E2E"
        
        kintai_config['name'] = self.kintai_agent_name
        kintai_config['memory_id'] = f"{self.kintai_agent_name}:e2e-project"
        kintai_config.pop('type', None) # Remove key not accepted by __init__
        kintai_config['redis_db'] = 1 # Use test DB

        manager_config['name'] = self.team_manager_name
        manager_config['memory_id'] = f"{self.team_manager_name}:e2e-project"
        manager_config.pop('type', None) # Remove key not accepted by __init__
        manager_config['redis_db'] = 1 # Use test DB
        
        # Override role_prompt for this specific test scenario
        manager_config['role_prompt'] = (
            "You are a Team Manager. If a user asks about team members and mentions "
            f"'{self.kintai_agent_name}', you MUST ask '{self.kintai_agent_name}' for the list of active agents. "
            "After receiving the list, you MUST report that information back to the user in Japanese."
        )

        self.broker = RedisBroker(db=1) # Use test DB
        self.broker.connect()
        self.pubsub = self.broker.client.pubsub()

        self.agents = []
        self.threads = []

        # 1. Start KintaiAgent
        self.kintai_agent = KintaiAgent(**kintai_config)
        self._start_agent(self.kintai_agent)

        # 2. Start TeamManager
        self.team_manager = RoleBasedGeminiCliAgent(**manager_config)
        self._start_agent(self.team_manager)

        # Allow agents time to initialize and subscribe
        time.sleep(5)

    def tearDown(self):
        """
        Clean up by shutting down all agents and stopping the listener.
        """
        for agent in self.agents:
            agent.shutdown()
        for thread in self.threads:
            thread.join(timeout=5)
        
        if self.pubsub:
            self.pubsub.unsubscribe()
            self.pubsub.close()
        
        if self.broker:
            self.broker.disconnect()

    def _start_agent(self, agent):
        """Starts a given agent in a new thread."""
        self.agents.append(agent)
        thread = threading.Thread(target=agent.observe_loop, daemon=True)
        thread.start()
        self.threads.append(thread)

    def test_team_member_query_scenario(self):
        """
        Executes the full E2E test scenario using a pubsub.listen() loop.
        """
        # --- Wait for the final response from TeamManager ---
        timeout_seconds = 60 # Increase timeout for E2E test
        final_response = None
        start_time = time.time()
        
        # Subscribe *before* publishing the initial message to avoid race conditions
        self.pubsub.subscribe(self.broker.channel)

        # --- Step 1: User sends initial message to TeamManager ---
        initial_message = Message(
            from_agent=self.user_agent_name,
            to_agent=self.team_manager_name,
            content=f"チームメンバーを教えて。{self.kintai_agent_name}が知っている",
            job_id=self.job_id
        )
        self.broker.publish(initial_message.to_json())

        for message in self.pubsub.listen():
            if time.time() - start_time > timeout_seconds:
                break
            
            # Ignore non-message types (like subscribe, pmessage, etc.)
            if message['type'] != 'message':
                continue
            
            try:
                msg = Message.from_json(message['data'])
                # Listen for the final response from the TeamManager to the User
                if (msg.from_agent == self.team_manager_name and 
                    msg.to_agent == self.user_agent_name and 
                    msg.job_id == self.job_id):
                    final_response = msg
                    break
            except (json.JSONDecodeError, KeyError):
                continue
        
        # --- Step 4: Assertions ---
        self.assertIsNotNone(final_response, f"E2E test timed out after {timeout_seconds} seconds. No final response received.")
        
        response_content = final_response.content
        print(f"\n[Test Result] Final Response from {final_response.from_agent}: {response_content}\n")
        
        # LLMの応答なので、キーワードで検証
        self.assertIn(self.team_manager_name, response_content, "Response should mention the TeamManager.")
        self.assertIn(self.kintai_agent_name, response_content, "Response should mention Kintaikun.")
        self.assertRegex(response_content, "アクティブ|active", "Response should mention active agents.")

if __name__ == "__main__":
    unittest.main()
