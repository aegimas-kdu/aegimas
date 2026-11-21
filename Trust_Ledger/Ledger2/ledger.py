"""Trust ledger for the humanitarian-supply-chain MAS.

Append-only, hash-chained log (one JSON entry per line).

Flow:  Coordinator -> record_reading(s) -> ledger -> readings_for_defense() -> Defense
       Defense     -> record_verdict()   (did each reading agree with the verdict?)
       Evaluator   -> set_audit()        (was each reading right vs ground truth?)

Nothing is ever edited. A reading is written once; the later facts about it
(verdict, audit) are NEW entries that point back at it by decision_id.
query() merges them into one record with the system's 9 fields:

    decision_id, agent_id, tool_id, key, value, parent_decision_ids,
    agreed_with_verdict, audit_correct, excused_by_parent
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

LEDGER_FILE = Path(__file__).parent / "ledger.jsonl"
GENESIS = "0" * 64  # prev_hash of the very first entry

# The 9 tools of the system. A reading from any other tool is rejected.
KNOWN_TOOLS = {
    "warehouse_inventory_db", "shelf_iot_sensors", "inbound_outbound_logs",   # Warehouse
    "fleet_specs_catalog", "live_gps_telemetry", "route_eta_calculator",      # Transportation
    "gis_distance_matrix", "fuel_and_toll_rates", "billing_quote_api",        # Logistics
}


# ---------------------------------------------------------------- hashing / IO

def _hash(entry):
    """SHA-256 of every field except the hash itself."""
    body = {k: v for k, v in entry.items() if k != "hash"}
    text = json.dumps(body, sort_keys=True)
    return hashlib.sha256(text.encode()).hexdigest()


def _read_all():
    """Read all entries from the file into a list."""
    if not LEDGER_FILE.exists():
        return []
    with open(LEDGER_FILE) as f:
        return [json.loads(line) for line in f if line.strip()]


def _write_new(entries, new_fields):
    """Chain each item of new_fields onto `entries`, save them in ONE write.
    Returns the stored entries."""
    stored = []
    prev = entries[-1]["hash"] if entries else GENESIS
    seq = len(entries)
    for fields in new_fields:
        full = {
            "seq": seq,                                        # position in the file
            "time": datetime.now(timezone.utc).isoformat(),
            "kind": fields["kind"],                            # reading | verdict | audit
            "decision_id": fields.get("decision_id"),          # readings only
            "agent_id": fields.get("agent_id"),
            "tool_id": fields.get("tool_id"),
            "key": fields.get("key"),
            "value": fields.get("value"),
            "parent_decision_ids": fields.get("parent_decision_ids", []),
            "ref": fields.get("ref"),                          # verdict/audit: the reading they are about
            "agreed_with_verdict": fields.get("agreed_with_verdict"),
            "audit_correct": fields.get("audit_correct"),
            "prev_hash": prev,
        }
        full["hash"] = _hash(full)
        prev = full["hash"]
        seq += 1
        entries = entries + [full]
        stored.append(full)
    with open(LEDGER_FILE, "a") as f:
        f.write("".join(json.dumps(e) + "\n" for e in stored))
    return stored


# ------------------------------------------------- Coordinator -> ledger (input)

def make_key(task):
    """Turn a Coordinator task into a stable key string.
    {"task": "check_stock", "warehouse": "W1", "kit": "K1"}
        -> "check_stock|kit=K1|warehouse=W1"
    A string is returned unchanged."""
    if isinstance(task, str):
        return task
    parts = [str(task["task"])]
    parts += [f"{k}={task[k]}" for k in sorted(task) if k != "task"]
    return "|".join(parts)


def _normalize(report):
    """Accept the agent report as the system sends it
    {"agent": "W_Agent_1", "answer": 50, "source": "warehouse_inventory_db", "task": {...}}
    or in ledger naming (agent_id / value / tool_id / key). Returns clean fields."""
    agent = report.get("agent_id", report.get("agent"))
    tool = report.get("tool_id", report.get("source"))
    if "value" in report:
        value = report["value"]
    elif "answer" in report:
        value = report["answer"]
    else:
        raise ValueError("report has no value/answer")
    key = report.get("key")
    if key is None and "task" in report:
        key = make_key(report["task"])
    if not agent:
        raise ValueError("report has no agent_id")
    if not key:
        raise ValueError("report has no key (or task to build one from)")
    if tool not in KNOWN_TOOLS:
        raise ValueError(f"unknown tool_id {tool!r}")
    return {
        "kind": "reading",
        "decision_id": report.get("decision_id"),
        "agent_id": agent,
        "tool_id": tool,
        "key": key,
        "value": value,
        "parent_decision_ids": list(report.get("parent_decision_ids") or []),
    }


def record_readings(reports):
    """Record a batch of agent reports from the Coordinator, in order.
    Parents may be earlier readings in the ledger OR earlier in this same batch.
    Returns the stored entries (each has its decision_id)."""
    entries = _read_all()
    known_ids = {e["decision_id"] for e in entries if e["kind"] == "reading"}
    prepared = []
    for i, report in enumerate(reports):
        r = _normalize(report)
        r["decision_id"] = r["decision_id"] or f"D{len(entries) + i:04d}"
        if r["decision_id"] in known_ids:
            raise ValueError(f"decision_id {r['decision_id']} already exists")
        missing = [p for p in r["parent_decision_ids"] if p not in known_ids]
        if missing:
            raise ValueError(f"unknown parent decision(s): {missing}")
        known_ids.add(r["decision_id"])
        prepared.append(r)
    return _write_new(entries, prepared)


def record_reading(report):
    """Record one agent report. Returns the stored entry."""
    return record_readings([report])[0]


# ----------------------------------------------------- reading the ledger (views)

def _merged(entries):
    """One record per reading, with its verdict/audit entries folded in."""
    agreed = {e["ref"]: e["agreed_with_verdict"] for e in entries if e["kind"] == "verdict"}
    audit = {e["ref"]: e["audit_correct"] for e in entries if e["kind"] == "audit"}
    out = []
    for e in entries:
        if e["kind"] != "reading":
            continue
        did = e["decision_id"]
        correct = audit.get(did)
        # Wrong, but a parent it built on was also wrong -> not this agent's fault.
        # Derived on read, so it stays right even if the parent is audited later.
        if correct is None:
            excused = None
        else:
            excused = correct is False and any(
                audit.get(p) is False for p in e["parent_decision_ids"])
        out.append({
            "decision_id": did,
            "agent_id": e["agent_id"],
            "tool_id": e["tool_id"],
            "key": e["key"],
            "value": e["value"],
            "parent_decision_ids": e["parent_decision_ids"],
            "agreed_with_verdict": agreed.get(did),
            "audit_correct": correct,
            "excused_by_parent": excused,
        })
    return out


def query(agent_id=None, tool_id=None, key=None):
    """Merged 9-field records, in order, optionally filtered. Read-only.
    None in agreed_with_verdict / audit_correct / excused_by_parent = not known yet."""
    return [r for r in _merged(_read_all())
            if (agent_id is None or r["agent_id"] == agent_id)
            and (tool_id is None or r["tool_id"] == tool_id)
            and (key is None or r["key"] == key)]


def readings_for_defense(key=None):
    """What the Defense module receives: the readings (optionally for one key)."""
    return query(key=key)


def trust_summary(agent_id):
    """Simple counts for one agent. A wrong reading that was excused_by_parent
    is not counted against the agent."""
    recs = query(agent_id=agent_id)
    audited = [r for r in recs if r["audit_correct"] is not None]
    return {
        "readings": len(recs),
        "audited": len(audited),
        "correct": sum(r["audit_correct"] for r in audited),
        "wrong_own_fault": sum(1 for r in audited
                               if not r["audit_correct"] and not r["excused_by_parent"]),
        "wrong_excused": sum(1 for r in audited if r["excused_by_parent"]),
        "agreed_with_verdict": sum(1 for r in recs if r["agreed_with_verdict"]),
    }


# ----------------------------------------- Defense / Evaluator -> ledger (outcomes)

def _reading_or_error(entries, decision_id):
    for e in entries:
        if e["kind"] == "reading" and e["decision_id"] == decision_id:
            return e
    raise ValueError(f"{decision_id!r} is not an existing reading")


def _same(a, b, tolerance):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) \
            and not isinstance(a, bool) and not isinstance(b, bool):
        return abs(a - b) <= tolerance
    return a == b


def record_verdict(decision_ids, verdict_value, tolerance=0):
    """Defense decided the answer is `verdict_value`. Each listed reading gets one
    verdict entry: agreed_with_verdict = (its value matches, within tolerance).
    Raises ValueError (nothing written) if an id is unknown or already has a verdict."""
    entries = _read_all()
    done = {e["ref"] for e in entries if e["kind"] == "verdict"}
    new = []
    for did in decision_ids:
        reading = _reading_or_error(entries, did)
        if did in done:
            raise ValueError(f"{did} already has a verdict")
        done.add(did)
        new.append({"kind": "verdict", "ref": did,
                    "agreed_with_verdict": _same(reading["value"], verdict_value, tolerance)})
    return _write_new(entries, new)


def set_audit(decision_id, correct):
    """Evaluator compared the reading with ground truth. Set once only."""
    entries = _read_all()
    _reading_or_error(entries, decision_id)
    if any(e["kind"] == "audit" and e["ref"] == decision_id for e in entries):
        raise ValueError(f"{decision_id} already has an audit")
    return _write_new(entries, [{"kind": "audit", "ref": decision_id,
                                 "audit_correct": bool(correct)}])[0]


# --------------------------------------------------------------------- integrity

def head_hash():
    """Hash of the newest entry. Store it somewhere else (e.g. in the Defense
    module) to detect deletion of the newest entries."""
    entries = _read_all()
    return entries[-1]["hash"] if entries else GENESIS


def first_failure():
    """Index of the first entry that fails a check, or None if all pass."""
    if not LEDGER_FILE.exists():
        return None
    prev = GENESIS
    with open(LEDGER_FILE) as f:
        lines = [line for line in f if line.strip()]
    for i, line in enumerate(lines):
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            return i
        if e.get("seq") != i:                 # no gaps, no reordering
            return i
        if e.get("prev_hash") != prev:        # link to the previous entry broken
            return i
        if e.get("hash") != _hash(e):         # content no longer matches its hash
            return i
        prev = e["hash"]
    return None


def verify_chain(expected_head=None):
    """True if the ledger is intact. If expected_head (an earlier head_hash())
    is given, the ledger must also still end at or contain that entry."""
    if first_failure() is not None:
        return False
    if expected_head is not None and expected_head != GENESIS:
        return any(e["hash"] == expected_head for e in _read_all())
    return True
