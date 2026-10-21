# Connect your agent by hand

The prompt in the README does all of this for you. These are the same steps, for when you want to do them yourself.

1. **Create your Evaboot account** at [dash.evaboot.com](https://dash.evaboot.com/accounts/signup/?last_click_origin=ai-account-research-agent-repo) and install the [Chrome extension](https://dash.evaboot.com/install/) to connect Sales Navigator. You need an active Sales Navigator seat.
2. **Get the repo:**
   ```bash
   git clone https://github.com/evaboot-labs/ai-account-research-agent.git
   cd ai-account-research-agent
   ```
3. **Connect the Evaboot MCP server.** Copy your API key from
   [dash.evaboot.com/dash/api/](https://dash.evaboot.com/dash/api/), then:
   ```bash
   cp .env.example .env          # paste the key after EVABOOT_API_KEY=
   export EVABOOT_API_KEY=...    # same key, for your agent
   ```
   - **Claude Code** reads `.mcp.json` in this folder and uses `EVABOOT_API_KEY` from your environment.
   - **Codex:** `codex mcp add evaboot --url https://mcp.evaboot.com/mcp --bearer-token-env-var EVABOOT_API_KEY`
   - **Cursor:** add `https://mcp.evaboot.com/mcp` with the header `Authorization: Bearer <your key>`.
   - **Claude or ChatGPT on the web:** add `https://mcp.evaboot.com/mcp` as a custom connector and sign in.
4. **Connect your CRM** (HubSpot, Pipedrive, Attio or any other) at [dash.evaboot.com/dash/integrations/](https://dash.evaboot.com/dash/integrations/). The agent pushes the approved leads there.
5. **Say who you look for** in [`TARGET.md`](../TARGET.md), or let your agent ask you.
6. **Check** (Python 3.9+, no packages to install):
   ```bash
   python3 research.py people-url --list 123
   ```
   It prints a Sales Navigator URL.

Then ask your agent: **"Research these accounts: <your companies>."**

Back to the [README](../README.md).
