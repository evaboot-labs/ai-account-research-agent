"""Builds n8n/ai-account-research-agent.json. Run: python3 n8n/build_workflow.py

The AI Agent only resolves the company names (that needs judgement). Everything after it is
deterministic: the same title search, picks and facts as research.py, then Claude writes the briefs.
"""
import json
import uuid
from pathlib import Path

MCP = "https://mcp.evaboot.com/mcp"
EVABOOT_CRED = {"httpBearerAuth": {"id": "", "name": "Evaboot MCP (Bearer)"}}
ANTHROPIC_CRED = {"anthropicApi": {"id": "", "name": "Anthropic"}}
SHEETS_CRED = {"googleSheetsOAuth2Api": {"id": "", "name": "Google Sheets account"}}
MODEL = "claude-sonnet-5-5"

nodes, connections = [], {}


def node(name, type_, version, params, pos, creds=None):
    n = {"parameters": params, "id": str(uuid.uuid4()), "name": name, "type": type_,
         "typeVersion": version, "position": pos}
    if creds:
        n["credentials"] = creds
    nodes.append(n)
    return name


def link(a, b, kind="main", out=0):
    connections.setdefault(a, {}).setdefault(kind, [])
    while len(connections[a][kind]) <= out:
        connections[a][kind].append([])
    connections[a][kind][out].append({"node": b, "type": kind, "index": 0})


def mcp_call(name, tool, json_expr, pos):
    return node(name, "@n8n/n8n-nodes-langchain.mcpClient", 1.1, {
        "endpointUrl": MCP, "authentication": "bearerAuth",
        "tool": {"__rl": True, "mode": "list", "value": tool, "cachedResultName": tool},
        "inputMode": "json", "jsonInput": json_expr, "options": {"timeout": 120000},
    }, pos, EVABOOT_CRED)


def code(name, js, pos):
    return node(name, "n8n-nodes-base.code", 2, {"jsCode": js}, pos)


# Every MCP Client result arrives as text content; this unwraps it to the tool's JSON.
UNWRAP = """
function unwrap(j) {
  let d = j && j.structuredContent ? j.structuredContent : j;
  if (d && Array.isArray(d.content) && d.content[0]) {
    const t = d.content[0].text;
    d = typeof t === 'string' ? JSON.parse(t) : t;
  }
  return d && d.result !== undefined ? d.result : d;
}
"""

TITLES = ('(CRO OR "Chief Revenue Officer" OR "Chief Sales Officer") OR ((VP OR "Vice President" OR SVP '
          'OR Director OR "Senior Director" OR Head OR "Head of") AND (Sales OR Revenue OR '
          '"Business Development" OR Commercial)) NOT (Assistant OR Coordinator OR Analyst OR Intern OR Trainee)')

PEOPLE_URL_JS = UNWRAP + r"""
// Same URL as research.py people-url: the account list plus the sales leadership titles.
const TITLES = %s;
function q(s, safe) {
  return Array.from(new TextEncoder().encode(s)).map(b => {
    const c = String.fromCharCode(b);
    return /[A-Za-z0-9_.~-]/.test(c) || safe.includes(c) ? c : '%%' + b.toString(16).toUpperCase().padStart(2, '0');
  }).join('');
}
const r = $('Resolve the companies').first().json.output;
const query = `(filters:List((type:ACCOUNT_LIST,values:List((id:${r.account_list_id},selectionType:INCLUDED))),` +
  `(type:CURRENT_TITLE,values:List((text:${q(TITLES, '')},selectionType:INCLUDED)))))`;
return [{ json: { search_url: 'https://www.linkedin.com/sales/search/people?query=' + q(query, '()'), count: 100 } }];
""" % json.dumps(TITLES)

