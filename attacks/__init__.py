"""Attacks on the simulator (Attack Dev). One file per attack:

  C0  c0_no_attack.py        no_attack         the clean world
  C1  c1_poison_tool.py      poison_tool        one tool returns wrong values
  C2  c2_byzantine_agent.py  byzantine_agent    one agent lies, its tools stay clean
  C3  c3_combined.py         combined_attack    one tool poisoned AND one agent lies

experiment.py runs requests on an attacked world and measures the result.

Usage:
  from attacks import combined_attack, run_request
  world = combined_attack('L_Agent_1', 0.3, 'gis_distance_matrix', 0.5, tool_where={'warehouse': 'W3'})
  result, channel = run_request(world, MajorityVoteDefense(), ('Malaria Treatment', 50, 'Muyinga Health Centre'))
"""
from attacks.c0_no_attack import no_attack
from attacks.c1_poison_tool import POISON_FIELDS, poison_tool
from attacks.c2_byzantine_agent import agent_questions, byzantine_agent
from attacks.c3_combined import combined_attack
from attacks.experiment import evaluate, run_request
