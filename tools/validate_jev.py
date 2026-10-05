"""Check the explainer's docs examples against real Jev answers via OpenRouter.

Usage:
    export OPENROUTER_API_KEY=...        # never commit the key
    python3 tools/validate_jev.py        # writes tools/validation-results.json

Uses OpenRouter's System One endpoint, which mirrors TypeSafe's native API.
Numbers will not match the docs exactly (model versions change); the point is
to confirm shapes, field names, the confidence formulas and the order of
magnitude of each docs example.
"""
import json, os, urllib.request

URL = "https://openrouter.ai/api/v1/systemone"
MODEL = os.environ.get("JEV_MODEL", "typesafe/jev-1.13")
KEY = os.environ["OPENROUTER_API_KEY"]

def call(state, questions):
    body = json.dumps({"state": state, "model": MODEL, "questions": questions}).encode()
    req = urllib.request.Request(URL, data=body, headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())

def choice_conf(p):
    n = len(p); m = max(p.values()); return (m - 1/n) / (1 - 1/n)

def score_conf(p):
    vals = [p[str(i)] for i in range(len(p))]; n = len(vals)
    m = max(range(n), key=lambda i: vals[i])
    d = sum(v * abs(i - m) for i, v in enumerate(vals))
    mad = sum(abs(i - (n - 1) / 2) for i in range(n)) / n
    return max(0.0, 1 - d / mad)

cases = []

# 1. Choice: docs ticket-routing example (docs: returns .61, billing .35, shipping .04, confidence .42)
cases.append(("choice_ticket", "Shoes arrived two weeks late and in the wrong size. Also I see two charges of $120 on my card. What are you going to do about this?",
  {"department": {"type": "choice", "instructions": "Which team should handle this?",
    "criteria": {"returns": "Exchanges, wrong or damaged items", "shipping": "Delivery status, delays, lost packages", "billing": "Charges, invoices, payment problems"}}}))

# 2. Score: docs PDF-export bug (docs: 0 / .89 / .11, score 1.11, confidence .84)
cases.append(("score_pdf", "Export to PDF fails with a spinner that never finishes. Some of our team say CSV export still works for them, others say it fails too.",
  {"bug_severity": {"type": "score", "instructions": "How severe is the reported issue?",
    "criteria": ["Cosmetic; no impact to functionality", "Broken or degraded feature, but workaround exists", "Blocking issue; no workaround exists"]}}))

# 3. Noul: the docs' six recorded human-escalation answers (.02 .07 .26 .40 .84 .99)
for i, msg in enumerate(["Thanks, that fixed it!", "How do I reset my password?", "I need this sorted today, whatever it takes.",
                         "Are you a bot?", "Is there any way to speak to someone about my invoice?",
                         "I have asked three times now. Can I please just talk to a real person?"]):
    cases.append((f"noul_{i}", msg, {"is_human_escalation": {"type": "noul", "instructions": "Is the customer asking for a human agent?"}}))

results = []
for name, state, qs in cases:
    try:
        res = call(state, qs)
        ans = next(iter(res["answers"].values()))
        check = {}
        if ans["type"] == "choice": check["confidence_recomputed"] = round(choice_conf(ans["probabilities"]), 3)
        if ans["type"] == "score":  check["confidence_recomputed"] = round(score_conf(ans["probabilities"]), 3)
        if ans["type"] == "noul":   check["confidence_optional"] = round(abs(2 * ans["noul"] - 1), 3)
        results.append({"case": name, "answer": ans, "check": check, "model": res.get("model"), "usage": res.get("usage")})
        print(name, json.dumps(ans), check)
    except Exception as e:
        results.append({"case": name, "error": str(e)}); print(name, "ERROR", e)

out = os.path.join(os.path.dirname(__file__), "validation-results.json")
json.dump(results, open(out, "w"), indent=2)
print("saved", out)
