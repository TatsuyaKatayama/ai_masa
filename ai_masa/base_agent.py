import sys
import json
import subprocess
from .models.message import Message
from .comms.redis_broker import RedisBroker
from .prompts import PROMPT_TEMPLATES, OBSERVER_INSTRUCTIONS

class BaseAgent:
    def __init__(self, name, role_prompt, redis_host='localhost', language='ja', 
                 llm_command="echo '{\"to_agent\": \"dummy\", \"content\": \"dummy response\"}'", 
                 llm_session_create_command="echo 'new_session_id'"):
        self.name = name
        self.role_prompt = role_prompt
        self.language = language
        self.llm_command = llm_command
        self.llm_session_create_command = llm_session_create_command
        
        # job_idごとに会話履歴とLLMセッションIDを管理
        self.context = {}  # { "job_id_1": [msg1, msg2], "job_id_2": [msg3] }
        self.job_sessions = {} # { "job_id_1": "llm_session_uuid_a", "job_id_2": "llm_session_uuid_b" }
        
        self.broker = RedisBroker(host=redis_host)
        self.broker.connect()

    def observe_loop(self):
        print(f"[{self.name}] Listening on Redis...")
        self.broker.subscribe(self._on_message_received)

    def _on_message_received(self, message_json):
        try:
            msg = Message.from_json(message_json)
            if msg.from_agent == self.name:
                return

            job_id = msg.job_id or "default"
            
            self.context.setdefault(job_id, []).append(msg)

            is_to_me = msg.to_agent == self.name
            if is_to_me:
                print(f"[{self.name}][{job_id}] 📨 Received from {msg.from_agent}: {msg.content}")
                self.think_and_respond(msg, job_id)
            elif self.name in msg.cc_agents:
                print(f"[{self.name}][{job_id}] 👀 (CC) Saw message from {msg.from_agent}")
                # CCで受信した場合も、観察者として思考する
                self.think_and_respond(msg, job_id, is_observer=True)

        except Exception as e:
            print(f"[{self.name}] Error in _on_message_received: {e}")

    def think_and_respond(self, trigger_msg, job_id, is_observer=False):
        llm_session_id = self.job_sessions.get(job_id)
        
        if not llm_session_id:
            print(f"[{self.name}][{job_id}] No session found. Creating a new one...")
            llm_session_id = self._create_llm_session(job_id)
            if not llm_session_id:
                print(f"[{self.name}][{job_id}] Failed to create LLM session. Aborting.")
                return
            self.job_sessions[job_id] = llm_session_id
            print(f"[{self.name}][{job_id}] New session created: {llm_session_id}")

        prompt = self._build_prompt(trigger_msg, job_id, is_observer=is_observer)
        llm_response_json = self._invoke_llm(prompt, llm_session_id)
        
        if not llm_response_json:
            print(f"[{self.name}][{job_id}] Error: LLM did not return a response.")
            return

        try:
            response_data = json.loads(llm_response_json)
            self.broadcast(
                target=response_data.get("to_agent"),
                content=response_data.get("content"),
                cc=response_data.get("cc_agents"),
                job_id=job_id
            )
        except json.JSONDecodeError as e:
            print(f"[{self.name}][{job_id}] Error decoding LLM response: {e}\nReceived: {llm_response_json}")
        except Exception as e:
            print(f"[{self.name}][{job_id}] Error processing LLM response: {e}")

    def _create_llm_session(self, job_id):
        """新しいLLMセッションを作成し、そのIDを返す"""
        print(f"[{self.name}][{job_id}] Initializing LLM session with role: {self.role_prompt}")
        try:
            # セッション作成コマンドにロールプロンプトを入力として渡す
            process = subprocess.run(
                self.llm_session_create_command,
                input=self.role_prompt,
                capture_output=True, text=True, shell=True, check=True
            )
            # コマンドの標準出力からセッションID（最後の行など）を取得
            session_id = process.stdout.strip().split('\n')[-1]
            return session_id
        except subprocess.CalledProcessError as e:
            print(f"[{self.name}][{job_id}] Error executing LLM session creation command: {e}\nStderr: {e.stderr}")
            return None
        except FileNotFoundError:
            print(f"[{self.name}][{job_id}] Error: LLM command not found: '{self.llm_session_create_command}'")
            return None

    def _build_prompt(self, trigger_msg, job_id, is_observer=False):
        history = "\n".join([f"- {msg.from_agent}: {msg.content}" for msg in self.context.get(job_id, [])])
        template = PROMPT_TEMPLATES.get(self.language, PROMPT_TEMPLATES['en'])
        
        observer_instructions = ""
        if is_observer:
            observer_instructions = OBSERVER_INSTRUCTIONS.get(self.language, OBSERVER_INSTRUCTIONS['en'])
            
        return template.format(
            name=self.name, role_prompt=self.role_prompt, history=history,
            from_agent=trigger_msg.from_agent, content=trigger_msg.content,
            observer_instructions=observer_instructions
        )

    def _invoke_llm(self, prompt, llm_session_id):
        print(f"[{self.name}][{self.job_sessions.get(llm_session_id, 'N/A')}] 🧠 Thinking...")
        
        # コマンドテンプレートのプレースホルダーを実際のセッションIDで置換
        command_to_run = self.llm_command.format(session_id=llm_session_id)

        try:
            process = subprocess.run(
                command_to_run,
                input=prompt, capture_output=True, text=True, shell=True, check=True
            )
            try:
                pretty_stdout = json.dumps(json.loads(process.stdout), ensure_ascii=False)
                print(f"[{self.name}] LLM command stdout: {pretty_stdout[:300]}")
            except json.JSONDecodeError:
                print(f"[{self.name}] LLM command stdout: {process.stdout[:300]}")
            return process.stdout
        except subprocess.CalledProcessError as e:
            print(f"[{self.name}] Error executing LLM command: {e}\nStderr: {e.stderr}")
            return None
        except FileNotFoundError:
            print(f"[{self.name}] Error: LLM command not found: '{command_to_run}'")
            return None

    def broadcast(self, target, content, cc=None, job_id="default"):
        if not target or not content:
            print(f"[{self.name}][{job_id}] ⚠️ Missing target or content. Aborting broadcast.")
            return
        msg = Message(self.name, target, content, cc_agents=cc, job_id=job_id)
        self.broker.publish(msg.to_json())
        print(f"[{self.name}][{job_id}] 🚀 Sent to {target}: {content}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python -m ai_masa.base_agent <Name> <Role> [language] [llm_command] [llm_session_create_command]")
        sys.exit(1)
    
    agent = BaseAgent(
        name=sys.argv[1],
        role_prompt=sys.argv[2],
        language=sys.argv[3] if len(sys.argv) > 3 else 'ja',
        llm_command=sys.argv[4] if len(sys.argv) > 4 else "echo '{\"to_agent\": \"dummy\", \"content\": \"dummy response\"}'",
        llm_session_create_command=sys.argv[5] if len(sys.argv) > 5 else "echo 'new_session_id'"
    )
    agent.observe_loop()
