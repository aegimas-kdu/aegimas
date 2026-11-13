# Simulator & Simulation Requirements — Meeting Notes

**For:** Team meeting to decide on simulation design
**From:** Crispin (Attack Dev perspective)

---

## What the Simulator Already Does (Ted & Bessie's work)

From `simulator.py` as it stands:

1. **Mission generation** — deterministic from a seed: 2-3 warehouses, 2-3 trucks, routes, targets, budget, deadline
2. **Three agent types** — Warehouse (stock), Transport (capacity/cost), Route (distance/time) — all report honestly
3. **Coordinator** — builds a delivery plan from claims (cheapest valid option)
4. **Plan checker** — validates plan against ground truth
5. **Seed management** — 50 dev seeds + 50 holdout seeds
6. **`run_mission()`** — full pipeline: generate → agents → [attack] → [defense] → plan → check

## What the Attacks Need from the Simulator

These are the interfaces my attack code depends on. If any change, attacks break.

| What I need | Currently provided? | Notes |
|---|---|---|
| `Mission` dataclass with `.warehouses`, `.trucks`, `.routes`, `.target_medical_kits`, `.target_tents`, `.deadline_hours`, `.budget` | Yes | Frozen dataclass — good, attacks can't accidentally mutate it |
| Claims as `list[dict]` with keys: `source_id`, `claim_type`, `field`, `value`, `truth` | Yes | The `truth` field is critical — attacks use it to craft targeted lies |
| `source_id` naming convention: `Agent_Warehouse_<name>`, `Agent_Transport_<name>`, `Agent_Route_<name>` | Yes | Attacks parse these to find which claims belong to which agent |
| Attack function signature: `attack_fn(mission, claims) -> modified_claims` | Yes | Defined in `run_mission()` |

## Decisions We Need to Make Together

### 1. How many missions per episode?
- Current plan says 20 missions per episode
- The ledger (D3) builds trust across missions within an episode
- **Proposal:** keep 20, but we need `runner.py` to loop missions and pass the ledger state between them

### 2. How many episodes per cell?
- Plan says ~100 episodes per cell (80 cells = 8000 episodes total)
- Each episode = 20 missions = 160,000 total mission runs
- **Question for John:** how long does one `run_mission()` call take? We need to estimate total runtime

### 3. Budget levels for defenses
- Plan: 20%, 40%, 60%, 80% of total claims can be audited
- **Question for Precieuse:** does "budget" mean fraction of claims checked, or fraction of verification cost? Need to align on definition

### 4. Ledger reset behavior
- D3-reset clears trust scores between episodes (fresh start each time)
- D3 (no reset) carries trust across episodes
- **Question:** should attacks also have a "persistent" variant where the adversary targets the same agent across missions? Currently each mission is independent

### 5. Attack targeting — random vs worst-case
- My draft uses **worst-case targeting** (always pick the target that maximises damage)
- Alternative: **random targeting** (pick a random agent to corrupt)
- **Recommendation:** use worst-case for the main experiment (tests defense upper bound), random as a sensitivity analysis if time permits

### 6. Attack strength parameters
- C1: how much to inflate stock? Currently: target + 50 kits, + 30 tents
- C2: how much to reduce travel time? Need to decide
- **Proposal:** make these configurable in `experiment.json` so we can run sensitivity sweeps

---

## What I Still Need to Implement

- [ ] `byzantine_agent()` — C1 attack function
- [ ] `poisoned_tool()` — C2 attack function
- [ ] `coordinated_attack()` — C3 attack function (composes C1 + C2)
- [ ] Unit tests for each attack (verify claims are modified correctly)
- [ ] Integration test: run_mission with each attack, confirm plan fails

## What I Need From Others

- **Ted/Bessie:** confirm the claim format won't change (or tell me what will change)
- **Precieuse:** what does the defense function signature look like? `defense_fn(mission, claims) -> (claims, audit_log)` — what's in `audit_log`?
- **John:** experiment.json schema — where do attack parameters go?
- **Marie Rosine:** does the ledger need to see which claims were attacked? (for analysis, not for the defense itself)
