from attacks import no_attack
from simulator import registry as R


def test_c0_is_a_clean_copy():
    world = no_attack()
    assert world['tools'] == R.get_world()['tools']
    assert world['tools'] is not R.get_world()['tools']
    assert world['attack'] == {'names': ['C0'], 'poisoned': [], 'liars': []}
