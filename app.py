"""DSCR Lead Capture Chatbot - Takeout FOH

Conversational AI for capturing DSCR loan leads via Chainlit.
Uses Claude tool use for structured data extraction + direct DB insert
for sub-20ms lead delivery to Kitchen (BOH).

Flow:
    1. User chats about DSCR loans
    2. Claude gathers info (loan type, geo, budget, timeline)
    3. When contact info collected, Claude calls submit_lead tool
    4. Tool extracts structured data → direct DB insert → Kitchen notified

Tech:
    - Chainlit 2.9.4 for conversational UI
    - Claude Sonnet 4 for chat + tool use
    - Direct PostgreSQL insert (shared DB with Kitchen)
    - PostgreSQL NOTIFY triggers Kitchen's listener
"""

import os
from uuid import uuid4

import anthropic
import chainlit as cl
from chainlit.data.sql_alchemy import SQLAlchemyDataLayer

from boh_db import send_lead_to_kitchen, BOH_DATABASE_URL


# Data persistence for conversation history (optional)
# If DATABASE_URL is set, conversations are saved to PostgreSQL
@cl.data_layer
def get_data_layer():
    db_url = os.environ.get("DATABASE_URL")
    if db_url:
        return SQLAlchemyDataLayer(conninfo=db_url)
    return None  # No persistence - conversations lost on session end


# Ensure API key is set
if not os.environ.get("ANTHROPIC_API_KEY"):
    raise ValueError("ANTHROPIC_API_KEY environment variable is required")

client = anthropic.AsyncAnthropic()

# Tool definition for structured lead capture
LEAD_CAPTURE_TOOL = {
    "name": "submit_lead",
    "description": """Submit captured lead information to the kitchen for processing.
Call this tool ONLY when you have collected the user's contact information (at minimum their name).
Include any location/geo and loan type info gathered during the conversation.""",
    "input_schema": {
        "type": "object",
        "properties": {
            "geo": {
                "type": "string",
                "description": "State abbreviation where user wants to invest (e.g., TX, CA, FL)"
            },
            "loan_type": {
                "type": "string",
                "enum": ["purchase", "cashout", "refinance"],
                "description": "Type of DSCR loan user is interested in"
            },
            "budget_min": {
                "type": "integer",
                "description": "Minimum budget/loan amount in dollars"
            },
            "budget_max": {
                "type": "integer",
                "description": "Maximum budget/loan amount in dollars"
            },
            "timeline": {
                "type": "string",
                "description": "When user plans to act (e.g., 'within 30 days', '3-6 months')"
            },
            "contact": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "User's full name"},
                    "email": {"type": "string", "description": "User's email address"},
                    "phone": {"type": "string", "description": "User's phone number"}
                },
                "required": ["name"],
                "additionalProperties": False
            }
        },
        "required": ["contact"],
        "additionalProperties": False
    }
}

# System prompt for DSCR specialist with tool use instructions
SYSTEM_PROMPT = """You are a DSCR loan specialist assistant helping real estate investors understand debt service coverage ratio.

## Your Role
- Stay focused only on DSCR topics
- Gather inputs to help users calculate or understand their DSCR
- Ask clarifying questions when needed
- Be conversational and helpful - ask one question at a time

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

## Lead Capture Flow

Guide the conversation to gather:
1. Loan type: purchase, cashout, or refinance
2. Location: which state they're investing in
3. Budget range: approximate loan amount
4. Timeline: when they plan to act
5. Contact info: name, email, and/or phone

## Using the submit_lead Tool

When you have collected the user's contact information (at minimum their name, ideally email or phone too), use the submit_lead tool to capture the lead. Include any geo, loan type, budget, or timeline info from the conversation.

After submitting the lead, thank the user warmly and let them know someone will be in touch soon."""


@cl.on_chat_start
async def start():
    """Initialize conversation history when chat starts."""
    # Generate unique session ID for deduplication
    session_id = str(uuid4())
    cl.user_session.set("session_id", session_id)
    cl.user_session.set("history", [])
    cl.user_session.set("lead_submitted", False)

    await cl.Message(
        content="Hi! I'm here to help you understand DSCR loans for real estate investing. Are you looking at a purchase, cash-out refinance, or rate-and-term refinance?"
    ).send()


@cl.on_message
async def main(message: cl.Message):
    """Handle incoming messages with tool use for lead capture."""
    history = cl.user_session.get("history")
    session_id = cl.user_session.get("session_id")
    lead_submitted = cl.user_session.get("lead_submitted", False)

    history.append({"role": "user", "content": message.content})

    # Use non-streaming for tool calls (simpler handling)
    # Can optimize to streaming later if needed
    response = await client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=history,
        tools=[LEAD_CAPTURE_TOOL] if not lead_submitted else [],
    )

    # Process response content blocks
    assistant_content = []

    for block in response.content:
        if block.type == "text":
            # Regular text response
            await cl.Message(content=block.text).send()
            assistant_content.append({"type": "text", "text": block.text})

        elif block.type == "tool_use" and block.name == "submit_lead":
            # Claude wants to submit the lead
            lead_data = block.input

            # Send to kitchen via direct DB insert
            lead_id = await send_lead_to_kitchen(lead_data, session_id)

            if lead_id:
                cl.user_session.set("lead_submitted", True)

                # Build tool result
                tool_result = {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": f"Lead submitted successfully. ID: {lead_id}"
                }

                # Log for debugging
                contact = lead_data.get("contact", {})
                print(f"Lead captured: {contact.get('name')} - {lead_data.get('loan_type', 'unknown')} in {lead_data.get('geo', 'unknown')}")
            else:
                tool_result = {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": "Lead captured (BOH connection not configured)",
                    "is_error": False  # Don't fail the conversation
                }
                cl.user_session.set("lead_submitted", True)

            # Add tool use and result to history
            assistant_content.append({
                "type": "tool_use",
                "id": block.id,
                "name": block.name,
                "input": block.input
            })

            # Continue conversation with tool result
            history.append({"role": "assistant", "content": assistant_content})
            history.append({"role": "user", "content": [tool_result]})

            # Get Claude's follow-up response after tool use
            followup = await client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=500,
                system=SYSTEM_PROMPT,
                messages=history,
            )

            if followup.content and followup.content[0].type == "text":
                await cl.Message(content=followup.content[0].text).send()
                history.append({"role": "assistant", "content": followup.content[0].text})

            cl.user_session.set("history", history)
            return  # Exit early, we handled the full flow

    # For non-tool responses, just save to history
    if assistant_content:
        # If there was only text, save as string
        if len(assistant_content) == 1 and assistant_content[0]["type"] == "text":
            history.append({"role": "assistant", "content": assistant_content[0]["text"]})
        else:
            history.append({"role": "assistant", "content": assistant_content})

    cl.user_session.set("history", history)
