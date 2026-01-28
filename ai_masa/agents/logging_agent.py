import argparse
import json
from datetime import datetime
from ..models.message import Message
from .listener_agent import ListenerAgent

class LoggingAgent(ListenerAgent):
    def __init__(self, name: str = "Logger", description: str = "An agent that logs all messages.",
                 user_lang: str = 'Japanese', memory_id: str = "listener_memory",
                 redis_host: str = 'localhost', redis_port: int = 6379, redis_db: int = 0,
                 start_heartbeat: bool = False, working_dir: str = ".", **kwargs):
        # LoggingAgentはハートビート不要のためFalseに設定
        super().__init__(
            name=name,
            description=description,
            user_lang=user_lang,
            memory_id=memory_id,
            redis_host=redis_host,
            redis_port=redis_port,
            redis_db=redis_db,
            start_heartbeat=False,
            **kwargs
        )
        self.working_dir = working_dir
        self.log_dir = f"{self.working_dir}/logs"
        import os
        os.makedirs(self.log_dir, exist_ok=True)
        self.log_files = {}

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
                self.memory_manager.add_message(self.memory_id, json.loads(message_json))

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

        if msg.job_id not in self.log_files:
            self.log_files[msg.job_id] = f"{self.log_dir}/{datetime.now().strftime('%Y%m%d_%H%M%S')}_{msg.job_id}.jsonl"
        
        log_file_path = self.log_files[msg.job_id]
        with open(log_file_path, "a", encoding="utf-8") as f:
            f.write(msg.to_json() + "\n")
        
        # コンソール出力も残しておく（デバッグ用）
        print(f"[{timestamp}][{msg.job_id}] {msg.from_agent} -> {msg.to_agent}{cc_info}: {msg.content}")

if __name__ == "__main__":
    # ListenerAgent.mainが、ここで定義されていない引数もkwargsとして
    # agent_classのコンストラクタに渡してくれる。
    # そのため、ここでは何もせずmainを呼び出すだけで良い。
    ListenerAgent.main(LoggingAgent)