from datetime import datetime, timedelta
import argparse
from ..models.message import Message
from .listener_agent import ListenerAgent

class KintaiAgent(ListenerAgent):
    def __init__(self, name: str = "KintaiAgent", description: str = "An agent that tracks active agents via heartbeats.",
                 user_lang: str = 'Japanese', memory_id: str = "listener_memory",
                 redis_host: str = 'localhost', redis_port: int = 6379, redis_db: int = 0,
                 heartbeat_timeout: int = 30, **kwargs):
        
        # KintaiAgent自身はハートビートを送信しないため、start_heartbeat=Falseに設定
        super().__init__(
            name=name,
            description=description,
            user_lang=user_lang,
            memory_id=memory_id,
            redis_host=redis_host,
            redis_port=redis_port,
            redis_db=redis_db,
            start_heartbeat=False,
            **kwargs # ListenerAgentに渡さない追加のkwargsはここで処理される
        )
        
        self.active_agents = {}  # agent_name: last_heartbeat_timestamp
        self.heartbeat_timeout = timedelta(seconds=heartbeat_timeout)

    def _handle_message(self, msg: Message):
        """
        Handles incoming messages for heartbeat tracking and status queries.
        """
        # ハートビートメッセージを内容とCCで判定
        if msg.content == 'heartbeat' and msg.cc_agents and '_broadcast_' in msg.cc_agents:
            self.active_agents[msg.from_agent] = datetime.now()
            # inactive agentのクリーンアップはハートビート受信時に行うのが効率的
            self._cleanup_inactive_agents()
            return

        # 自分宛のメッセージでなければ無視
        # BaseAgentの_on_message_receivedで既にフィルタリングされているため、ここには自分宛のメッセージかCCメッセージのみが来る
        # ListenerAgentの_handle_messageは自分宛のメッセージのみを処理する想定であれば、以下が必要
        if msg.to_agent != self.name:
            return

        # 自分宛のメッセージであれば、キーワードに関わらず応答する
        self._respond_to_status_query(msg)

    def _cleanup_inactive_agents(self):
        """Removes agents that have not sent a heartbeat within the timeout period."""
        now = datetime.now()
        inactive_agents = [
            agent for agent, last_seen in self.active_agents.items()
            if now - last_seen > self.heartbeat_timeout
        ]
        for agent in inactive_agents:
            if agent == self.name: # 自身はタイムアウト対象外
                continue
            del self.active_agents[agent]

    def _respond_to_status_query(self, trigger_msg: Message):
        """
        Sends a list of currently active agents.
        """
        self._cleanup_inactive_agents()  # Update list before responding
        
        # 自分自身もリストに含める
        self.active_agents[self.name] = datetime.now()
        agent_list = sorted(list(self.active_agents.keys()))
        
        if not agent_list:
            response_content = f"I am {self.name}, a bot. Currently, no other agents are active."
        else:
            response_content = f"I am {self.name}, a bot. The following agents are currently active:\n- " + "\n- ".join(agent_list)
        
        self.broadcast(
            target=trigger_msg.from_agent,
            content=response_content,
            job_id=trigger_msg.job_id
        )

if __name__ == "__main__":
    # ListenerAgent.main()を使用するため、ここでは追加の引数を定義するのみ
    parser = argparse.ArgumentParser(description="Run a KintaiAgent.")
    parser.add_argument("name", type=str, help="The name of the agent.")
    parser.add_argument("description", type=str, nargs='?', 
                        default="An agent that tracks active agents via heartbeats.", 
                        help="Description of the agent.")
    parser.add_argument("--user_lang", type=str, default="Japanese", help="Language for user interaction.")
    parser.add_argument("--memory_id", type=str, required=True, help="Memory ID for the agent's history.")
    parser.add_argument("--redis_host", type=str, default="localhost", help="Redis host.")
    parser.add_argument("--redis_port", type=int, default=6379, help="Redis port.")
    parser.add_argument("--redis_db", type=int, default=0, help="Redis DB.")
    parser.add_argument("--heartbeat_timeout", type=int, default=30, help="Timeout in seconds for agent heartbeats.")

    # ListenerAgent.mainに引数を渡し、そこでパースとエージェントの起動を行う
    ListenerAgent.main(KintaiAgent)