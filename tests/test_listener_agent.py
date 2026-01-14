import unittest
from unittest.mock import MagicMock, patch, call
import json
import sys

from ai_masa.agents.listener_agent import ListenerAgent
from ai_masa.models.message import Message

# ListenerAgentを継承するダミークラスを定義
class ConcreteListenerAgent(ListenerAgent):
    def __init__(self, name, description, memory_id, **kwargs):
        super().__init__(name, description, memory_id=memory_id, **kwargs)
        self.handled_messages = []

    def think_and_respond(self, trigger_msg: Message, job_id: str, is_observer: bool = False):
        self.handled_messages.append(trigger_msg)

class TestListenerAgent(unittest.TestCase):

    def setUp(self):
        self.mock_broker_patcher = patch('ai_masa.agents.base_agent.RedisBroker')
        self.mock_memory_manager_patcher = patch('ai_masa.agents.base_agent.MemoryManager')
        self.mock_base_agent_start_heartbeat_patcher = patch('ai_masa.agents.base_agent.BaseAgent._start_heartbeat')

        self.MockRedisBroker = self.mock_broker_patcher.start()
        self.MockMemoryManager = self.mock_memory_manager_patcher.start()
        self.mock_base_agent_start_heartbeat = self.mock_base_agent_start_heartbeat_patcher.start()

        self.mock_broker_instance = self.MockRedisBroker.return_value
        self.mock_memory_manager_instance = self.MockMemoryManager.return_value

        self.agent = ConcreteListenerAgent(
            name="TestListener",
            description="A test listener agent.",
            memory_id="TestListener:test_project",
            memory_manager=self.mock_memory_manager_instance
        )

    def tearDown(self):
        self.mock_broker_patcher.stop()
        self.mock_memory_manager_patcher.stop()
        self.mock_base_agent_start_heartbeat_patcher.stop()

    def test_on_message_received_calls_think_and_respond(self):
        """
        _on_message_receivedがBaseAgentのロジックを呼び出し、think_and_respondが呼ばれるかテスト。
        """
        trigger_message = Message("User", "TestListener", "Hello Listener", job_id="job-1").to_json()
        
        with patch.object(self.agent, 'think_and_respond', wraps=self.agent.think_and_respond) as mock_think:
            self.agent._on_message_received(trigger_message)
            
            # think_and_respondが呼ばれたことを確認
            mock_think.assert_called_once()
            
            # MemoryManagerにメッセージが追加されたことを確認
            self.mock_memory_manager_instance.add_message.assert_called_once_with("TestListener:test_project", json.loads(trigger_message))

            # メッセージが処理されたことを確認
            self.assertEqual(len(self.agent.handled_messages), 1)
            self.assertEqual(self.agent.handled_messages[0].content, "Hello Listener")

    def test_on_message_received_ignores_own_messages(self):
        """
        ListenerAgentは自身の送信メッセージを処理しないことをテスト (BaseAgentが既にフィルタリング)。
        """
        own_message = Message("TestListener", "User", "My message", job_id="job-2").to_json()
        self.agent._on_message_received(own_message)
        
        self.mock_memory_manager_instance.add_message.assert_not_called()
        self.assertEqual(len(self.agent.handled_messages), 0)

    def test_on_message_received_ignores_heartbeats(self):
        """
        ハートビートメッセージはthink_and_respondに渡されないことをテスト。
        """
        heartbeat_msg = Message("AgentA", "AgentA", "heartbeat", cc_agents=["_broadcast_", "TestListener"], job_id="_system_").to_json()
        with patch.object(self.agent, 'think_and_respond') as mock_think:
            self.agent._on_message_received(heartbeat_msg)
            
            self.mock_memory_manager_instance.add_message.assert_called_once()
            # think_and_respondは呼ばれない
            mock_think.assert_not_called()
            self.assertEqual(len(self.agent.handled_messages), 0)
