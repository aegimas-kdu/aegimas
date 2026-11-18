"""C2: Byzantine agent. One agent lies; the tools stay clean.

The liar reads its tools honestly, then reports its main reading x factor in BOTH readings, so its two
readings still agree and the lie looks consistent. The lie is applied after the agent reads and before
the defense decides, so run attacked worlds with attacks.experiment.run_request.
"""
from attacks.base import KEY_FIELDS, fresh_world
from simulator import registry


def agent_questions(agent_id, world=None):
    world = world or registry.get_world()
    agent = next((a for a in world['agents'] if a['agent_id'] == agent_id), None)
    if agent is None:
        raise ValueError(f'Unknown agent {agent_id}')
    return [q for q, spec in registry.QUESTIONS.items() if spec['domain'] == agent['domain']]


def byzantine_agent(agent_id, factor, where=None, questions=None, world=None):
    """Make `agent_id` lie by `factor` on the claims that match `where` and `questions`.

    where:     mission-key filter, e.g. {'warehouse': 'W1'}; None lies on every key.
    questions: e.g. ['Q5']; None lies on every question of the agent's domain.
    world:     an already attacked world, to stack attacks (C3); defaults to the clean world.
    """
    allowed = agent_questions(agent_id, world)
    if factor <= 0 or factor == 1:
        raise ValueError('factor must be positive and different from 1')
    questions = list(questions or allowed)
    for q in questions:
        if q not in allowed:
            raise ValueError(f'{agent_id} does not answer {q}; it answers {allowed}')
    where = dict(where or {})
    for key_field in where:
        if key_field not in KEY_FIELDS:
            raise ValueError(f'Unknown key field "{key_field}"; use one of {KEY_FIELDS}')

    world = fresh_world(world)
    world['attack']['liars'].append({'agent_id': agent_id, 'factor': factor, 'where': where,
                                     'questions': sorted(questions)})
    world['attack']['names'].append('C2')
    return world


def lie(world, claim):
    """Apply every matching lie to one claim, in place. Returns True if the claim was changed."""
    key = dict(zip(registry.QUESTIONS[claim['question']]['key'], claim['key']))
    changed = False
    for liar in world.get('attack', {}).get('liars', []):
        if liar['agent_id'] != claim['agent_id'] or claim['question'] not in liar['questions']:
            continue
        if any(key.get(k) != v for k, v in liar['where'].items()):
            continue
        value = max(1, round(claim['readings'][0]['value'] * liar['factor']))
        for reading in claim['readings']:
            reading['value'] = value
        claim['answer'] = value
        changed = True
    return changed
