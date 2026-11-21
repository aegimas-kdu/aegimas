
import tempfile
import time
from pathlib import Path

from ledger import Ledger

SIZES = (1_000, 5_000, 10_000)


def reading(i):
    return {"agent_id": f"agent_{i % 9}", "tool_id": f"tool_{i % 9}",
            "key": f"q{i % 5}", "value": 50}


print(f"{'entries':>8} {'add all (s)':>12} {'per entry (ms)':>15} "
      f"{'file (KB)':>10} {'verify (s)':>11}")
with tempfile.TemporaryDirectory() as tmp:
    for n in SIZES:
        L = Ledger(Path(tmp) / f"bench_{n}.jsonl")
        t0 = time.perf_counter()
        for i in range(n):
            L.append(reading(i))
        add = time.perf_counter() - t0

        t0 = time.perf_counter()
        ok = L.verify_chain()           # always re-reads the file from disk
        verify = time.perf_counter() - t0
        assert ok

        kb = L.path.stat().st_size / 1024
        print(f"{n:>8} {add:>12.3f} {add / n * 1000:>15.3f} "
              f"{kb:>10.1f} {verify:>11.3f}")
