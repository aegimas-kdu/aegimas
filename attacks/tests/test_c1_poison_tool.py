import pytest

from attacks import POISON_FIELDS, poison_tool
from simulator import registry as R
from simulator import truth as T
from simulator.agents.coordinator import AgentCoordinator
from simulator.defense import MajorityVoteDefense

KEY = {'warehouse': 'W3', 'hospital': 'C2', 'vehicle': 'Truck'}
LOGISTICS = ['L_Agent_1', 'L_Agent_2', 'L_Agent_3']


def readings_by_tool(claim):
    return {r['tool_id']: r['value'] for r in claim['readings']}


def test_c1_never_changes_the_cached_clean_world():
    before = R.find_record(R.get_world(), 'gis_distance_matrix', KEY)['map_distance_km']
    poison_tool('gis_distance_matrix', 0.5)
    assert R.find_record(R.get_world(), 'gis_distance_matrix', KEY)['map_distance_km'] == before
    assert 'attack' not in R.get_world()


def test_c1_changes_only_the_poisoned_tool_readings():
    world = poison_tool('gis_distance_matrix', 0.5)
    truth = T.truth_distance('W3', 'C2')
    for agent_id in LOGISTICS:
        values = readings_by_tool(R.get_claim(agent_id, 'Q3', KEY, world=world))
        for tool_id, value in values.items():
            assert value == (round(truth * 0.5) if tool_id == 'gis_distance_matrix' else truth)
    # L_Agent_1 uses GIS as primary, L_Agent_2 as backup, L_Agent_3 not at all.
    answers = {a: R.get_claim(a, 'Q3', KEY, world=world)['answer'] for a in LOGISTICS}
    assert answers == {'L_Agent_1': round(truth * 0.5), 'L_Agent_2': truth, 'L_Agent_3': truth}


def test_c1_corrupts_every_question_the_tool_answers():
    world = poison_tool('gis_distance_matrix', 0.5)
    q5 = readings_by_tool(R.get_claim('L_Agent_1', 'Q5', KEY, world=world))
    assert q5['gis_distance_matrix'] != T.truth_cost('W3', 'C2', 'Truck')
    assert q5['billing_quote_api'] == T.truth_cost('W3', 'C2', 'Truck')


def test_c1_slice_poisons_only_the_matching_records():
    world = poison_tool('gis_distance_matrix', 2, where={'warehouse': 'W3'})
    for record in world['tools']['gis_distance_matrix']['records']:
        truth = T.truth_distance(record['warehouse_id'], record['hospital_id'])
        expected = truth * 2 if record['warehouse_id'] == 'W3' else truth
        assert record['map_distance_km'] == expected
    assert len(world['attack']['poisoned']) == 6 * 3  # 6 hospitals x 3 vehicles for W3
    assert all(p['key']['warehouse'] == 'W3' for p in world['attack']['poisoned'])


def test_c1_attacks_stack_on_a_given_world():
    world = poison_tool('gis_distance_matrix', 0.5, where={'warehouse': 'W1'})
    world = poison_tool('billing_quote_api', 0.5, where={'warehouse': 'W1'}, world=world)
    assert world['attack']['names'] == ['C1', 'C1']
    assert {p['tool_id'] for p in world['attack']['poisoned']} == {'gis_distance_matrix', 'billing_quote_api'}


@pytest.mark.parametrize('tool_id', sorted(POISON_FIELDS))
def test_c1_every_tool_can_be_poisoned_and_still_reads(tool_id):
    world = poison_tool(tool_id, 1.5)
    domain = world['tools'][tool_id]['domain']
    question = next(q for q, spec in R.QUESTIONS.items()
                    if spec['domain'] == domain and (q, tool_id) in R.DERIVE)
    key = {'warehouse': 'W1', 'hospital': 'C1', 'vehicle': 'Van', 'medicine': 'Paracetamol'}
    agent = next(a for a in world['agents'] if tool_id in (a['primary_tool'], a['backup_tool']))
    claim = R.get_claim(agent['agent_id'], question, key, {'resolved_distance_km': 120}, world=world)
    assert isinstance(readings_by_tool(claim)[tool_id], int)


def test_c1_bad_arguments_raise():
    with pytest.raises(ValueError):
        poison_tool('no_such_tool', 0.5)
    with pytest.raises(ValueError):
        poison_tool('gis_distance_matrix', 1)
    with pytest.raises(ValueError):
        poison_tool('fleet_specs_catalog', 0.5, where={'warehouse': 'W1'})  # keyed by vehicle only
    with pytest.raises(ValueError):
        poison_tool('gis_distance_matrix', 0.5, where={'warehouse': 'W9'})


def test_c1_single_tool_is_outvoted_by_majority_vote():
    # One poisoned tool reaches 2 of 6 readings but only 1 of 3 answers, so majority vote holds.
    world = poison_tool('gis_distance_matrix', 0.5)
    coordinator = AgentCoordinator(defense=MajorityVoteDefense(), world=world)
    distance, _ = coordinator.ask('Q3', KEY)
    assert distance == T.truth_distance('W3', 'C2')
