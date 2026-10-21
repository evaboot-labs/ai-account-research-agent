"""Helpers for the account research agent. No network calls: the agent does the Evaboot work
through the Evaboot MCP and uses these commands to keep the choices and the facts deterministic.

    python3 research.py people-url --list <account_list_id>      Sales Navigator people search for the list
    python3 research.py pick <search.json> --accounts "A,B" [--per-company 3]   choose the senior sales leaders
    python3 research.py facts <export.json> --account-ids <ids> > research/facts.json   real signals per company
    python3 research.py sheet <facts.json> <briefs.json> > research/accounts.csv
"""
import argparse
import csv
import json
import re
import sys
from urllib.parse import quote

# Sales leadership titles. Edit TARGET.md to change who the agent looks for; keep this in step.
TITLES = ('(CRO OR "Chief Revenue Officer" OR "Chief Sales Officer") OR ((VP OR "Vice President" OR SVP '
          'OR Director OR "Senior Director" OR Head OR "Head of") AND (Sales OR Revenue OR '
          '"Business Development" OR Commercial)) NOT (Assistant OR Coordinator OR Analyst OR Intern OR Trainee)')

# Lower rank = more senior. Pre-sales, engineering and enablement roles are not buyers.
RANKS = [
    (r"\b(chief (revenue|sales|commercial) officer|cro|cso)\b", 1),
    (r"\b(svp|evp|senior vice president|executive vice president)\b", 2),
    (r"\b(vp|vice president)\b.*\b(sales|revenue|business development|commercial)\b", 3),
    (r"\bhead of (global |international )?(sales|business development|revenue|commercial)\b", 4),
    (r"\b(senior director|sr\.? director)\b", 5),
    (r"\bdirector\b", 6),
    (r"\bhead\b", 7),
]
NOT_BUYERS = re.compile(r"pre[- ]?sales|engineering|enablement|post sales|partnerships?\b(?!.*sales)", re.I)
# "CRO" is also conversion rate optimization: a marketing or web title with no sales word is not a buyer.
NOT_SALES = re.compile(r"optimi[sz]ation|marketing|\bweb\b", re.I)
SALES_WORD = re.compile(r"sales|revenue|business development|commercial", re.I)


def rank(title):
    if NOT_BUYERS.search(title) or (NOT_SALES.search(title) and not SALES_WORD.search(title)):
        return 99
    for pattern, r in RANKS:
        if re.search(pattern, title, re.I):
            return r
    return 50


def people_url(list_id):
    query = (f"(filters:List((type:ACCOUNT_LIST,values:List((id:{list_id},selectionType:INCLUDED))),"
             f"(type:CURRENT_TITLE,values:List((text:{quote(TITLES, safe='')},selectionType:INCLUDED)))))")
    return "https://www.linkedin.com/sales/search/people?query=" + quote(query, safe="()")


# A title with a region or segment ("VP Sales, Asia", "VP Sales - Defence") covers less than the global role.
SCOPED = re.compile(r",| - | – |\bregional\b|\bchannel\b", re.I)


def pick(path, per_company, accounts=None):
    """search.json = the result of the MCP tool search_sn_leads (elements: name, title, company, entityUrn).
    accounts: the company names of the account list. Sales Navigator shows page names such as
    "Quentic (an AMCS company)" or "Sellsy CRM & Invoicing | We're hiring!", and people who list
    a past employer; each name is matched to the account it starts with, the rest are dropped."""
    data = json.load(open(path))
    elements = data.get("elements") or data.get("data", {}).get("elements") or data.get("result", {}).get("data", {}).get("elements", [])
    names = sorted(accounts or [], key=len, reverse=True)
    by_company, seen, dropped = {}, set(), []
    for e in elements:
        company = re.split(r"\s*[|(]", e["company"])[0].strip()
        if names:
            company = next((a for a in names if company.lower().startswith(a.lower())), None)
            if not company:
                dropped.append(f'{e["name"]} ({e["company"]})')
                continue
        key = (e["name"].strip().lower(), company.lower())
        if key in seen:
            continue
        seen.add(key)
        by_company.setdefault(company, []).append({**e, "account": company, "rank": rank(e["title"])})
    chosen = []
    for company, people in by_company.items():
        people = sorted((p for p in people if p["rank"] < 99),
                        key=lambda p: (p["rank"], bool(SCOPED.search(p["title"].strip()))))
        chosen += people[:per_company]
    missing = [a for a in names if a not in by_company]
    return {"chosen": chosen, "no_match": missing, "dropped": dropped, "urns": [p["entityUrn"] for p in chosen]}


