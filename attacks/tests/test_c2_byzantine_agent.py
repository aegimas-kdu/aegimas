import pytest

from attacks import byzantine_agent, evaluate, no_attack, poison_tool, run_request
from simulator import registry as R
from simulator import truth as T
from simulator.defense import MajorityVoteDefense
from simulator.nodefense import NoDefense

REQUEST = ('Malaria Treatment', 50, 'Muyinga Health Centre')  # clean plan: W2 Gitega, Van, cost 270


def logistics_claims(channel, question, warehouse):
    return {c['agent_id']: c for c in channel.claims if c['question'] == question and c['key'][0] == warehouse}


def test_c2_leaves_the_tools_clean():
    world = byzantine_agent('L_Agent_1', 0.3)
    assert world['tools'] == R.get_world()['tools']
    assert world['attack']['liars'] == [{'agent_id': 'L_Agent_1', 'factor': 0.3, 'where': {},
                                         'questions': ['Q3', 'Q5']}]


def test_c2_liar_reports_the_same_lie_in_both_readings():
    world = byzantine_agent('L_Agent_1', 0.3, where={'warehouse': 'W1'})
    _, channel = run_request(world, MajorityVoteDefense(), REQUEST)
    claims = logistics_claims(channel, 'Q5', 'W1')
    truth = T.truth_cost('W1', 'C1', claims['L_Agent_1']['key'][2])
    liar = claims['L_Agent_1']
    assert liar['answer'] == round(truth * 0.3)
    assert [r['value'] for r in liar['readings']] == [round(truth * 0.3)] * 2
    assert claims['L_Agent_2']['answer'] == truth and claims['L_Agent_3']['answer'] == truth


def test_c2_only_lies_where_and_on_the_questions_asked():
    world = byzantine_agent('L_Agent_1', 0.3, where={'warehouse': 'W1'}, questions=['Q5'])
    _, channel = run_request(world, MajorityVoteDefense(), REQUEST)
    assert all(c['agent_id'] == 'L_Agent_1' and c['question'] == 'Q5' and c['key'][0] == 'W1'
               for c in channel.lied)
    assert channel.lied
    for claim in channel.claims:
        if claim not in channel.lied:
            key = dict(zip(R.QUESTIONS[claim['question']]['key'], claim['key']))
            if claim['question'] != 'Q4':
                expected = {'Q1': lambda: T.truth_stock(key['warehouse'], key['medicine']),
                            'Q2': lambda: T.truth_capacity(key['vehicle']),
                            'Q3': lambda: T.truth_distance(key['warehouse'], key['hospital']),
                            'Q5': lambda: T.truth_cost(key['warehouse'], key['hospital'], key['vehicle'])}
                assert claim['answer'] == expected[claim['question']]()


def test_c2_does_not_change_the_world_it_was_given():
    base = poison_tool('gis_distance_matrix', 0.5)
    stacked = byzantine_agent('L_Agent_2', 0.5, world=base)
    assert base['attack']['liars'] == []
    assert stacked['attack']['names'] == ['C1', 'C2']


def test_c2_bad_arguments_raise():
    with pytest.raises(ValueError):
        byzantine_agent('X_Agent_9', 0.5)
    with pytest.raises(ValueError):
        byzantine_agent('L_Agent_1', 1)
    with pytest.raises(ValueError):
        byzantine_agent('L_Agent_1', 0.5, questions=['Q1'])  # a logistics agent does not answer stock
    with pytest.raises(ValueError):
        byzantine_agent('L_Agent_1', 0.5, where={'city': 'Gitega'})


def test_c2_one_liar_is_outvoted_by_majority_vote():
    world = byzantine_agent('L_Agent_1', 0.3, where={'warehouse': 'W1'})
    report = evaluate(world, lambda s: MajorityVoteDefense(), REQUEST, [0])
    assert report['success_rate'] == 0 and report['corruption_rate'] == 0


def test_c2_one_liar_fools_no_defense_some_of_the_time():
    world = byzantine_agent('L_Agent_1', 0.3, where={'warehouse': 'W1'})
    report = evaluate(world, lambda s: NoDefense(seed=s), REQUEST, range(60))
    assert 0 < report['success_rate'] < 1
    assert report['typical_plan'][0] == 'W1'


def test_clean_world_has_no_effect():
    report = evaluate(no_attack(), lambda s: NoDefense(seed=s), REQUEST, range(20))
    assert report['success_rate'] == 0 and report['corruption_rate'] == 0
    assert report['clean_plan'] == ('W2', 'Van')
