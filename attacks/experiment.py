"""Run relief requests on an attacked world and measure what the attack did.

This module plays the evaluator: it may read truth.py and world['attack']. The defense never sees either.

Metrics (per defense, over many seeds):
  success_rate     share of runs where the chosen plan differs from the clean plan
  corruption_rate  share of the defense's decisions that differ from the truth
  avg_extra_cost   mean extra REAL cost the NGO pays, over the runs where the plan changed
"""
from collections import Counter

from attacks.c0_no_attack import no_attack
from attacks.c2_byzantine_agent import lie
from simulator import truth as T
from simulator.agents.coordinator import AgentCoordinator
from simulator.defense import MajorityVoteDefense
from simulator.participants.hospital import find_camp
from simulator.world_ids import WAREHOUSE_IDS


class AttackedChannel:
    """Sits between the agents and the defense: applies the agent-level attacks (C2) to each claim,
    hands the claims to the defense, and records what the defense saw and decided."""

    def __init__(self, world, defense):
        self.world, self.defense = world, defense
        self.claims, self.decisions, self.lied = [], {}, []

    def decide(self, question, key, claims):
        for claim in claims:
            if lie(self.world, claim):
                self.lied.append(claim)
        self.claims += claims
        value = self.defense.decide(question, key, claims)
        self.decisions[(question, tuple(sorted(key.items())))] = value
        return value


def run_request(world, defense, request):
    """request = (medicine, quantity, camp_name). Returns (coordinator result, channel)."""
    channel = AttackedChannel(world, defense)
    result = AgentCoordinator(defense=channel, world=world).run_simulation(*request)
    return result, channel


def chosen_plan(result):
    if result['warehouse']['decision'] != 'Approved':
        return None
    return WAREHOUSE_IDS[result['warehouse']['warehouse_name']], result['transportation']['vehicle']


def truth_value(question, key):
    w, h, v, m = key.get('warehouse'), key.get('hospital'), key.get('vehicle'), key.get('medicine')
    return {'Q1': lambda: T.truth_stock(w, m), 'Q2': lambda: T.truth_capacity(v),
            'Q3': lambda: T.truth_distance(w, h), 'Q4': lambda: T.truth_time_minutes(w, h, v),
            'Q5': lambda: T.truth_cost(w, h, v)}[question]()


def real_cost(plan, hospital):
    return None if plan is None else T.truth_cost(plan[0], hospital, plan[1])


def evaluate(world, make_defense, request, seeds):
    """Run the request once per seed with make_defense(seed) and summarise the attack's effect."""
    hospital = find_camp(request[2])['camp_id']
    clean_plan = chosen_plan(run_request(no_attack(), MajorityVoteDefense(), request)[0])
    runs = []
    for seed in seeds:
        result, channel = run_request(world, make_defense(seed), request)
        plan = chosen_plan(result)
        wrong = sum(value != truth_value(q, dict(key)) for (q, key), value in channel.decisions.items())
        extra = None
        if plan != clean_plan and plan is not None and clean_plan is not None:
            extra = real_cost(plan, hospital) - real_cost(clean_plan, hospital)
        runs.append({'seed': seed, 'plan': plan, 'fooled': plan != clean_plan, 'extra_cost': extra,
                     'wrong': wrong, 'decisions': len(channel.decisions)})
    fooled = [r for r in runs if r['fooled']]
    extras = [r['extra_cost'] for r in fooled if r['extra_cost'] is not None]
    return {
        'clean_plan': clean_plan,
        'success_rate': len(fooled) / len(runs),
        'corruption_rate': sum(r['wrong'] for r in runs) / max(1, sum(r['decisions'] for r in runs)),
        'avg_extra_cost': sum(extras) / len(extras) if extras else None,
        'typical_plan': Counter(r['plan'] for r in fooled).most_common(1)[0][0] if fooled else clean_plan,
        'runs': runs,
    }
