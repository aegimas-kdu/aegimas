import json
import tempfile
import threading
from pathlib import Path

import ledger
from ledger import LedgerTamperedError

# Work on a throwaway file so the real ledger.jsonl is never touched.
_tmp = tempfile.TemporaryDirectory()
ledger.LEDGER_FILE = Path(_tmp.name) / "ledger_test.jsonl"


def reading(i, parents=None):
    return {"agent_id": f"agent_{i % 3}", "tool_id": f"tool_{i % 2}",
            "key": f"stock:W{i % 4}:K1", "value": 50 + i,
            "parent_decision_ids": parents or []}


def fresh(n=10):
    ledger.LEDGER_FILE.unlink(missing_ok=True)
    return ledger.append_many([reading(i) for i in range(n)])


def read_lines():
    return ledger.LEDGER_FILE.read_text().splitlines()


def write_lines(lines):
    ledger.LEDGER_FILE.write_text("\n".join(lines) + "\n")


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
check("query(agent_0) is only agent_0, in order",
      [r["decision_id"] for r in ledger.query("agent_0")] ==
      [r["decision_id"] for r in ledger.query("agent_0")]
      and all(r["agent_id"] == "agent_0" for r in ledger.query("agent_0")))
check("query_tool works", all(r["tool_id"] == "tool_0" for r in ledger.query_tool("tool_0")))
check("query for an unknown agent is empty", ledger.query("nobody") == [])

# 8. Tamper: edit a value
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

print("\nAll checks passed.")
_tmp.cleanup()
