"""C3: coordinated byzantine + tool-poisoning attack.

The attacker poisons one tool AND turns one agent into a liar at the same time.
This is the hardest scenario: the poisoned tool corrupts readings of every agent that
uses it, while the liar independently fabricates values, so the defense faces two
different sources of wrong information.

The attack is built by stacking C1 and C2 on the same world.
"""
from attacks.c1_poison_tool import poison_tool
from attacks.c2_byzantine_agent import byzantine_agent


def combined_attack(agent_id, agent_factor, tool_id, tool_factor,
                    agent_where=None, agent_questions=None,
                    tool_where=None, tool_fields=None, world=None):
    """Poison one tool AND make one agent lie on the same world.

    agent_id:       the agent that lies (e.g. 'L_Agent_1').
    agent_factor:   the liar reports its reading x agent_factor.
    tool_id:        the tool that returns wrong values (e.g. 'gis_distance_matrix').
    tool_factor:    the tool's raw fields are multiplied by tool_factor.
    agent_where:    mission-key filter for the liar, e.g. {'warehouse': 'W1'}.
    agent_questions: which questions the liar lies on; None = all in its domain.
    tool_where:     mission-key filter for the poison, e.g. {'warehouse': 'W3'}.
    tool_fields:    which raw fields to poison; None = the defaults for tool_id.
    world:          an already attacked world to stack on; defaults to the clean world.
    """
    world = poison_tool(tool_id, tool_factor, where=tool_where, fields=tool_fields, world=world)
    world = byzantine_agent(agent_id, agent_factor, where=agent_where,
                            questions=agent_questions, world=world)
    return world
