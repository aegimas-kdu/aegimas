import json
import tempfile
import threading
import time
from pathlib import Path

import ledger
from ledger import Ledger, LedgerTamperedError

# Work on throwaway files so the real ledger.jsonl is never touched.
_tmp = tempfile.TemporaryDirectory()
TMP = Path(_tmp.name)
ledger.LEDGER_FILE = TMP / "ledger_test.jsonl"


def reading(i, parents=None):
    return {"agent_id": f"agent_{i % 3}", "tool_id": f"tool_{i % 2}",
            "key": f"stock:W{i % 4}:K1", "value": 50 + i,
            "parent_decision_ids": parents or []}


def fresh(n=10):
    ledger.LEDGER_FILE.unlink(missing_ok=True)
    return ledger.append_many([reading(i) for i in range(n)])


def read_lines(path=None):
    return (path or ledger.LEDGER_FILE).read_text().splitlines()


def write_lines(lines, path=None):
    (path or ledger.LEDGER_FILE).write_text("\n".join(lines) + "\n")


def blocked(call):
    try:
        call()
    except ValueError as err:
        return str(err)
    raise AssertionError("expected ValueError, but the call succeeded")


def check(label, condition):
    print(("PASS  " if condition else "FAIL  ") + label)
    assert condition, label


# 1. Ten readings: the chain is valid, and decision_id is the position
stored = fresh()
check("10 readings, chain OK", ledger.verify_chain())
check("decision_ids run 0..9", [e["decision_id"] for e in stored] == list(range(10)))

# 2. Coordinator input: the agent-report names are accepted too
e = ledger.append({"agent": "W_Agent_1", "answer": 50,
                   "source": "warehouse_inventory_db", "key": "stock:W1:K1"})
check("agent/answer/source accepted",
      (e["agent_id"], e["value"], e["tool_id"]) ==
      ("W_Agent_1", 50, "warehouse_inventory_db"))

# 2b. ...and the coordinator's task dict can stand in for the key
task = {"task": "check_stock", "warehouse": "W1", "kit": "K1"}
same_task = {"kit": "K1", "warehouse": "W1", "task": "check_stock"}  # other order
e1 = ledger.append({"agent": "W_Agent_2", "answer": 50,
                    "source": "shelf_iot_sensors", "task": task})
e2 = ledger.append({"agent": "W_Agent_3", "answer": 50,
                    "source": "inbound_outbound_logs", "task": same_task})
check("task dict becomes the key; field order does not matter",
      e1["key"] == e2["key"] == ledger.make_key(task))

# 3. Parents must be existing readings
child = ledger.append(reading(11, parents=[0, 1]))
check("reading with parents stored", child["parent_decision_ids"] == [0, 1])
blocked(lambda: ledger.append(reading(12, parents=[999])))
blocked(lambda: ledger.append(reading(12, parents=[0, 0])))
verdict = ledger.set_verdict(0, True)
blocked(lambda: ledger.append(reading(12, parents=[verdict["id"]])))
check("bad parents blocked (missing, duplicate, not a reading)", ledger.verify_chain())

# 4. Bad input is rejected and nothing is written
size = len(read_lines())
for bad in ({"tool_id": "t", "key": "k", "value": 1},                # no agent
            {"agent_id": "a", "key": "k", "value": 1},               # no tool
            {"agent_id": "a", "tool_id": "t", "value": 1},           # no key
            {"agent_id": "a", "tool_id": "t", "key": "k"},           # no value
            {"agent_id": " ", "tool_id": "t", "key": "k", "value": 1},
            {"agent_id": "a", "tool_id": "t", "key": "k", "value": float("nan")},
            {"agent_id": "a", "tool_id": "t", "key": "k", "value": object()}):
    blocked(lambda bad=bad: ledger.append(bad))
check("invalid readings rejected, nothing written", len(read_lines()) == size)

# 5. append_many is all-or-nothing
blocked(lambda: ledger.append_many([reading(20), {"agent_id": "a"}]))
check("batch with one bad reading writes nothing", len(read_lines()) == size)

