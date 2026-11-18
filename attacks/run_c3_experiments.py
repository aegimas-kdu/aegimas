"""C3 Experiment Runner — Coordinated Byzantine + Tool-Poisoning Attack

Runs the combined attack (C3) across multiple configurations and defenses,
captures results to attacks/results/c3_experiments.txt.

Usage from the Defense-systems folder:
    python -m attacks.run_c3_experiments
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collections import Counter

from attacks import combined_attack, evaluate, no_attack, poison_tool, byzantine_agent
from attacks.experiment import chosen_plan, real_cost, truth_value
from simulator.defense import MajorityVoteDefense
from simulator.nodefense import NoDefense

REQUEST = ('Malaria Treatment', 50, 'Muyinga Health Centre')
SEEDS = range(60)

DEFENSES = {
    'No defense': lambda s: NoDefense(seed=s),
    'Majority vote': lambda s: MajorityVoteDefense(),
}

# ---- C3 Experiment Configurations ----
# Each config: (name, description, combined_attack kwargs)
C3_CONFIGS = [
    # Config 1: Liar on logistics + poison on distance tool, same warehouse
    (
        'C3-1: Same target (W1)',
        'L_Agent_1 lies x0.3 on W1 + gis_distance_matrix poisoned x0.5 on W1',
        dict(agent_id='L_Agent_1', agent_factor=0.3, tool_id='gis_distance_matrix', tool_factor=0.5,
             agent_where={'warehouse': 'W1'}, tool_where={'warehouse': 'W1'}),
    ),
    # Config 2: Liar and poison target different warehouses (spread attack)
    (
        'C3-2: Split targets (agent W1, tool W3)',
        'L_Agent_1 lies x0.3 on W1 + gis_distance_matrix poisoned x0.5 on W3',
        dict(agent_id='L_Agent_1', agent_factor=0.3, tool_id='gis_distance_matrix', tool_factor=0.5,
             agent_where={'warehouse': 'W1'}, tool_where={'warehouse': 'W3'}),
    ),
    # Config 3: Aggressive factors (stronger attack)
    (
        'C3-3: Aggressive (x0.1 liar, x3.0 poison)',
        'L_Agent_1 lies x0.1 on W1 + gis_distance_matrix poisoned x3.0 on W1',
        dict(agent_id='L_Agent_1', agent_factor=0.1, tool_id='gis_distance_matrix', tool_factor=3.0,
             agent_where={'warehouse': 'W1'}, tool_where={'warehouse': 'W1'}),
    ),
    # Config 4: Transportation agent lies + fleet tool poisoned
    (
        'C3-4: Transport domain attack',
        'T_Agent_1 lies x0.3 + fleet_specs_catalog poisoned x0.5 on Van',
        dict(agent_id='T_Agent_1', agent_factor=0.3, tool_id='fleet_specs_catalog', tool_factor=0.5,
             agent_where={}, tool_where={'vehicle': 'Van'}),
    ),
    # Config 5: Global poison (all records) + targeted liar
    (
        'C3-5: Global poison + targeted liar',
        'L_Agent_2 lies x0.5 on W2 + fuel_and_toll_rates poisoned x2.0 everywhere',
        dict(agent_id='L_Agent_2', agent_factor=0.5, tool_id='fuel_and_toll_rates', tool_factor=2.0,
             agent_where={'warehouse': 'W2'}, tool_where={}),
    ),
    # Config 6: Warehouse domain — agent lies + inventory tool poisoned
    (
        'C3-6: Warehouse domain attack',
        'W_Agent_1 lies x0.3 + warehouse_inventory_db poisoned x0.5 on W1',
        dict(agent_id='W_Agent_1', agent_factor=0.3, tool_id='warehouse_inventory_db', tool_factor=0.5,
             agent_where={'warehouse': 'W1'}, tool_where={'warehouse': 'W1'}),
    ),
]

# ---- Comparison baselines: C1-only and C2-only versions of some configs ----
BASELINE_CONFIGS = [
    ('C1-only: gis x0.5 on W1', lambda: poison_tool('gis_distance_matrix', 0.5, where={'warehouse': 'W1'})),
    ('C2-only: L_Agent_1 x0.3 on W1', lambda: byzantine_agent('L_Agent_1', 0.3, where={'warehouse': 'W1'})),
    ('C0: no attack', lambda: no_attack()),
]


def run_one(name, world, defense_name, make_defense, seeds):
    seeded = defense_name == 'No defense'
    report = evaluate(world, make_defense, REQUEST, seeds if seeded else [0])
    if not seeded:
        report['runs'] = [dict(report['runs'][0], seed=s) for s in seeds]
    return report


def format_report(report):
    lines = []
    lines.append(f"  Success rate (attack fools the plan): {100 * report['success_rate']:.1f}%")
    lines.append(f"  Decision corruption rate:             {100 * report['corruption_rate']:.1f}%")
    if report['avg_extra_cost'] is not None:
        lines.append(f"  Avg extra real cost when fooled:      +{report['avg_extra_cost']:.0f}")
    else:
        lines.append(f"  Avg extra real cost when fooled:      n/a (never fooled or no cost diff)")
    lines.append(f"  Clean plan:  {report['clean_plan']}")
    lines.append(f"  Typical attacked plan: {report['typical_plan']}")
    fooled = sum(1 for r in report['runs'] if r['fooled'])
    lines.append(f"  Runs fooled: {fooled}/{len(report['runs'])}")
    return '\n'.join(lines)


def main():
    output_lines = []
    output_lines.append('=' * 80)
    output_lines.append('C3 EXPERIMENT RESULTS — Coordinated Byzantine + Tool-Poisoning Attack')
    output_lines.append(f'Request: {REQUEST[1]} x {REQUEST[0]} -> {REQUEST[2]}')
    output_lines.append(f'Seeds: {SEEDS.start}-{SEEDS.stop - 1} ({len(SEEDS)} runs per config)')
    output_lines.append('=' * 80)

    # ---- Run C3 configs ----
    for config_name, description, kwargs in C3_CONFIGS:
        output_lines.append('')
        output_lines.append('-' * 80)
        output_lines.append(f'CONFIG: {config_name}')
        output_lines.append(f'  {description}')
        output_lines.append('-' * 80)
        world = combined_attack(**kwargs)
        print(f'Running {config_name}...')
        for defense_name, make_defense in DEFENSES.items():
            report = run_one(config_name, world, defense_name, make_defense, SEEDS)
            output_lines.append(f'\n  Defense: {defense_name}')
            output_lines.append(format_report(report))

    # ---- Run baselines for comparison ----
    output_lines.append('')
    output_lines.append('=' * 80)
    output_lines.append('BASELINES FOR COMPARISON (C0, C1-only, C2-only)')
    output_lines.append('=' * 80)

    for baseline_name, make_world in BASELINE_CONFIGS:
        output_lines.append('')
        output_lines.append(f'--- {baseline_name} ---')
        world = make_world()
        print(f'Running baseline {baseline_name}...')
        for defense_name, make_defense in DEFENSES.items():
            report = run_one(baseline_name, world, defense_name, make_defense, SEEDS)
            output_lines.append(f'\n  Defense: {defense_name}')
            output_lines.append(format_report(report))

    # ---- Write results ----
    results_dir = Path(__file__).resolve().parent / 'results'
    results_dir.mkdir(parents=True, exist_ok=True)
    output_path = results_dir / 'c3_experiments.txt'
    text = '\n'.join(output_lines) + '\n'
    output_path.write_text(text, encoding='utf-8')
    print(f'\nResults written to {output_path}')
    print(text)


if __name__ == '__main__':
    main()
