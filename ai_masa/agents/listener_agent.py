import sys
import signal
import argparse
from typing import Optional, List, Dict, Any

from ..models.message import Message
from .base_agent import BaseAgent

class ListenerAgent(BaseAgent):
    """
    A base class for agents that primarily listen to messages and perform actions.
    It handles common setup and teardown logic.
    """
    def __init__(self, name: str, description: str, user_lang: str = 'Japanese',
                 memory_id: str = "listener_memory", redis_host: str = 'localhost', redis_port: int = 6379, redis_db: int = 0,
                 start_heartbeat: bool = False, **kwargs):
        super().__init__(
            name=name,
            description=description,
            user_lang=user_lang,
            memory_id=memory_id,
            redis_host=redis_host,
            redis_port=redis_port,
            redis_db=redis_db,
            start_heartbeat=start_heartbeat,
            **kwargs
        )

    def _on_message_received(self, message_json: str):
        """
        Decodes the message, calls the BaseAgent's logic for history saving and
        thinking, and then calls the specific handler for listening actions.
        """
        try:
            msg = Message.from_json(message_json)
            
            # First, let the BaseAgent handle its logic (saving history, calling think_and_respond)
            super()._on_message_received(message_json)
            
            # Second, if the message is relevant, also call the specific listener handler.
            # This allows ListenerAgents to react to messages (like heartbeats)
            # that might not trigger a "response" via think_and_respond.
            if self._is_message_for_me(msg):
                self._handle_message(msg)

        except Exception as e:
            print(f"[{self.name}] Error in _on_message_received: {e}")

    def think_and_respond(self, trigger_msg: Message, job_id: str, is_observer: bool = False):
        """
        Listener agents typically don't have complex think_and_respond logic.
        Their primary logic is in _handle_message. We can keep this pass
        as _on_message_received now calls _handle_message directly.
        """
        pass

    @classmethod
    def main(cls, agent_class):
        """
        A class method to run the agent with proper signal handling.
        """
        parser = argparse.ArgumentParser(description=f"Run a {agent_class.__name__}.")
        parser.add_argument("name", type=str, help="The name of the agent.")
        parser.add_argument("description", type=str, nargs='?', 
                            default=f"A {agent_class.__name__} agent.", 
                            help="Description of the agent.")
        parser.add_argument("--user_lang", type=str, default="Japanese", help="Language for user interaction.")
        parser.add_argument("--memory_id", type=str, required=True, help="Memory ID for the agent's history.")
        parser.add_argument("--redis_host", type=str, default="localhost", help="Redis host.")
        parser.add_argument("--redis_port", type=int, default=6379, help="Redis port.")
        parser.add_argument("--redis_db", type=int, default=0, help="Redis DB.")
        parser.add_argument("--start_heartbeat", action="store_true", help="Start heartbeat for the agent.")

        # Parse known arguments. Pass unknown arguments as kwargs to agent_class.
        args, unknown_args = parser.parse_known_args()

        kwargs = {}
        for i in range(0, len(unknown_args), 2):
            if unknown_args[i].startswith('--'):
                key = unknown_args[i][2:].replace('-', '_')
                if i + 1 < len(unknown_args):
                    kwargs[key] = unknown_args[i+1]
                else:
                    print(f"Warning: Argument {unknown_args[i]} is missing a value.", file=sys.stderr)
            else:
                print(f"Warning: Ignoring unexpected argument: {unknown_args[i]}", file=sys.stderr)

        agent = agent_class(
            name=args.name,
            description=args.description,
            user_lang=args.user_lang,
            memory_id=args.memory_id,
            redis_host=args.redis_host,
            redis_port=args.redis_port,
            redis_db=args.redis_db,
            start_heartbeat=args.start_heartbeat,
            **kwargs
        )

        def signal_handler(sig, frame):
            print(f"[{agent.name}] Shutdown signal received. Stopping...")
            agent.shutdown()
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
            # AgentManagerと同じくshutdown()を呼ぶことで、heartbeat timerもキャンセルされる
            agent.shutdown()
            
if __name__ == "__main__":
    print("This is a base class module and is not meant to be run directly.")
