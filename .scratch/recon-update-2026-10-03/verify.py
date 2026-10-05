"""Document/traceability checks, not product acceptance tests."""
from pathlib import Path
import json
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
TASK = Path(__file__).resolve().parent
ROOT = TASK.parents[1]
plan = json.loads((ROOT / ".scratch/radar-v1/publication-plan.json").read_text(encoding="utf-8"))
old_plan = json.loads((TASK / "before/.scratch/radar-v1/publication-plan.json").read_text(encoding="utf-8"))
updates = json.loads((TASK / "updates.json").read_text(encoding="utf-8"))
remote = {x["number"]: x for x in json.loads((TASK / "remote-before.json").read_text(encoding="utf-8-sig"))}
assert len(plan["tickets"]) == len(old_plan["tickets"]) == 67
assert {x["id"]: x["rdr"] for x in plan["tickets"]} == {x["id"]: x["rdr"] for x in old_plan["tickets"]}
assert {r for x in plan["tickets"] for r in x["rdr"]} == {f"RDR-{i:03d}" for i in range(1, 135)}
required = ["Objective / What to build", "Context / SDD references", "In scope", "Out of scope", "Blocked by", "External gates / prerequisites", "Contracts", "Implementation constraints", "Acceptance criteria", "Tests required", "Observability", "Documentation to update", "Completion report"]
for u in updates:
    text = (ROOT / u["bodyFile"]).read_text(encoding="utf-8")
    assert "\ufffd" not in text, (u["number"], "encoding")
    assert text.startswith(f"# TKT-{u['number']:02d}: {u['title'].split('] ', 1)[1]}\n"), u["number"]
    for heading in required:
        assert text.count("## " + heading + "\n") == 1, (u["number"], heading)
    before_rdr = re.search(r"^Cobertura canônica:.*$", remote[u["number"]]["body"], flags=re.M)[0]
    assert before_rdr in text, (u["number"], "RDR body coverage")
    assert "publicação ainda pendente" not in text, u["number"]
    assert "test Channel" not in text and "assisted portal capture" not in text, u["number"]
    assert "6+8 verificações offline" in text and "AUTO" in text, u["number"]
    assert "- [x]" not in text, (u["number"], "no unproved acceptance")
    ticket = next(t for t in plan["tickets"] if int(t["id"].split("-")[1]) == u["number"])
    assert ticket["blockedBy"] == u["blockedBy"]
    assert ticket["title"] == u["title"].split("] ", 1)[1]

by_id = {t["id"]: t for t in plan["tickets"]}
visiting, visited = set(), set()
def visit(node):
    assert node not in visiting, (node, "dependency cycle")
    if node in visited:
        return
    visiting.add(node)
    for dep in by_id[node]["blockedBy"]:
        assert dep in by_id
        visit(dep)
    visiting.remove(node)
    visited.add(node)
for key in by_id:
    visit(key)
assert by_id["TKT-48"]["blockedBy"] == ["TKT-20", "TKT-37"]
assert by_id["TKT-50"]["blockedBy"] == ["TKT-20", "TKT-49"]
assert by_id["TKT-51"]["blockedBy"] == ["TKT-35"]
assert by_id["TKT-51"]["alternativeRoutes"] == [["TKT-47", "TKT-48"], ["TKT-49", "TKT-48"], ["TKT-49", "TKT-50"]]
for route in by_id["TKT-51"]["alternativeRoutes"]:
    assert all(x in by_id for x in route)

# Fixture bytes and existing test code are immutable in this revision.
for filename in ["FIXTURES_SANITIZED.json", "FOLLOWUP_EVIDENCE.json", "SELECTOR_REGISTRY_CANDIDATE.json", "verify_recon_fixtures.py", "verify_followup_evidence.py"]:
    assert f"docs/recon/2026-10-02/{filename}" not in json.loads((TASK / "changed-files.json").read_text(encoding="utf-8"))
active = ["docs/00_SDD_MASTER.md", "docs/07_BROWSER_BRIDGE.md", "docs/09_PUBLISHING.md", "docs/14_DELIVERY_PLAN.md"]
for path in active:
    content = (ROOT / path).read_text(encoding="utf-8")
    assert "PUBLISH_WHATSAPP_CHANNEL" not in content
    assert "WhatsApp Channels" not in content
bridge = (ROOT / "docs/07_BROWSER_BRIDGE.md").read_text(encoding="utf-8")
assert "- GENERATE_SHOPEE_AFFILIATE_LINK" not in bridge
print("PASS: 67 tickets / RDR-001..134 preserved; 28 complete issue bodies; acyclic blockers and 3 routes; no unproved AC; fixture/test files unchanged.")
