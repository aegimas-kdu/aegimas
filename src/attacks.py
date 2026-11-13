"""
AegisMAS Attack Module — four attack conditions (C0–C3).

Each attack is a function with the signature:
    attack_fn(mission, claims) -> modified_claims

The attack intercepts agent claims AFTER they report but BEFORE the
coordinator sees them.  The agent itself is never modified — this is
the wrapper pattern.

Attack conditions:
  C0  No attack         — baseline control
  C1  Byzantine agent   — one warehouse agent emits false stock claims
  C2  Poisoned tool     — a route tool returns manipulated travel times
  C3  Coordinated       — C1 + C2 targeting the same warehouse
"""

import copy
from typing import Dict, List

from src.simulator import Mission


# ---- helpers ---------------------------------------------------------------

def _find_weakest_warehouse(mission: Mission):
    """Find the warehouse with the biggest stock deficit relative to the target.

    Returns the warehouse name (str) that is the worst choice — the one
    whose actual stock is farthest below what the mission needs.  This is
    the best target for the attacker because inflating its numbers is most
    likely to trick the coordinator into choosing it.
    """
    worst_name = None
    worst_deficit = -float("inf")

    for w in mission.warehouses:
        kit_gap = mission.target_medical_kits - w.medical_kits
        tent_gap = mission.target_tents - w.tents
        deficit = kit_gap + tent_gap
        if deficit > worst_deficit:
            worst_deficit = deficit
            worst_name = w.name

    return worst_name


# ---- C0: no attack --------------------------------------------------------

def no_attack(mission: Mission, claims: List[Dict]) -> List[Dict]:
    """C0: No attack. Pass claims through unchanged."""
    return list(claims)


# ---- C1: Byzantine agent ---------------------------------------------------

def byzantine_agent(mission: Mission, claims: List[Dict]) -> List[Dict]:
    """C1: One warehouse agent lies about its stock levels.

    Picks the weakest warehouse and inflates its reported stock so the
    coordinator thinks it can fulfill the order.
    """
    target_wh = _find_weakest_warehouse(mission)
    target_source = f"Agent_Warehouse_{target_wh}"

    modified = []
    for claim in claims:
        c = copy.copy(claim)

        if c["source_id"] == target_source:
            if c["field"] == "medical_kits":
                c["value"] = mission.target_medical_kits + 50
            elif c["field"] == "tents":
                c["value"] = mission.target_tents + 30

        modified.append(c)

    return modified


# ---- C2: poisoned tool -----------------------------------------------------

def poisoned_tool(mission: Mission, claims: List[Dict]) -> List[Dict]:
    """C2: The route tool returns manipulated data for one route.

    The route agent is honest — it reports what the tool told it.
    But the tool was compromised.

    Targeting strategy: make the route to the BEST warehouse look too
    slow.  The coordinator skips it and is forced to pick a warehouse
    that either lacks stock or is over budget, causing the plan to fail.
    This is a denial-of-service on the good option rather than promotion
    of a bad one.
    """
    # Find the best warehouse — one that has enough stock and whose
    # plan the coordinator would normally choose.  We pick the one with
    # the most surplus stock (hardest for the coordinator to replace).
    best_wh = None
    best_surplus = -float("inf")

    for w in mission.warehouses:
        if (w.medical_kits >= mission.target_medical_kits and
                w.tents >= mission.target_tents):
            surplus = ((w.medical_kits - mission.target_medical_kits) +
                       (w.tents - mission.target_tents))
            if surplus > best_surplus:
                best_surplus = surplus
                best_wh = w.name

    # If no warehouse qualifies, just target the weakest (won't do much)
    if best_wh is None:
        best_wh = _find_weakest_warehouse(mission)

    target_source = f"Agent_Route_{best_wh}"

    modified = []
    for claim in claims:
        c = copy.copy(claim)

        if c["source_id"] == target_source:
            if c["field"] == "time_hours":
                # Make the route look way too slow
                c["value"] = mission.deadline_hours * 2.5
            elif c["field"] == "distance_km":
                c["value"] = c["truth"] * 3.0

        modified.append(c)

    return modified


# ---- C3: coordinated attack ------------------------------------------------

def coordinated_attack(mission: Mission, claims: List[Dict]) -> List[Dict]:
    """C3: Byzantine agent + poisoned tool working together.

    Two-pronged attack:
    - C1 inflates stock of the weakest warehouse (pull: lure coordinator toward it)
    - C2 blocks the route to the best warehouse (push: eliminate the good option)

    Together they push the coordinator away from the right choice and
    pull it toward the wrong one.
    """
    claims = byzantine_agent(mission, claims)
    claims = poisoned_tool(mission, claims)
    return claims


# ---- registry for the runner -----------------------------------------------

ATTACKS = {
    "C0": no_attack,
    "C1": byzantine_agent,
    "C2": poisoned_tool,
    "C3": coordinated_attack,
}


# ---- quick test ------------------------------------------------------------

if __name__ == "__main__":
    from src.simulator import generate_mission, create_agents, build_plan, check_plan

    print("=" * 60)
    print("Attack module tests")
    print("=" * 60)

    seed = 1000
    mission = generate_mission(seed)
    agents = create_agents(mission)
    original_claims = agents["claims"]

    print(f"\nMission (seed {seed}):")
    print(f"  Need: {mission.target_medical_kits} kits, {mission.target_tents} tents")
    print(f"  Deadline: {mission.deadline_hours}h, Budget: ${mission.budget:.0f}")
    for w in mission.warehouses:
        print(f"  Warehouse {w.name}: {w.medical_kits} kits, {w.tents} tents")

    target = _find_weakest_warehouse(mission)
    print(f"\n  Attack target (weakest warehouse): {target}")

    for name, attack_fn in ATTACKS.items():
        claims = attack_fn(mission, original_claims)
        plan = build_plan(mission, claims)
        verdict = check_plan(mission, plan)
        status = "PASS" if verdict["valid"] else "FAIL"

        changed = sum(
            1 for orig, mod in zip(original_claims, claims)
            if orig["value"] != mod["value"]
        )

        print(f"\n  {name}: {status}  (claims changed: {changed})")
        if plan:
            print(f"       Plan: warehouse={plan['warehouse']}, "
                  f"cost=${plan['total_cost']:.0f}")
        for r in verdict["reasons"]:
            print(f"       Reason: {r}")
