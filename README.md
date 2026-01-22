# Takeout FOH - DSCR Lead Capture Chatbot

A Chainlit-based conversational AI for capturing DSCR (Debt Service Coverage Ratio) loan leads. This is a **Front of House (FOH)** component in the restaurant metaphor ecosystem.

## Team Context

This repo is worked on by multiple Opus 4.5 instances:

| Role | Responsibility |
|------|----------------|
| **Takeout Manager** | Overall ownership, architecture decisions, integration with BOH |
| **Kitchen Auditor** | Reviews alignment with BOH/kitchen patterns, data flow validation |
| **Takeout 2** | Feature implementation, bug fixes |
| **Takeout Assist** | Support tasks, testing, documentation |

## Where This Fits

```
FOH (Front of House)          BOH (Back of House)
--------------------          -------------------
Dining Room                   Kitchen (FastAPI)
Bar                           └── Cooking Lines
Takeout  <── YOU ARE HERE     └── Expo Counter
```

- **Takeout** = Self-service, minimal interaction, template-based
- Leads captured here eventually flow to BOH for processing
- Currently standalone; webhook integration to kitchen is TODO

## Current State

**Live URL:** https://foh-chainlit-dscr-chatbot-cvxg7.ondigitalocean.app

**What works:**
- Conversational lead capture via Claude (claude-sonnet-4-20250514)
- Session-based conversation history
- DSCR-focused system prompt constrains responses
- Deployed on Digital Ocean App Platform (auto-deploy on push to `main`)

**What's missing:**
- [x] ~~Streaming responses~~ **Done** - responses now appear word-by-word
- [ ] Webhook to BOH for lead delivery
- [ ] Data persistence (leads lost on session end)
- [ ] UI customization (logo, colors, branding)
- [ ] Structured input collection (forms, action buttons)

## Tech Stack

| Component | Version | Purpose |
|-----------|---------|---------|
| Chainlit | 2.9.4 | Conversational UI framework |
| Anthropic SDK | 0.75.0 | Claude API client |
| asyncpg | 0.30.0 | Postgres driver (not yet wired up) |
| Python | 3.12 | Runtime |

## Key Files

```
├── app.py                 # Main chatbot logic (~80 lines)
├── requirements.txt       # Python dependencies
├── Dockerfile             # DO deployment config
├── chainlit.md            # Welcome page shown to users
├── llm.txt                # Chainlit docs index for LLM reference
├── CLAUDE.md              # Project-specific instructions
└── .chainlit/
    └── config.toml        # UI and feature configuration
```

## Local Development

```bash
cd /home/dev/apps/(restaurant)/(takeout)/chainlit
source .venv/bin/activate
export ANTHROPIC_API_KEY="your-key"
chainlit run app.py
```

Opens at http://localhost:8000

## How the Chatbot Works

1. User starts chat → `@cl.on_chat_start` initializes empty history, sends greeting
2. User sends message → appended to conversation history
3. Full history + `SYSTEM_PROMPT` sent to Claude API
4. Claude responds (currently blocking, not streaming)
5. Response appended to history, sent to UI
6. Repeat until user provides contact info

**System prompt focus areas:**
- DSCR education (formula, thresholds, loan types)
- Lead qualification (purchase/cashout/refi, location, budget, timeline)
- Contact info collection

## Configuration

Key settings in `.chainlit/config.toml`:
- Session timeout: 1 hour
- User session TTL: 15 days
- File uploads: Enabled (up to 20 files, 500MB max)
- Assistant name: "Your DSCR Agent"

## Deployment

- **Platform:** Digital Ocean App Platform
- **Trigger:** Auto-deploy on push to `main`
- **Instances:** 1 (WebSocket sticky sessions required)
- **Env vars:** `ANTHROPIC_API_KEY` set in DO dashboard (encrypted)

## Documentation Reference

See `llm.txt` for full Chainlit docs index. Key docs for upcoming work:

- [Streaming](https://docs.chainlit.io/advanced-features/streaming) - word-by-word responses
- [Ask for Input](https://docs.chainlit.io/api-reference/ask/ask-for-input) - structured forms
- [Data Persistence](https://docs.chainlit.io/data-persistence/overview) - save conversations
- [Customization](https://docs.chainlit.io/customisation/overview) - branding

## Next Priority

**Data persistence** - wire up `asyncpg` to save leads/conversations to Postgres.
