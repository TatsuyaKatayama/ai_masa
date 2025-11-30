import uuid
import json
import datetime

class Message:
    def __init__(self, from_agent, to_agent, content, job_id="default", cc_agents=None, msg_id=None):
        self.message_id = msg_id or str(uuid.uuid4())
        self.timestamp = datetime.datetime.now().isoformat()
        self.from_agent = from_agent
        self.to_agent = to_agent
        self.cc_agents = cc_agents if cc_agents is not None else []
        self.content = content
        self.job_id = job_id

    def to_json(self):
        return json.dumps(self.__dict__, ensure_ascii=False)

    @staticmethod
    def from_json(json_str):
        data = json.loads(json_str)
        return Message(
            from_agent=data.get("from_agent"),
            to_agent=data.get("to_agent"),
            content=data.get("content"),
            job_id=data.get("job_id"),
            cc_agents=data.get("cc_agents"),
            msg_id=data.get("message_id")
        )
