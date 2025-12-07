import unittest
import time
import threading
from unittest.mock import patch

from ai_masa.agents.logging_agent import LoggingAgent
from ai_masa.models.message import Message
from ai_masa.comms.redis_broker import RedisBroker

class TestLoggingAgentIntegration(unittest.TestCase):

    def setUp(self):
        """Set up for integration test with a real Redis connection."""
        self.redis_host = 'localhost'
        self.agent = LoggingAgent(redis_host=self.redis_host)
        
        # Publisher for tests
        self.publisher = RedisBroker(host=self.redis_host)
        self.publisher.connect()

        # Start agent's listening loop in a background thread
        self.agent_thread = threading.Thread(target=self.agent.observe_loop, daemon=True)
        self.agent_thread.start()
        
        # Give a moment for the subscriber to be ready
        time.sleep(0.1) 

    def tearDown(self):
        """Clean up resources after tests."""
        # Signal the agent's loops to stop
        self.agent.shutdown()
        # Wait for the agent thread to terminate
        self.agent_thread.join(timeout=2)
        # Now that the thread is stopped, we can safely disconnect
        self.agent.broker.disconnect()
        self.publisher.disconnect()

    @patch('builtins.print')
    def test_logs_message_published_to_redis(self, mock_print):
        """Test that a message published to Redis is logged by the agent."""
        msg = Message(
            from_agent="TestPublisher",
            to_agent="AnyAgent",
            content="Live Redis Test",
            job_id="live-job-1"
        )
        
        # Publish the message
        self.publisher.publish(msg.to_json())
        
        # Wait for the agent to process the message
        time.sleep(0.2) 

        # Verify that print was called with the correct format
        # We can't check the timestamp exactly, so we check the other parts.
        self.assertTrue(mock_print.called)
        
        # Get the actual call arguments
        actual_output = mock_print.call_args[0][0]
        
        # Check for the presence of the key components of the message
        self.assertIn("[live-job-1]", actual_output)
        self.assertIn("TestPublisher -> AnyAgent:", actual_output)
        self.assertIn("Live Redis Test", actual_output)

if __name__ == '__main__':
    unittest.main()
