from abc import ABC, abstractmethod

class MessageBroker(ABC):
    @abstractmethod
    def connect(self):
        pass
    @abstractmethod
    def publish(self, message_json: str):
        pass
    @abstractmethod
    def subscribe(self, callback):
        pass
