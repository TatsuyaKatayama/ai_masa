import sys
import uuid
import threading
from .base_agent import BaseAgent
from ..models.message import Message

class UserInputAgent(BaseAgent):
    """
    ユーザーからのコンソール入力を受け付け、他のエージェントにメッセージを送信するエージェント。
    LLMは使用しない。
    """
    def __init__(self, name="UserInputAgent", redis_host='localhost', default_target_agent="GeminiCliAgent"):
        # LLM関連のコマンドは不要なため、親クラスの初期化時にダミー値を渡す
        super().__init__(
            name=name,
            description="Handles user input from the console.",
            redis_host=redis_host,
            llm_command="",
            llm_session_create_command=""
        )
        self.default_target_agent = default_target_agent
        self.shutdown_event = threading.Event()
        self.response_received_event = threading.Event()
        self.response_received_event.set()  # 最初は入力可能にする
        print(f"[{self.name}] Initialized. I will send messages to '{self.default_target_agent}'.")

    def think_and_respond(self, trigger_msg, job_id, is_observer=False):
        # このエージェントはLLMによる思考を行わない
        pass

    def _on_message_received(self, message_json):
        # 自分宛のメッセージやCCはコンソールに表示するだけ
        try:
            msg = Message.from_json(message_json)
            if msg.from_agent == self.name:
                return # 自分が送信したメッセージは無視

            job_id = msg.job_id or "default"
            
            is_to_me = msg.to_agent == self.name
            if is_to_me:
                # 自分宛のメッセージが来たら、表示して入力ブロックを解除
                print(f"\n[{self.name}][{job_id}] 📨 Received from {msg.from_agent}: {msg.content}")
                self.response_received_event.set()
            elif self.name in msg.cc_agents:
                 # CCの場合は表示するだけ
                 print(f"\n[{self.name}][{job_id}] 👀 (CC) Saw message from {msg.from_agent} to {msg.to_agent}: {msg.content}")

        except Exception as e:
            print(f"[{self.name}] Error in _on_message_received: {e}")

    def start_interaction(self):
        """
        メッセージ受信を別スレッドで開始し、メインスレッドでユーザー入力を処理する。
        """
        # メッセージ受信ループをデーモンスレッドで開始
        observer_thread = threading.Thread(target=self.observe_loop, daemon=True)
        observer_thread.start()

        self._input_loop()
        
        # 終了処理
        self.shutdown_event.set()
        self.broker.disconnect()
        print(f"[{self.name}] Shutting down.")

    def _input_loop(self):
        """
        ユーザーからの入力を受け付け、メッセージをブロードキャストするループ。
        返信があるまで次の入力を待つ。
        """
        print(f"[{self.name}] Starting user input loop. Press Ctrl+C or type 'quit' to exit.")
        job_id = str(uuid.uuid4()) # 会話の開始時に新しいJOB IDを生成
        print(f"A new job has started. Job ID: {job_id}")

        while not self.shutdown_event.is_set():
            try:
                # 返信が来るまで待機
                self.response_received_event.wait()

                # ユーザーに行動を促す
                print("\nEnter your message (or type 'newjob' to start a new conversation): ", end="")
                user_input = sys.stdin.readline().strip()

                if not user_input:
                    continue
                
                if user_input.lower() == 'quit':
                    break
                
                if user_input.lower() == 'newjob':
                    job_id = str(uuid.uuid4())
                    print(f"\nA new job has started. Job ID: {job_id}")
                    continue

                # メッセージを送信する直前に入力をブロック
                self.response_received_event.clear()
                self.broadcast(
                    target=self.default_target_agent,
                    content=user_input,
                    job_id=job_id
                )
                print(f"[{self.name}] Waiting for a response...")

            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"[{self.name}] An error occurred in input loop: {e}")

    def observe_loop(self):
        """
        Redisからのメッセージを継続的に監視する。
        """
        print(f"[{self.name}] Listening for responses on Redis...")
        self.broker.subscribe(self._on_message_received, self.shutdown_event)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: python -m ai_masa.agents.user_input_agent <AgentName> [DefaultTargetAgent]")
        sys.exit(1)

    agent = UserInputAgent(
        name=sys.argv[1],
        default_target_agent=sys.argv[2] if len(sys.argv) > 2 else 'GeminiCliAgent'
    )
    agent.start_interaction()