# 6. Verdict and outcome: set once, strict values, only for readings
blocked(lambda: ledger.set_verdict(0, False))                 # already has one
blocked(lambda: ledger.set_verdict(999, True))                # does not exist
blocked(lambda: ledger.set_verdict(1, "yes"))                 # not a real bool
ledger.set_verdict(1, False)
ledger.set_outcome(1, False, excused_by_parent=True)
blocked(lambda: ledger.set_outcome(1, True))                  # already audited
blocked(lambda: ledger.set_outcome(2, True, excused_by_parent=True))
ledger.set_outcome(0, True)
check("verdicts/outcomes added, chain OK", ledger.verify_chain())

# 7. query returns the nine-field record with everything joined in
fields = ["decision_id", "agent_id", "tool_id", "key", "value",
          "parent_decision_ids", "agreed_with_verdict", "audit_correct",
          "excused_by_parent"]
r0, r1, r2 = ledger.get(0), ledger.get(1), ledger.get(2)
check("record has exactly the nine fields", list(r0) == fields)
check("reading 0: verdict True, audit True, not excused",
      (r0["agreed_with_verdict"], r0["audit_correct"], r0["excused_by_parent"])
      == (True, True, False))
check("reading 1: verdict False, audit False, excused",
      (r1["agreed_with_verdict"], r1["audit_correct"], r1["excused_by_parent"])
      == (False, False, True))
check("reading 2: nothing known yet (all None)",
      (r2["agreed_with_verdict"], r2["audit_correct"], r2["excused_by_parent"])
      == (None, None, None))
ids_0 = [r["decision_id"] for r in ledger.query("agent_0")]
check("query(agent_0) is only agent_0, oldest first",
      ids_0 == sorted(ids_0) and len(ids_0) > 1
      and all(r["agent_id"] == "agent_0" for r in ledger.query("agent_0")))
check("query_tool works", all(r["tool_id"] == "tool_0" for r in ledger.query_tool("tool_0")))
check("query for an unknown agent is empty", ledger.query("nobody") == [])

# 7b. Returned records are copies: changing one never changes the ledger
rec = ledger.get(0)
rec["value"] = 99999
rec["parent_decision_ids"].append(7)
check("returned records are copies", ledger.get(0)["value"] == 50
      and ledger.get(0)["parent_decision_ids"] == [])

# 8. Tamper: edit a value (the file's size changes, so every call notices)
stored = fresh()
lines = read_lines()
lines[3] = lines[3].replace('"value": 53', '"value": 5300')
write_lines(lines)
check("edit a value: chain broken at entry 3",
      not ledger.verify_chain() and ledger.first_failure() == 3)
for call in (lambda: ledger.query("agent_0"),
             lambda: ledger.append(reading(0)),
             lambda: ledger.set_verdict(0, True)):
    try:
        call()
        raise AssertionError("tampered ledger was used")
    except LedgerTamperedError as err:
        assert err.index == 3
check("query/append/set_verdict refuse a tampered ledger", True)

# 9. Tamper: flip a late-filled field (an audit result)
fresh()
ledger.set_outcome(2, False)
lines = read_lines()
lines[-1] = lines[-1].replace('"audit_correct": false', '"audit_correct": true')
write_lines(lines)
check("flip an audit result: caught", not ledger.verify_chain())

# 10. Tamper: delete a middle entry, and reorder two entries
fresh()
lines = read_lines()
del lines[4]
write_lines(lines)
check("delete a middle entry: caught", not ledger.verify_chain())
fresh()
lines = read_lines()
lines[4], lines[5] = lines[5], lines[4]
write_lines(lines)
check("reorder two entries: caught", not ledger.verify_chain())

# 11. Known limitations (stated in the report, shown here on purpose)
fresh()
write_lines(read_lines()[:-1])
check("LIMITATION: deleting the newest entry is NOT detected", ledger.verify_chain())

fresh()
entries = [json.loads(line) for line in read_lines()]
entries[3]["value"] = 5300
prev = entries[2]["hash"]
for e in entries[3:]:                         # attacker recomputes every later hash
    e["prev_hash"] = prev
    e["hash"] = ledger._hash(e)
    prev = e["hash"]
write_lines([json.dumps(e) for e in entries])
check("LIMITATION: a full rewrite of every later hash is NOT detected", ledger.verify_chain())

