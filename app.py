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
        # DO managed databases use postgresql:// but SQLAlchemy async needs postgresql+asyncpg://
        if db_url.startswith("postgresql://") and "+asyncpg" not in db_url:
            db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
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

The user has already selected their loan type, location, and timeline via buttons at the start of the conversation. This data is pre-filled - you don't need to ask for it again.

Focus on gathering:
1. Budget range (loan amount they're considering)
2. Property details (if relevant)
3. Contact info (name, email, phone)

When you have collected the user's contact information (at minimum their name, ideally email or phone too), use the submit_lead tool to capture the lead. The system will automatically merge in the loan type, geo, and timeline from the earlier button selections.

After submitting the lead, thank the user warmly and let them know someone will be in touch soon."""


# ============================================================================
# Structured Input Functions (called from on_chat_start flow)
# ============================================================================

# Valid US state codes for validation
US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC"
}


async def ask_location():
    """Ask user which state they're investing in via action buttons."""
    res = await cl.AskActionMessage(
        content="Which state are you looking to invest in?",
        actions=[
            cl.Action(name="geo", payload={"state": "TX"}, label="🤠 Texas"),
            cl.Action(name="geo", payload={"state": "FL"}, label="🌴 Florida"),
            cl.Action(name="geo", payload={"state": "CA"}, label="☀️ California"),
            cl.Action(name="geo", payload={"state": "other"}, label="📍 Other"),
        ],
        timeout=120
    ).send()

    if res:
        state = res.get("payload", {}).get("state")
        if state == "other":
            # Ask for text input if "Other" selected
            text_res = await cl.AskUserMessage(
                content="No problem! Which state are you targeting? (e.g., NY, OH, GA)",
                timeout=120
            ).send()
            if text_res:
                state = text_res.get("output", "").strip().upper()[:2]  # Normalize to 2-letter code
                if state not in US_STATES:
                    await cl.Message(
                        content=f"'{state}' doesn't look like a US state code. No worries - tell me more during our chat!"
                    ).send()
                    state = None

        cl.user_session.get("lead_data")["geo"] = state
        await ask_timeline()
    else:
        # Timeout - continue to conversation anyway
        await start_conversation("No worries! Let's chat about DSCR loans. What questions do you have?")


async def ask_timeline():
    """Ask user about their timeline via action buttons."""
    res = await cl.AskActionMessage(
        content="What's your timeline?",
        actions=[
            cl.Action(name="timeline", payload={"value": "asap"}, label="🔥 ASAP"),
            cl.Action(name="timeline", payload={"value": "1-3mo"}, label="📅 1-3 months"),
            cl.Action(name="timeline", payload={"value": "3-6mo"}, label="📆 3-6 months"),
            cl.Action(name="timeline", payload={"value": "6+mo"}, label="🗓️ 6+ months"),
        ],
        timeout=120
    ).send()

    if res:
        timeline = res.get("payload", {}).get("value")
        cl.user_session.get("lead_data")["timeline"] = timeline

    await ask_budget()


async def ask_budget():
    """Ask user about their budget range via action buttons."""
    res = await cl.AskActionMessage(
        content="What loan amount are you considering?",
        actions=[
            cl.Action(name="budget", payload={"min": 100000, "max": 250000}, label="💰 $100K - $250K"),
            cl.Action(name="budget", payload={"min": 250000, "max": 500000}, label="💰 $250K - $500K"),
            cl.Action(name="budget", payload={"min": 500000, "max": 1000000}, label="💰 $500K - $1M"),
            cl.Action(name="budget", payload={"min": 1000000, "max": 5000000}, label="💰 $1M+"),
        ],
        timeout=120
    ).send()

    if res:
        payload = res.get("payload", {})
        cl.user_session.get("lead_data")["budget_min"] = payload.get("min")
        cl.user_session.get("lead_data")["budget_max"] = payload.get("max")

    # Build context message based on all collected data
    lead_data = cl.user_session.get("lead_data", {})
    loan_type = lead_data.get("loan_type", "DSCR loan")
    geo = lead_data.get("geo", "your target area")

    intro = f"Great! So you're exploring a {loan_type} in {geo}. "
    intro += "Let's talk about the property details. What questions do you have?"

    await start_conversation(intro)


async def start_conversation(intro_message: str):
    """Transition from structured inputs to streaming conversation."""
    # Add intro to history so Claude has context
    history = cl.user_session.get("history", [])
    history.append({"role": "assistant", "content": intro_message})
    cl.user_session.set("history", history)

    await cl.Message(content=intro_message).send()


# ============================================================================
# Chainlit Event Handlers
# ============================================================================

@cl.on_chat_start
async def start():
    """Initialize session and start structured input flow with loan type buttons."""
    # Generate unique session ID for deduplication
    session_id = str(uuid4())
    cl.user_session.set("session_id", session_id)
    cl.user_session.set("history", [])
    cl.user_session.set("lead_data", {})  # Store structured inputs here
    cl.user_session.set("lead_submitted", False)

    # Start with loan type selection via action buttons
    res = await cl.AskActionMessage(
        content="Hi! What type of DSCR loan are you exploring?",
        actions=[
            cl.Action(name="loan", payload={"type": "purchase"}, label="🏠 Purchase"),
            cl.Action(name="loan", payload={"type": "cashout"}, label="💵 Cash-Out"),
            cl.Action(name="loan", payload={"type": "refi"}, label="🔄 Refinance"),
        ],
        timeout=120
    ).send()

    if res:
        loan_type = res.get("payload", {}).get("type")
        cl.user_session.get("lead_data")["loan_type"] = loan_type
        await ask_location()  # Continue to Takeout 3's function
    else:
        # Timeout or skip - continue to conversation anyway
        await start_conversation("No worries! What would you like to know about DSCR loans?")


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
            # Merge structured inputs from buttons with Claude's extracted data
            structured_data = cl.user_session.get("lead_data", {})
            lead_data = {**structured_data, **block.input}  # Claude's data overrides if present

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
