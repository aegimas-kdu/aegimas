# Attack System — Developer Guide

**Project:** Trust-Ledgered Resilience of Multi-Agent AI Systems Against Combined Byzantine and Tool-Poisoning Attacks  
**Owner:** Attack Dev (Crispin)  
**Last updated:** 2026-11-19

---

## Overview

The `attacks/` folder implements three attack types (plus a clean baseline) on the **real simulator** — a humanitarian logistics system with 9 agents, 9 tools, 3 warehouses, 6 hospitals, and 3 vehicle types operating in Burundi.

The attacks are **independent from the defense framework** (`defense/`). The defense side has its own simplified toy world for testing D4-Base and D4+. When the defense team is ready to integrate, they will need to adapt their defense interface to match the simulator's coordinator contract (see "For the Defense Team" below).

---

## The 9 Agents (3 per domain)

| Domain | Agent | Role | Primary Tool | Backup Tool |
|---|---|---|---|---|
| Warehouse | W_Agent_1 | Inventory Clerk | warehouse_inventory_db | inbound_outbound_logs |
| Warehouse | W_Agent_2 | Sensor Monitor | shelf_iot_sensors | warehouse_inventory_db |
| Warehouse | W_Agent_3 | Dispatch Auditor | inbound_outbound_logs | shelf_iot_sensors |
| Transportation | T_Agent_1 | Fleet Analyst | fleet_specs_catalog | route_eta_calculator |
| Transportation | T_Agent_2 | GPS Monitor | live_gps_telemetry | fleet_specs_catalog |
| Transportation | T_Agent_3 | ETA Auditor | route_eta_calculator | live_gps_telemetry |
| Logistics | L_Agent_1 | Distance Analyst | gis_distance_matrix | billing_quote_api |
| Logistics | L_Agent_2 | Cost Analyst | fuel_and_toll_rates | gis_distance_matrix |
| Logistics | L_Agent_3 | Quote Auditor | billing_quote_api | fuel_and_toll_rates |

Each agent reads TWO tools (primary + backup) per question, producing 2 readings per claim.

## The 9 Tools

| Domain | Tool | What it provides |
|---|---|---|
| Warehouse | warehouse_inventory_db | Stock counts |
| Warehouse | shelf_iot_sensors | Shelf weight (stock proxy) |
| Warehouse | inbound_outbound_logs | Inbound/outbound records |
| Transportation | fleet_specs_catalog | Vehicle capacity & speed |
| Transportation | live_gps_telemetry | Live GPS payload & speed |
| Transportation | route_eta_calculator | ETA estimates |
| Logistics | gis_distance_matrix | Distance between warehouses and hospitals |
| Logistics | fuel_and_toll_rates | Fuel costs and toll fees |
| Logistics | billing_quote_api | Total delivery cost quotes |

---

## The 4 Attack Types

### C0 — No Attack (clean baseline)
```python
from attacks import no_attack
world = no_attack()
```
Returns a clean copy of the world. Every other attack is compared against this.

### C1 — Tool Poisoning
```python
from attacks import poison_tool
world = poison_tool('gis_distance_matrix', 0.5, where={'warehouse': 'W3'})
```
One tool returns wrong values. The `factor` multiplies the tool's raw fields (`< 1` makes values look smaller, `> 1` bigger). The `where` filter targets specific records (e.g., one warehouse only). Every agent that reads this tool gets the wrong value — agents stay honest.

### C2 — Byzantine Agent
```python
from attacks import byzantine_agent
world = byzantine_agent('L_Agent_1', 0.3, where={'warehouse': 'W1'}, questions=['Q5'])
```
One agent lies. It reads its tools honestly, then reports `reading x factor` in BOTH readings (so its lie looks internally consistent). The tools stay clean. The `where` filter targets specific keys, and `questions` limits which questions the agent lies on.

### C3 — Combined Attack (Byzantine + Tool Poisoning)
```python
from attacks import combined_attack
world = combined_attack(
    agent_id='L_Agent_1', agent_factor=0.3,
    tool_id='gis_distance_matrix', tool_factor=0.5,
    agent_where={'warehouse': 'W1'},
    tool_where={'warehouse': 'W3'},
)
```
One tool is poisoned AND one agent lies at the same time. This is the hardest scenario: two independent sources of wrong information. Built by chaining C1 then C2 on the same world. All `where`/`factor` parameters are independent for the agent and tool sides.

---

## How to Run

### Prerequisites
```
pip install streamlit altair pandas
```
Python 3.10+ required. Run everything from the `Defense-systems/` root folder.

### Run all tests
```
python -m pytest attacks/tests/ -v
```
33 tests covering C0, C1, C2, C3.

### Run C3 experiments (captures results to file)
```
python -m attacks.run_c3_experiments
```
Outputs to `attacks/results/c3_experiments.txt`. Runs 6 C3 configurations + 3 baselines, 60 seeds each, against No Defense and Majority Vote.

### Launch the interactive demo (Streamlit)
```
python -m streamlit run attacks/demo_app.py
```
Opens a browser UI where you can:
- Pick any attack type (C0, C1, C2, C3)
- Configure agent, tool, factors, target warehouse
- See one-run details and multi-seed statistics
- Compare defenses side by side
- View an attack map (every target x factor combination)