def num(v):
    try:
        return float(str(v).replace(",", ""))
    except ValueError:
        return None


def facts(path, account_ids=None):
    """export.json = the Evaboot export (get_export or the API). One entry per company, only real fields.
    account_ids: the LinkedIn company ids of the target list. A person who changed jobs since the list was
    made is exported with the new company: those people go to "left_account", not to the briefs."""
    out, left = {}, []
    for p in json.load(open(path)).get("prospects") or []:
        cid = (p.get("Company Linkedin URL Unique ID") or "").rstrip("/").split("/")[-1]
        if account_ids and cid not in account_ids:
            left.append({"name": p.get("Full Name"), "now_at": p["Company Name"], "title": p.get("Current Job")})
            continue
        c = out.setdefault(p["Company Name"], {
            "company": p["Company Name"],
            "website": p.get("Company Website URL") or "",
            "industry": p.get("Company Industry") or "",
            "linkedin_id": (p.get("Company Linkedin URL Unique ID") or "").rstrip("/").split("/")[-1],
            "employees": num(p.get("Company Employee Exact Count")) or None,
            "employee_range": p.get("Company Employee Range") or "",
            "growth_6m_pct": num(p.get("Company Employee Growth 6 Months (%)")),
            "growth_1y_pct": num(p.get("Company Employee Growth 1 Year (%)")),
            "growth_2y_pct": num(p.get("Company Employee Growth 2 Years (%)")),
            "sales_team": num(p.get("Sales Team Size")),
            "business_development_team": num(p.get("Business Development Size")),
            "founded": p.get("Company Year Founded") or "",
            "headquarters": p.get("Company Location") or "",
            "description": " ".join((p.get("Company Description") or "").split())[:500],
            "people": [],
        })
        c["people"].append({
            "name": p.get("Full Name") or "",
            "title": (p.get("Current Job") or "").strip(),
            "email": p.get("Email") or "",
            "email_status": p.get("Email Status") or "not found",
            # Evaboot splits tenure into years + months: 1 year 7 months = 19 months.
            "months_in_position": (num(p.get("Years in Position")) or 0) * 12 + (num(p.get("Months in Position")) or 0),
            "months_in_company": (num(p.get("Years in Company")) or 0) * 12 + (num(p.get("Months in Company")) or 0),
            "new_in_role": str(p.get("Has New Position")).lower() in ("true", "yes", "1"),
            "posts": p.get("Posting Frequency") or "",
            "linkedin": p.get("Linkedin URL Public") or "",
        })
    for c in out.values():
        c["people"].sort(key=lambda x: rank(x["title"]))
    return {"accounts": list(out.values()), "left_account": left}


def sheet(facts_path, briefs_path):
    briefs = json.load(open(briefs_path))
    w = csv.writer(sys.stdout)
    w.writerow(["Company", "Signal", "Why now", "Suggested opener", "Contact", "Title", "Email", "Email status", "LinkedIn", "Approve (yes/no)"])
    order = {"strong": 0, "medium": 1, "weak": 2}
    accounts = json.load(open(facts_path))["accounts"]
    for c in sorted(accounts, key=lambda c: order.get(briefs.get(c["company"], {}).get("signal"), 3)):
        b = briefs.get(c["company"], {})
        for i, p in enumerate(c["people"]):
            w.writerow([c["company"], b.get("signal", "") if i == 0 else "", b.get("why_now", "") if i == 0 else "", b.get("opener", "") if i == 0 else "",
                        p["name"], p["title"], p["email"], p["email_status"], p["linkedin"], ""])


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("people-url"); a.add_argument("--list", required=True)
    a = sub.add_parser("pick"); a.add_argument("search"); a.add_argument("--per-company", type=int, default=3)
    a.add_argument("--accounts", help="comma-separated company names of the account list")
    a = sub.add_parser("facts"); a.add_argument("export"); a.add_argument("--account-ids", help="comma-separated")
    a = sub.add_parser("sheet"); a.add_argument("facts"); a.add_argument("briefs")
    args = ap.parse_args()
    if args.cmd == "people-url":
        print(people_url(args.list))
    elif args.cmd == "pick":
        print(json.dumps(pick(args.search, args.per_company, args.accounts.split(",") if args.accounts else None), indent=2, ensure_ascii=False))
    elif args.cmd == "facts":
        ids = set(args.account_ids.split(",")) if args.account_ids else None
        print(json.dumps(facts(args.export, ids), indent=2, ensure_ascii=False))
    else:
        sheet(args.facts, args.briefs)


if __name__ == "__main__":
    main()
