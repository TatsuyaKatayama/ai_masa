import os
import unittest
import threading
import time
import uuid
import json
import yaml
from ai_masa.agents.kintai_agent import KintaiAgent
from ai_masa.agents.role_based_gemini_cli_agent import RoleBasedGeminiCliAgent
from ai_masa.comms.redis_broker import RedisBroker
from ai_masa.models.message import Message

class TestE2ETeamInteraction(unittest.TestCase):
    """
    Tests a full end-to-end scenario involving multiple agents coordinating
    to answer a user's query, inspired by test_gemini_cli_agent_integration.
    """
    def setUp(self):
        """
        Set up the test environment by starting the necessary agents in
        separate threads.
        """
        self.job_id = str(uuid.uuid4())
        
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
        manager_config['name'] = self.team_manager_name
        
        # Override role_prompt for this specific test scenario
        manager_config['role_prompt'] = (
            "You are a Team Manager. If a user asks about team members and mentions "
            f"'{self.kintai_agent_name}', you MUST ask '{self.kintai_agent_name}' for the list of active agents. "
            "After receiving the list, you MUST report that information back to the user in Japanese."
        )

        self.broker = RedisBroker()
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
        # --- Step 1: User sends initial message to TeamManager ---
        initial_message = Message(
            from_agent=self.user_agent_name,
            to_agent=self.team_manager_name,
            content=f"チームメンバーを教えて。{self.kintai_agent_name}が知っている",
            job_id=self.job_id
        )
        self.broker.publish(initial_message.to_json())

        # --- Wait for the final response from TeamManager ---
        timeout_seconds = 45
        final_response = None
        start_time = time.time()
        
        self.pubsub.subscribe(self.broker.channel)
        for message in self.pubsub.listen():
            if time.time() - start_time > timeout_seconds:
                break
            
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
