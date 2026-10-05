"""Resumable update of existing issues and native blockers, authorized by operator."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
TASK = Path(__file__).resolve().parent
ROOT = TASK.parents[1]
REPO = "dsanti-lunara/radar-de-ofertas"
updates = json.loads((TASK / "updates.json").read_text(encoding="utf-8"))
initial = {x["number"]: x for x in json.loads((TASK / "remote-before.json").read_text(encoding="utf-8-sig"))}
plan_path = ROOT / ".scratch/radar-v1/publication-plan.json"
plan = json.loads(plan_path.read_text(encoding="utf-8"))
native_ids = {f"TKT-{p['number']:02d}": p["databaseId"] for p in plan["published"]}
progress_path = TASK / "publication-progress.json"
progress = json.loads(progress_path.read_text(encoding="utf-8")) if progress_path.exists() else {"bodies": [], "blockers": [], "verified": []}

def gh(*args):
    p = subprocess.run(["gh", *args], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode:
        raise RuntimeError(p.stderr.decode("utf-8", errors="replace"))
    return p.stdout.decode("utf-8-sig")

def record():
    progress_path.write_text(json.dumps(progress, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

for u in updates:
    number = u["number"]
    target = (ROOT / u["bodyFile"]).read_text(encoding="utf-8").replace("\r\n", "\n")
    current = json.loads(gh("issue", "view", str(number), "--repo", REPO, "--json", "title,body,state,labels"))
    assert current["state"] == "OPEN", (number, "state changed")
    current_body = current["body"].replace("\r\n", "\n")
    initial_body = initial[number]["body"].replace("\r\n", "\n")
    if current_body not in [target, initial_body]:
        raise RuntimeError(f"Concurrent body change on #{number}; preserved for reconciliation")
    allowed_titles = [initial[number]["title"], u["title"]]
    assert current["title"] in allowed_titles, (number, "concurrent title change")
    labels = {l["name"] for l in current["labels"]}
    if current_body != target or current["title"] != u["title"] or u["label"] not in labels or (number == 37 and "ready-for-agent" in labels):
        args = ["issue", "edit", str(number), "--repo", REPO, "--title", u["title"], "--body-file", str(ROOT / u["bodyFile"])]
        if u["label"] not in labels:
            args += ["--add-label", u["label"]]
        if number == 37 and "ready-for-agent" in labels:
            args += ["--remove-label", "ready-for-agent"]
        gh(*args)
    if number not in progress["bodies"]:
        progress["bodies"].append(number)
    record()
    print(f"Body/title/label updated #{number}", flush=True)

# Only approved removals: discovery is not mandatory to API link; API entitlement
# is not mandatory for manual link or manual Slice route.
expected_before = {48: {20, 37, 47}, 50: {20, 37, 49}, 51: {35, 37}}
for number in [48, 50, 51]:
    u = next(x for x in updates if x["number"] == number)
    endpoint = f"repos/{REPO}/issues/{number}/dependencies/blocked_by"
    actual = json.loads(gh("api", endpoint))
    actual_numbers = {x["number"] for x in actual}
    desired_numbers = {int(x.split("-")[1]) for x in u["blockedBy"]}
    assert actual_numbers in [expected_before[number], desired_numbers], (number, "concurrent dependency change", actual_numbers)
    for dependency in actual:
        if dependency["number"] not in desired_numbers:
            assert dependency["id"] == native_ids[f"TKT-{dependency['number']:02d}"]
            gh("api", "--method", "DELETE", endpoint + "/" + str(dependency["id"]))
    verified = {x["number"] for x in json.loads(gh("api", endpoint))}
    assert verified == desired_numbers, (number, verified, desired_numbers)
    if number not in progress["blockers"]:
        progress["blockers"].append(number)
    record()
    print(f"Native blockers verified #{number}: {sorted(verified)}", flush=True)

final = json.loads(gh("issue", "list", "--repo", REPO, "--state", "all", "--limit", "200", "--json", "number,title,body,state,labels,updatedAt"))
(TASK / "remote-after.json").write_text(json.dumps(final, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
by_number = {i["number"]: i for i in final}
assert len(final) == len(initial) == 67
for u in updates:
    number = u["number"]
    actual = by_number[number]
    assert actual["body"].replace("\r\n", "\n") == (ROOT / u["bodyFile"]).read_text(encoding="utf-8").replace("\r\n", "\n"), (number, "body mismatch")
    assert actual["title"] == u["title"] and actual["state"] == "OPEN"
    labels = {x["name"] for x in actual["labels"]}
    assert u["label"] in labels
    if number == 37:
        assert "ready-for-agent" not in labels
    if number not in progress["verified"]:
        progress["verified"].append(number)
    u["remoteUpdatedAt"] = actual["updatedAt"]
    u["bodySha256"] = hashlib.sha256(actual["body"].replace("\r\n", "\n").encode()).hexdigest()
plan["reconRevision"]["status"] = "published-and-verified"
plan["reconRevision"]["nativeBlockerChanges"] = {str(n): next(x["blockedBy"] for x in updates if x["number"] == n) for n in [48, 50, 51]}
plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
(TASK / "updates.json").write_text(json.dumps(updates, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
record()
print("PASS: 28 remote issue bodies/titles/labels and 3 native dependency sets verified; 67 existing issues preserved; no issues created/closed.", flush=True)