PICK_JS = UNWRAP + r"""
// Same rules as research.py pick: most senior buyers first, global roles before regional ones.
const RANKS = [
  [/\b(chief (revenue|sales|commercial) officer|cro|cso)\b/i, 1],
  [/\b(svp|evp|senior vice president|executive vice president)\b/i, 2],
  [/\b(vp|vice president)\b.*\b(sales|revenue|business development|commercial)\b/i, 3],
  [/\bhead of (global |international )?(sales|business development|revenue|commercial)\b/i, 4],
  [/\b(senior director|sr\.? director)\b/i, 5],
  [/\bdirector\b/i, 6],
  [/\bhead\b/i, 7],
];
const NOT_BUYERS = /pre[- ]?sales|engineering|enablement|post sales|partnerships?\b(?!.*sales)/i;
// "CRO" is also conversion rate optimization: a marketing or web title with no sales word is not a buyer.
const NOT_SALES = /optimi[sz]ation|marketing|\bweb\b/i;
const SALES_WORD = /sales|revenue|business development|commercial/i;
const SCOPED = /,| - | – |\bregional\b|\bchannel\b/i;
const rank = t => NOT_BUYERS.test(t) || (NOT_SALES.test(t) && !SALES_WORD.test(t)) ? 99 : (RANKS.find(([re]) => re.test(t)) || [0, 50])[1];

const data = unwrap($json);
const elements = (data.data && data.data.elements) || data.elements || [];
const resolved = $('Resolve the companies').first().json.output.companies.map(c => c.name);
const names = [...resolved].sort((a, b) => b.length - a.length);
const per = Number($('Target accounts').first().json['Leaders per company']) || 3;
const byCompany = {}, seen = new Set(), dropped = [];
for (const e of elements) {
  const page = e.company.split(/\s*[|(]/)[0].trim();
  const account = names.find(a => page.toLowerCase().startsWith(a.toLowerCase()));
  if (!account) { dropped.push(`${e.name} (${e.company})`); continue; }
  const key = e.name.trim().toLowerCase() + '|' + account.toLowerCase();
  if (seen.has(key)) continue;
  seen.add(key);
  (byCompany[account] = byCompany[account] || []).push({ ...e, account, rank: rank(e.title) });
}
const chosen = [];
for (const people of Object.values(byCompany)) {
  people.filter(p => p.rank < 99)
    .sort((a, b) => a.rank - b.rank || SCOPED.test(a.title.trim()) - SCOPED.test(b.title.trim()))
    .slice(0, per).forEach(p => chosen.push(p));
}
return [{ json: {
  chosen, urns: chosen.map(p => p.entityUrn), dropped,
  no_match: resolved.filter(a => !byCompany[a]),
} }];
"""

FACTS_JS = UNWRAP + r"""
// Same as research.py facts: real fields only, tenure = years * 12 + months.
const num = v => { const n = parseFloat(String(v ?? '').replace(/,/g, '')); return isNaN(n) ? null : n; };
const ids = new Set($('Resolve the companies').first().json.output.companies.map(c => String(c.id)));
const prospects = unwrap($json).prospects || [];
if (!prospects.length) throw new Error('The export returned no leads. Open the lead list in Sales Navigator and check it is not empty.');
const out = {}, left = [];
for (const p of prospects) {
  const cid = String(p['Company Linkedin URL Unique ID'] || '').replace(/\/$/, '').split('/').pop();
  if (!ids.has(cid)) { left.push({ name: p['Full Name'], now_at: p['Company Name'], title: p['Current Job'] }); continue; }
  const c = out[p['Company Name']] = out[p['Company Name']] || {
    company: p['Company Name'], employees: num(p['Company Employee Exact Count']) || null,
    employee_range: p['Company Employee Range'] || '',
    growth_6m_pct: num(p['Company Employee Growth 6 Months (%)']),
    growth_1y_pct: num(p['Company Employee Growth 1 Year (%)']),
    growth_2y_pct: num(p['Company Employee Growth 2 Years (%)']),
    sales_team: num(p['Sales Team Size']), business_development_team: num(p['Business Development Size']),
    description: String(p['Company Description'] || '').split(/\s+/).join(' ').slice(0, 500), people: [],
  };
  c.people.push({
    name: p['Full Name'] || '', title: String(p['Current Job'] || '').trim(),
    email: p['Email'] || '', email_status: p['Email Status'] || 'not found',
    months_in_position: (num(p['Years in Position']) || 0) * 12 + (num(p['Months in Position']) || 0),
    new_in_role: ['true', 'yes', '1'].includes(String(p['Has New Position']).toLowerCase()),
    linkedin: p['Linkedin URL Public'] || '',
  });
}
return [{ json: { accounts: Object.values(out), left_account: left } }];
"""

