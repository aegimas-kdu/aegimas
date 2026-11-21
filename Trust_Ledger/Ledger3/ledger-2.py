"""Trust ledger: an append-only, hash-chained log (one JSON entry per line).

The ledger keeps one logical record per READING, meaning one answer that one
agent gave using one tool:

    decision_id, agent_id, tool_id, key, value, parent_decision_ids,
    agreed_with_verdict, audit_correct, excused_by_parent

Who writes what (the order of the pipeline):

    Coordinator -> append / append_many   writes the reading (first 6 fields)
    Defense     -> set_verdict            fills in agreed_with_verdict
    Evaluator   -> set_outcome            fills in audit_correct, excused_by_parent
    Defense     -> query / query_tool     reads the records back

A reading is written once and never edited. The last three fields are only
known later, so each one is added as its own NEW chained entry that points at
the reading (kind "verdict" or "audit"), and may be set once only. query()
joins them back together, so the caller always sees the full nine-field record
(None = not known yet). Editing any entry, including a verdict or an audit,
breaks the chain and is caught by verify_chain().
"""
import hashlib
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

LEDGER_FILE = Path(__file__).parent / "ledger.jsonl"
GENESIS = "0" * 64  # prev_hash of the very first entry

READING, VERDICT, AUDIT = "reading", "verdict", "audit"

# Agents report {"agent", "answer", "source"}; accept those names as well.
_ALIASES = {"agent": "agent_id", "source": "tool_id", "answer": "value"}

# Every stored entry has all of these fields (None when they do not apply),
# so every kind of entry is hashed the same way.
_BLANK = {
    "decision_id": None, "agent_id": None, "tool_id": None, "key": None,
    "value": None, "parent_decision_ids": None, "ref": None,
    "agreed_with_verdict": None, "audit_correct": None,
    "excused_by_parent": None,
}

_lock = threading.RLock()  # one writer at a time inside this process


class LedgerTamperedError(Exception):
    """The ledger fails verification. `.index` is the first bad entry."""

    def __init__(self, index):
        super().__init__(f"ledger fails verification at entry {index}")
        self.index = index


# ---------------------------------------------------------------- internals

def _hash(entry):
    """SHA-256 of every field except the hash itself."""
    body = {k: v for k, v in entry.items() if k != "hash"}
    text = json.dumps(body, sort_keys=True)
    return hashlib.sha256(text.encode()).hexdigest()


def _load():
    """Read the whole ledger, checking the chain while reading.
    Raises LedgerTamperedError at the first entry that fails a check, so
    nothing is ever returned or extended from a ledger that was altered."""
    if not LEDGER_FILE.exists():
        return []
    with open(LEDGER_FILE, encoding="utf-8") as f:
        lines = [line for line in f if line.strip()]
    entries, prev = [], GENESIS
    for i, line in enumerate(lines):
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            raise LedgerTamperedError(i)
        if (not isinstance(e, dict)
                or e.get("id") != i                 # ids run 0, 1, 2, ... no gaps
                or e.get("prev_hash") != prev       # link to previous entry
                or e.get("hash") != _hash(e)):      # content matches its hash
            raise LedgerTamperedError(i)
        entries.append(e)
        prev = e["hash"]
    return entries


def _entry(index, prev_hash, kind, **fields):
    """Build one full entry, linked to the previous one."""
    e = {"id": index, "time": datetime.now(timezone.utc).isoformat(),
         "kind": kind, **_BLANK, **fields, "prev_hash": prev_hash}
    e["hash"] = _hash(e)
    return e


def _write(new_entries):
    """Add entries to the end of the file in a single write."""
    if new_entries:
        with open(LEDGER_FILE, "a", encoding="utf-8", newline="\n") as f:
            f.write("".join(json.dumps(e) + "\n" for e in new_entries))


def _text(raw, name):
    v = raw.get(name)
    if not isinstance(v, str) or not v.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return v


def _flag(v, name):
    if not isinstance(v, bool):
        raise ValueError(f"{name} must be True or False")
    return v


def _clean_reading(raw, readings):
    """Check one incoming reading and return the fields to store.
    `readings` maps id -> reading entry for the readings already stored."""
    if not isinstance(raw, dict):
        raise ValueError("a reading must be a dict")
    raw = dict(raw)
    for alias, name in _ALIASES.items():
        if alias in raw and name not in raw:
            raw[name] = raw[alias]
    if "value" not in raw:
        raise ValueError("a reading needs a value")
    try:
        json.dumps(raw["value"], allow_nan=False)
    except (TypeError, ValueError):
        raise ValueError("value must be JSON-serializable (no NaN or infinity)")
    parents = raw.get("parent_decision_ids") or []
    if not isinstance(parents, (list, tuple)):
        raise ValueError("parent_decision_ids must be a list")
    parents = list(parents)
    if len(set(parents)) != len(parents):
        raise ValueError("parent_decision_ids contains duplicates")
    for p in parents:
        if type(p) is not int or p not in readings:
            raise ValueError(f"parent decision {p!r} is not an existing reading")
    return {"agent_id": _text(raw, "agent_id"), "tool_id": _text(raw, "tool_id"),
            "key": _text(raw, "key"), "value": raw["value"],
            "parent_decision_ids": parents}