# 12. Several writers at once keep the chain valid
ledger.LEDGER_FILE.unlink(missing_ok=True)
def worker(n):
    for j in range(10):
        ledger.append(reading(n * 10 + j))
threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
[t.start() for t in threads]
[t.join() for t in threads]
check("8 threads x 10 appends: 80 entries, chain OK",
      len(read_lines()) == 80 and ledger.verify_chain())

# ------------------------------------------------ new in this version

# 13. Speed: a run shaped like the real system must not slow down as it grows.
#     Per mission: 5 questions x 3 agents, a verdict and an audit for each
#     reading, and the defense reading every agent's history.
agents = [f"{d}_Agent_{i}" for d in "WTL" for i in (1, 2, 3)]
perf = Ledger(TMP / "perf.jsonl")
t0 = time.perf_counter()
for m in range(50):
    for q in range(5):
        group = agents[(q % 3) * 3:(q % 3) * 3 + 3]
        rows = perf.append_many([{"agent_id": a, "tool_id": "tool_x",
                                  "key": f"q{q}", "value": 50} for a in group])
        for r in rows:
            perf.set_verdict(r["decision_id"], True)
            perf.set_outcome(r["decision_id"], True)
    for a in agents:
        perf.query(a)
took = time.perf_counter() - t0
check(f"50 missions (2250 entries) in {took:.2f} s (limit 10 s)", took < 10)
check("...and the chain is still valid", perf.verify_chain())

# 14. One ledger file per run: separate Ledger objects do not interfere
a, b = Ledger(TMP / "run_a.jsonl"), Ledger(TMP / "run_b.jsonl")
a.append_many([reading(i) for i in range(5)])
b.append_many([reading(i) for i in range(3)])
check("two ledgers are independent",
      len(a.query("agent_0")) == 2 and len(b.query("agent_0")) == 1
      and a.verify_chain() and b.verify_chain())
check("a ledger in a new folder is created on first write",
      Ledger(TMP / "runs" / "x.jsonl").append(reading(0))["decision_id"] == 0)

# 15. A new Ledger object on the same file sees the same data and continues it
again = Ledger(TMP / "run_a.jsonl")
check("reopened ledger sees the same records",
      again.query("agent_0") == a.query("agent_0"))
new = again.append(reading(9))
check("reopened ledger continues the chain",
      new["decision_id"] == 5 and a.verify_chain()
      and a.get(5)["value"] == 59)       # the other object notices the new entry

# 16. Cache versus disk
c = Ledger(TMP / "cache.jsonl")
c.append_many([reading(i) for i in range(10)])
lines = read_lines(c.path)
lines[3] = lines[3].replace('"value": 53', '"value": 5300')   # size changes
write_lines(lines, c.path)
try:
    c.query("agent_0")
    raise AssertionError("outside edit went unnoticed")
except LedgerTamperedError as err:
    check("default mode notices an outside edit that changes the file", err.index == 3)

s = Ledger(TMP / "strict.jsonl", strict=True)
s.append_many([reading(i) for i in range(10)])
lines = read_lines(s.path)
lines[4], lines[5] = lines[5], lines[4]                      # same size
write_lines(lines, s.path)
try:
    s.query("agent_0")
    raise AssertionError("strict mode missed a same-size edit")
except LedgerTamperedError:
    check("strict mode catches even a same-size edit on the next call", True)

f = Ledger(TMP / "fast.jsonl")
f.append_many([reading(i) for i in range(10)])
lines = read_lines(f.path)
lines[4], lines[5] = lines[5], lines[4]                      # same size
write_lines(lines, f.path)
check("verify_chain always reads the disk, so it catches the same-size edit",
      not f.verify_chain())

# 17. A file in the old format is refused with a clear message, not misread
old = TMP / "old_format.jsonl"
entry = {"id": 0, "kind": "claim", "agent_id": "a", "claim": "x",
         "prev_hash": ledger.GENESIS}
entry["hash"] = ledger._hash(entry)
old.write_text(json.dumps(entry) + "\n")
check("old-format ledger file is refused with a clear message",
      "older format" in blocked(lambda: Ledger(old).query("a")))

print("\nAll checks passed.")
_tmp.cleanup()
