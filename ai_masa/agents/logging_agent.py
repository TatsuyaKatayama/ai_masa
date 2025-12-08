from datetime import datetime
from ..models.message import Message
from .listener_agent import ListenerAgent

class LoggingAgent(ListenerAgent):
    def __init__(self, name="Logger", description="An agent that logs all messages.", **kwargs):
        # LoggingAgentはハートビート不要のためFalseに設定
        super().__init__(name, description, start_heartbeat=False, **kwargs)

    def _handle_message(self, msg: Message):
        """
        Handles incoming messages and logs them.
        """
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cc_info = f" (CC: {', '.join(msg.cc_agents)})" if msg.cc_agents else ""
        
        # _broadcast_と_heartbeat_はシステムメッセージなのでログ出力から除外
        if msg.to_agent in ["_broadcast_", "_heartbeat_"] or \
           (msg.cc_agents and "_broadcast_" in msg.cc_agents):
            return
            
        print(f"[{timestamp}][{msg.job_id}] {msg.from_agent} -> {msg.to_agent}{cc_info}: {msg.content}")

if __name__ == "__main__":
    ListenerAgent.main(LoggingAgent)