def _records(entries):
    """Join readings with their verdicts and audits into the nine-field records."""
    verdicts = {e["ref"]: e for e in entries if e["kind"] == VERDICT}
    audits = {e["ref"]: e for e in entries if e["kind"] == AUDIT}
    out = []
    for e in entries:
        if e["kind"] != READING:
            continue
        v, a = verdicts.get(e["id"]), audits.get(e["id"])
        out.append({
            "decision_id": e["decision_id"],
            "agent_id": e["agent_id"],
            "tool_id": e["tool_id"],
            "key": e["key"],
            "value": e["value"],
            "parent_decision_ids": e["parent_decision_ids"],
            "agreed_with_verdict": v["agreed_with_verdict"] if v else None,
            "audit_correct": a["audit_correct"] if a else None,
            "excused_by_parent": a["excused_by_parent"] if a else None,
        })
    return out


def _add_late(kind, decision_id, **fields):
    """Add a verdict or audit entry for an existing reading, once only."""
    with _lock:
        entries = _load()
        if (type(decision_id) is not int
                or not 0 <= decision_id < len(entries)
                or entries[decision_id]["kind"] != READING):
            raise ValueError(f"decision {decision_id!r} is not an existing reading")
        if any(e["kind"] == kind and e["ref"] == decision_id for e in entries):
            raise ValueError(f"decision {decision_id} already has a {kind}")
        e = _entry(len(entries), entries[-1]["hash"], kind,
                   ref=decision_id, **fields)
        _write([e])
        return e


# ------------------------------------------------------ Coordinator -> ledger

def append_many(readings):
    """Record several readings (for example every agent's answer to one
    question) in one step. Each reading is a dict:

        agent_id, tool_id, key, value, parent_decision_ids (optional)

    (agent / source / answer are accepted for agent_id / tool_id / value.)
    Every reading is checked first; if any is invalid nothing is written.
    Returns the stored entries. Each one's "decision_id" is what later calls
    (set_verdict, set_outcome, parent_decision_ids) use to refer to it."""
    with _lock:
        entries = _load()
        readings_by_id = {e["id"]: e for e in entries if e["kind"] == READING}
        prev = entries[-1]["hash"] if entries else GENESIS
        new = []
        for raw in readings:
            clean = _clean_reading(raw, readings_by_id)
            index = len(entries) + len(new)
            e = _entry(index, prev, READING, decision_id=index, **clean)
            new.append(e)
            prev = e["hash"]
        _write(new)
        return new


def append(entry):
    """Record one reading. Returns the stored entry (use its "decision_id")."""
    return append_many([entry])[0]


# ------------------------------------------------------- Defense / Evaluator

def set_verdict(decision_id, agreed_with_verdict):
    """Defense: record whether this reading agreed with the defense's verdict.
    Adds a NEW entry. Raises ValueError if the id is not a reading or already
    has a verdict."""
    return _add_late(VERDICT, decision_id,
                     agreed_with_verdict=_flag(agreed_with_verdict,
                                               "agreed_with_verdict"))


def set_outcome(decision_id, audit_correct, excused_by_parent=False):
    """Evaluator: record whether the reading was correct against the ground
    truth, and whether a wrong reading is excused because it was built on a
    wrong parent reading. Adds a NEW entry. Raises ValueError if the id is not
    a reading, already has an audit, or a correct reading is marked excused."""
    _flag(audit_correct, "audit_correct")
    _flag(excused_by_parent, "excused_by_parent")
    if audit_correct and excused_by_parent:
        raise ValueError("a correct reading cannot be excused")
    return _add_late(AUDIT, decision_id, audit_correct=audit_correct,
                     excused_by_parent=excused_by_parent)


# ------------------------------------------------------------ ledger -> Defense

def query(agent_id):
    """One agent's readings, oldest first, as nine-field records. Read-only.
    Raises LedgerTamperedError if the ledger fails verification."""
    return [r for r in _records(_load()) if r["agent_id"] == agent_id]


def query_tool(tool_id):
    """One tool's readings, oldest first, as nine-field records. Read-only.
    Lets the defense spot a poisoned tool across all the agents that used it."""
    return [r for r in _records(_load()) if r["tool_id"] == tool_id]


def get(decision_id):
    """One reading as a nine-field record. Raises ValueError if not found."""
    for r in _records(_load()):
        if r["decision_id"] == decision_id:
            return r
    raise ValueError(f"decision {decision_id!r} is not an existing reading")


# ------------------------------------------------------------- verification

def first_failure():
    """Index of the first entry that fails a check, or None if all pass."""
    try:
        _load()
    except LedgerTamperedError as err:
        return err.index
    return None


def verify_chain():
    """True if the whole ledger is intact, otherwise False."""
    return first_failure() is None
