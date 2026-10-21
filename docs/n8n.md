# Run it in n8n

[`n8n/ai-account-research-agent.json`](../n8n/ai-account-research-agent.json) is the same agent for n8n. You type your companies into a form, the workflow fills your approval sheet, and a second form page asks before anything goes to your CRM.

## What runs

1. **Target accounts** (form): your companies, one per line, and how many leaders per company.
2. **Resolve the companies** (AI Agent with Claude and the Evaboot MCP server): finds each company's LinkedIn page and saves them as a Sales Navigator account list.
3. **Preview, pick, save, export** (MCP Client nodes and Code): the same title search and the same picks as `research.py`, then an Evaboot export of only those people, with emails. 1 credit per lead.
4. **Write the briefs** (Claude): a why-now brief and an opener per company, from the export fields only.
5. **Add to the approval sheet** (Google Sheets): one row per contact, strong accounts first.
6. **Approve** (form page): yes pushes the export to your CRM through Evaboot, no stops.

## Set it up

1. **Connect your CRM** to Evaboot at [dash.evaboot.com/dash/integrations/](https://dash.evaboot.com/dash/integrations/).
2. **Make the sheet:** a Google Sheet with this header row:
   `Company, Signal, Why now, Suggested opener, Contact, Title, Email, Email status, LinkedIn, Approve (yes/no)`
3. **Import** the JSON in n8n: *Workflows > Import from file*.
4. **Add three credentials:**
   - **Bearer Auth** named `Evaboot MCP (Bearer)`: your key from [dash.evaboot.com/dash/api/](https://dash.evaboot.com/dash/api/). Select it on the **Evaboot MCP** node and on every MCP Client node.
   - **Anthropic** on both Claude nodes.
   - **Google Sheets** on **Add to the approval sheet**.
5. **Fill in Your settings:** `sheet_url` is your sheet's URL with its `gid` (open the tab, copy the address bar), `crm` is the type of your Evaboot destination (`hubspot`, `pipedrive`, `attio`, ...).
6. **Test:** click *Execute workflow*, enter 2 or 3 companies, and watch the sheet fill.

## Good to know

- Each run creates an account list and a lead list in your Sales Navigator, named with the date.
- The workflow waits 30 seconds after the lead list is saved: an export started at once can return no leads.
- The AI steps retry up to 3 times: Claude sometimes returns an empty answer.
- The push sends every exported lead. Delete the ones you reject in your CRM afterwards.

Back to the [README](../README.md).
