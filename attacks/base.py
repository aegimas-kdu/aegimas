"""Shared helpers for every attack.

Every attack returns a NEW world (a deep copy of registry.get_world()); the cached clean world is
never changed. Run it with attacks.experiment.run_request, which also applies the agent-level
attacks (C2). Each attacked world carries world['attack'], the attacker's own log of what was
changed, for the evaluator only: the agents, the coordinator and the defense must never read it.
"""
import copy

from simulator import registry

KEY_FIELDS = ('warehouse', 'hospital', 'vehicle', 'medicine')


def fresh_world(world=None):
    world = copy.deepcopy(world if world is not None else registry.get_world())
    world.setdefault('attack', {'names': [], 'poisoned': [], 'liars': []})
    return world


def record_key(tool_id, record):
    # The record's identity in mission-key names, e.g. {'warehouse': 'W3', 'hospital': 'C1', 'vehicle': 'Van'}.
    return {key_field: record[record_field] for record_field, key_field in registry.TOOL_KEYS[tool_id].items()}
