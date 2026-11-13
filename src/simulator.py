"""
AegisMAS Simulator — the multi-agent supply-chain world (v2).

New structure based on the 3-Route Tool Schema:
  - 3 domains (Warehouse, Transportation, Logistics)
  - 9 tools (3 per domain), each reaching the same truth via different formulas
  - 9 agents (1 per tool), one agent asked per fact
  - 27 facts per mission (stock, capacity, distance, time, cost)

We build this file step by step, one function at a time.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Tuple
from pathlib import Path
import math
import random


# ---------------------------------------------------------------------------
# STEP 1: WAREHOUSE
# ---------------------------------------------------------------------------
# A warehouse holds medical kits. The 'stock' field is the TRUE number
# of kits — this is ground truth that never changes.
#
# frozen=True means the object cannot be modified after creation.
# This protects ground truth from being accidentally changed by
# attack or defense code.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Warehouse:
    """A warehouse with a known true stock level."""
    name: str       # "Alpha", "Bravo", or "Charlie"
    stock: int      # true number of medical kits


# ---------------------------------------------------------------------------
# STEP 2: VEHICLE
# ---------------------------------------------------------------------------
# A vehicle carries kits from a warehouse to the camp.
# 'capacity' is the true number of kits it can carry per trip.
#
# The coordinator uses this to calculate:
#   trips_needed = ceil(demand / capacity)
#   total_cost   = trips_needed * cost_per_trip
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Vehicle:
    """A vehicle that delivers supplies."""
    name: str       # "Van", "Truck", or "Drone"
    capacity: int   # true kits per trip


# ---------------------------------------------------------------------------
# STEP 3: TOOLKIT — the raw fields for all 9 tools
# ---------------------------------------------------------------------------
# Each tool is a dict of raw fields.  The keys are the field names
# from the 3-Route Tool Schema.  Example for warehouse T1:
#   {"listed_stock_count": 50}
#
# The ToolKit groups all 9 tools for ONE (warehouse, vehicle) pair.
# Why per pair?  Because time and cost depend on which warehouse AND
# which vehicle you pick.  Stock and distance depend only on the
# warehouse, and capacity depends only on the vehicle — but we store
# them per pair for simplicity (the values are just repeated).
#
# Tool naming convention:
#   warehouse_t1, warehouse_t2, warehouse_t3
#   transport_t1, transport_t2, transport_t3
#   logistics_t1, logistics_t2, logistics_t3
# ---------------------------------------------------------------------------

# The 9 tool IDs — we'll reference these everywhere
TOOL_IDS = [
    "warehouse_t1", "warehouse_t2", "warehouse_t3",
    "transport_t1", "transport_t2", "transport_t3",
    "logistics_t1", "logistics_t2", "logistics_t3",
]

# Which domain each tool belongs to
TOOL_DOMAIN = {
    "warehouse_t1": "warehouse", "warehouse_t2": "warehouse",
    "warehouse_t3": "warehouse",
    "transport_t1": "transport", "transport_t2": "transport",
    "transport_t3": "transport",
    "logistics_t1": "logistics", "logistics_t2": "logistics",
    "logistics_t3": "logistics",
}


@dataclass
class ToolKit:
    """Raw fields for all 9 tools, for one (warehouse, vehicle) pair.

    Each field is a dict holding the tool's raw data.
    The formulas to compute answers from raw fields are in
    compute_answer() (Step 10).
    """
    # --- Warehouse domain (Q1: stock) ---
    # T1: warehouse_inventory_db
    warehouse_t1: Dict = field(default_factory=dict)
    # T2: shelf_iot_sensors
    warehouse_t2: Dict = field(default_factory=dict)
    # T3: inbound_outbound_logs
    warehouse_t3: Dict = field(default_factory=dict)

    # --- Transportation domain (Q2: capacity, Q4: time) ---
    # T1: fleet_specs_catalog
    transport_t1: Dict = field(default_factory=dict)
    # T2: live_gps_telemetry
    transport_t2: Dict = field(default_factory=dict)
    # T3: route_eta_calculator
    transport_t3: Dict = field(default_factory=dict)

    # --- Logistics domain (Q3: distance, Q5: cost) ---
    # T1: gis_distance_matrix
    logistics_t1: Dict = field(default_factory=dict)
    # T2: fuel_and_toll_rates
    logistics_t2: Dict = field(default_factory=dict)
    # T3: billing_quote_api
    logistics_t3: Dict = field(default_factory=dict)

    def get_tool(self, tool_id: str) -> Dict:
        """Get a tool's raw fields by its ID string."""
        return getattr(self, tool_id)


# ---------------------------------------------------------------------------
# STEP 5: WAREHOUSE TOOL GENERATOR
# ---------------------------------------------------------------------------
# Given the true stock, create raw fields for all 3 warehouse tools
# so that each formula computes back to the true stock.
#
# Works BACKWARDS from the truth:
#   T1: listed_stock_count = true_stock  (direct)
#   T2: pick unit_weight, compute total_weight = stock * unit_weight
#   T3: pick shipped_today, compute starting_stock = stock + shipped
# ---------------------------------------------------------------------------

def _generate_warehouse_tools(true_stock: int, rng: random.Random) -> dict:
    """Create raw fields for the 3 warehouse tools.

    Args:
        true_stock: the real number of kits (e.g. 50)
        rng: seeded random generator for picking intermediate values

    Returns:
        Dict with keys "warehouse_t1", "warehouse_t2", "warehouse_t3",
        each holding a dict of raw fields.
    """
    # T1: direct count — simplest tool
    t1 = {"listed_stock_count": true_stock}

    # T2: weight-based — pick a unit weight, compute total weight
    unit_weight = rng.choice([2, 4, 5, 10])
    total_weight = true_stock * unit_weight
    t2 = {"total_shelf_weight_kg": total_weight,
          "unit_weight_kg": unit_weight}

    # T3: log-based — pick how many shipped, compute starting stock
    shipped = rng.randint(5, 50)
    starting = true_stock + shipped
    t3 = {"starting_stock": starting,
          "shipped_today": shipped}

    return {"warehouse_t1": t1, "warehouse_t2": t2, "warehouse_t3": t3}


# ---------------------------------------------------------------------------
# STEP 6: TRANSPORT TOOL GENERATOR
# ---------------------------------------------------------------------------
# Each transport tool answers TWO questions:
#   Q2 (capacity): kits per trip
#   Q4 (time): minutes to deliver
#
# Time depends on distance (from Logistics domain).  The generator
# receives true_distance so it can build consistent time formulas.
#
# T3's time (estimated_minutes) is direct — it does NOT use distance.
# This makes it immune to distance poisoning (important for defense).
# ---------------------------------------------------------------------------

def _find_clean_divisor(numerator: int, rng: random.Random,
                        min_val: int = 1, max_val: int = 50) -> int:
    """Find a random divisor of numerator within [min_val, max_val].

    Used to pick intermediate values that divide evenly, avoiding
    floating-point errors.  If no exact divisor exists, picks the
    closest one that gives an integer result.
    """
    divisors = [d for d in range(min_val, max_val + 1)
                if numerator % d == 0]
    if divisors:
        return rng.choice(divisors)
    return rng.choice(range(min_val, max_val + 1))


