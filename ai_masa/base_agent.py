import sys
import json
import subprocess
from .models.message import Message
from .comms.redis_broker import RedisBroker
from .prompts import PROMPT_TEMPLATES

class BaseAgent:
    def __init__(self, name, role_prompt, redis_host='localhost', language='ja', llm_command=None):
        self.name = name
        self.role_prompt = role_prompt
        self.context = []
        self.language = language
        self.llm_command = llm_command
        
        # RedisBrokerを使用
        self.broker = RedisBroker(host=redis_host)
        self.broker.connect()

    def observe_loop(self):
        """受信待機ループ開始"""
        print(f"[{self.name}] Listening on Redis...")
        self.broker.subscribe(self._on_message_received)

    def _on_message_received(self, message_json):
        """受信時のコールバック"""
        try:
            msg = Message.from_json(message_json)
            
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
        """LLMの思考をトリガーし、応答を生成・送信する"""
        prompt = self._build_prompt(trigger_msg)
        llm_response_json = self._invoke_llm(prompt)
        
        if not llm_response_json:
            print(f"[{self.name}] Error: LLM did not return a response.")
            return

        try:
            response_data = json.loads(llm_response_json)
            self.broadcast(
                target=response_data.get("to_agent"),
                content=response_data.get("content"),
                cc=response_data.get("cc_agents")
            )
        except json.JSONDecodeError as e:
            print(f"[{self.name}] Error decoding LLM response: {e}")
            print(f"[{self.name}] Received: {llm_response_json}")
        except Exception as e:
            print(f"[{self.name}] Error processing LLM response: {e}")

    def _build_prompt(self, trigger_msg):
        """LLMへのプロンプトを構築する"""
        history = "\n".join([f"- {msg.from_agent}: {msg.content}" for msg in self.context])
        
        template = PROMPT_TEMPLATES.get(self.language, PROMPT_TEMPLATES['en'])
        
        return template.format(
            name=self.name,
            role_prompt=self.role_prompt,
            history=history,
            from_agent=trigger_msg.from_agent,
            content=trigger_msg.content
        )

    def _invoke_llm(self, prompt):
        """LLMを呼び出す。llm_commandが指定されていれば外部コマンドとして、なければダミーを返す"""
        print(f"[{self.name}] 🧠 Thinking...")

        if self.llm_command:
            try:
                # 外部コマンドを実行し、標準入力にプロンプトを渡し、標準出力を受け取る
                process = subprocess.run(
                    self.llm_command,
                    input=prompt,
                    capture_output=True,
                    text=True,
                    shell=True,
                    check=True
                )
                # ログ出力のために、一度JSONをデコード・再エンコードして見やすくする
                try:
                    pretty_stdout = json.dumps(json.loads(process.stdout), ensure_ascii=False)
                    print(f"[{self.name}] LLM command stdout: {pretty_stdout[:300]}")
                except json.JSONDecodeError:
                    # JSONとしてパースできない場合はそのまま出力
                    print(f"[{self.name}] LLM command stdout: {process.stdout[:300]}")
                return process.stdout
            except subprocess.CalledProcessError as e:
                print(f"[{self.name}] Error executing LLM command: {e}")
                print(f"[{self.name}] Stderr: {e.stderr}")
                return None
            except FileNotFoundError:
                print(f"[{self.name}] Error: LLM command not found: '{self.llm_command}'")
                return None
        else:
            # llm_commandが指定されていない場合のダミーレスポンス
            print(f"[{self.name}] (Using dummy response)")
            dummy_response = {
                "to_agent": "dummy_agent",
                "cc_agents": [],
                "content": "This is a dummy response as llm_command is not set."
            }
            return json.dumps(dummy_response, ensure_ascii=False)

    def broadcast(self, target, content, cc=None):
        if not target or not content:
            print(f"[{self.name}] ⚠️ Missing target or content. Aborting broadcast.")
            return
        msg = Message(self.name, target, content, cc_agents=cc)
        self.broker.publish(msg.to_json())
        print(f"[{self.name}] 🚀 Sent to {target}: {content}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python -m ai_masa.base_agent <Name> <Role> [language] [llm_command]")
        sys.exit(1)
    
    name = sys.argv[1]
    role = sys.argv[2]
    lang = sys.argv[3] if len(sys.argv) > 3 else 'ja'
    cmd = sys.argv[4] if len(sys.argv) > 4 else None

    agent = BaseAgent(name, role, language=lang, llm_command=cmd)
    agent.observe_loop()
