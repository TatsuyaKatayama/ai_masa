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

Based on the conversation history below and the last message, decide the next action to take.
The action should be sending a message to another agent.
You must generate the response in the JSON format specified in your role prompt.

[Conversation History]
{history}

[Last Message]
From: {from_agent}
Content: {content}

[Your Response (JSON format)]
"""