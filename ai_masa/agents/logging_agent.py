import argparse
import json
from datetime import datetime
from ..models.message import Message
from .listener_agent import ListenerAgent

class LoggingAgent(ListenerAgent):
    def __init__(self, name: str = "Logger", description: str = "An agent that logs all messages.",
                 user_lang: str = 'Japanese', session_id: str = "listener_session",
                 redis_host: str = 'localhost', redis_port: int = 6379, redis_db: int = 0,
                 **kwargs):
        # LoggingAgentはハートビート不要のためFalseに設定
        super().__init__(
            name=name,
            description=description,
            user_lang=user_lang,
            session_id=session_id,
            redis_host=redis_host,
            redis_port=redis_port,
            redis_db=redis_db,
            start_heartbeat=False,
            **kwargs
        )

    def _on_message_received(self, message_json: str):
        """
        Overrides the parent method to log all messages, regardless of recipient.
        """
        try:
            msg = Message.from_json(message_json)
            # Don't log its own messages
            if msg.from_agent == self.name:
                return
            
            # Log the message unconditionally
            self._handle_message(msg)

            # Also, save the message to its own history session if it was meant for this agent (e.g., CC'd)
            # This re-uses the logic from BaseAgent without calling think_and_respond
            if self._is_message_for_me(msg):
                self.session_manager.add_message(self.session_id, json.loads(message_json))

        except Exception as e:
            print(f"[{self.name}] Error in _on_message_received: {e}")

    def _handle_message(self, msg: Message):
        """
        Handles incoming messages and logs them.
        """
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cc_info = f" (CC: {', '.join(msg.cc_agents)})" if msg.cc_agents else ""
        
        # _broadcast_と_heartbeat_はシステムメッセージなのでログ出力から除外
        if msg.to_agent in ["_broadcast_", "_heartbeat_"] or \
           (msg.cc_agents and "_broadcast_" in msg.cc_agents) or \
           (msg.content == "heartbeat" and (msg.job_id == "_system_" or "_broadcast_" in (msg.cc_agents or []))):
            return
            
        print(f"[{timestamp}][{msg.job_id}] {msg.from_agent} -> {msg.to_agent}{cc_info}: {msg.content}")

if __name__ == "__main__":
    # ListenerAgent.main()を使用するため、ここでは追加の引数を定義するのみ
    parser = argparse.ArgumentParser(description="Run a LoggingAgent.")
    parser.add_argument("name", type=str, help="The name of the agent.")
    parser.add_argument("description", type=str, nargs='?', 
                        default="An agent that logs all messages.", 
                        help="Description of the agent.")
    parser.add_argument("--user_lang", type=str, default="Japanese", help="Language for user interaction.")
    parser.add_argument("--session_id", type=str, required=True, help="Session ID for the agent's history.")
    parser.add_argument("--redis_host", type=str, default="localhost", help="Redis host.")
    parser.add_argument("--redis_port", type=int, default=6379, help="Redis port.")
    parser.add_argument("--redis_db", type=int, default=0, help="Redis DB.")

    # ListenerAgent.mainに引数を渡し、そこでパースとエージェントの起動を行う
    ListenerAgent.main(LoggingAgent)