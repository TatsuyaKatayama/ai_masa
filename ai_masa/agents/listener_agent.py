import sys
import signal
from ..models.message import Message
from .base_agent import BaseAgent

class ListenerAgent(BaseAgent):
    """
    A base class for agents that primarily listen to messages and perform actions.
    It handles common setup and teardown logic.
    """
    def __init__(self, name, description, start_heartbeat=False, **kwargs):
        super().__init__(name, description, start_heartbeat=start_heartbeat, **kwargs)

    def _on_message_received(self, message_json):
        """
        Decodes the message and calls the specific handler.
        """
        try:
            msg = Message.from_json(message_json)
            # Ignore own messages
            if msg.from_agent == self.name:
                return
            self._handle_message(msg)
        except Exception as e:
            print(f"[{self.name}] Error in _on_message_received: {e}")

    def _handle_message(self, message: Message):
        """
        Subclasses must implement this method to process incoming messages.
        """
        raise NotImplementedError

    def think_and_respond(self, trigger_msg, job_id, is_observer=False):
        """
        Listener agents typically don't have complex think_and_respond logic,
        as their actions are triggered directly by _on_message_received.
        """
        pass

    @classmethod
    def main(cls, agent_class):
        """
        A class method to run the agent with proper signal handling.
        """
        if len(sys.argv) < 2:
            print(f"Usage: python -m {cls.__module__} <AgentName>")
            sys.exit(1)

        agent_name = sys.argv[1]
        
        # 追加の引数をkwargsとしてagent_classのコンストラクタに渡す
        kwargs = {}
        for arg in sys.argv[2:]:
            if arg.startswith('--'):
                key_value = arg[2:].split('=', 1)
                if len(key_value) == 2:
                    key, value = key_value
                    kwargs[key.replace('-', '_')] = value
                else:
                    print(f"Warning: Ignoring malformed argument: {arg}")

        agent = agent_class(name=agent_name, **kwargs)

        def signal_handler(sig, frame):
            print(f"[{agent.name}] Shutdown signal received. Stopping...")
            agent.shutdown()
            # In case shutdown hangs, ensure exit.
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        print(f"[{agent.name}] Starting agent '{agent.name}'. Press Ctrl+C to stop.")
        try:
            agent.observe_loop()
        except (KeyboardInterrupt, SystemExit):
             print(f"[{agent.name}] Loop interrupted.")
        finally:
            print(f"[{agent.name}] Cleaning up and stopping agent.")
            agent.broker.disconnect()
            
if __name__ == "__main__":
    # This script is intended to be a base class and not run directly.
    print("This is a base class module and is not meant to be run directly.")
