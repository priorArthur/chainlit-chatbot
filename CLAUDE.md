# Chainlit Real Estate Chatbot

## Project Overview
Front-of-house (FOH) chatbot for DSCR lead capture using Chainlit + Claude API.

## Tech Stack
- **Framework:** Chainlit 2.9.4
- **LLM:** Claude (anthropic 0.75.0)
- **Deployment:** Digital Ocean App Platform
- **Repo:** https://github.com/priorArthur/chainlit-chatbot

## Live URL
- DO URL: https://foh-chainlit-dscr-chatbot-cvxg7.ondigitalocean.app
- Custom domain: TBD (user setting up via Cloudflare)

## Local Development
```bash
cd /home/dev/apps/chainlit
source .venv/bin/activate
export ANTHROPIC_API_KEY="your-key"
chainlit run app.py
```
Opens at http://localhost:8000

## Deployment
- Auto-deploys on push to `main` branch
- Environment variable `ANTHROPIC_API_KEY` set in DO dashboard (encrypted, runtime only)
- Single instance required (WebSockets need sticky sessions - multiple instances cause "Invalid session" errors)

## Architecture Fit
This is a "Front of House" component in the restaurant metaphor:
- Captures leads via conversational AI
- Future: webhook to BOH (`/home/dev/apps/boh`) for lead processing
- Future: landing page at root domain, chatbot at `chat.` subdomain

## Key Files
- `app.py` - Main chatbot logic with Claude integration
- `Dockerfile` - Container config for DO deployment
- `requirements.txt` - Python dependencies
- `chainlit.md` - Auto-generated welcome page (customizable)

## Chatbot Flow
1. Asks buy or sell
2. Location preferences
3. Budget range
4. Timeline
5. Contact info collection

## Next Steps
- [ ] Add webhook to send captured leads to BOH
- [ ] Create landing page for root domain
- [ ] Customize Chainlit UI (logo, colors, name)
- [ ] Add lead qualification logic
- [ ] Connect to BOH ticket creation API

## Customization
Edit `.chainlit/config.toml` (create if needed):
```toml
[UI]
name = "Your Brand Assistant"
description = "Find your dream home"
default_theme = "light"

[UI.theme.light]
primary = "#2563eb"
```

## Scaling Notes
- Start with 1 instance ($25/mo)
- For multiple instances: need sticky sessions / session affinity
- Monitor via DO Insights tab
