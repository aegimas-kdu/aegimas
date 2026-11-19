# AEGIMAS — Trust-Ledgered Resilience of Multi-Agent AI Systems Against Combined Byzantine and Tool-Poisoning Attacks

A humanitarian logistics simulator where 9 AI agents coordinate medicine deliveries across Burundi, and we study how attacks (byzantine agents, tool poisoning, and their combination) can compromise the system — and how defenses (majority vote, trust ledgers) can stop them.

---

## Project Structure

```
├── simulator/          # The core simulator (9 agents, 9 tools, 3 warehouses, 6 hospitals)
├── attacks/            # C0, C1, C2, C3 attack implementations + interactive demo
├── defense/            # D1, D4-Base, D4+ trust-ledger defenses
├── experimentations/   # Experiment results and analysis
├── results/            # Raw result files
├── TEAM_WORKFLOW.md    # How each team member pushes their work
└── README.md           # This file
```

---

## The Simulator

A multi-agent system for humanitarian medicine delivery in Burundi. The coordinator receives a request (e.g., "deliver 50 units of Malaria Treatment to Muyinga Health Centre") and asks 9 agents across 3 domains:

| Domain | Agents | Tools | Questions |
|---|---|---|---|
| Warehouse | W_Agent_1, W_Agent_2, W_Agent_3 | warehouse_inventory_db, shelf_iot_sensors, inbound_outbound_logs | Q1: stock |
| Transportation | T_Agent_1, T_Agent_2, T_Agent_3 | fleet_specs_catalog, live_gps_telemetry, route_eta_calculator | Q2: capacity, Q4: time |
| Logistics | L_Agent_1, L_Agent_2, L_Agent_3 | gis_distance_matrix, fuel_and_toll_rates, billing_quote_api | Q3: distance, Q5: cost |

Each agent reads 2 tools (primary + backup) per question. The coordinator picks the cheapest warehouse-vehicle combination.

---

## The Attacks

| Attack | Type | Description |
|---|---|---|
| C0 | No attack | Clean baseline |
| C1 | Tool poisoning | One tool returns wrong values; agents stay honest |
| C2 | Byzantine agent | One agent lies; tools stay clean |
| C3 | Combined | One tool poisoned AND one agent lies simultaneously |

**Key finding:** C1 and C2 alone never fool MajorityVoteDefense (only 1 of 3 votes corrupted). C3 can break through when the liar and poisoned tool target different agents' primary tools (2 of 3 votes corrupted).

See `attacks/ATTACKS_README.md` for full documentation.

---

## The Defenses

| Defense | Description |
|---|---|
| NoDefense | Trusts a single random agent (baseline) |
| MajorityVoteDefense | 3 agents vote, strict majority wins |
| D4-Base | Trust memory + blame + quarantine |
| D4+ | D4-Base + cascade revision + fast path + fact-level flags |

See `defense/` for the defense implementations.

---

## Quick Start

### Prerequisites

```
pip install streamlit altair pandas pytest
```

Python 3.10+ required. Run everything from the project root folder.

### Run the interactive demo

```
python -m streamlit run attacks/demo_app.py
```

### Run all tests

```
python -m pytest attacks/tests/ -v
```

### Run a single attack in Python

```python
from attacks import combined_attack, run_request
from simulator.defense import MajorityVoteDefense

world = combined_attack(
    agent_id='L_Agent_2', agent_factor=2.0,
    tool_id='billing_quote_api', tool_factor=2.0,
    agent_where={'warehouse': 'W2'}, tool_where={'warehouse': 'W2'},
)
result, channel = run_request(world, MajorityVoteDefense(),
                              ('Malaria Treatment', 50, 'Muyinga Health Centre'))
print(result['warehouse']['warehouse_name'])
print(result['transportation']['transportation_cost'])
```

---

## Team Roles

| Role | Folder | What they do |
|---|---|---|
| Simulator Dev | `simulator/` | The base simulator: agents, tools, coordinator, world data |
| Attack Dev | `attacks/` | C0, C1, C2, C3 attacks, demo app, tests |
| Defense Dev | `defense/` | D4-Base, D4+ trust-ledger defenses |
| Experimenter | `experimentations/` | Run experiments, analyze results |
| Trust Ledger Dev | `defense/` | Trust scoring, ledger, quarantine logic |
| Reporter | `docs/` | Paper text, figures, final report |

See `TEAM_WORKFLOW.md` for how to clone, commit, and push.

---

## How to Contribute

1. Clone the repository:
   ```
   git clone https://github.com/aegimas-kdu/aegimas.git
   cd aegimas
   ```

2. Set your git identity:
   ```
   git config user.name "Your Full Name"
   git config user.email "your.email@example.com"
   ```

3. Work on YOUR folder only, then:
   ```
   git pull origin main
   git add <your files>
   git commit -m "Your descriptive message"
   git push origin main
   ```
