import ledger


def fresh():
    ledger.LEDGER_FILE.unlink(missing_ok=True)


def read_lines():
    return ledger.LEDGER_FILE.read_text().splitlines()


def write_lines(lines):
    ledger.LEDGER_FILE.write_text("\n".join(lines) + "\n")


def expect_error(label, fn):
    try:
        fn()
        print("NOT BLOCKED:", label)
    except ValueError as err:
        print("blocked:", err)


TASK = {"task": "check_stock", "warehouse": "W1", "kit": "K1"}


def stock_round():
    """Three warehouse agents answer the same question (agent 2 is Byzantine)."""
    return ledger.record_readings([
        {"agent": "W_Agent_1", "answer": 50,  "source": "warehouse_inventory_db", "task": TASK},
        {"agent": "W_Agent_2", "answer": 50,  "source": "shelf_iot_sensors",      "task": TASK},
        {"agent": "W_Agent_3", "answer": 500, "source": "inbound_outbound_logs",  "task": TASK},
    ])


# 1. Coordinator report format is accepted and gets all 9 fields
fresh()
r = stock_round()
print("ids:", [e["decision_id"] for e in r], "| chain OK:", ledger.verify_chain())  # True
print("record:", ledger.query(agent_id="W_Agent_1")[0])

# 2. Handoff to Defense
key = ledger.make_key(TASK)
print("for defense:", len(ledger.readings_for_defense(key)), "readings")           # 3

# 3. Defense verdict (set once), then Evaluator audit (set once)
ids = [e["decision_id"] for e in r]
ledger.record_verdict(ids, 50)
for e in ledger.query(key=key):
    print(e["agent_id"], "agreed:", e["agreed_with_verdict"])                      # T, T, F
expect_error("second verdict", lambda: ledger.record_verdict([ids[0]], 50))
ledger.set_audit(ids[0], True)
ledger.set_audit(ids[2], False)
expect_error("second audit", lambda: ledger.set_audit(ids[0], False))
expect_error("audit unknown id", lambda: ledger.set_audit("D9999", True))

# 4. Parents + excused_by_parent: agent computes travel time from a wrong distance
bad_dist = ledger.record_reading({"agent_id": "L_Agent_1", "value": 90,
                                  "tool_id": "gis_distance_matrix", "key": "distance|W1|C2"})
child = ledger.record_reading({"agent_id": "T_Agent_1", "value": 45,
                               "tool_id": "route_eta_calculator", "key": "eta|W1|C2|Van",
                               "parent_decision_ids": [bad_dist["decision_id"]]})
ledger.set_audit(child["decision_id"], False)      # child audited first...
ledger.set_audit(bad_dist["decision_id"], False)   # ...parent later: still excused
c = ledger.query(agent_id="T_Agent_1")[0]
print("child wrong:", c["audit_correct"], "excused:", c["excused_by_parent"])      # False, True
print("summary T_Agent_1:", ledger.trust_summary("T_Agent_1"))

# 5. Bad input is rejected
expect_error("unknown tool", lambda: ledger.record_reading(
    {"agent_id": "x", "value": 1, "tool_id": "made_up_db", "key": "k"}))
expect_error("unknown parent", lambda: ledger.record_reading(
    {"agent_id": "x", "value": 1, "tool_id": "billing_quote_api", "key": "k",
     "parent_decision_ids": ["D9999"]}))
expect_error("duplicate decision_id", lambda: ledger.record_reading(
    {"decision_id": ids[0], "agent_id": "x", "value": 1, "tool_id": "billing_quote_api", "key": "k"}))
print("chain OK after all that:", ledger.verify_chain())                          # True

# 6. Tamper: edit an old entry
lines = read_lines()
lines[1] = lines[1].replace('"value": 50', '"value": 51')
write_lines(lines)
print("after edit, chain OK:", ledger.verify_chain(),
      "| first failure at", ledger.first_failure())                               # False, 1

# 7. Tamper: delete a middle entry
fresh(); stock_round(); stock_round()
lines = read_lines(); del lines[2]; write_lines(lines)
print("after deleting a middle entry:", ledger.verify_chain())                    # False

# 8. Deleting the newest entry: caught only if the head hash was stored elsewhere
fresh(); stock_round()
head = ledger.head_hash()
write_lines(read_lines()[:-1])
print("no stored head:", ledger.verify_chain(),
      "| with stored head:", ledger.verify_chain(expected_head=head))              # True, False
