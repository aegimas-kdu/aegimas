"""C0: no attack. The clean baseline every other attack is compared against."""
from attacks.base import fresh_world


def no_attack(world=None):
    world = fresh_world(world)
    world['attack']['names'].append('C0')
    return world
