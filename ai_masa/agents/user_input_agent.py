import sys
import uuid
import threading
import argparse
from typing import Optional, List, Dict, Any
from .base_agent import BaseAgent
from ..models.message import Message

class UserInputAgent(BaseAgent):
    """
    ユーザーからのコンソール入力を受け付け、他のエージェントにメッセージを送信するエージェント。
    LLMは使用しない。
    """
    def __init__(self, name: str = "UserInputAgent", description: str = "Handles user input from the console.",
                 user_lang: str = 'Japanese', memory_id: str = "user_input_memory",
                 redis_host: str = 'localhost', redis_port: int = 6379, redis_db: int = 0,
                 default_target_agent: Optional[str] = None, **kwargs):
        
        # LLM関連のコマンドは不要なため、親クラスの初期化時にダミー値を渡す
        super().__init__(
            name=name,
            description=description,
            user_lang=user_lang,
            memory_id=memory_id,
            redis_host=redis_host,
            redis_port=redis_port,
            redis_db=redis_db,
            llm_command="echo '{\"to_agent\": \"dummy\", \"content\": \"dummy response\"}'", # ダミーコマンド
            llm_session_create_command="echo 'new_session_id'", # ダミーコマンド
            start_heartbeat=False, # UserInputAgentはハートビート不要
            **kwargs
        )
        self.default_target_agent = default_target_agent
        self.shutdown_event = threading.Event()
        self.response_received_event = threading.Event()
        self.response_received_event.set()  # 最初は入力可能にする
        if self.default_target_agent:
            print(f"[{self.name}] Initialized. I will send messages to '{self.default_target_agent}'.")
        else:
            print(f"[{self.name}] Initialized. No default target agent set.")

    def think_and_respond(self, trigger_msg: Message, job_id: str, is_observer: bool = False):
        # このエージェントはLLMによる思考を行わない
        pass

    def _on_message_received(self, message_json: str):
        """
        Decodes the message, passes it to BaseAgent for history saving,
        and handles user input blocking/unblocking.
        """
        try:
            msg = Message.from_json(message_json)
            # BaseAgentの履歴保存ロジックを利用
            super()._on_message_received(message_json)

            job_id = msg.job_id or "default"
            
            # 自分宛のメッセージであれば、表示して入力ブロックを解除
            if msg.to_agent == self.name:
                print(f"\n[{self.name}][{job_id}] 📨 Received from {msg.from_agent}: {msg.content}")
                self.response_received_event.set()
            elif self.name in (msg.cc_agents or []):
                 # CCの場合は表示するだけ (入力ブロックは解除しない)
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
        
        # 終了処理はfinallyブロックで一元的に行う

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

                if not self.default_target_agent:
                    print(f"[{self.name}] Error: No default target agent set. Cannot send message.", file=sys.stderr)
                    self.response_received_event.set() # Re-enable input
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
    parser = argparse.ArgumentParser(description="Launch a UserInputAgent.")
    parser.add_argument("name", type=str, help="The name of the agent.")
    parser.add_argument("description", type=str, nargs='?', default="Handles user input from the console.", help="Description of the agent.")
    parser.add_argument("--user_lang", type=str, default="Japanese", help="Language for user interaction.")
    parser.add_argument("--memory_id", type=str, required=True, help="Memory ID for the agent's history.")
    parser.add_argument("--redis_host", type=str, default="localhost", help="Redis host.")
    parser.add_argument("--redis_port", type=int, default=6379, help="Redis port.")
    parser.add_argument("--redis_db", type=int, default=0, help="Redis DB.")
    parser.add_argument("--default_target_agent", type=str, help="The default agent to send messages to.")

    args = parser.parse_args()

    agent = UserInputAgent(
        name=args.name,
        description=args.description,
        user_lang=args.user_lang,
        memory_id=args.memory_id,
        redis_host=args.redis_host,
        redis_port=args.redis_port,
        redis_db=args.redis_db,
        default_target_agent=args.default_target_agent
    )
    try:
        agent.start_interaction()
    except KeyboardInterrupt:
        print(f"[{agent.name}] Shutting down.")
    finally:
        agent.shutdown()
        agent.broker.disconnect()