ROWS_JS = r"""
// One row per contact; the company's brief sits on its first row. Strong accounts first.
const order = { strong: 0, medium: 1, weak: 2 };
const briefs = Object.fromEntries($json.output.briefs.map(b => [b.company, b]));
const accounts = $('Company facts').first().json.accounts
  .sort((a, b) => (order[(briefs[a.company] || {}).signal] ?? 3) - (order[(briefs[b.company] || {}).signal] ?? 3));
const rows = [];
for (const c of accounts) {
  const b = briefs[c.company] || {};
  c.people.forEach((p, i) => rows.push({ json: {
    'Company': c.company, 'Signal': i ? '' : b.signal || '', 'Why now': i ? '' : b.why_now || '',
    'Suggested opener': i ? '' : b.opener || '', 'Contact': p.name, 'Title': p.title,
    'Email': p.email, 'Email status': p.email_status, 'LinkedIn': p.linkedin, 'Approve (yes/no)': '',
  } }));
}
return rows;
"""

PICK_CRM_JS = UNWRAP + r"""
const want = String($('Your settings').first().json.crm).toLowerCase();
const rows = unwrap($json).integrations || [];
const crm = rows.find(r => r.type === want && r.setup_finished && r.status === 'active');
if (!crm) throw new Error(`No connected ${want} destination in Evaboot. Connect it at https://dash.evaboot.com/dash/integrations/`);
return [{ json: { integration_id: crm.id, label: crm.label } }];
"""

RESOLVE_SYSTEM = """You resolve a user's target companies to their LinkedIn Sales Navigator company ids, then save them as one account list. Use only the Evaboot tools.

1. For each company, call search_sn_accounts with search_url = https://www.linkedin.com/sales/search/company?query=(keywords:<company name, URL-encoded>) and count 5. The id is the number at the end of entityUrn (urn:li:fs_salesCompany:<id>).
2. Pick the result whose name matches the company best. If the user gave a LinkedIn URL, use its id. If nothing matches, put the company in not_found.
3. Call create_account_list_from_ids once with all the ids and list_name "Account research - <today's date>".
4. Return the list id and, for each company, the exact name shown by Sales Navigator and its id.

Never call any other tool. Never export anything."""

BRIEF_SYSTEM = """You write a "why now" brief per company for a sales team, from the JSON facts you are given. Use only those facts: never add anything from memory.

Signals, strongest first: a new sales leader (new_in_role true, or months_in_position under 6); fast growth (growth_2y_pct over 30, or growth_1y_pct over 15); two or more people under 12 months in role; team shape (sales_team, business_development_team); shrinking headcount (growth_2y_pct under -10).
Grade (the signal field is exactly one word: strong, medium or weak): strong = a new sales leader, or fast growth with a new hire. medium = one weaker signal. weak = none: write "No timing trigger" and why, and leave the opener empty.
Rules: why_now is two sentences at most and names people by title, not by name. Always give the period of a growth number ("up 50% in 2 years"). A title that is no longer a sales title means the person moved on: say so. The opener is one or two sentences to the most senior contact, by first name: it names the signal and asks a question or makes one observation. No pitch, no product name."""

# Nodes, left to right.
node("Target accounts", "n8n-nodes-base.formTrigger", 2.2, {
    "formTitle": "Research target accounts",
    "formDescription": "Your AI Agent finds the sales leaders at each company, gets their verified emails with Evaboot, and writes a why-now brief per company. The export costs 1 Evaboot credit per lead.",
    "formFields": {"values": [
        {"fieldLabel": "Target companies", "fieldType": "textarea", "requiredField": True,
         "placeholder": "One company name or LinkedIn company URL per line, about 10"},
        {"fieldLabel": "Leaders per company", "fieldType": "number", "requiredField": True, "placeholder": "3"},
    ]},
    "responseMode": "lastNode", "options": {},
}, [0, 0])
node("Your settings", "n8n-nodes-base.set", 3.4, {"assignments": {"assignments": [
    {"id": str(uuid.uuid4()), "name": "sheet_url", "type": "string",
     "value": "PASTE_YOUR_GOOGLE_SHEET_URL_WITH_GID"},
    {"id": str(uuid.uuid4()), "name": "crm", "type": "string", "value": "hubspot"},
]}, "includeOtherFields": True, "options": {}}, [220, 0])
node("Resolve the companies", "@n8n/n8n-nodes-langchain.agent", 2.2, {
    "promptType": "define", "text": "={{ $('Target accounts').item.json['Target companies'] }}",
    "hasOutputParser": True, "options": {"systemMessage": RESOLVE_SYSTEM, "maxIterations": 40},
}, [440, 0])
node("Claude", "@n8n/n8n-nodes-langchain.lmChatAnthropic", 1.3, {
    "model": {"__rl": True, "mode": "list", "value": MODEL, "cachedResultName": MODEL},
    "options": {"maxTokensToSample": 4000},
}, [380, 220], ANTHROPIC_CRED)
node("Evaboot MCP", "@n8n/n8n-nodes-langchain.mcpClientTool", 1.4, {
    "endpointUrl": MCP, "authentication": "bearerAuth", "include": "selected",
    "includeTools": ["search_sn_accounts", "create_account_list_from_ids"], "options": {"timeout": 120000},
}, [500, 220], EVABOOT_CRED)
node("Account list", "@n8n/n8n-nodes-langchain.outputParserStructured", 1.3, {
    "jsonSchemaExample": json.dumps({"account_list_id": "7518731638898372608",
                                     "companies": [{"name": "Pexip", "id": "2914650"}],
                                     "not_found": ["Acme"]}, indent=2),
}, [620, 220])
code("Build the people search", PEOPLE_URL_JS, [700, 0])
mcp_call("Preview the sales leaders", "search_sn_leads",
         "={{ JSON.stringify({ search_url: $json.search_url, count: $json.count }) }}", [920, 0])
