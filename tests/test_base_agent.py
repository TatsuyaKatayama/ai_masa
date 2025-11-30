import unittest
from unittest.mock import patch, MagicMock, call
import json
import subprocess

from ai_masa.base_agent import BaseAgent
from ai_masa.models.message import Message
from ai_masa.prompts import OBSERVER_INSTRUCTIONS

class TestBaseAgentWithSession(unittest.TestCase):

    @patch('subprocess.run')
    @patch('ai_masa.base_agent.RedisBroker')
    def test_new_job_creates_session_and_responds(self, MockRedisBroker, mock_subprocess_run):
        mock_broker_instance = MockRedisBroker.return_value
        llm_response_json = json.dumps({"to_agent": "User", "content": "初めまして、TestAgentです。"})
        mock_subprocess_run.side_effect = [
            subprocess.CompletedProcess(args='create_session_cmd', returncode=0, stdout='session-12345', stderr=''),
            subprocess.CompletedProcess(args='gemini -r session-12345', returncode=0, stdout=llm_response_json, stderr='')
        ]
        agent = BaseAgent("TestAgent", "あなたはテストエージェントです。", llm_command="gemini -r {session_id}", llm_session_create_command="create_session_cmd")
        trigger_message = Message(from_agent="User", to_agent="TestAgent", content="こんにちは", job_id="job-abc")
        agent._on_message_received(trigger_message.to_json())
        self.assertEqual(mock_subprocess_run.call_count, 2)
        calls = mock_subprocess_run.call_args_list
        self.assertEqual(calls[0].args[0], 'create_session_cmd')
        self.assertEqual(calls[1].args[0], 'gemini -r session-12345')
        self.assertEqual(agent.job_sessions['job-abc'], 'session-12345')
        mock_broker_instance.publish.assert_called_once()
        published_data = json.loads(mock_broker_instance.publish.call_args[0][0])
        self.assertEqual(published_data['content'], "初めまして、TestAgentです。")

    @patch('subprocess.run')
    @patch('ai_masa.base_agent.RedisBroker')
    def test_existing_job_uses_same_session(self, MockRedisBroker, mock_subprocess_run):
        mock_broker_instance = MockRedisBroker.return_value
        llm_response_json = json.dumps({"to_agent": "User", "content": "はい、同じセッションで応答しています。"})
        mock_subprocess_run.return_value = subprocess.CompletedProcess(args='gemini -r session-existing', returncode=0, stdout=llm_response_json, stderr='')
        agent = BaseAgent("TestAgent", "あなたはテストエージェントです。", llm_command="gemini -r {session_id}")
        agent.job_sessions['job-xyz'] = 'session-existing'
        trigger_message = Message(from_agent="User", to_agent="TestAgent", content="調子はどう？", job_id="job-xyz")
        agent._on_message_received(trigger_message.to_json())
        mock_subprocess_run.assert_called_once()
        self.assertEqual(mock_subprocess_run.call_args.args[0], 'gemini -r session-existing')
        mock_broker_instance.publish.assert_called_once()
        published_data = json.loads(mock_broker_instance.publish.call_args[0][0])
        self.assertEqual(published_data['content'], "はい、同じセッションで応答しています。")

    @patch('subprocess.run')
    @patch('ai_masa.base_agent.RedisBroker')
    def test_cc_message_triggers_observer_prompt(self, MockRedisBroker, mock_subprocess_run):
        mock_broker_instance = MockRedisBroker.return_value
        llm_response_json = json.dumps({"to_agent": "", "content": ""})
        mock_subprocess_run.return_value = subprocess.CompletedProcess(args='gemini -r session-cc', returncode=0, stdout=llm_response_json, stderr='')
        agent = BaseAgent("ObserverAgent", "あなたは会話を監視するエージェントです。", llm_command="gemini -r {session_id}")
        agent.job_sessions['job-cc-test'] = 'session-cc'
        trigger_message = Message("AgentA", "AgentB", "進めておいてください。", cc_agents=["ObserverAgent"], job_id="job-cc-test")
        agent._on_message_received(trigger_message.to_json())
        mock_subprocess_run.assert_called_once()
        prompt = mock_subprocess_run.call_args.kwargs['input']
        self.assertIn(OBSERVER_INSTRUCTIONS['ja'], prompt)
        mock_broker_instance.publish.assert_not_called()

    @patch('subprocess.run')
    @patch('ai_masa.base_agent.RedisBroker')
    def test_multi_agent_conversation_with_cc_context(self, MockRedisBroker, mock_subprocess_run):
        job_id = "job-nabla-chan"
        mock_broker_instance = MockRedisBroker.return_value

        def mock_llm_logic(args, input, **kwargs):
            prompt = input
            if "あなたの名前はナブラ" in prompt and "あなたの名前と特技は？" in prompt:
                response = {"to_agent": "User", "cc_agents": ["Agent2"], "content": "名前はナブラ。特技は計算"}
                return subprocess.CompletedProcess(args=args, returncode=0, stdout=json.dumps(response), stderr='')
            if "あなたは優秀なアシスタントです" in prompt and "ナブラちゃんの特技は？" in prompt:
                response = {"to_agent": "User", "content": "計算"}
                return subprocess.CompletedProcess(args=args, returncode=0, stdout=json.dumps(response), stderr='')
            return subprocess.CompletedProcess(args=args, returncode=0, stdout='{"to_agent":""}', stderr='Observing')

        mock_subprocess_run.side_effect = mock_llm_logic

        agent1 = BaseAgent("Agent1", "あなたの名前はナブラ。計算が得意です。", llm_command="gemini -r {session_id}")
        agent2 = BaseAgent("Agent2", "あなたは優秀なアシスタントです。", llm_command="gemini -r {session_id}")
        agent1.job_sessions[job_id] = 'session-nabla'
        agent2.job_sessions[job_id] = 'session-nabla'

        msg1 = Message("User", "Agent1", "あなたの名前と特技は？", job_id=job_id, cc_agents=["Agent2"])
        agent1._on_message_received(msg1.to_json())
        agent2._on_message_received(msg1.to_json())

        agent1_response_json = mock_broker_instance.publish.call_args[0][0]
        agent2._on_message_received(agent1_response_json)

        msg2 = Message("User", "Agent2", "ナブラちゃんの特技は？", job_id=job_id)
        agent2._on_message_received(msg2.to_json())

        final_response_data = json.loads(mock_broker_instance.publish.call_args[0][0])
        self.assertEqual(final_response_data['from_agent'], "Agent2")
        self.assertEqual(final_response_data['content'], "計算")
        self.assertEqual(mock_broker_instance.publish.call_count, 2)

if __name__ == '__main__':
    unittest.main()
