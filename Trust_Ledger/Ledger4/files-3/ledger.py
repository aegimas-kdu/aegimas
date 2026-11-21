
import copy
import hashlib
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

LEDGER_FILE = Path(__file__).parent / "ledger.jsonl"
GENESIS = "0" * 64  # prev_hash of the very first entry

READING, VERDICT, AUDIT = "reading", "verdict", "audit"
_KINDS = (READING, VERDICT, AUDIT)

# Agents report {"agent", "answer", "source"}; accept those names as well.
_ALIASES = {"agent": "agent_id", "source": "tool_id", "answer": "value"}

_BLANK = {
    "decision_id": None, "agent_id": None, "tool_id": None, "key": None,
    "value": None, "parent_decision_ids": None, "ref": None,
    "agreed_with_verdict": None, "audit_correct": None,
    "excused_by_parent": None,
}


class LedgerTamperedError(Exception):


    def __init__(self, index):
        super().__init__(f"ledger fails verification at entry {index}")
        self.index = index


# ---------------------------------------------------------------- helpers

def make_key(task):

    try:
        return json.dumps(task, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        raise ValueError("task must be a JSON-serializable dict")


def _hash(entry):

    body = {k: v for k, v in entry.items() if k != "hash"}
    text = json.dumps(body, sort_keys=True)
    return hashlib.sha256(text.encode()).hexdigest()


def _entry(index, prev_hash, kind, **fields):

    e = {"id": index, "time": datetime.now(timezone.utc).isoformat(),
         "kind": kind, **_BLANK, **fields, "prev_hash": prev_hash}
    e["hash"] = _hash(e)
    return e


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
    if raw.get("key") is None and isinstance(raw.get("task"), dict):
        raw["key"] = make_key(raw["task"])
    if "value" not in raw:
        raise ValueError("a reading needs a value")
    try:
        # store exactly what a reload from the file would give back
        value = json.loads(json.dumps(raw["value"], allow_nan=False))
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
            "key": _text(raw, "key"), "value": value,
            "parent_decision_ids": parents}


# Ledger objects on the same file share one lock, so writers never interleave.
_path_locks = {}
_path_locks_guard = threading.Lock()


def _lock_for(path):
    name = str(Path(path).resolve())
    with _path_locks_guard:
        return _path_locks.setdefault(name, threading.RLock())



