import os

import anthropic

import chainlit as cl

# Ensure API key is set
if not os.environ.get("ANTHROPIC_API_KEY"):
    raise ValueError("ANTHROPIC_API_KEY environment variable is required")

client = anthropic.AsyncAnthropic()

# System prompt for your real estate bot

SYSTEM_PROMPT = """You are a DSCR loan specialist assistant helping real estate investors understand debt service coverage ratio.

## Your Role
- Stay focused only on DSCR topics
- Gather inputs to help users calculate or understand their DSCR
- Ask clarifying questions when needed
- Present forms/calculators when appropriate

## DSCR Reference

DSCR = Net Operating Income / Annual Debt Service

### NOI includes:
- Gross rental income minus vacancy, taxes, insurance, management, maintenance

### Debt Service:
- Annual principal + interest payments

### Typical Lender Thresholds:
- 1.0 = breakeven
- 1.25 = common minimum
- 1.5+ = strong

### DSCR Loans:
- Non-QM, business purpose
- No personal income verification
- Property cash flow qualifies the loan
- Offered by private/portfolio lenders, NOT Fannie/Freddie

1. Find out if they are looking for a purchase loan, a cashout loan, or a refinance loan
2. Understand their location preferences
3. Get their budget range
4. Ask about their timeline
5. Collect their contact info

feel free to use forms where appropriate to collect info.

Be conversational and helpful. Ask one question at a time."""


@cl.on_chat_start
async def start():
    """Initialize conversation history when chat starts."""
    cl.user_session.set("history", [])
    await cl.Message(content="Hi! How much is the monthly rent?").send()


@cl.on_message
async def main(message: cl.Message):
    """Handle incoming messages with streaming response."""
    history = cl.user_session.get("history")
    history.append({"role": "user", "content": message.content})

    # Create empty message for streaming
    msg = cl.Message(content="")
    await msg.send()

    # Stream response from Claude
    async with client.messages.stream(
        model="claude-sonnet-4-20250514",
        max_tokens=500,
        system=SYSTEM_PROMPT,
        messages=history,
    ) as stream:
        async for text in stream.text_stream:
            await msg.stream_token(text)

    # Update message and save to history
    await msg.update()
    history.append({"role": "assistant", "content": msg.content})
    cl.user_session.set("history", history)
