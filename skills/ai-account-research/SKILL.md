---
name: ai-account-research
description: Research a short list of target accounts for outbound - find the 2 to 3 most senior sales leaders at each company in Sales Navigator, get their verified emails with Evaboot, write a "why now" brief and an opener per company from real company and role data, put everything in a sheet for approval, then push the approved leads to the user's CRM. Use when the user gives a list of target companies and asks for account research, decision makers, an account-based list, or who to contact and why now.
---

# AI account research

This skill runs inside a clone of https://github.com/evaboot-labs/ai-account-research-agent: it uses the repo's `research.py`, `TARGET.md` and `docs/`. If `research.py` is not in the working directory, clone the repo and work from there.

You do the Sales Navigator and Evaboot work through the Evaboot MCP server (`https://mcp.evaboot.com/mcp`). Every tool named below is an Evaboot MCP tool. `research.py` makes no network calls: it builds the search URL, picks the people, and turns the export into facts and a sheet, so the choices are the same on every run.

## Rules

- Confirm with the user before every call that writes to their Sales Navigator seat, spends credits, or sends data: `create_account_list_from_ids`, `create_lead_list_from_ids`, `export_sn_search_or_list`, `push_export`. Show what you will do and the credit cost, then wait for a yes.
- The export costs 1 credit per lead. Export only the people you picked, never the whole search.
- Write a brief only from fields in the export (see [references/signals.md](references/signals.md)). Never add a fact from memory or the web. If a company has no signal, say "no timing trigger" and leave the opener empty.
- Never send an email. This skill stops at the CRM.
- Print every Sales Navigator URL as a Markdown link with the URL in angle brackets: `[Open in Sales Navigator](<url>)`.

## Step 0: check the setup

1. Call `verify_token` and `get_daily_export_quota`. `has_valid_salesnav` must be true. If not, send the user to `docs/connect-your-agent.md`, step 1.
2. Read `TARGET.md`. If it still holds the example, ask the user which roles they sell to and update it. If they change the titles, update `TITLES` and `RANKS` in `research.py` to match.
3. Ask for the target companies: names or LinkedIn company URLs, about 10. More than 25 makes the sheet hard to review.

## Step 1: resolve each company to its LinkedIn id

Company names are ambiguous ("Pexip" and "PEXIP LIMITED" are two pages). For each company:

1. Call `search_sn_accounts` with a Sales Navigator account search URL for the name. The id is the number in `entityUrn` (`urn:li:fs_salesCompany:<id>`).
2. If several results match, show the user the candidates with their size and location, and let them pick.
3. If none match, tell the user and drop the company.

Do not use `build_sn_search_from_prompt` to pin named companies: it does not resolve all of them.

Show the resolved list (name, id, employees). On a yes, call `create_account_list_from_ids` with the ids. Keep the list id and the company ids.

## Step 2: find the sales leaders, free

1. Run `python3 research.py people-url --list <account_list_id>`. This is a people search on the account list with the titles from `TARGET.md`.
2. Call `search_sn_leads` on that URL with `count: 100`. This preview costs nothing. Save the result to `data/search.json`.
3. If `paging.total` is over 100, call `search_sn_leads` again with `start: 100` and add the elements to the file.
4. Run `python3 research.py pick data/search.json --accounts "<the resolved company names>" --per-company 3`. It keeps the most senior buyers per company (CRO, then SVP, VP, Head of Sales, Director, global roles before regional ones), drops pre-sales, engineering and enablement roles, merges page-name variants ("Quentic (an AMCS company)") and drops people whose company is not in the list (`dropped`).
5. Show the picks per company. Flag the companies in `no_match`: small companies often have no sales title. Offer their founder or CEO instead, with a second `search_sn_leads` on a founder title.

## Step 3: export only the picked people

1. On a yes, call `create_lead_list_from_ids` with the `urns` from `pick` (the full `urn:li:fs_salesProfile:(...)` values).
2. Call `export_sn_search_or_list` on that lead list with emails, then poll `get_export` until it is done. Save the JSON to `data/export.json`.
3. Run `python3 research.py facts data/export.json --account-ids <comma-separated company ids> > research/facts.json`.
4. Read `left_account` in the output. People there changed company after the list was made. Tell the user, and keep them out of the briefs.

## Step 4: write the briefs

Read [references/signals.md](references/signals.md), then write `research/briefs.json`: one entry per company with `signal` (`strong`, `medium` or `weak`), `why_now` (two sentences at most, every number from `facts.json`) and `opener` (one or two sentences to the most senior contact). Then:

```bash
python3 research.py sheet research/facts.json research/briefs.json > research/accounts.csv
```

## Step 5: approval

Put `research/accounts.csv` where the user reviews: a Google Sheet when the session has a Google Drive tool, otherwise the CSV file. Strong accounts come first. Ask the user to mark each row `yes` or `no` in the last column, or to tell you what to change. Wait.

## Step 6: push to the CRM

1. Call `list_integrations`. Use the user's CRM row (HubSpot, Pipedrive, Attio or any other) with `setup_finished: true`. If there is none, send them to https://dash.evaboot.com/dash/integrations/ to connect it, and wait.
2. The push sends every lead of the export. If the user rejected some rows, tell them those leads arrive too and must be deleted in the CRM, or offer to skip the push and import the approved rows of the CSV instead.
3. On a yes, call `push_export` with the integration id and the extraction id. If the status is `running`, poll `get_push`. Report how many leads arrived.

The briefs stay in the sheet: the push carries the Evaboot fields, not the briefs.
