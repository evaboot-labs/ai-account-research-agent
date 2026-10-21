# Agent instructions

This repo is an AI account research agent. The user gives about 10 target companies; the agent finds the 2 to 3 most senior sales leaders at each one in Sales Navigator, gets their verified emails with Evaboot, writes a "why now" brief per company from real company and role data, and waits for the user's approval in a sheet before it pushes the leads to their CRM. When the user asks for account research or decision makers at a list of companies:

1. Follow the skill in `skills/ai-account-research/SKILL.md` step by step.
2. Use `research.py` for the search URL, the picks, the facts and the sheet. It makes no network calls; the Evaboot MCP server does the Sales Navigator work (`.mcp.json`).
3. Write briefs only from `research/facts.json`, per `skills/ai-account-research/references/signals.md`.
4. If the user is not connected yet, follow `docs/connect-your-agent.md` with them.
5. If the user wants n8n instead, follow `docs/n8n.md` with them one step at a time: you cannot click inside n8n, so say exactly what to do and wait for their confirmation.

Confirm with the user before every call that saves, sends or changes anything, and before every export: it spends 1 Evaboot credit per lead. Never send an email. Never ask for or handle another tool's API key: the user connects those in the tool itself. Never commit `.env`, `data/` or `research/`: they hold real people's data.
