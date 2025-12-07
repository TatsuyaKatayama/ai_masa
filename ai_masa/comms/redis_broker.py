import redis
import time
from .broker_base import MessageBroker

class RedisBroker(MessageBroker):
    def __init__(self, host='localhost', port=6379, channel='ai_masa_channel'):
        self.host = host
        self.port = port
        self.channel = channel
        self.client = None
        self.pubsub = None

    def connect(self):
        # decode_responses=True にすることで、bytesではなくstrで受け取る
        self.client = redis.Redis(host=self.host, port=self.port, decode_responses=True)
        try:
            self.client.ping()
            print(f"[RedisBroker] Connected to {self.host}:{self.port}")
        except redis.ConnectionError:
            print(f"[RedisBroker] 🔴 Connection Failed. Is Redis running?")
            raise

    def publish(self, message_json: str):
        if self.client:
            self.client.publish(self.channel, message_json)

    def subscribe(self, callback, shutdown_event=None):
        if not self.client:
            raise ConnectionError("Broker not connected")
        
        self.pubsub = self.client.pubsub()
        self.pubsub.subscribe(self.channel)
        
        print(f"[RedisBroker] Subscribed to channel: {self.channel}")
        
        while True:
            if shutdown_event and shutdown_event.is_set():
                break

            # タイムアウト付きでメッセージを取得
            message = self.pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message and message['type'] == 'message':
                callback(message['data'])
            
            # CPUを過剰に消費しないように少し待機
            time.sleep(0.01)

    def disconnect(self):
        if self.pubsub:
            self.pubsub.unsubscribe()
            self.pubsub.close()
        if self.client:
            self.client.close()
        print(f"[RedisBroker] Disconnected from {self.host}:{self.port}")
