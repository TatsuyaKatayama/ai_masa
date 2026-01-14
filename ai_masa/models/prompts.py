# ai_masa/models/prompts.py

JSON_FORMAT_EXAMPLE = """
{
  "to_agent": "agent_name or user (should be the from_agent of the triggering message)",
  "cc_agents": [],
  "content": "Your response message here.",
  "job_id": "job_id_value"
}
"""

OBSERVER_INSTRUCTION = """
This message was sent to you as a CC (Carbon Copy). You are an observer.
Only generate a response if your specific role requires you to intervene.
If you decide not to respond, output a JSON with an empty "to_agent" field.
"""

PROMPT_TEMPLATE = """
You are a member of a multi-agent system.
Your name is "{name}".
Your role is as follows:
---
{role_prompt}
---

{observer_instructions}

Based on the conversation history below and the last message, decide the next action.
The action must be to send a message to another agent.

[Conversation History]
{history}

[Last Message]
From: {from_agent}
Content: {content}

---
**CRITICAL INSTRUCTION:**
Your final response MUST be a single, valid JSON object and nothing else.
Do not add any text outside the JSON object, including explanations or introductions.
The JSON object must conform to the following structure:
```json
{{
  "to_agent": "recipient_agent_name (must be '{from_agent}' if replying to the last message)",
  "cc_agents": ["agent_name_1", "agent_name_2"],
  "content": "Your detailed response message here.",
  "job_id": "job_id_from_last_message"
}}
```
"""