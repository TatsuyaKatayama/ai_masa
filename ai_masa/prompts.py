# ai_masa/ai_masa/prompts.py

OBSERVER_INSTRUCTIONS = {
    "Japanese": """
このメッセージはCC（カーボンコピー）としてあなたに届きました。あなたは観察者です。
あなたの特定の役割が介入を要求する場合にのみ、応答を生成してください。
応答しない場合は、"to_agent"フィールドを空にしたJSONを出力してください。
""",
    "en": """
This message was sent to you as a CC (Carbon Copy). You are an observer.
Only generate a response if your specific role requires you to intervene.
If you decide not to respond, output a JSON with an empty "to_agent" field.
"""
}

PROMPT_TEMPLATES = {
    "Japanese": """
あなたはマルチエージェントシステムの一員です。
あなたの名前は「{name}」です。
あなたの役割は以下の通りです。
---
{role_prompt}
---

{observer_instructions}

以下の会話履歴と、最後のメッセージを踏まえて、次に行うべきアクションを考えてください。
アクションは、他のエージェントへのメッセージ送信です。
必ず以下のJSON形式で応答を生成してください。

【会話履歴】
{history}

【最後のメッセージ】
From: {from_agent}
Content: {content}

【あなたの応答（JSON形式）】
{{
  "to_agent": "相手のエージェント名",
  "cc_agents": ["CCにいれるエージェント名のリスト"],
  "content": "具体的な指示や応答内容"
}}
""",
    "en": """
You are a member of a multi-agent system.
Your name is "{name}".
Your role is as follows:
---
{role_prompt}
---

{observer_instructions}

Based on the conversation history below and the last message, decide the next action to take.
The action should be sending a message to another agent.
You must generate the response in the following JSON format.

[Conversation History]
{history}

[Last Message]
From: {from_agent}
Content: {content}

[Your Response (JSON format)]
{{
  "to_agent": "The name of the agent to send to",
  "cc_agents": ["List of agent names for CC"],
  "content": "Specific instructions or response content"
}}
"""
}