def _generate_transport_tools(true_capacity: int, true_time: int,
                              true_distance: int,
                              rng: random.Random) -> dict:
    """Create raw fields for the 3 transport tools.

    Args:
        true_capacity: real kits per trip (e.g. 20)
        true_time: real delivery time in minutes (e.g. 90)
        true_distance: real distance in km (needed for time formulas)
        rng: seeded random generator

    Returns:
        Dict with keys "transport_t1", "transport_t2", "transport_t3".
    """
    # ---- T1: fleet_specs_catalog ----
    # Capacity: direct
    # Time: (distance / avg_speed_kmh) * 60 = true_time
    #   => avg_speed_kmh = (distance * 60) / true_time
    numerator_t1 = true_distance * 60
    avg_speed = numerator_t1 / true_time
    t1 = {"max_kit_capacity": true_capacity,
          "avg_speed_kmh": avg_speed}

    # ---- T2: live_gps_telemetry ----
    # Capacity: max_payload_kg / kit_unit_weight_kg = true_capacity
    kit_weight = _find_clean_divisor(true_capacity * 100, rng, 2, 10)
    # Recalculate: we want payload/kit_weight = capacity exactly
    kit_weight = rng.choice([2, 4, 5, 10])
    max_payload = true_capacity * kit_weight
    # Time: (distance / live_speed) * 60 + delay = true_time
    #   pick delay, then live_speed = (distance * 60) / (true_time - delay)
    max_delay = max(1, true_time // 4)
    delay = rng.randint(1, min(max_delay, 30))
    drive_time = true_time - delay
    if drive_time <= 0:
        delay = 0
        drive_time = true_time
    live_speed = (true_distance * 60) / drive_time
    t2 = {"max_payload_kg": max_payload,
          "kit_unit_weight_kg": kit_weight,
          "live_speed_kmh": live_speed,
          "traffic_delay_mins": delay}

    # ---- T3: route_eta_calculator ----
    # Capacity: cargo_bay_volume / kit_box_volume = true_capacity
    box_volume = rng.choice([0.1, 0.2, 0.25, 0.5])
    bay_volume = true_capacity * box_volume
    # Time: direct (does NOT depend on distance)
    t3 = {"cargo_bay_volume_m3": bay_volume,
          "kit_box_volume_m3": box_volume,
          "estimated_minutes": true_time}

    return {"transport_t1": t1, "transport_t2": t2, "transport_t3": t3}


# ---------------------------------------------------------------------------
# STEP 7: LOGISTICS TOOL GENERATOR
# ---------------------------------------------------------------------------
# Each logistics tool answers TWO questions:
#   Q3 (distance): km from warehouse to camp
#   Q5 (cost): dollars per trip
#
# T1's cost formula uses distance (cost = distance * rate_per_km),
# so a poisoned distance cascades into a wrong cost — same pattern
# as transport time depending on distance.
#
# T3 stores both values directly — immune to cascading errors.
# ---------------------------------------------------------------------------

def _generate_logistics_tools(true_distance: int, true_cost: int,
                              rng: random.Random) -> dict:
    """Create raw fields for the 3 logistics tools.

    Args:
        true_distance: real distance in km (e.g. 60)
        true_cost: real cost per trip in dollars (e.g. 120)
        rng: seeded random generator

    Returns:
        Dict with keys "logistics_t1", "logistics_t2", "logistics_t3".
    """
    # ---- T1: gis_distance_matrix ----
    # Distance: direct
    # Cost: distance * base_rate_per_km = true_cost
    #   => base_rate_per_km = true_cost / true_distance
    base_rate = true_cost / true_distance
    t1 = {"map_distance_km": true_distance,
          "base_rate_per_km": base_rate}

    # ---- T2: fuel_and_toll_rates ----
    # Distance: fuel_liters * km_per_liter = true_distance
    #   pick km_per_liter, compute fuel_liters
    km_per_liter = _find_clean_divisor(true_distance, rng, 5, 15)
    fuel_liters = true_distance // km_per_liter
    # Cost: (fuel_liters * price_per_liter) + toll_fee = true_cost
    #   pick toll_fee, compute price_per_liter
    max_toll = max(1, true_cost // 4)
    toll_fee = rng.randint(5, min(max_toll, 50))
    fuel_cost_part = true_cost - toll_fee
    if fuel_liters > 0:
        price_per_liter = fuel_cost_part / fuel_liters
    else:
        price_per_liter = 0
        toll_fee = true_cost
    t2 = {"fuel_liters": fuel_liters,
          "km_per_liter": km_per_liter,
          "price_per_liter": price_per_liter,
          "toll_fee": toll_fee}

    # ---- T3: billing_quote_api ----
    # Distance: direct
    # Cost: direct
    t3 = {"billed_mileage_km": true_distance,
          "total_quoted_cost": true_cost}

    return {"logistics_t1": t1, "logistics_t2": t2, "logistics_t3": t3}


# ---------------------------------------------------------------------------
# STEP 4: MISSION — ties everything together
# ---------------------------------------------------------------------------
# A Mission is a complete delivery scenario.  It holds:
#   - The task: what needs delivering and the constraints
#   - The world: warehouses and vehicles available
#   - Ground truth: the real answers to all 5 questions
#   - Tool data: raw fields for all 9 tools, per (warehouse, vehicle) pair
#
# True values are stored as dicts:
#   true_stock[warehouse_name] = int          (Q1)
#   true_capacity[vehicle_name] = int         (Q2)
#   true_distance[warehouse_name] = int       (Q3)
#   true_time[(wh_name, veh_name)] = int      (Q4)
#   true_cost[(wh_name, veh_name)] = int      (Q5)
#
# Tool data is stored as:
#   tools[(wh_name, veh_name)] = ToolKit      (all 9 tools for that pair)
# ---------------------------------------------------------------------------

@dataclass
class Mission:
    """A complete delivery request with ground truth and tool data."""
    seed: int

    # The task
    demand: int              # how many kits to deliver
    deadline_minutes: int    # max delivery time in minutes
    budget: int              # max total cost in dollars

    # The world
    warehouses: Tuple[Warehouse, ...]
    vehicles: Tuple[Vehicle, ...]

    # Ground truth — the real answers (used by plan checker, never by agents)
    true_stock: Dict[str, int] = field(default_factory=dict)
    true_capacity: Dict[str, int] = field(default_factory=dict)
    true_distance: Dict[str, int] = field(default_factory=dict)
    true_time: Dict[tuple, int] = field(default_factory=dict)
    true_cost: Dict[tuple, int] = field(default_factory=dict)

    # Tool data — raw fields agents read from (may be poisoned by C2)
    tools: Dict[tuple, ToolKit] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# STEP 8: MISSION GENERATOR
# ---------------------------------------------------------------------------
# generate_mission(seed) creates a complete, reproducible mission.
#
# Pipeline:
#   1. Pick random true values (stock, capacity, distance, time, cost)
#   2. Guarantee feasibility (boost one pair if needed)
#   3. Generate all 9 tools for every (warehouse, vehicle) pair
#   4. Return a Mission object
#
# Same seed ALWAYS gives the same mission — critical for reproducibility.
# ---------------------------------------------------------------------------

WAREHOUSE_NAMES = ["Alpha", "Bravo", "Charlie"]
VEHICLE_NAMES = ["Van", "Truck", "Drone"]


def _pick_clean_time(distance: int, rng: random.Random,
                     min_time: int = 30, max_time: int = 150) -> int:
    """Pick a time value where (distance*60)/time is a clean number.

    This ensures T1's avg_speed_kmh = (distance*60)/time has no
    floating-point errors.
    """
    numerator = distance * 60
    # Find all times in range that divide evenly into numerator
    clean_times = [t for t in range(min_time, max_time + 1)
                   if numerator % t == 0]
    if clean_times:
        return rng.choice(clean_times)
    # Fallback: pick any time (small float error acceptable)
    return rng.randint(min_time, max_time)


def generate_mission(seed: int) -> Mission:
    """Generate a deterministic mission from a seed number.

    Same seed always produces the exact same mission.

    Args:
        seed: integer seed for the random generator

    Returns:
        A complete Mission with true values and tool data.
    """
    rng = random.Random(seed)

    # ---- 1. Pick how many warehouses and vehicles ----
    num_warehouses = rng.choice([2, 3])
    num_vehicles = rng.choice([2, 3])

    # ---- 2. Pick the demand, deadline, and budget ----
    demand = rng.randint(20, 80)
    deadline = rng.randint(60, 150)
    budget = rng.randint(200, 800)

    # ---- 3. Pick true values for each warehouse ----
    true_stock = {}
    for i in range(num_warehouses):
        name = WAREHOUSE_NAMES[i]
        true_stock[name] = rng.randint(10, 120)

    true_distance = {}
    for i in range(num_warehouses):
        name = WAREHOUSE_NAMES[i]
        # Distances that make clean time calculations
        true_distance[name] = rng.choice([20, 30, 40, 50, 60, 80, 100, 120])

    # ---- 4. Pick true values for each vehicle ----
    true_capacity = {}
    for i in range(num_vehicles):
        name = VEHICLE_NAMES[i]
        true_capacity[name] = rng.randint(10, 50)

    # ---- 5. Pick true time and cost for each (warehouse, vehicle) pair ----
    true_time = {}
    true_cost = {}
    for wh_name in list(true_stock.keys()):
        dist = true_distance[wh_name]
        for veh_name in list(true_capacity.keys()):
            pair = (wh_name, veh_name)
            true_time[pair] = _pick_clean_time(dist, rng)
            true_cost[pair] = rng.randint(50, 300)

    # ---- 6. Guarantee feasibility ----
    # Check if at least one pair can fulfill the mission
    warehouses_list = [Warehouse(name=n, stock=true_stock[n])
                       for n in list(true_stock.keys())]
    vehicles_list = [Vehicle(name=n, capacity=true_capacity[n])
                     for n in list(true_capacity.keys())]

    feasible = False
    for wh in warehouses_list:
        if wh.stock < demand:
            continue
        for veh in vehicles_list:
            pair = (wh.name, veh.name)
            trips = math.ceil(demand / veh.capacity)
            total_cost = trips * true_cost[pair]
            if (true_time[pair] <= deadline and total_cost <= budget):
                feasible = True
                break
        if feasible:
            break

    if not feasible:
        # Boost one warehouse to make it feasible
        idx = rng.randint(0, num_warehouses - 1)
        boost_wh = WAREHOUSE_NAMES[idx]
        true_stock[boost_wh] = demand + rng.randint(5, 30)
        # Also fix time and budget for at least one vehicle
        boost_veh = VEHICLE_NAMES[rng.randint(0, num_vehicles - 1)]
        pair = (boost_wh, boost_veh)
        # Make sure time fits
        if true_time[pair] > deadline:
            deadline = true_time[pair] + rng.randint(5, 20)
        # Make sure cost fits
        trips = math.ceil(demand / true_capacity[boost_veh])
        total_cost = trips * true_cost[pair]
        if total_cost > budget:
            budget = total_cost + rng.randint(50, 200)
        # Rebuild the warehouse object
        warehouses_list[idx] = Warehouse(
            name=boost_wh, stock=true_stock[boost_wh])

    warehouses = tuple(warehouses_list)
    vehicles = tuple(vehicles_list)

    # ---- 7. Generate tool data for every (warehouse, vehicle) pair ----
    tools = {}
    for wh in warehouses:
        for veh in vehicles:
            pair = (wh.name, veh.name)

            wh_tools = _generate_warehouse_tools(
                true_stock[wh.name], rng)
            tr_tools = _generate_transport_tools(
                true_capacity[veh.name], true_time[pair],
                true_distance[wh.name], rng)
            lg_tools = _generate_logistics_tools(
                true_distance[wh.name], true_cost[pair], rng)

            # Combine all 9 tools into one ToolKit
            tk = ToolKit(
                warehouse_t1=wh_tools["warehouse_t1"],
                warehouse_t2=wh_tools["warehouse_t2"],
                warehouse_t3=wh_tools["warehouse_t3"],
                transport_t1=tr_tools["transport_t1"],
                transport_t2=tr_tools["transport_t2"],
                transport_t3=tr_tools["transport_t3"],
                logistics_t1=lg_tools["logistics_t1"],
                logistics_t2=lg_tools["logistics_t2"],
                logistics_t3=lg_tools["logistics_t3"],
            )
            tools[pair] = tk

    # ---- 8. Build and return the Mission ----
    return Mission(
        seed=seed,
        demand=demand,
        deadline_minutes=deadline,
        budget=budget,
        warehouses=warehouses,
        vehicles=vehicles,
        true_stock=true_stock,
        true_capacity=true_capacity,
        true_distance=true_distance,
        true_time=true_time,
        true_cost=true_cost,
        tools=tools,
    )


# ---------------------------------------------------------------------------
# STEP 9: AGENT IDS AND CLAIM STRUCTURE
# ---------------------------------------------------------------------------
# 9 agents, one per tool.  Agent N uses tool N in its domain.
# A claim is a dict recording one agent's answer to one question.
# ---------------------------------------------------------------------------

AGENT_IDS = [
    "warehouse_agent_1", "warehouse_agent_2", "warehouse_agent_3",
    "transport_agent_1", "transport_agent_2", "transport_agent_3",
    "logistics_agent_1", "logistics_agent_2", "logistics_agent_3",
]

# Map each agent to its tool
AGENT_TO_TOOL = {
    "warehouse_agent_1": "warehouse_t1",
    "warehouse_agent_2": "warehouse_t2",
    "warehouse_agent_3": "warehouse_t3",
    "transport_agent_1": "transport_t1",
    "transport_agent_2": "transport_t2",
    "transport_agent_3": "transport_t3",
    "logistics_agent_1": "logistics_t1",
    "logistics_agent_2": "logistics_t2",
    "logistics_agent_3": "logistics_t3",
}

# Map each agent to its domain
AGENT_DOMAIN = {
    "warehouse_agent_1": "warehouse",
    "warehouse_agent_2": "warehouse",
    "warehouse_agent_3": "warehouse",
    "transport_agent_1": "transport",
    "transport_agent_2": "transport",
    "transport_agent_3": "transport",
    "logistics_agent_1": "logistics",
    "logistics_agent_2": "logistics",
    "logistics_agent_3": "logistics",
}

# The 3 agents in each domain (for the picker to choose from)
DOMAIN_AGENTS = {
    "warehouse": ["warehouse_agent_1", "warehouse_agent_2",
                   "warehouse_agent_3"],
    "transport": ["transport_agent_1", "transport_agent_2",
                   "transport_agent_3"],
    "logistics": ["logistics_agent_1", "logistics_agent_2",
                   "logistics_agent_3"],
}


# ---------------------------------------------------------------------------
# STEP 10: COMPUTE ANSWER — the 9 formulas
# ---------------------------------------------------------------------------
# Given a tool_id and its raw fields, apply the right formula.
# This is what an honest agent does: read the tool, compute, report.
#
# For time and cost, the agent also needs the decided distance
# (resolved earlier in the question order).
# ---------------------------------------------------------------------------

def compute_answer(tool_id: str, tool_fields: Dict,
                   question: str,
                   decided_distance: float = None) -> float:
    """Apply the formula for a given tool and question.

    Args:
        tool_id: which tool (e.g. "warehouse_t1")
        tool_fields: the tool's raw fields dict
        question: one of "stock", "capacity", "distance", "time", "cost"
        decided_distance: the resolved distance (needed for time/cost
                          formulas in transport T1/T2 and logistics T1)

    Returns:
        The computed answer as a number.
    """
    # ---- WAREHOUSE TOOLS (stock) ----
    if tool_id == "warehouse_t1":
        return tool_fields["listed_stock_count"]

    elif tool_id == "warehouse_t2":
        return (tool_fields["total_shelf_weight_kg"]
                / tool_fields["unit_weight_kg"])

    elif tool_id == "warehouse_t3":
        return (tool_fields["starting_stock"]
                - tool_fields["shipped_today"])

    # ---- TRANSPORT TOOLS (capacity or time) ----
    elif tool_id == "transport_t1":
        if question == "capacity":
            return tool_fields["max_kit_capacity"]
        else:  # time
            return (decided_distance
                    / tool_fields["avg_speed_kmh"]) * 60

    elif tool_id == "transport_t2":
        if question == "capacity":
            return (tool_fields["max_payload_kg"]
                    / tool_fields["kit_unit_weight_kg"])
        else:  # time
            return ((decided_distance
                     / tool_fields["live_speed_kmh"]) * 60
                    + tool_fields["traffic_delay_mins"])

    elif tool_id == "transport_t3":
        if question == "capacity":
            return (tool_fields["cargo_bay_volume_m3"]
                    / tool_fields["kit_box_volume_m3"])
        else:  # time
            return tool_fields["estimated_minutes"]

    # ---- LOGISTICS TOOLS (distance or cost) ----
    elif tool_id == "logistics_t1":
        if question == "distance":
            return tool_fields["map_distance_km"]
        else:  # cost
            return (decided_distance
                    * tool_fields["base_rate_per_km"])

    elif tool_id == "logistics_t2":
        if question == "distance":
            return (tool_fields["fuel_liters"]
                    * tool_fields["km_per_liter"])
        else:  # cost
            return (tool_fields["fuel_liters"]
                    * tool_fields["price_per_liter"]
                    + tool_fields["toll_fee"])

    elif tool_id == "logistics_t3":
        if question == "distance":
            return tool_fields["billed_mileage_km"]
        else:  # cost
            return tool_fields["total_quoted_cost"]


# ---------------------------------------------------------------------------
# STEP 11: CREATE CLAIMS — generate all 27 claims for one mission
# ---------------------------------------------------------------------------
# Question order: Stock -> Capacity -> Distance -> Time -> Cost
# Distance must be resolved before time and cost (dependency chain).
#
# The agent_picker_fn decides which of the 3 agents to ask per fact.
# Default: rotation by (mission_number + fact_index) % 3.
# D3 overrides this with trust-based selection.
# ---------------------------------------------------------------------------

def default_agent_picker(domain: str, fact_index: int,
                         mission_number: int = 0) -> str:
    """Pick an agent by rotation: (mission_number + fact_index) % 3.

    Used by D0, D2, and D3-reset.  D3 overrides this with trust-based
    selection from the ledger.
    """
    agents = DOMAIN_AGENTS[domain]
    idx = (mission_number + fact_index) % 3
    return agents[idx]


def create_claims(mission: Mission, mission_id: int,
                  agent_picker_fn=None) -> List[Dict]:
    """Generate all 27 claims for one mission.

    Follows the question order: Stock -> Capacity -> Distance ->
    Time -> Cost.  Distance is resolved first because time and cost
    depend on it.

    Args:
        mission: the Mission object
        mission_id: mission number in the episode (for claim IDs)
        agent_picker_fn: function(domain, fact_index, mission_number)
                         -> agent_id.  Defaults to rotation.

    Returns:
        List of claim dicts, in question order.
    """
    if agent_picker_fn is None:
        agent_picker_fn = default_agent_picker

    claims = []
    claim_counter = 0
    fact_index = 0

    # We'll track decided distances for use in time/cost
    decided_distance = {}    # warehouse_name -> distance value
    # We'll track which distance claim each pair depends on
    distance_claim_ids = {}  # warehouse_name -> claim_id

    # ---- Q1: STOCK (one per warehouse) ----
    for wh in mission.warehouses:
        agent_id = agent_picker_fn("warehouse", fact_index, mission_id)
        tool_id = AGENT_TO_TOOL[agent_id]
        pair_for_tool = (wh.name, mission.vehicles[0].name)
        tool_fields = mission.tools[pair_for_tool].get_tool(tool_id)

        answer = compute_answer(tool_id, tool_fields, "stock")
        claim_id = f"m{mission_id}_c{claim_counter}"

        claims.append({
            "claim_id": claim_id,
            "mission_id": mission_id,
            "agent_id": agent_id,
            "tool_id": tool_id,
            "key": f"stock|{wh.name}",
            "answer": answer,
            "truth": mission.true_stock[wh.name],
            "parent_decision_id": None,
        })
        claim_counter += 1
        fact_index += 1

    # ---- Q2: CAPACITY (one per vehicle) ----
    for veh in mission.vehicles:
        agent_id = agent_picker_fn("transport", fact_index, mission_id)
        tool_id = AGENT_TO_TOOL[agent_id]
        pair_for_tool = (mission.warehouses[0].name, veh.name)
        tool_fields = mission.tools[pair_for_tool].get_tool(tool_id)

        answer = compute_answer(tool_id, tool_fields, "capacity")
        claim_id = f"m{mission_id}_c{claim_counter}"

        claims.append({
            "claim_id": claim_id,
            "mission_id": mission_id,
            "agent_id": agent_id,
            "tool_id": tool_id,
            "key": f"capacity|{veh.name}",
            "answer": answer,
            "truth": mission.true_capacity[veh.name],
            "parent_decision_id": None,
        })
        claim_counter += 1
        fact_index += 1

    # ---- Q3: DISTANCE (one per warehouse) ----
    for wh in mission.warehouses:
        agent_id = agent_picker_fn("logistics", fact_index, mission_id)
        tool_id = AGENT_TO_TOOL[agent_id]
        pair_for_tool = (wh.name, mission.vehicles[0].name)
        tool_fields = mission.tools[pair_for_tool].get_tool(tool_id)

        answer = compute_answer(tool_id, tool_fields, "distance")
        claim_id = f"m{mission_id}_c{claim_counter}"

        # Record decided distance for use in time/cost
        decided_distance[wh.name] = answer
        distance_claim_ids[wh.name] = claim_id

        claims.append({
            "claim_id": claim_id,
            "mission_id": mission_id,
            "agent_id": agent_id,
            "tool_id": tool_id,
            "key": f"distance|{wh.name}",
            "answer": answer,
            "truth": mission.true_distance[wh.name],
            "parent_decision_id": None,
        })
        claim_counter += 1
        fact_index += 1

    # ---- Q4: TIME (one per warehouse-vehicle pair) ----
    for wh in mission.warehouses:
        for veh in mission.vehicles:
            pair = (wh.name, veh.name)
            agent_id = agent_picker_fn("transport", fact_index, mission_id)
            tool_id = AGENT_TO_TOOL[agent_id]
            tool_fields = mission.tools[pair].get_tool(tool_id)

            dist = decided_distance[wh.name]
            answer = compute_answer(tool_id, tool_fields, "time",
                                    decided_distance=dist)
            claim_id = f"m{mission_id}_c{claim_counter}"

            claims.append({
                "claim_id": claim_id,
                "mission_id": mission_id,
                "agent_id": agent_id,
                "tool_id": tool_id,
                "key": f"time|{wh.name}|{veh.name}",
                "answer": answer,
                "truth": mission.true_time[pair],
                "parent_decision_id": distance_claim_ids[wh.name],
            })
            claim_counter += 1
            fact_index += 1

    # ---- Q5: COST (one per warehouse-vehicle pair) ----
    for wh in mission.warehouses:
        for veh in mission.vehicles:
            pair = (wh.name, veh.name)
            agent_id = agent_picker_fn("logistics", fact_index, mission_id)
            tool_id = AGENT_TO_TOOL[agent_id]
            tool_fields = mission.tools[pair].get_tool(tool_id)

            dist = decided_distance[wh.name]
            answer = compute_answer(tool_id, tool_fields, "cost",
                                    decided_distance=dist)
            claim_id = f"m{mission_id}_c{claim_counter}"

            claims.append({
                "claim_id": claim_id,
                "mission_id": mission_id,
                "agent_id": agent_id,
                "tool_id": tool_id,
                "key": f"cost|{wh.name}|{veh.name}",
                "answer": answer,
                "truth": mission.true_cost[pair],
                "parent_decision_id": distance_claim_ids[wh.name],
            })
            claim_counter += 1
            fact_index += 1

    return claims


# ---------------------------------------------------------------------------
# STEP 12: COORDINATOR — build_plan()
# ---------------------------------------------------------------------------
# The coordinator ONLY sees claims.  It never looks at true values.
# It reconstructs its picture of the world from claims, then picks
# the cheapest (warehouse, vehicle) pair that satisfies all constraints.
# ---------------------------------------------------------------------------

def build_plan(mission: Mission, claims: List[Dict],
               excluded_sources: List[str] = None) -> Dict:
    """Build a delivery plan from agent claims.

    Args:
        mission: provides demand, deadline, budget (the task — not secrets)
        claims: the list of claim dicts from create_claims()
        excluded_sources: agent_ids or tool_ids to ignore (quarantined)

    Returns:
        A plan dict if valid option found, or None.
    """
    if excluded_sources is None:
        excluded_sources = []

    # ---- Extract answers from claims ----
    stock = {}       # warehouse_name -> reported stock
    capacity = {}    # vehicle_name -> reported capacity
    distance = {}    # warehouse_name -> reported distance
    time_map = {}    # (wh_name, veh_name) -> reported time
    cost_map = {}    # (wh_name, veh_name) -> reported cost

    for claim in claims:
        # Skip claims from quarantined sources
        if (claim["agent_id"] in excluded_sources
                or claim["tool_id"] in excluded_sources):
            continue

        key = claim["key"]
        parts = key.split("|")
        question = parts[0]

        if question == "stock":
            stock[parts[1]] = claim["answer"]
        elif question == "capacity":
            capacity[parts[1]] = claim["answer"]
        elif question == "distance":
            distance[parts[1]] = claim["answer"]
        elif question == "time":
            time_map[(parts[1], parts[2])] = claim["answer"]
        elif question == "cost":
            cost_map[(parts[1], parts[2])] = claim["answer"]

    # ---- Find the cheapest valid (warehouse, vehicle) pair ----
    best_plan = None
    best_total_cost = float("inf")

    for wh in mission.warehouses:
        wh_name = wh.name
        if wh_name not in stock:
            continue
        if stock[wh_name] < mission.demand:
            continue

        for veh in mission.vehicles:
            veh_name = veh.name
            pair = (wh_name, veh_name)

            if veh_name not in capacity:
                continue
            if pair not in time_map or pair not in cost_map:
                continue

            reported_time = time_map[pair]
            if reported_time > mission.deadline_minutes:
                continue

            reported_cap = capacity[veh_name]
            if reported_cap <= 0:
                continue

            trips = math.ceil(mission.demand / reported_cap)
            total_cost = trips * cost_map[pair]

            if total_cost > mission.budget:
                continue

            if total_cost < best_total_cost:
                best_total_cost = total_cost
                best_plan = {
                    "warehouse": wh_name,
                    "vehicle": veh_name,
                    "trips": trips,
                    "total_cost": total_cost,
                    "reported_time": reported_time,
                }

    return best_plan


# ---------------------------------------------------------------------------
# STEP 13: PLAN CHECKER — check_plan()
# ---------------------------------------------------------------------------
# Validates a plan against GROUND TRUTH.  The coordinator built the
# plan from claims (which may contain lies); the checker looks at
# what is actually true.
# ---------------------------------------------------------------------------

def check_plan(mission: Mission, plan: Dict) -> Dict:
    """Check whether a plan is valid against ground truth.

    Args:
        mission: the Mission with true values
        plan: the plan dict from build_plan(), or None

    Returns:
        Dict with "valid" (bool) and "reasons" (list of failure strings).
    """
    result = {"valid": False, "reasons": []}

    if plan is None:
        result["reasons"].append("No plan was produced")
        return result

    wh_name = plan["warehouse"]
    veh_name = plan["vehicle"]
    pair = (wh_name, veh_name)

    # Check 1: Does the warehouse actually have enough stock?
    real_stock = mission.true_stock[wh_name]
    if real_stock < mission.demand:
        result["reasons"].append(
            f"Stock: {wh_name} has {real_stock} kits, "
            f"need {mission.demand}")

    # Check 2: Can it arrive on time?
    real_time = mission.true_time[pair]
    if real_time > mission.deadline_minutes:
        result["reasons"].append(
            f"Time: {real_time} min > {mission.deadline_minutes} min deadline")

    # Check 3: Is it within budget?
    real_capacity = mission.true_capacity[veh_name]
    real_trips = math.ceil(mission.demand / real_capacity)
    real_cost = real_trips * mission.true_cost[pair]
    if real_cost > mission.budget:
        result["reasons"].append(
            f"Cost: ${real_cost} > ${mission.budget} budget")

    if not result["reasons"]:
        result["valid"] = True

    return result


# ---------------------------------------------------------------------------
# STEP 14: RUN ONE MISSION — the main entry point
# ---------------------------------------------------------------------------
# This ties everything together into a single function call.
# The runner will call this thousands of times with different seeds,
# attack types, and defense configurations.
#
# Pipeline:
#   generate -> create claims -> [attack] -> [defense] ->
#   build plan -> check plan -> return result
#
# Returns a result dict that the metrics module will analyze.
# ---------------------------------------------------------------------------

def run_mission(seed: int,
                mission_id: int = 0,
                attack_fn=None,
                defense_fn=None,
                agent_picker_fn=None) -> Dict:
    """Run one complete mission and return the outcome.

    Args:
        seed:       the mission seed (determines the scenario).
        mission_id: mission number within the episode (for claim IDs
                    and agent rotation).
        attack_fn:  optional function that modifies claims.
                    Signature: attack_fn(mission, claims) -> claims.
                    None means no attack (C0 baseline).
        defense_fn: optional function that audits claims.
                    Signature: defense_fn(mission, claims) -> (claims, audit_log).
                    None means no defense (D0 baseline).
        agent_picker_fn: optional function to choose agents.
                    Signature: agent_picker_fn(domain, fact_index, mission_number)
                    -> agent_id.  None means default rotation.

    Returns:
        Dict with keys:
          seed, mission, claims_original, claims_after_attack,
          claims_after_defense, audit_log, plan, verdict
    """
    # 1. Generate the mission
    mission = generate_mission(seed)

    # 2-3. Create claims (agents read tools, compute answers)
    claims_original = create_claims(mission, mission_id, agent_picker_fn)

    # 4. Attack phase: optionally corrupt the claims
    if attack_fn is not None:
        claims_after_attack = attack_fn(mission, claims_original)
    else:
        claims_after_attack = list(claims_original)

    # 5. Defense phase: optionally audit/filter claims
    audit_log = []
    if defense_fn is not None:
        claims_after_defense, audit_log = defense_fn(
            mission, claims_after_attack)
    else:
        claims_after_defense = claims_after_attack

    # 6. Coordinator builds a plan from surviving claims
    plan = build_plan(mission, claims_after_defense)

    # 7. Checker validates against ground truth
    verdict = check_plan(mission, plan)

    # 8. Return everything
    return {
        "seed": seed,
        "mission_id": mission_id,
        "mission": mission,
        "claims_original": claims_original,
        "claims_after_attack": claims_after_attack,
        "claims_after_defense": claims_after_defense,
        "audit_log": audit_log,
        "plan": plan,
        "verdict": verdict,
    }


# ---------------------------------------------------------------------------
# SEED MANAGEMENT
# ---------------------------------------------------------------------------

SEEDS_DIR = Path(__file__).resolve().parent.parent / "seeds"


def load_seeds(name: str) -> List[int]:
    """Load seeds from a file in the seeds/ directory.

    Args:
        name: either "dev" or "holdout"

    Returns:
        List of integer seeds.
    """
    path = SEEDS_DIR / f"{name}_seeds.txt"
    seeds = []
    with open(path) as f:
        for line in f:
            stripped = line.strip()
            if stripped:
                seeds.append(int(stripped))
    return seeds


# ---------------------------------------------------------------------------
# Quick test: run this file directly to check Steps 1-8
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=== Step 1: Warehouse ===")
    w = Warehouse(name="Alpha", stock=50)
    print(w)
    print(f"Name: {w.name}, Stock: {w.stock}")

    try:
        w.stock = 100
    except AttributeError as e:
        print(f"Frozen works! Cannot modify: {e}")

    w2 = Warehouse(name="Alpha", stock=50)
    print(f"Same values are equal: {w == w2}")

    w3 = Warehouse(name="Bravo", stock=80)
    print(f"Different values are not equal: {w != w3}")

    print()
    print("=== Step 2: Vehicle ===")
    v = Vehicle(name="Van", capacity=20)
    print(v)
    print(f"Name: {v.name}, Capacity: {v.capacity} kits/trip")

    try:
        v.capacity = 50
    except AttributeError as e:
        print(f"Frozen works! Cannot modify: {e}")

    v2 = Vehicle(name="Truck", capacity=35)
    v3 = Vehicle(name="Drone", capacity=10)
    print(f"Three vehicles: {v.name}({v.capacity}), "
          f"{v2.name}({v2.capacity}), {v3.name}({v3.capacity})")

    # Quick math preview: if demand=40 and capacity=20
    demand = 40
    trips = math.ceil(demand / v.capacity)
    print(f"Demand={demand}, Van capacity={v.capacity} -> "
          f"trips needed = ceil({demand}/{v.capacity}) = {trips}")

    print()
    print("=== Step 3: ToolKit ===")

    # Create a ToolKit for the pair (Alpha, Van)
    # True values: stock=50, capacity=20, distance=60, time=90, cost=120
    tk = ToolKit(
        # Warehouse tools — all three compute stock = 50
        warehouse_t1={"listed_stock_count": 50},
        warehouse_t2={"total_shelf_weight_kg": 250, "unit_weight_kg": 5},
        warehouse_t3={"starting_stock": 70, "shipped_today": 20},

        # Transport tools — all three compute capacity=20, time=90
        transport_t1={"max_kit_capacity": 20, "avg_speed_kmh": 40},
        transport_t2={"max_payload_kg": 100, "kit_unit_weight_kg": 5,
                      "live_speed_kmh": 48, "traffic_delay_mins": 15},
        transport_t3={"cargo_bay_volume_m3": 2.0, "kit_box_volume_m3": 0.1,
                      "estimated_minutes": 90},

        # Logistics tools — all three compute distance=60, cost=120
        logistics_t1={"map_distance_km": 60, "base_rate_per_km": 2},
        logistics_t2={"fuel_liters": 6, "km_per_liter": 10,
                      "price_per_liter": 15, "toll_fee": 30},
        logistics_t3={"billed_mileage_km": 60, "total_quoted_cost": 120},
    )

    # Verify: manually compute each tool's answer
    # Warehouse
    t1_stock = tk.warehouse_t1["listed_stock_count"]
    t2_stock = (tk.warehouse_t2["total_shelf_weight_kg"]
                / tk.warehouse_t2["unit_weight_kg"])
    t3_stock = (tk.warehouse_t3["starting_stock"]
                - tk.warehouse_t3["shipped_today"])
    print(f"Stock from 3 tools: T1={t1_stock}, T2={t2_stock}, T3={t3_stock}")
    assert t1_stock == t2_stock == t3_stock == 50, "Stock mismatch!"

    # Logistics (distance)
    t1_dist = tk.logistics_t1["map_distance_km"]
    t2_dist = (tk.logistics_t2["fuel_liters"]
               * tk.logistics_t2["km_per_liter"])
    t3_dist = tk.logistics_t3["billed_mileage_km"]
    print(f"Distance from 3 tools: T1={t1_dist}, T2={t2_dist}, T3={t3_dist}")
    assert t1_dist == t2_dist == t3_dist == 60, "Distance mismatch!"

    # Transport (time, using true distance=60)
    dist = 60
    t1_time = (dist / tk.transport_t1["avg_speed_kmh"]) * 60
    t2_time = ((dist / tk.transport_t2["live_speed_kmh"]) * 60
               + tk.transport_t2["traffic_delay_mins"])
    t3_time = tk.transport_t3["estimated_minutes"]
    print(f"Time from 3 tools: T1={t1_time}, T2={t2_time}, T3={t3_time}")
    assert t1_time == t2_time == t3_time == 90, "Time mismatch!"

    # Test get_tool()
    fields = tk.get_tool("warehouse_t1")
    print(f"get_tool('warehouse_t1') = {fields}")

    # Test TOOL_IDS
    print(f"All 9 tool IDs: {TOOL_IDS}")
    print(f"warehouse_t2 domain: {TOOL_DOMAIN['warehouse_t2']}")

    print()
    print("=== Step 4: Mission ===")

    # Build a small mission by hand: 2 warehouses, 2 vehicles
    alpha = Warehouse(name="Alpha", stock=50)
    bravo = Warehouse(name="Bravo", stock=25)
    van = Vehicle(name="Van", capacity=20)
    truck = Vehicle(name="Truck", capacity=35)

    mission = Mission(
        seed=42,
        demand=40,
        deadline_minutes=120,
        budget=500,
        warehouses=(alpha, bravo),
        vehicles=(van, truck),
        true_stock={"Alpha": 50, "Bravo": 25},
        true_capacity={"Van": 20, "Truck": 35},
        true_distance={"Alpha": 60, "Bravo": 30},
        true_time={
            ("Alpha", "Van"): 90, ("Alpha", "Truck"): 75,
            ("Bravo", "Van"): 45, ("Bravo", "Truck"): 38,
        },
        true_cost={
            ("Alpha", "Van"): 120, ("Alpha", "Truck"): 200,
            ("Bravo", "Van"): 80, ("Bravo", "Truck"): 130,
        },
        # tools would go here — we'll fill them in Step 8
        tools={},
    )

    print(f"Mission seed={mission.seed}: deliver {mission.demand} kits")
    print(f"  Deadline: {mission.deadline_minutes} min, Budget: ${mission.budget}")
    print(f"  Warehouses: {[w.name for w in mission.warehouses]}")
    print(f"  Vehicles: {[v.name for v in mission.vehicles]}")
    print(f"  True stock: {mission.true_stock}")
    print(f"  True distance: {mission.true_distance}")
    print(f"  True time (Alpha,Van): {mission.true_time[('Alpha', 'Van')]} min")
    print(f"  True cost (Alpha,Van): ${mission.true_cost[('Alpha', 'Van')]}/trip")

    # Verify: which pairs are valid?
    for wh in mission.warehouses:
        for veh in mission.vehicles:
            pair = (wh.name, veh.name)
            stock_ok = mission.true_stock[wh.name] >= mission.demand
            time_ok = mission.true_time[pair] <= mission.deadline_minutes
            trips = math.ceil(mission.demand / mission.true_capacity[veh.name])
            total_cost = trips * mission.true_cost[pair]
            cost_ok = total_cost <= mission.budget
            valid = stock_ok and time_ok and cost_ok
            status = "VALID" if valid else "invalid"
            reason = []
            if not stock_ok:
                reason.append(f"stock {wh.stock}<{mission.demand}")
            if not time_ok:
                reason.append(f"time {mission.true_time[pair]}>{mission.deadline_minutes}")
            if not cost_ok:
                reason.append(f"cost ${total_cost}>${mission.budget}")
            reason_str = f" ({', '.join(reason)})" if reason else ""
            print(f"  {wh.name}+{veh.name}: {trips} trips, "
                  f"${total_cost} -> {status}{reason_str}")

    print()
    print("=== Step 5: Warehouse Tool Generator ===")
    rng = random.Random(42)

    # Generate tools for a warehouse with 50 kits
    wh_tools = _generate_warehouse_tools(50, rng)
    print(f"T1: {wh_tools['warehouse_t1']}")
    print(f"T2: {wh_tools['warehouse_t2']}")
    print(f"T3: {wh_tools['warehouse_t3']}")

    # Verify all 3 formulas give stock = 50
    t1_stock = wh_tools["warehouse_t1"]["listed_stock_count"]
    t2_stock = (wh_tools["warehouse_t2"]["total_shelf_weight_kg"]
                / wh_tools["warehouse_t2"]["unit_weight_kg"])
    t3_stock = (wh_tools["warehouse_t3"]["starting_stock"]
                - wh_tools["warehouse_t3"]["shipped_today"])
    print(f"Computed stock: T1={t1_stock}, T2={t2_stock}, T3={t3_stock}")
    assert t1_stock == t2_stock == t3_stock == 50

    # Test with different stock values
    for stock in [10, 80, 200]:
        tools = _generate_warehouse_tools(stock, rng)
        s1 = tools["warehouse_t1"]["listed_stock_count"]
        s2 = (tools["warehouse_t2"]["total_shelf_weight_kg"]
              / tools["warehouse_t2"]["unit_weight_kg"])
        s3 = (tools["warehouse_t3"]["starting_stock"]
              - tools["warehouse_t3"]["shipped_today"])
        assert s1 == s2 == s3 == stock, f"Failed for stock={stock}"
        print(f"  stock={stock}: T1={s1}, T2={s2}, T3={s3} -- all match")

    print()
    print("=== Step 6: Transport Tool Generator ===")

    # True values: capacity=20, time=90 min, distance=60 km
    tr_tools = _generate_transport_tools(20, 90, 60, rng)
    print(f"T1: {tr_tools['transport_t1']}")
    print(f"T2: {tr_tools['transport_t2']}")
    print(f"T3: {tr_tools['transport_t3']}")

    # Verify capacity from all 3 tools
    t1_cap = tr_tools["transport_t1"]["max_kit_capacity"]
    t2_cap = (tr_tools["transport_t2"]["max_payload_kg"]
              / tr_tools["transport_t2"]["kit_unit_weight_kg"])
    t3_cap = (tr_tools["transport_t3"]["cargo_bay_volume_m3"]
              / tr_tools["transport_t3"]["kit_box_volume_m3"])
    print(f"Capacity: T1={t1_cap}, T2={t2_cap}, T3={t3_cap}")
    assert t1_cap == t2_cap == t3_cap == 20, f"Capacity mismatch!"

    # Verify time from all 3 tools (using true distance=60)
    dist = 60
    t1_time = (dist / tr_tools["transport_t1"]["avg_speed_kmh"]) * 60
    t2_time = ((dist / tr_tools["transport_t2"]["live_speed_kmh"]) * 60
               + tr_tools["transport_t2"]["traffic_delay_mins"])
    t3_time = tr_tools["transport_t3"]["estimated_minutes"]
    print(f"Time: T1={t1_time}, T2={t2_time}, T3={t3_time}")
    assert abs(t1_time - 90) < 0.01, f"T1 time wrong: {t1_time}"
    assert abs(t2_time - 90) < 0.01, f"T2 time wrong: {t2_time}"
    assert t3_time == 90, f"T3 time wrong: {t3_time}"

    # Note: T3 time does NOT use distance — it's direct
    # So if distance were poisoned (say 20), T3 still says 90
    fake_dist = 20
    t1_time_bad = (fake_dist / tr_tools["transport_t1"]["avg_speed_kmh"]) * 60
    t3_time_ok = tr_tools["transport_t3"]["estimated_minutes"]
    print(f"With poisoned distance={fake_dist}: T1 gives {t1_time_bad:.0f} min "
          f"(WRONG), T3 still gives {t3_time_ok} min (immune)")

    print()
    print("=== Step 7: Logistics Tool Generator ===")

    # True values: distance=60 km, cost=$120/trip
    lg_tools = _generate_logistics_tools(60, 120, rng)
    print(f"T1: {lg_tools['logistics_t1']}")
    print(f"T2: {lg_tools['logistics_t2']}")
    print(f"T3: {lg_tools['logistics_t3']}")

    # Verify distance from all 3 tools
    t1_dist = lg_tools["logistics_t1"]["map_distance_km"]
    t2_dist = (lg_tools["logistics_t2"]["fuel_liters"]
               * lg_tools["logistics_t2"]["km_per_liter"])
    t3_dist = lg_tools["logistics_t3"]["billed_mileage_km"]
    print(f"Distance: T1={t1_dist}, T2={t2_dist}, T3={t3_dist}")
    assert t1_dist == t2_dist == t3_dist == 60, "Distance mismatch!"

    # Verify cost from all 3 tools
    t1_cost = t1_dist * lg_tools["logistics_t1"]["base_rate_per_km"]
    t2_cost = (lg_tools["logistics_t2"]["fuel_liters"]
               * lg_tools["logistics_t2"]["price_per_liter"]
               + lg_tools["logistics_t2"]["toll_fee"])
    t3_cost = lg_tools["logistics_t3"]["total_quoted_cost"]
    print(f"Cost: T1={t1_cost}, T2={t2_cost}, T3={t3_cost}")
    assert abs(t1_cost - 120) < 0.01, f"T1 cost wrong: {t1_cost}"
    assert abs(t2_cost - 120) < 0.01, f"T2 cost wrong: {t2_cost}"
    assert t3_cost == 120, f"T3 cost wrong: {t3_cost}"

    # Show cascading: if distance poisoned to 20, T1 cost is wrong
    fake_dist = 20
    t1_cost_bad = fake_dist * lg_tools["logistics_t1"]["base_rate_per_km"]
    t3_cost_ok = lg_tools["logistics_t3"]["total_quoted_cost"]
    print(f"With poisoned distance={fake_dist}: T1 cost=${t1_cost_bad:.0f} "
          f"(WRONG), T3 cost=${t3_cost_ok} (immune)")

    print()
    print("=== Step 8: generate_mission() ===")

    # Generate a mission from seed
    m = generate_mission(1000)
    print(f"Mission seed={m.seed}: deliver {m.demand} kits")
    print(f"  Deadline: {m.deadline_minutes} min, Budget: ${m.budget}")
    print(f"  Warehouses: {[w.name for w in m.warehouses]}")
    print(f"  Vehicles: {[v.name for v in m.vehicles]}")
    print(f"  True stock: {m.true_stock}")
    print(f"  True capacity: {m.true_capacity}")
    print(f"  True distance: {m.true_distance}")

    # Verify feasibility: at least one pair must work
    found_valid = False
    for wh in m.warehouses:
        for veh in m.vehicles:
            pair = (wh.name, veh.name)
            trips = math.ceil(m.demand / m.true_capacity[veh.name])
            total_cost = trips * m.true_cost[pair]
            stock_ok = m.true_stock[wh.name] >= m.demand
            time_ok = m.true_time[pair] <= m.deadline_minutes
            cost_ok = total_cost <= m.budget
            valid = stock_ok and time_ok and cost_ok
            if valid:
                found_valid = True
            status = "VALID" if valid else "invalid"
            print(f"  {wh.name}+{veh.name}: stock={m.true_stock[wh.name]}, "
                  f"time={m.true_time[pair]}min, "
                  f"{trips} trips * ${m.true_cost[pair]} = ${total_cost} "
                  f"-> {status}")
    assert found_valid, "Mission is not feasible!"
    print("  Feasibility: OK (at least one valid pair)")

    # Verify tool consistency for one pair
    pair = (m.warehouses[0].name, m.vehicles[0].name)
    tk = m.tools[pair]
    wh_name, veh_name = pair
    true_s = m.true_stock[wh_name]
    true_d = m.true_distance[wh_name]
    true_c = m.true_capacity[veh_name]
    true_t = m.true_time[pair]
    true_co = m.true_cost[pair]

    # Check warehouse tools all give true stock
    s1 = tk.warehouse_t1["listed_stock_count"]
    s2 = tk.warehouse_t2["total_shelf_weight_kg"] / tk.warehouse_t2["unit_weight_kg"]
    s3 = tk.warehouse_t3["starting_stock"] - tk.warehouse_t3["shipped_today"]
    assert s1 == s2 == s3 == true_s, f"Stock mismatch for {pair}"

    # Check logistics tools all give true distance
    d1 = tk.logistics_t1["map_distance_km"]
    d2 = tk.logistics_t2["fuel_liters"] * tk.logistics_t2["km_per_liter"]
    d3 = tk.logistics_t3["billed_mileage_km"]
    assert d1 == d2 == d3 == true_d, f"Distance mismatch for {pair}"

    # Check transport tools all give true capacity
    c1 = tk.transport_t1["max_kit_capacity"]
    c2 = tk.transport_t2["max_payload_kg"] / tk.transport_t2["kit_unit_weight_kg"]
    c3 = tk.transport_t3["cargo_bay_volume_m3"] / tk.transport_t3["kit_box_volume_m3"]
    assert c1 == c2 == c3 == true_c, f"Capacity mismatch for {pair}"

    print(f"  Tool consistency for {pair}: ALL 9 tools match truth")

    # Reproducibility: same seed = same mission
    m2 = generate_mission(1000)
    assert m.demand == m2.demand
    assert m.true_stock == m2.true_stock
    assert m.true_time == m2.true_time
    print(f"  Reproducibility: seed 1000 gives same mission twice: OK")

    # Different seed = different mission
    m3 = generate_mission(2000)
    print(f"  Different seed: demand {m.demand} vs {m3.demand}")

    # Test several seeds for feasibility
    print(f"  Testing 10 seeds for feasibility...")
    for s in range(1000, 1010):
        mi = generate_mission(s)
        ok = False
        for wh in mi.warehouses:
            for veh in mi.vehicles:
                p = (wh.name, veh.name)
                trips = math.ceil(mi.demand / mi.true_capacity[veh.name])
                tc = trips * mi.true_cost[p]
                if (mi.true_stock[wh.name] >= mi.demand
                        and mi.true_time[p] <= mi.deadline_minutes
                        and tc <= mi.budget):
                    ok = True
        assert ok, f"Seed {s} not feasible!"
    print(f"  All 10 seeds feasible: OK")

    print()
    print("=== Steps 9-11: Agents, compute_answer, create_claims ===")

    # Use seed 1000 mission from Step 8
    m = generate_mission(1000)

    # Test compute_answer for one pair
    pair = (m.warehouses[0].name, m.vehicles[0].name)
    tk = m.tools[pair]
    wh_name = m.warehouses[0].name
    veh_name = m.vehicles[0].name

    # Stock via warehouse_t1
    stock_ans = compute_answer("warehouse_t1",
                               tk.get_tool("warehouse_t1"), "stock")
    print(f"compute_answer stock via T1: {stock_ans} "
          f"(truth: {m.true_stock[wh_name]})")
    assert stock_ans == m.true_stock[wh_name]

    # Distance via logistics_t2
    dist_ans = compute_answer("logistics_t2",
                              tk.get_tool("logistics_t2"), "distance")
    print(f"compute_answer distance via T2: {dist_ans} "
          f"(truth: {m.true_distance[wh_name]})")
    assert dist_ans == m.true_distance[wh_name]

    # Time via transport_t1 (needs distance)
    time_ans = compute_answer("transport_t1",
                              tk.get_tool("transport_t1"), "time",
                              decided_distance=m.true_distance[wh_name])
    print(f"compute_answer time via T1: {time_ans} "
          f"(truth: {m.true_time[pair]})")
    assert abs(time_ans - m.true_time[pair]) < 0.01

    # Create all claims
    claims = create_claims(m, mission_id=0)
    print(f"\nTotal claims: {len(claims)}")

    # Count by question type
    stock_claims = [c for c in claims if c["key"].startswith("stock")]
    cap_claims = [c for c in claims if c["key"].startswith("capacity")]
    dist_claims = [c for c in claims if c["key"].startswith("distance")]
    time_claims = [c for c in claims if c["key"].startswith("time")]
    cost_claims = [c for c in claims if c["key"].startswith("cost")]
    n_wh = len(m.warehouses)
    n_veh = len(m.vehicles)
    expected = n_wh + n_veh + n_wh + (n_wh * n_veh) + (n_wh * n_veh)
    print(f"  Stock: {len(stock_claims)} (expected {n_wh})")
    print(f"  Capacity: {len(cap_claims)} (expected {n_veh})")
    print(f"  Distance: {len(dist_claims)} (expected {n_wh})")
    print(f"  Time: {len(time_claims)} (expected {n_wh * n_veh})")
    print(f"  Cost: {len(cost_claims)} (expected {n_wh * n_veh})")
    print(f"  Total: {len(claims)} (expected {expected})")
    assert len(claims) == expected

    # Verify all honest claims match truth
    all_honest = all(abs(c["answer"] - c["truth"]) < 0.01 for c in claims)
    print(f"  All claims match truth (honest agents): {all_honest}")
    assert all_honest

    # Show the first few claims
    print(f"\n  First 5 claims:")
    for c in claims[:5]:
        parent = c["parent_decision_id"] or "none"
        print(f"    {c['claim_id']}: {c['key']} = {c['answer']} "
              f"(agent={c['agent_id']}, tool={c['tool_id']}, "
              f"parent={parent})")

    # Show a time claim with its parent
    time_claim = time_claims[0]
    print(f"\n  Time claim with parent:")
    print(f"    {time_claim['claim_id']}: {time_claim['key']} "
          f"= {time_claim['answer']}")
    print(f"    parent_decision_id: {time_claim['parent_decision_id']} "
          f"(the distance claim it depends on)")

    print()
    print("=== Steps 12-13: build_plan and check_plan ===")

    # Use seed 1000 mission and its honest claims
    m = generate_mission(1000)
    claims = create_claims(m, mission_id=0)

    # Build a plan from honest claims
    plan = build_plan(m, claims)
    if plan:
        print(f"Plan: {plan['warehouse']} + {plan['vehicle']}, "
              f"{plan['trips']} trips, ${plan['total_cost']:.0f}, "
              f"{plan['reported_time']:.0f} min")
    else:
        print("No plan found")

    # Check the plan against ground truth
    verdict = check_plan(m, plan)
    status = "VALID" if verdict["valid"] else "INVALID"
    print(f"Plan checker: {status}")
    for reason in verdict["reasons"]:
        print(f"  - {reason}")

    # With honest claims, the plan should ALWAYS be valid
    assert verdict["valid"], "Honest claims should produce a valid plan!"
    print("Honest claims -> valid plan: OK")

    # Test with no plan
    verdict_none = check_plan(m, None)
    assert not verdict_none["valid"]
    print(f"No plan -> {verdict_none['reasons'][0]}: OK")

    # Test across 10 seeds: honest claims should always give valid plans
    print(f"\nTesting 10 seeds: honest claims -> valid plan...")
    for s in range(1000, 1010):
        mi = generate_mission(s)
        cl = create_claims(mi, mission_id=0)
        pl = build_plan(mi, cl)
        vd = check_plan(mi, pl)
        status = "PASS" if vd["valid"] else "FAIL"
        plan_info = ""
        if pl:
            plan_info = f" ({pl['warehouse']}+{pl['vehicle']}, ${pl['total_cost']:.0f})"
        print(f"  Seed {s}: {status}{plan_info}")
        assert vd["valid"], f"Seed {s} failed with honest claims!"

    print("All 10 seeds pass with honest claims!")

    print()
    print("=== Step 14: run_mission() pipeline ===")

    # Run a mission with no attack, no defense (C0/D0 baseline)
    result = run_mission(seed=1000, mission_id=0)
    print(f"Result keys: {list(result.keys())}")
    print(f"  Seed: {result['seed']}")
    print(f"  Mission ID: {result['mission_id']}")
    print(f"  Original claims: {len(result['claims_original'])}")
    print(f"  After attack: {len(result['claims_after_attack'])}")
    print(f"  After defense: {len(result['claims_after_defense'])}")
    print(f"  Audit log: {result['audit_log']}")

    plan = result["plan"]
    verdict = result["verdict"]
    if plan:
        print(f"  Plan: {plan['warehouse']}+{plan['vehicle']}, "
              f"${plan['total_cost']:.0f}")
    print(f"  Verdict: {'VALID' if verdict['valid'] else 'INVALID'}")
    assert verdict["valid"], "C0/D0 baseline must produce a valid plan!"

    # No attack means claims_original == claims_after_attack
    for orig, after in zip(result["claims_original"],
                           result["claims_after_attack"]):
        assert orig["answer"] == after["answer"], \
            "No attack should leave claims unchanged!"
    print("  No attack: claims unchanged: OK")

    # No defense means claims_after_attack == claims_after_defense
    assert result["claims_after_attack"] is result["claims_after_defense"]
    print("  No defense: claims passed through: OK")

    # Test with a dummy attack that doubles all stock answers
    def dummy_attack(mission, claims):
        import copy
        modified = []
        for c in claims:
            mc = copy.copy(c)
            if mc["key"].startswith("stock"):
                mc["answer"] = mc["answer"] * 2
            modified.append(mc)
        return modified

    result_atk = run_mission(seed=1000, mission_id=1,
                             attack_fn=dummy_attack)
    # Check that the attack modified stock claims
    for c in result_atk["claims_after_attack"]:
        if c["key"].startswith("stock"):
            # Doubled stock should be 2x the original
            orig_claim = [oc for oc in result_atk["claims_original"]
                          if oc["claim_id"] == c["claim_id"]][0]
            assert c["answer"] == orig_claim["answer"] * 2
    print("  Dummy attack (2x stock): claims modified correctly: OK")

    # Test with a dummy defense that drops all claims (worst case)
    def dummy_defense(mission, claims):
        return [], [{"action": "dropped_all"}]

    result_def = run_mission(seed=1000, mission_id=2,
                             defense_fn=dummy_defense)
    assert result_def["plan"] is None, \
        "No claims should mean no plan!"
    assert not result_def["verdict"]["valid"]
    assert len(result_def["audit_log"]) == 1
    print("  Dummy defense (drop all): no plan, invalid: OK")

    # Reproducibility: same seed+id gives same result
    r1 = run_mission(seed=1000, mission_id=0)
    r2 = run_mission(seed=1000, mission_id=0)
    assert r1["verdict"]["valid"] == r2["verdict"]["valid"]
    assert r1["plan"]["warehouse"] == r2["plan"]["warehouse"]
    print("  Reproducibility: same seed = same result: OK")

    # Run 10 seeds through the pipeline
    print(f"\n  Running 10 seeds through full pipeline (C0/D0)...")
    for s in range(1000, 1010):
        r = run_mission(seed=s, mission_id=s - 1000)
        status = "PASS" if r["verdict"]["valid"] else "FAIL"
        plan_info = ""
        if r["plan"]:
            plan_info = (f" ({r['plan']['warehouse']}"
                         f"+{r['plan']['vehicle']})")
        print(f"    Seed {s}: {status}{plan_info}")
        assert r["verdict"]["valid"], \
            f"Seed {s} failed with no attack!"
    print("  All 10 seeds pass with C0/D0 baseline!")

    print()
    print("All steps 1-14 pass!")
    print("Simulator is complete!")
