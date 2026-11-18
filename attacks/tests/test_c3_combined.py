import pytest

from attacks import combined_attack, evaluate, no_attack, run_request
from simulator import registry as R
from simulator import truth as T
from simulator.defense import MajorityVoteDefense
from simulator.nodefense import NoDefense

REQUEST = ('Malaria Treatment', 50, 'Muyinga Health Centre')


def readings_by_tool(claim):
    return {r['tool_id']: r['value'] for r in claim['readings']}


def test_c3_stacks_both_attack_names():
    world = combined_attack('L_Agent_1', 0.3, 'gis_distance_matrix', 0.5)
    assert world['attack']['names'] == ['C1', 'C2']
    assert len(world['attack']['liars']) == 1
    assert len(world['attack']['poisoned']) > 0


def test_c3_poisons_the_tool_and_makes_the_agent_lie():
    clean = R.get_world()
    world = combined_attack('L_Agent_1', 0.3, 'gis_distance_matrix', 2.0,
                            tool_where={'warehouse': 'W3'})
    for record, clean_rec in zip(world['tools']['gis_distance_matrix']['records'],
                                  clean['tools']['gis_distance_matrix']['records']):
        if record['warehouse_id'] == 'W3':
            assert record['map_distance_km'] == max(1, round(clean_rec['map_distance_km'] * 2))
        else:
            assert record['map_distance_km'] == clean_rec['map_distance_km']
    assert world['attack']['liars'][0]['agent_id'] == 'L_Agent_1'
    assert world['attack']['liars'][0]['factor'] == 0.3


def test_c3_does_not_modify_the_base_world():
    base = no_attack()
    world = combined_attack('L_Agent_1', 0.3, 'gis_distance_matrix', 0.5, world=base)
    assert base['attack']['liars'] == []
    assert len(base['attack']['poisoned']) == 0
    assert len(world['attack']['liars']) == 1
    assert len(world['attack']['poisoned']) > 0


def test_c3_liar_and_poison_affect_different_claims():
    world = combined_attack('L_Agent_1', 0.3, 'gis_distance_matrix', 0.5,
                            agent_where={'warehouse': 'W1'},
                            tool_where={'warehouse': 'W3'})
    _, channel = run_request(world, MajorityVoteDefense(), REQUEST)
    lied_agents = {c['agent_id'] for c in channel.lied}
    assert 'L_Agent_1' in lied_agents
    poisoned_tools = {p['tool_id'] for p in world['attack']['poisoned']}
    assert 'gis_distance_matrix' in poisoned_tools


def test_c3_with_where_filters():
    world = combined_attack('L_Agent_1', 0.3, 'gis_distance_matrix', 2.0,
                            agent_where={'warehouse': 'W1'},
                            tool_where={'warehouse': 'W3'})
    assert world['attack']['liars'][0]['where'] == {'warehouse': 'W1'}
    assert all(p['key']['warehouse'] == 'W3' for p in world['attack']['poisoned'])


def test_c3_majority_vote_still_holds_with_one_liar_and_one_tool():
    world = combined_attack('L_Agent_1', 0.3, 'gis_distance_matrix', 0.5,
                            agent_where={'warehouse': 'W1'},
                            tool_where={'warehouse': 'W3'})
    report = evaluate(world, lambda s: MajorityVoteDefense(), REQUEST, [0])
    assert report['corruption_rate'] < 0.5


def test_c3_fools_no_defense_more_often_than_c1_or_c2_alone():
    seeds = range(60)
    world_c1 = no_attack()
    from attacks.c1_poison_tool import poison_tool
    world_c1 = poison_tool('gis_distance_matrix', 0.3, where={'warehouse': 'W1'})
    from attacks.c2_byzantine_agent import byzantine_agent
    world_c2 = byzantine_agent('L_Agent_1', 0.3, where={'warehouse': 'W1'})
    world_c3 = combined_attack('L_Agent_1', 0.3, 'gis_distance_matrix', 0.3,
                               agent_where={'warehouse': 'W1'},
                               tool_where={'warehouse': 'W1'})
    make_no_defense = lambda s: NoDefense(seed=s)
    r_c1 = evaluate(world_c1, make_no_defense, REQUEST, seeds)
    r_c2 = evaluate(world_c2, make_no_defense, REQUEST, seeds)
    r_c3 = evaluate(world_c3, make_no_defense, REQUEST, seeds)
    assert r_c3['corruption_rate'] >= max(r_c1['corruption_rate'], r_c2['corruption_rate'])


def test_c3_bad_arguments_propagate():
    with pytest.raises(ValueError):
        combined_attack('X_Agent_9', 0.5, 'gis_distance_matrix', 0.5)
    with pytest.raises(ValueError):
        combined_attack('L_Agent_1', 0.5, 'no_such_tool', 0.5)
    with pytest.raises(ValueError):
        combined_attack('L_Agent_1', 1, 'gis_distance_matrix', 0.5)
    with pytest.raises(ValueError):
        combined_attack('L_Agent_1', 0.5, 'gis_distance_matrix', 1)