code("Pick the most senior", PICK_JS, [1140, 0])
mcp_call("Save the picks as a lead list", "create_lead_list_from_ids",
         "={{ JSON.stringify({ profile_urns: $json.urns, list_name: 'Account research - picks ' + $now.toFormat('yyyy-MM-dd HH:mm') }) }}",
         [1360, 0])
node("Let LinkedIn save the list", "n8n-nodes-base.wait", 1.1, {"amount": 30}, [1470, 200])
mcp_call("Export with emails", "export_sn_search_or_list",
         "={{ JSON.stringify({ linkedin_url: 'https://www.linkedin.com/sales/lists/people/' + "
         "$json.structuredContent.result.batches[0].list_id, search_name: 'Account research - picks', list_category: 'all' }) }}", [1580, 0])
node("Wait 30 s", "n8n-nodes-base.wait", 1.1, {"amount": 30}, [1800, 0])
mcp_call("Check the export", "get_export",
         "={{ JSON.stringify({ extraction_id: $('Export with emails').first().json.structuredContent.result.extraction_id }) }}", [2020, 0])
node("Done?", "n8n-nodes-base.if", 2.2, {"conditions": {
    "options": {"caseSensitive": True, "typeValidation": "loose", "version": 2},
    "conditions": [{"id": str(uuid.uuid4()), "leftValue": "={{ $json.structuredContent.result.status }}",
                    "rightValue": "EXECUTED", "operator": {"type": "string", "operation": "equals"}}],
    "combinator": "and"}, "options": {}}, [2240, 0])
code("Company facts", FACTS_JS, [2460, -100])
node("Write the briefs", "@n8n/n8n-nodes-langchain.agent", 2.2, {
    "promptType": "define", "text": "={{ JSON.stringify($json.accounts) }}", "hasOutputParser": True,
    "options": {"systemMessage": BRIEF_SYSTEM, "maxIterations": 3},
}, [2680, -100])
node("Claude (briefs)", "@n8n/n8n-nodes-langchain.lmChatAnthropic", 1.3, {
    "model": {"__rl": True, "mode": "list", "value": MODEL, "cachedResultName": MODEL},
    "options": {"maxTokensToSample": 6000},
}, [2640, 120], ANTHROPIC_CRED)
node("Briefs", "@n8n/n8n-nodes-langchain.outputParserStructured", 1.3, {
    "schemaType": "manual",
    "inputSchema": json.dumps({"type": "object", "required": ["briefs"], "properties": {"briefs": {
        "type": "array", "items": {"type": "object", "required": ["company", "signal", "why_now", "opener"],
                                   "properties": {"company": {"type": "string"},
                                                  "signal": {"type": "string", "enum": ["strong", "medium", "weak"]},
                                                  "why_now": {"type": "string"}, "opener": {"type": "string"}}}}}},
                              indent=2),
}, [2780, 120])
code("One row per contact", ROWS_JS, [2900, -100])
node("Add to the approval sheet", "n8n-nodes-base.googleSheets", 4.7, {
    "operation": "append",
    "documentId": {"__rl": True, "mode": "url", "value": "={{ $('Your settings').first().json.sheet_url }}"},
    "sheetName": {"__rl": True, "mode": "url", "value": "={{ $('Your settings').first().json.sheet_url }}"},
    "columns": {"mappingMode": "autoMapInputData", "value": {}, "matchingColumns": [], "schema": []},
    "options": {},
}, [3120, -100], SHEETS_CRED)
node("Approve", "n8n-nodes-base.form", 2.3, {
    "formFields": {"values": [{"fieldLabel": "Push these leads to your CRM?", "fieldType": "dropdown",
                               "fieldOptions": {"values": [{"option": "Yes, push them"}, {"option": "No, stop here"}]},
                               "requiredField": True}]},
    "options": {"formTitle": "Review the sheet",
                "formDescription": "Read the briefs in your approval sheet first. The push sends every exported lead, so delete the ones you reject in the CRM afterwards."},
}, [3340, -100])
node("Approved?", "n8n-nodes-base.if", 2.2, {"conditions": {
    "options": {"caseSensitive": True, "typeValidation": "strict", "version": 2},
    "conditions": [{"id": str(uuid.uuid4()), "leftValue": "={{ $json['Push these leads to your CRM?'] }}",
                    "rightValue": "Yes, push them", "operator": {"type": "string", "operation": "equals"}}],
    "combinator": "and"}, "options": {}}, [3560, -100])
