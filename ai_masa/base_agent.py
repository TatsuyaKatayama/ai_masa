import sys
from .models.message import Message
from .comms.redis_broker import RedisBroker

class BaseAgent:
    def __init__(self, name, role_prompt, redis_host='localhost'):
        self.name = name
        self.role_prompt = role_prompt
        self.context = []
        
        # RedisBrokerを使用
        self.broker = RedisBroker(host=redis_host)
        self.broker.connect()

    def observe_loop(self):
        """受信待機ループ開始"""
        print(f"[{self.name}] Listening on Redis...")
        # ブロッキング処理のため、メインスレッドはここで止まる
        self.broker.subscribe(self._on_message_received)

    def _on_message_received(self, message_json):
        """受信時のコールバック"""
        try:
            msg = Message.from_json(message_json)
            
            # 自分宛て判定 (送信元が自分の場合は無視)
            if msg.from_agent == self.name:
                return

            is_to_me = msg.to_agent == self.name
            is_cc_me = self.name in msg.cc_agents

            if is_to_me or is_cc_me:
                self.context.append(msg)
                
                if is_to_me:
                    print(f"[{self.name}] 📨 Received from {msg.from_agent}: {msg.content}")
                    self.think_and_respond(msg)
                else:
                    print(f"[{self.name}] 👀 (CC) Saw message from {msg.from_agent}")

        except Exception as e:
            print(f"[{self.name}] Error: {e}")

    def think_and_respond(self, trigger_msg):
        """LLM思考ロジックのスタブ"""
        # ここでGemini等を呼び出す
        pass

    def broadcast(self, target, content, cc=None):
        msg = Message(self.name, target, content, cc_agents=cc)
        self.broker.publish(msg.to_json())
        print(f"[{self.name}] 🚀 Sent to {target}: {content}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python -m ai_masa.base_agent <Name> <Role>")
        sys.exit(1)
    
    agent = BaseAgent(sys.argv[1], sys.argv[2])
    agent.observe_loop()
