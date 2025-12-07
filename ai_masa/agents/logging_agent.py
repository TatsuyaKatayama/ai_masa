import sys
import signal
import threading
from datetime import datetime
from ..models.message import Message
from .base_agent import BaseAgent

class LoggingAgent(BaseAgent):
    def __init__(self, name="Logger", description="An agent that logs all messages.", **kwargs):
        # LoggingAgentはハートビート不要のためFalseに設定
        super().__init__(name, description, start_heartbeat=False, **kwargs)

    def _on_message_received(self, message_json):
        try:
            msg = Message.from_json(message_json)
            # 自分のメッセージは無視 (ハートビートなど)
            if msg.from_agent == self.name:
                return

            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cc_info = f" (CC: {', '.join(msg.cc_agents)})" if msg.cc_agents else ""
            
            # _broadcast_はシステムメッセージなのでログ出力から除外
            if msg.to_agent == "_broadcast_" or (msg.cc_agents and "_broadcast_" in msg.cc_agents):
                return
                
            print(f"[{timestamp}][{msg.job_id}] {msg.from_agent} -> {msg.to_agent}{cc_info}: {msg.content}")

        except Exception as e:
            print(f"[{self.name}] Error in _on_message_received: {e}")

    def think_and_respond(self, trigger_msg, job_id, is_observer=False):
        # Logger agent does not respond to messages.
        pass

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m ai_masa.agents.logging_agent <AgentName>")
        sys.exit(1)

    agent_name = sys.argv[1]
    agent = LoggingAgent(name=agent_name)

    def signal_handler(sig, frame):
        print(f"[{agent_name}] Shutdown signal received. Stopping...")
        agent.shutdown()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print(f"[{agent_name}] Starting agent. Press Ctrl+C to stop.")
    try:
        # observe_loopはブロッキングメソッド
        agent.observe_loop()
    finally:
        agent.broker.disconnect()
        print(f"[{agent_name}] Agent stopped.")