class Ledger:

    def __init__(self, path=None, strict=False):
        self.path = Path(LEDGER_FILE if path is None else path)
        self.strict = strict
        self._lock = _lock_for(self.path)
        self._clear()

    # -- in-memory index of the file --------------------------------------

    def _clear(self):
        self._entries = []
        self._readings, self._verdicts, self._audits = {}, {}, {}
        self._by_agent, self._by_tool = {}, {}
        self._sig = None  # None = the index cannot be trusted yet

    def _signature(self):
        try:
            st = self.path.stat()
        except FileNotFoundError:
            return (0, 0)
        return (st.st_size, st.st_mtime_ns)

    def _note(self, e):
        self._entries.append(e)
        if e["kind"] == READING:
            self._readings[e["id"]] = e
            self._by_agent.setdefault(e["agent_id"], []).append(e["id"])
            self._by_tool.setdefault(e["tool_id"], []).append(e["id"])
        elif e["kind"] == VERDICT:
            self._verdicts[e["ref"]] = e
        elif e["kind"] == AUDIT:
            self._audits[e["ref"]] = e

    def _rebuild(self):
        """Re-read the file from disk, check the whole chain, rebuild the
        index. Raises LedgerTamperedError at the first entry that fails."""
        sig = self._signature()
        self._clear()
        lines = []
        if self.path.exists():
            with open(self.path, encoding="utf-8") as f:
                lines = [line for line in f if line.strip()]
        prev = GENESIS
        for i, line in enumerate(lines):
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                raise LedgerTamperedError(i)
            if (not isinstance(e, dict)
                    or e.get("id") != i                # ids run 0, 1, 2, ... no gaps
                    or e.get("prev_hash") != prev      # link to previous entry
                    or e.get("hash") != _hash(e)):     # content matches its hash
                raise LedgerTamperedError(i)
            if e.get("kind") not in _KINDS:
                raise ValueError(
                    f"entry {i} has unknown kind {e.get('kind')!r}; this looks "
                    "like a ledger file from an older format, start a new file")
            self._note(e)
            prev = e["hash"]
        self._sig = sig

    def _sync(self):
        if self.strict or self._sig is None or self._sig != self._signature():
            self._rebuild()

    def _write(self, new):
        if not new:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8", newline="\n") as f:
            f.write("".join(json.dumps(e) + "\n" for e in new))
        for e in new:
            self._note(e)
        self._sig = self._signature()

    def _record(self, rid):
        """The nine-field record for one reading (copies, safe to modify)."""
        e = self._readings[rid]
        v, a = self._verdicts.get(rid), self._audits.get(rid)
        return {
            "decision_id": e["decision_id"],
            "agent_id": e["agent_id"],
            "tool_id": e["tool_id"],
            "key": e["key"],
            "value": copy.deepcopy(e["value"]),
            "parent_decision_ids": list(e["parent_decision_ids"]),
            "agreed_with_verdict": v["agreed_with_verdict"] if v else None,
            "audit_correct": a["audit_correct"] if a else None,
            "excused_by_parent": a["excused_by_parent"] if a else None,
        }

    def _add_late(self, kind, decision_id, **fields):
        """Add a verdict or audit entry for an existing reading, once only."""
        with self._lock:
            self._sync()
            if type(decision_id) is not int or decision_id not in self._readings:
                raise ValueError(f"decision {decision_id!r} is not an existing reading")
            table = self._verdicts if kind == VERDICT else self._audits
            if decision_id in table:
                raise ValueError(f"decision {decision_id} already has a {kind}")
            e = _entry(len(self._entries), self._entries[-1]["hash"], kind,
                       ref=decision_id, **fields)
            self._write([e])
            return copy.deepcopy(e)

    # -- Coordinator -> ledger ----------------------------------------------

    def append_many(self, readings):
        """Record several readings (for example every agent's answer to one
        question) in one step. Each reading is a dict:

            agent_id, tool_id, value, and either key or task,
            parent_decision_ids (optional)

        (agent / source / answer are accepted for agent_id / tool_id / value;
        task is the coordinator's task dict, turned into the key by make_key.)
        Every reading is checked first; if any is invalid nothing is written.
        Returns the stored entries. Each one's "decision_id" is what later
        calls (set_verdict, set_outcome, parent_decision_ids) refer to."""
        with self._lock:
            self._sync()
            prev = self._entries[-1]["hash"] if self._entries else GENESIS
            new = []
            for raw in readings:
                clean = _clean_reading(raw, self._readings)
                index = len(self._entries) + len(new)
                e = _entry(index, prev, READING, decision_id=index, **clean)
                new.append(e)
                prev = e["hash"]
            self._write(new)
            return copy.deepcopy(new)

    def append(self, entry):
        """Record one reading. Returns the stored entry (use "decision_id")."""
        return self.append_many([entry])[0]

    # -- Defense / Evaluator -----------------------------------------------

    def set_verdict(self, decision_id, agreed_with_verdict):
        """Defense: record whether this reading agreed with the defense's
        verdict. Adds a NEW entry. Raises ValueError if the id is not a
        reading or already has a verdict."""
        return self._add_late(
            VERDICT, decision_id,
            agreed_with_verdict=_flag(agreed_with_verdict, "agreed_with_verdict"))

    def set_outcome(self, decision_id, audit_correct, excused_by_parent=False):
        """Evaluator: record whether the reading was correct against the
        ground truth, and whether a wrong reading is excused because it was
        built on a wrong parent reading. Adds a NEW entry. Raises ValueError if
        the id is not a reading, already has an audit, or a correct reading is
        marked excused."""
        _flag(audit_correct, "audit_correct")
        _flag(excused_by_parent, "excused_by_parent")
        if audit_correct and excused_by_parent:
            raise ValueError("a correct reading cannot be excused")
        return self._add_late(AUDIT, decision_id, audit_correct=audit_correct,
                              excused_by_parent=excused_by_parent)

    # -- ledger -> Defense -------------------------------------------------

    def query(self, agent_id):
        """One agent's readings, oldest first, as nine-field records.
        Read-only. Raises LedgerTamperedError if the ledger fails checks."""
        with self._lock:
            self._sync()
            return [self._record(i) for i in self._by_agent.get(agent_id, [])]

    def query_tool(self, tool_id):
        """One tool's readings, oldest first, as nine-field records. Lets the
        defense spot a poisoned tool across all the agents that used it."""
        with self._lock:
            self._sync()
            return [self._record(i) for i in self._by_tool.get(tool_id, [])]

    def get(self, decision_id):
        """One reading as a nine-field record. Raises ValueError if missing."""
        with self._lock:
            self._sync()
            if type(decision_id) is not int or decision_id not in self._readings:
                raise ValueError(f"decision {decision_id!r} is not an existing reading")
            return self._record(decision_id)

   

    def first_failure(self):
        """Index of the first entry that fails a check, or None if all pass.
        Always re-reads the file from disk."""
        with self._lock:
            try:
                self._rebuild()
            except LedgerTamperedError as err:
                return err.index
            return None

    def verify_chain(self):
        """True if the whole ledger is intact, otherwise False. Always
        re-reads the file from disk."""
        return self.first_failure() is None


# ------------------------------------------- module-level functions (default)

_default = None
_default_guard = threading.Lock()


def _ledger():
    """The shared default Ledger, following LEDGER_FILE if it is reassigned."""
    global _default
    with _default_guard:
        if _default is None or _default.path != Path(LEDGER_FILE):
            _default = Ledger(LEDGER_FILE)
        return _default


def append_many(readings):
    return _ledger().append_many(readings)


def append(entry):
    return _ledger().append(entry)


def set_verdict(decision_id, agreed_with_verdict):
    return _ledger().set_verdict(decision_id, agreed_with_verdict)


def set_outcome(decision_id, audit_correct, excused_by_parent=False):
    return _ledger().set_outcome(decision_id, audit_correct, excused_by_parent)


def query(agent_id):
    return _ledger().query(agent_id)


def query_tool(tool_id):
    return _ledger().query_tool(tool_id)


def get(decision_id):
    return _ledger().get(decision_id)


def first_failure():
    return _ledger().first_failure()


def verify_chain():
    return _ledger().verify_chain()
