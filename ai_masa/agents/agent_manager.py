import sys
import threading
import time
from .base_agent import BaseAgent
from ..models.message import Message

class AgentManager(BaseAgent):
    """
    他のエージェントの生存を監視し、状態を報告するエージェント。
    """
    def __init__(self, name="AgentManager", redis_host='localhost', timeout_seconds=60):
        super().__init__(
            name=name,
            description="I am an agent manager, monitoring the status of other agents.",
            redis_host=redis_host
        )
        self.active_agents = {}  # { "agent_name": last_heartbeat_timestamp }
        self.timeout_seconds = timeout_seconds
        self.lock = threading.RLock()
        
        # タイムアウトしたエージェントを定期的にチェックするスレッドを開始
        self._start_monitoring()

    def _on_message_received(self, message_json):
        """
        メッセージを受信したときの処理をオーバーライド。
        ハートビートメッセージを特別に処理する。
        """
        try:
            msg = Message.from_json(message_json)
            
            # ブロードキャストCCがあれば、生存通知として記録
            if "_broadcast_" in msg.cc_agents:
                with self.lock:
                    if msg.from_agent not in self.active_agents:
                        print(f"[{self.name}] ✅ New agent detected: {msg.from_agent}")
                    self.active_agents[msg.from_agent] = time.time()
            
            # 自分宛のメッセージであれば、通常の処理（思考など）を行う
            if msg.to_agent == self.name and msg.from_agent != self.name:
                super()._on_message_received(message_json)

        except Exception as e:
            print(f"[{self.name}] Error in _on_message_received: {e}")
    
    def _start_monitoring(self):
        """タイムアウト監視ループを別スreadで開始する"""
        monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        monitor_thread.start()

    def _monitor_loop(self, _run_once=False):
        """アクティブなエージェントを監視し、タイムアウトしたものを報告する"""
        print(f"[{self.name}] Monitoring agent statuses...")
        while not self.shutdown_event.is_set():
            timed_out_agents = []
            with self.lock:
                now = time.time()
                for agent_name, last_seen in self.active_agents.items():
                    if now - last_seen > self.timeout_seconds:
                        timed_out_agents.append(agent_name)
                
                if timed_out_agents:
                    for agent_name in timed_out_agents:
                        print(f"[{self.name}] ❌ Agent timed out and removed: {agent_name}")
                        del self.active_agents[agent_name]
                    
                    # 変化があった場合にのみステータスを出力
                    self.print_status()
            
            if _run_once:
                break
            
            time.sleep(15) # 15秒ごとにチェック


    def think_and_respond(self, trigger_msg, job_id, is_observer=False):
        """
        AgentManagerは通常、自律的に思考しないが、
        ステータスを問い合わせられたら答えるようにできる。
        """
        if "status" in trigger_msg.content.lower():
            self.print_status(target=trigger_msg.from_agent, job_id=job_id)

    def print_status(self, target=None, job_id=None):
        """現在のアクティブなエージェントの状況を表示または送信する"""
        with self.lock:
            if not self.active_agents:
                status_report = "No active agents detected."
            else:
                status_list = [f"- {name} (last seen {int(time.time() - ts)}s ago)" for name, ts in self.active_agents.items()]
                status_report = "Active agents:\n" + "\n".join(status_list)

        if target:
            self.broadcast(target, status_report, job_id=job_id)
        else:
            print(f"\n--- Agent Status ---\n{status_report}\n--------------------")

if __name__ == "__main__":
    agent = AgentManager()
    # AgentManagerは主にリッスンするので、observe_loopを直接呼び出す
    try:
        agent.observe_loop()
    except KeyboardInterrupt:
        print(f"[{agent.name}] Shutting down.")
        agent.shutdown_event.set()
