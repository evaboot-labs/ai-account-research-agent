# Why-now signals

A "why now" brief says why this company might buy this quarter. It uses only the fields that `research.py facts` returns. If a fact is not in `facts.json`, it does not go in the brief.

## The signals, strongest first

| Signal | Field in `facts.json` | Reads as |
|---|---|---|
| New sales leader | `people[].new_in_role` is true, or `months_in_position` under 6 | A new leader resets the plan and the tools in the first months. |
| Fast growth | `growth_2y_pct` over 30, or `growth_1y_pct` over 15 | More people and more territory to cover. |
| Sales team build-out | Two or more people with `months_in_position` under 12 | The team is being rebuilt or expanded. |
| Team shape | `sales_team` and `business_development_team` | A large prospecting team to keep fed, or a very small one. |
| Shrinking headcount | `growth_2y_pct` under -10 | The same targets with fewer people. Lead with efficiency. |

`months_in_position` already adds the years: Evaboot splits tenure into years and months, and `research.py` joins them.

## Grading

- **strong:** a new sales leader, or fast growth together with a new hire.
- **medium:** one weaker signal: team shape, a new hire outside sales, or shrinking headcount.
- **weak:** none of the above. Write "No timing trigger" and why, and leave the opener empty. Do not invent a reason.

## Checks before you write

- A title that is not a sales title any more (for example "Co-Founder, Board Member") means the person moved on. Say so in the brief.
- `employees` can be empty. Use `employee_range` then.
- Never quote a growth number without its period ("up 50% in 2 years").

## People in the brief

The brief names people by title, not by name ("New VP Sales, 2 months in the role"): it is about the account. The opener is the only place for a first name.

## Opener

One or two sentences to the most senior contact, by first name. It names the signal and asks a question or makes one observation. No pitch, no product name, no flattery beyond a short congratulation on a new role.
