import ledger

def fresh(n=10):
    ledger.LEDGER_FILE.unlink(missing_ok=True)
    for i in range(n):
        ledger.append({"agent_id": f"agent_{i % 3}", "claim": f"claim {i}", "source": "test"})


def read_lines():
    return ledger.LEDGER_FILE.read_text().splitlines()


def write_lines(lines):
    ledger.LEDGER_FILE.write_text("\n".join(lines) + "\n")


# 1. Add 10 entries: the chain should be valid
fresh()
print("10 entries, chain OK:", ledger.verify_chain())             # True

# 2. Outcomes are new entries, set once only
ledger.set_outcome(2, True)
ledger.set_outcome(3, False)
print("after set_outcome, chain OK:", ledger.verify_chain())      # True
for bad_call in (lambda: ledger.set_outcome(2, False),            # already has one
                 lambda: ledger.set_outcome(99, True)):           # does not exist
    try:
        bad_call()
    except ValueError as err:
        print("blocked:", err)

# 3. Query one agent's history
print("agent_2 history:", ledger.query("agent_2"))

# 4. Correct a mistake with a normal new claim (no editing, no extra function)
ledger.append({"agent_id": "checker",
               "claim": "Correction to entry 5: the right answer is 'claim 5b'",
               "source": "correction:5"})
print("after correction, chain OK:", ledger.verify_chain())       # True

# 5. Tamper: edit an old entry by hand
lines = read_lines()
lines[3] = lines[3].replace("claim 3", "claim 3 (edited)")
write_lines(lines)
print("after edit, chain OK:", ledger.verify_chain(),
      "| first failure at entry", ledger.first_failure())         # False, 3

# 6. Tamper: delete an entry in the middle
fresh()
lines = read_lines()
del lines[4]
write_lines(lines)
print("after deleting a middle entry:", ledger.verify_chain())    # False

# 7. Known limitation: deleting the newest entry is NOT detected
fresh()
lines = read_lines()
write_lines(lines[:-1])
print("after deleting the last entry:", ledger.verify_chain(),
      "(not detected unless the latest hash is stored elsewhere)")  # True