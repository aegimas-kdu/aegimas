"""Trust ledger: an append-only, hash-chained log (one JSON entry per line)."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

LEDGER_FILE = Path(__file__).parent / "ledger.jsonl"
GENESIS = "0" * 64  # prev_hash of the very first entry



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


def _add(fields):
    """Build the next entry, link it to the previous one, save it as one line."""
    entries = _read_all()
    full = {
        "id": len(entries),
        "time": datetime.now(timezone.utc).isoformat(),
        "kind": fields["kind"],
        "agent_id": fields.get("agent_id"),
        "claim": fields.get("claim"),
        "source": fields.get("source"),
        "ref": fields.get("ref"),          # id of the claim an outcome is about
        "correct": fields.get("correct"),  # used by outcome entries
        "prev_hash": entries[-1]["hash"] if entries else GENESIS,
    }
    full["hash"] = _hash(full)
    with open(LEDGER_FILE, "a") as f:
        f.write(json.dumps(full) + "\n")
    return full


def append(entry):
    """Record a claim. entry = {"agent_id": ..., "claim": ..., "source": ...}.
    Returns the stored entry (use its "id" later with set_outcome)."""
    return _add({
        "kind": "claim",
        "agent_id": entry["agent_id"],
        "claim": entry["claim"],
        "source": entry["source"],
    })


def query(agent_id):
    """Return one agent's claims in order. Each has outcome True / False / None
    (None = not yet known). Read-only."""
    entries = _read_all()
    outcomes = {e["ref"]: e["correct"] for e in entries if e["kind"] == "outcome"}
    return [
        {"id": e["id"], "claim": e["claim"], "source": e["source"],
         "outcome": outcomes.get(e["id"])}
        for e in entries
        if e["kind"] == "claim" and e["agent_id"] == agent_id
    ]


def set_outcome(entry_id, correct):
    """Record whether claim `entry_id` was right. Adds a NEW outcome entry.
    Raises ValueError if the id is not a claim, or already has an outcome."""
    entries = _read_all()
    if not (0 <= entry_id < len(entries)) or entries[entry_id]["kind"] != "claim":
        raise ValueError(f"entry {entry_id} is not an existing claim")
    if any(e["kind"] == "outcome" and e["ref"] == entry_id for e in entries):
        raise ValueError(f"entry {entry_id} already has an outcome")
    return _add({"kind": "outcome", "ref": entry_id, "correct": bool(correct)})


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
        if e.get("id") != i:                  # ids must run 0, 1, 2, ... with no gaps
            return i
        if e.get("prev_hash") != prev:        # link to the previous entry broken
            return i
        if e.get("hash") != _hash(e):         # content no longer matches its hash
            return i
        prev = e["hash"]
    return None


def verify_chain():
    """True if the whole ledger is intact, otherwise False."""
    return first_failure() is None