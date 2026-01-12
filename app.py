import os
import chainlit as cl
import anthropic

# Ensure API key is set
if not os.environ.get("ANTHROPIC_API_KEY"):
    raise ValueError("ANTHROPIC_API_KEY environment variable is required")

client = anthropic.Anthropic()

# System prompt for your real estate bot
SYSTEM_PROMPT = """You are a friendly real estate assistant. Your job is to:
1. Find out if they want to buy or sell
2. Understand their location preferences
3. Get their budget range
4. Ask about their timeline
5. Collect their contact info

Be conversational and helpful. Ask one question at a time."""


@cl.on_chat_start
async def start():
    """Initialize conversation history when chat starts."""
    cl.user_session.set("history", [])
    await cl.Message(content="Hi! Are you looking to buy or sell a property?").send()


@cl.on_message
async def main(message: cl.Message):
    """Handle incoming messages."""
    history = cl.user_session.get("history")
    history.append({"role": "user", "content": message.content})

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=500,
        system=SYSTEM_PROMPT,
        messages=history,
    )

    assistant_message = response.content[0].text
    history.append({"role": "assistant", "content": assistant_message})
    cl.user_session.set("history", history)

    await cl.Message(content=assistant_message).send()
