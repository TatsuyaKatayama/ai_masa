from datetime import datetime, timedelta
from ..models.message import Message
from .listener_agent import ListenerAgent

class KintaiAgent(ListenerAgent):
    def __init__(self, name="KintaiAgent", description="An agent that tracks active agents via heartbeats.", **kwargs):
        # `heartbeat_timeout` をkwargsから取り出し、super()に渡さないようにする
        heartbeat_timeout_seconds = int(kwargs.pop('heartbeat_timeout', 30))
        # KintaiAgent自身はハートビートを送信しないため、start_heartbeat=Falseに設定
        super().__init__(name, description, start_heartbeat=False, **kwargs)
        
        self.active_agents = {}  # agent_name: last_heartbeat_timestamp
        # タイムアウトは環境変数や引数で設定可能にするとより堅牢
        self.heartbeat_timeout = timedelta(seconds=heartbeat_timeout_seconds)

    def _handle_message(self, msg: Message):
        """
        Handles incoming messages for heartbeat tracking and status queries.
        """
        # ハートビートメッセージを内容とCCで判定
        if msg.content == 'heartbeat' and msg.cc_agents and '_broadcast_' in msg.cc_agents:
            self.active_agents[msg.from_agent] = datetime.now()
            #  inactive agentのクリーンアップはハートビート受信時に行うのが効率的
            self._cleanup_inactive_agents()
            return

        # 自分宛のメッセージでなければ無視
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
        """Sends a list of currently active agents."""
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
    ListenerAgent.main(KintaiAgent)