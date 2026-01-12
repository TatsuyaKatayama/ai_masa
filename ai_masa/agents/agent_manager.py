import sys
import threading
import time
import argparse

from .base_agent import BaseAgent
from ..models.message import Message

class AgentManager(BaseAgent):
    """
    他のエージェントの生存を監視し、状態を報告するエージェント。
    """
    def __init__(self, name: str = "AgentManager", description: str = "I am an agent manager, monitoring the status of other agents.",
                 session_id: str = "_system_manager_session_", redis_host: str = 'localhost', redis_port: int = 6379, redis_db: int = 0,
                 timeout_seconds: int = 60, **kwargs):
        super().__init__(
            name=name,
            description=description,
            session_id=session_id,
            redis_host=redis_host,
            redis_port=redis_port,
            redis_db=redis_db,
            start_heartbeat=False, # AgentManager自身は監視対象ではないのでハートビートは送信しない
            **kwargs
        )
        self.active_agents = {}  # { "agent_name": last_heartbeat_timestamp }
        self.timeout_seconds = timeout_seconds
        self.lock = threading.RLock()
        
        # タイムアウトしたエージェントを定期的にチェックするスレッドを開始
        self._start_monitoring()

    def _on_message_received(self, message_json: str):
        """
        メッセージを受信したときの処理をオーバーライド。
        ハートビートメッセージを特別に処理する。
        """
        try:
            msg = Message.from_json(message_json)

            # 自分自身のメッセージはBaseAgentで無視されるため、ここでは処理しない
            # if msg.from_agent == self.name:
            #     return
            
            # ブロードキャストCCがあれば、生存通知として記録
            if msg.cc_agents and "_broadcast_" in msg.cc_agents:
                with self.lock:
                    if msg.from_agent not in self.active_agents:
                        print(f"[{self.name}] ✅ New agent detected: {msg.from_agent}")
                    self.active_agents[msg.from_agent] = time.time()
            
            # 自分宛のメッセージであれば、通常の処理（思考など）を行う
            # BaseAgentの_on_message_receivedが_is_message_for_meでフィルタリングするため、
            # ここではsuper()を直接呼ぶ代わりに、_is_message_for_meの条件を再度チェックする。
            # これにより、BaseAgentのadd_messageロジックが適切に適用される。
            if self._is_message_for_me(msg):
                super()._on_message_received(message_json)

        except Exception as e:
            print(f"[{self.name}] Error in _on_message_received: {e}")
    
    def _start_monitoring(self):
        """タイムアウト監視ループを別スレッドで開始する"""
        monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        monitor_thread.start()

    def _monitor_loop(self, _run_once: bool = False):
        """アクティブなエージェントを監視し、タイムアウトしたものを報告する"""
        print(f"[{self.name}] Monitoring agent statuses...")
        while not self.shutdown_event.is_set():
            timed_out_agents = []
            with self.lock:
                now = time.time()
                for agent_name, last_seen in self.active_agents.items():
                    # AgentManager自身は監視対象外
                    if agent_name == self.name:
                        continue
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

    def think_and_respond(self, trigger_msg: Message, job_id: str, is_observer: bool = False):
        """
        AgentManagerは通常、自律的に思考しないが、
        ステータスを問い合わせられたら答えるようにできる。
        """
        if "status" in trigger_msg.content.lower():
            self.print_status(target=trigger_msg.from_agent, job_id=job_id)
        # BaseAgentのthink_and_respondを呼び出さないため、LLM呼び出しは発生しない

    def print_status(self, target: str = None, job_id: str = None):
        """現在のアクティブなエージェントの状況を表示または送信する"""
        with self.lock:
            # AgentManager自身もアクティブエージェントとしてリストに含める
            self.active_agents[self.name] = time.time()
            
            if not self.active_agents:
                status_report = "No active agents detected." # このパスは通常到達しない
            else:
                status_list = [f"- {name} (last seen {int(time.time() - ts)}s ago)" 
                               for name, ts in sorted(self.active_agents.items())]
                status_report = "Active agents:\n" + "\n".join(status_list)

        if target:
            self.broadcast(target, status_report, job_id=job_id)
        else:
            print(f"\n--- Agent Status ---\n{status_report}\n--------------------")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the AgentManager.")
    parser.add_argument("name", type=str, nargs='?', default="AgentManager", help="Name of the agent (default: AgentManager)")
    parser.add_argument("--description", type=str, default="I am an agent manager, monitoring the status of other agents.", help="Description of the agent")
    parser.add_argument("--session_id", type=str, default="_system_manager_session_", help="Session ID for the agent's history")
    parser.add_argument("--redis_host", type=str, default="localhost", help="Redis host")
    parser.add_argument("--redis_port", type=int, default=6379, help="Redis port")
    parser.add_argument("--redis_db", type=int, default=0, help="Redis DB")
    parser.add_argument("--timeout_seconds", type=int, default=60, help="Timeout for agent heartbeats in seconds")

    args = parser.parse_args()

    agent = AgentManager(
        name=args.name,
        description=args.description,
        session_id=args.session_id,
        redis_host=args.redis_host,
        redis_port=args.redis_port,
        redis_db=args.redis_db,
        timeout_seconds=args.timeout_seconds
    )
    try:
        agent.observe_loop()
    except KeyboardInterrupt:
        print(f"[{agent.name}] Shutting down.")
    finally:
        agent.shutdown() # Ensure proper shutdown, including stopping heartbeats
        agent.broker.disconnect()