mcp_call("Find the CRM", "list_integrations", "{}", [3780, -200])
code("Pick the CRM", PICK_CRM_JS, [4000, -200])
mcp_call("Push to the CRM", "push_export",
         "={{ JSON.stringify({ integration_id: $json.integration_id, extraction_id: "
         "$('Export with emails').first().json.structuredContent.result.extraction_id }) }}",
         [4220, -200])
node("Pushed", "n8n-nodes-base.form", 2.3, {"operation": "completion", "completionTitle": "Leads pushed",
                                            "completionMessage": "The approved leads are on their way to your CRM.",
                                            "options": {}}, [4440, -200])
node("Stopped", "n8n-nodes-base.form", 2.3, {"operation": "completion", "completionTitle": "Nothing pushed",
                                             "completionMessage": "The briefs stay in your sheet.", "options": {}},
     [3780, 0])

for a, b in [("Target accounts", "Your settings"), ("Your settings", "Resolve the companies"),
             ("Resolve the companies", "Build the people search"), ("Build the people search", "Preview the sales leaders"),
             ("Preview the sales leaders", "Pick the most senior"), ("Pick the most senior", "Save the picks as a lead list"),
             ("Save the picks as a lead list", "Let LinkedIn save the list"),
             ("Let LinkedIn save the list", "Export with emails"), ("Export with emails", "Wait 30 s"),
             ("Wait 30 s", "Check the export"), ("Check the export", "Done?"),
             ("Company facts", "Write the briefs"), ("Write the briefs", "One row per contact"),
             ("One row per contact", "Add to the approval sheet"),
             ("Find the CRM", "Pick the CRM"), ("Pick the CRM", "Push to the CRM"), ("Push to the CRM", "Pushed")]:
    link(a, b)
link("Done?", "Company facts", out=0)
link("Done?", "Wait 30 s", out=1)
link("Approved?", "Find the CRM", out=0)
link("Approved?", "Stopped", out=1)
link("Claude", "Resolve the companies", "ai_languageModel")
link("Evaboot MCP", "Resolve the companies", "ai_tool")
link("Account list", "Resolve the companies", "ai_outputParser")
link("Claude (briefs)", "Write the briefs", "ai_languageModel")
link("Briefs", "Write the briefs", "ai_outputParser")

# Claude sometimes returns an empty final answer, which fails the output parser; a retry fixes it.
for n in nodes:
    if n["type"] == "@n8n/n8n-nodes-langchain.agent":
        n.update({"retryOnFail": True, "maxTries": 3, "waitBetweenTries": 2000})

# The sheet append runs once per row; the approval form must run once.
nodes[[n["name"] for n in nodes].index("Add to the approval sheet")]["executeOnce"] = False
link("Add to the approval sheet", "Approve")
nodes[[n["name"] for n in nodes].index("Approve")]["executeOnce"] = True
link("Approve", "Approved?")

workflow = {"name": "AI account research agent (Evaboot MCP + Claude)", "nodes": nodes,
            "connections": connections, "settings": {"executionOrder": "v1"}, "pinData": {}}
out = Path(__file__).with_name("ai-account-research-agent.json")
out.write_text(json.dumps(workflow, indent=2, ensure_ascii=False) + "\n")
print(out, len(nodes), "nodes")
