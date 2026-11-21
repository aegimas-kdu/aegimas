
from ledger import Ledger

# Create a new ledger file
L = Ledger("my_first_ledger.jsonl")

print("LEDGER STARTED")

# 1. Store information from an agent
reading = L.append({
    "agent_id": "Agent_1",
    "tool_id": "Tool_A",
    "key": "stock_check",
    "value": 50
})

print("\n1. READING STORED")
print(reading)

# 2. Defense records its verdict
L.set_verdict(reading["decision_id"], True)

print("\n2. VERDICT RECORDED")

# 3. Evaluator records the audit
L.set_outcome(reading["decision_id"], True)

print("\n3. AUDIT RECORDED")

# 4. Retrieve the complete record
print("\n4. COMPLETE RECORD")
print(L.get(reading["decision_id"]))

# 5. Verify the ledger
print("\n5. VERIFYING LEDGER")

if L.verify_chain():
    print("SUCCESS: Ledger integrity is valid!")
else:
    print("WARNING: Ledger integrity failed!")