### Run a single attack in Python
```python
from attacks import combined_attack, run_request
from simulator.defense import MajorityVoteDefense

world = combined_attack('L_Agent_1', 0.3, 'gis_distance_matrix', 0.5,
                        agent_where={'warehouse': 'W1'},
                        tool_where={'warehouse': 'W3'})
result, channel = run_request(world, MajorityVoteDefense(),
                              ('Malaria Treatment', 50, 'Muyinga Health Centre'))
print(result['warehouse']['warehouse_name'])
print(result['transportation']['vehicle'])
print(result['transportation']['transportation_cost'])
```

### Run the evaluate function for statistics
```python
from attacks import combined_attack, evaluate
from simulator.defense import MajorityVoteDefense

world = combined_attack('L_Agent_1', 0.3, 'gis_distance_matrix', 0.5)
report = evaluate(world, lambda s: MajorityVoteDefense(),
                  ('Malaria Treatment', 50, 'Muyinga Health Centre'), range(60))
print(f"Attack success rate: {report['success_rate']:.1%}")
print(f"Corruption rate: {report['corruption_rate']:.1%}")
print(f"Extra cost when fooled: +{report['avg_extra_cost']}")
```

---

## File Structure

```
attacks/
  __init__.py              # Exports: no_attack, poison_tool, byzantine_agent,
                           #          combined_attack, evaluate, run_request, etc.
  base.py                  # Shared helpers (fresh_world, record_key)
  c0_no_attack.py          # C0: clean baseline
  c1_poison_tool.py        # C1: tool poisoning
  c2_byzantine_agent.py    # C2: byzantine agent
  c3_combined.py           # C3: combined attack (C1 + C2)
  experiment.py            # Evaluator: run_request, evaluate, truth_value
  run_c3_experiments.py    # Experiment runner (outputs to results/)
  demo_app.py              # Streamlit interactive demo
  results/
    c3_experiments.txt     # Captured experiment results
  tests/
    test_c0_no_attack.py
    test_c1_poison_tool.py
    test_c2_byzantine_agent.py
    test_c3_combined.py
```

---

## Key Design Decisions

1. **Attacks stack via the `world` parameter.** Each attack returns a new world (deep copy). Pass one attack's world into the next to combine them. C3 is literally `poison_tool(...) -> byzantine_agent(..., world=result)`.

2. **The cached clean world is never modified.** `fresh_world()` always deep-copies, so attacks are side-effect free.

3. **Agent lies are applied at runtime, not in the world data.** The `lie()` function in `c2_byzantine_agent.py` runs inside `AttackedChannel.decide()` — it intercepts claims after the agent reads and before the defense sees them. This is why the C2 attack leaves `world['tools']` clean.

4. **`world['attack']` is the attacker's log.** It records what was changed (poisoned tools, liars) for the evaluator only. The agents, coordinator, and defense must NEVER read it.

5. **Two defenses available now:** `MajorityVoteDefense` (3 agents vote, majority wins) and `NoDefense` (trusts 1 random agent). The full defenses (D4-Base, D4+) are in `defense/` but use a different interface.

---

## For the Defense Team

The simulator's coordinator calls defenses with this contract:
```python
defense.decide(question, key, claims)  # 3 arguments
```
- `question`: string like 'Q3', 'Q5'
- `key`: dict like {'warehouse': 'W3', 'hospital': 'C2', 'vehicle': 'Truck'}
- `claims`: list of claim dicts (each has agent_id, answer, readings, etc.)
- Returns: a single value (the defense's decision)

Your D4-Base/D4+ defenses use a different contract:
```python
defense.decide(question, key, agents, ask, parent=None)  # 5 arguments
```

To connect your defenses to the real simulator, you need an **adapter** that bridges these two interfaces. The adapter would need to:
- Accept claims (already collected) and present them to the defense as if `ask()` was called
- Handle the `parent` parameter for cascade revision (the coordinator runs Q3 distance before Q4/Q5)
- Return a single value from the defense's decision dict

---

## Experiment Results Summary (C3)

From `attacks/results/c3_experiments.txt` (60 seeds, request: 50 x Malaria Treatment -> Muyinga Health Centre):

| Config | No Defense | Majority Vote |
|---|---|---|
| C3-1: Same target W1 (agent x0.3 + tool x0.5) | 68.3% fooled, +169 cost | 0% fooled |
| C3-2: Split targets (agent W1, tool W3) | 83.3% fooled, +140 cost | 0% fooled |
| C3-3: Aggressive (x0.1 + x3.0) | 68.3% fooled, +169 cost | 0% fooled |
| C3-4: Transport domain | 33.3% fooled, +70 cost | 0% fooled |
| C3-5: Global poison + targeted liar | 0% fooled (corrupts but same plan) | 0% fooled |
| C3-6: Warehouse domain | 0% fooled | 0% fooled |
| **Baseline: C1-only** | **55.0% fooled, +130 cost** | **0% fooled** |
| **Baseline: C2-only** | **68.3% fooled, +169 cost** | **0% fooled** |

**Key findings:**
- C3-2 (split targets) is the most effective: 83.3% vs C1's 55% and C2's 68.3% alone
- Majority vote blocks all attacks because 1 liar + 1 poisoned tool still leaves honest majority
- The combined attack is most dangerous when liar and poison target DIFFERENT warehouses
- Warehouse and some transport attacks don't change the final plan (they corrupt decisions but W2/Van remains cheapest)
