"""Attack Lab. Run from the Defense-systems folder:  python -m streamlit run attacks/demo_app.py"""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import altair as alt
import pandas as pd
import streamlit as st

from attacks import POISON_FIELDS, agent_questions, byzantine_agent, combined_attack, evaluate, no_attack, poison_tool, run_request
from attacks.experiment import chosen_plan, real_cost, truth_value
from simulator import registry as R
from simulator import truth as T
from simulator.defense import MajorityVoteDefense
from simulator.nodefense import NoDefense
from simulator.participants.hospital import get_camp_registry
from simulator.world_ids import MEDICINES, VEHICLE_TYPES, WAREHOUSE_IDS

# name -> (make_defense(seed), uses the seed)
DEFENSES = {
    'No defense': (lambda s: NoDefense(seed=s), True),
    'Majority vote': (lambda s: MajorityVoteDefense(), False),
}
MAP_FACTORS = [0.3, 0.5, 2.0, 3.0]
MAP_SEEDS = 20
WAREHOUSES = {wid: name for name, wid in WAREHOUSE_IDS.items()}
AGENTS = {a['agent_id']: a for a in R.get_world()['agents']}
RED = 'background-color: #fecaca; color: #7f1d1d'

st.set_page_config(page_title='Attack Lab', layout='wide')


def build_world(config):
    kind, *params = config
    if kind == 'C1':
        tool_id, where, factor = params
        return poison_tool(tool_id, factor, where=dict(where))
    if kind == 'C2':
        agent_id, questions, where, factor = params
        return byzantine_agent(agent_id, factor, where=dict(where), questions=list(questions))
    if kind == 'C3':
        agent_id, questions, agent_where, agent_factor, tool_id, tool_where, tool_factor = params
        return combined_attack(agent_id, agent_factor, tool_id, tool_factor,
                               agent_where=dict(agent_where), agent_questions=list(questions),
                               tool_where=dict(tool_where))
    return no_attack()


@st.cache_data(show_spinner=False)
def measure(config, defense_name, request, n_seeds):
    make, seeded = DEFENSES[defense_name]
    report = evaluate(build_world(config), make, request, range(n_seeds) if seeded else [0])
    if not seeded:  # the result is the same for every seed, so repeat the single run
        report['runs'] = [dict(report['runs'][0], seed=s) for s in range(n_seeds)]
    return report


def plan_text(plan):
    return 'rejected' if plan is None else f'{plan[0]} {WAREHOUSES[plan[0]].split()[0]} · {plan[1]}'


def where_text(where, everything):
    return ', '.join(f'{k}={v}' for k, v in where) or everything


def threat_text(config):
    if config[0] == 'C1':
        _, tool_id, where, factor = config
        return f"C1 · poison `{tool_id}` · {where_text(where, 'all records')} · ×{factor}"
    if config[0] == 'C2':
        _, agent_id, questions, where, factor = config
        return f"C2 · `{agent_id}` lies on {', '.join(questions)} · {where_text(where, 'all keys')} · ×{factor}"
    if config[0] == 'C3':
        _, agent_id, questions, agent_where, agent_factor, tool_id, tool_where, tool_factor = config
        return (f"C3 · `{agent_id}` lies ×{agent_factor} on {', '.join(questions)} "
                f"({where_text(agent_where, 'all keys')}) + poison `{tool_id}` ×{tool_factor} "
                f"({where_text(tool_where, 'all records')})")
    return 'C0 · no attack'


# ---- sidebar: experiment config ---------------------------------------------
with st.sidebar:
    st.header('Scenario')
    camps = get_camp_registry()
    camp_name = st.selectbox('Destination', [c['name'] for c in camps])
    medicine = st.selectbox('Item', MEDICINES)
    quantity = st.number_input('Quantity', 1, 1000, 50, 10)

    st.header('Attack')
    attack = st.radio('Attack', ['C0 · none', 'C1 · tool poisoning', 'C2 · lying agent',
                                  'C3 · combined (tool + agent)'], index=1,
                      label_visibility='collapsed')
    if attack.startswith('C1'):
        tools = sorted(POISON_FIELDS)
        tool_id = st.selectbox('Tool', tools, index=tools.index('gis_distance_matrix'))
        slice_field = 'warehouse' if 'warehouse' in R.TOOL_KEYS[tool_id].values() else 'vehicle'
        options = ['All'] + (list(WAREHOUSES) if slice_field == 'warehouse' else VEHICLE_TYPES)
        target = st.selectbox(f'Target {slice_field}', options, index=1)
        where = () if target == 'All' else ((slice_field, target),)
        factor = st.slider('Factor', 0.1, 3.0, 0.3, 0.1, help='× applied to the value. <1 smaller, >1 bigger.')
        config = ('C1', tool_id, where, factor)
    elif attack.startswith('C2'):
        agent_id = st.selectbox('Agent', list(AGENTS),
                                format_func=lambda a: f"{a} · main tool {AGENTS[a]['primary_tool']}", index=6)
        allowed = agent_questions(agent_id)
        questions = st.multiselect('Questions', allowed, default=allowed,
                                   format_func=lambda q: f"{q} {R.QUESTIONS[q]['name']}")
        target = st.selectbox('Target warehouse', ['All'] + list(WAREHOUSES), index=1)
        where = () if target == 'All' else (('warehouse', target),)
        factor = st.slider('Factor', 0.1, 3.0, 0.3, 0.1, help='The liar reports its reading × factor.')
        config = ('C2', agent_id, tuple(questions or allowed), where, factor)
    elif attack.startswith('C3'):
        st.markdown('**Byzantine agent**')
        agent_id = st.selectbox('Agent', list(AGENTS),
                                format_func=lambda a: f"{a} · main tool {AGENTS[a]['primary_tool']}", index=6)
        allowed = agent_questions(agent_id)
        questions = st.multiselect('Questions', allowed, default=allowed,
                                   format_func=lambda q: f"{q} {R.QUESTIONS[q]['name']}")
        agent_target = st.selectbox('Agent target warehouse', ['All'] + list(WAREHOUSES), index=1,
                                    key='c3_agent_wh')
        agent_where = () if agent_target == 'All' else (('warehouse', agent_target),)
        agent_factor = st.slider('Agent factor', 0.1, 3.0, 0.3, 0.1, key='c3_agent_f',
                                 help='The liar reports its reading × factor.')
        st.markdown('**Tool poisoning**')
        tools = sorted(POISON_FIELDS)
        tool_id = st.selectbox('Tool', tools, index=tools.index('gis_distance_matrix'), key='c3_tool')
        slice_field = 'warehouse' if 'warehouse' in R.TOOL_KEYS[tool_id].values() else 'vehicle'
        options = ['All'] + (list(WAREHOUSES) if slice_field == 'warehouse' else VEHICLE_TYPES)
        tool_target = st.selectbox(f'Tool target {slice_field}', options, index=1, key='c3_tool_wh')
        tool_where = () if tool_target == 'All' else ((slice_field, tool_target),)
        tool_factor = st.slider('Tool factor', 0.1, 3.0, 0.5, 0.1, key='c3_tool_f',
                                help='× applied to the tool value. <1 smaller, >1 bigger.')
        config = ('C3', agent_id, tuple(questions or allowed), agent_where, agent_factor,
                  tool_id, tool_where, tool_factor)
    else:
        config = ('C0',)

    st.header('Run')
    n_seeds = st.slider('Seeds', 10, 200, 100, 10, help='Repetitions. Only "No defense" depends on the seed.')

request = (medicine, quantity, camp_name)
hospital = next(c for c in camps if c['name'] == camp_name)['camp_id']

st.title('Attack Lab')
st.markdown(f'**Scenario:** {quantity} × {medicine} → {camp_name}')
tab_exp, tab_map = st.tabs(['Experiment', 'Attack map'])

# =============================================================================
# Experiment: one attack, every defense
# =============================================================================
def plan_card(result, label):
    """Reported vs real distance, time and cost of the plan the coordinator chose."""
    st.markdown(f'**{label}**')
    plan = chosen_plan(result)
    if plan is None:
        st.warning(f"Rejected: {result['warehouse']['reason']}")
        return
    t = result['transportation']
    w, v = plan
    st.markdown(f'#### {plan_text(plan)}')
    rows = [{'': name, 'Reported': reported, 'Real': real, 'Correct': 'yes' if reported == real else 'NO'}
            for name, reported, real in [
                ('Distance (km)', t['distance_km'], T.truth_distance(w, hospital)),
                ('Time (min)', t['delivery_time_minutes'], T.truth_time_minutes(w, hospital, v)),
                ('Cost', t['transportation_cost'], T.truth_cost(w, hospital, v))]]
    st.dataframe(pd.DataFrame(rows).style.apply(lambda r: [RED if r['Correct'] == 'NO' else ''] * len(r), axis=1),
                 hide_index=True, width='stretch')


with tab_exp:
    reports = {name: measure(config, name, request, n_seeds) for name in DEFENSES}
    clean_plan = next(iter(reports.values()))['clean_plan']
    clean_cost = real_cost(clean_plan, hospital)
    st.markdown(f'**Threat:** {threat_text(config)}')

    # ---- one run, side by side -------------------------------------------------
    st.subheader('One run')
    c1, c2 = st.columns(2)
    defense_name = c1.selectbox('Defense', list(DEFENSES))
    seed = c2.number_input('Seed', 0, 10_000, 0,
                           help='"No defense" trusts a different random agent for each seed. Majority vote ignores it.')
    world = build_world(config)
    result, channel = run_request(world, DEFENSES[defense_name][0](seed), request)
    clean_result = run_request(no_attack(), MajorityVoteDefense(), request)[0]
    attacked_plan = chosen_plan(result)

    left, right = st.columns(2)
    with left:
        plan_card(clean_result, 'Clean world: the correct plan')
    with right:
        plan_card(result, f'Attacked world: {defense_name}')

    if config[0] == 'C0':
        st.info('No attack: both sides give the same plan.')
    elif attacked_plan == clean_plan:
        st.success('Attack FAILED in this run: the coordinator kept the correct plan.')
    elif attacked_plan is None:
        st.error('ATTACK SUCCEEDED in this run: the request was rejected although it could be delivered.')
    else:
        attacked_cost = real_cost(attacked_plan, hospital)
        honest = result['transportation']['transportation_cost'] == attacked_cost
        st.error(f'ATTACK SUCCEEDED in this run: the order goes to **{plan_text(attacked_plan)}** instead of '
                 f'**{plan_text(clean_plan)}**. The NGO really pays {attacked_cost} instead of {clean_cost} '
                 f'(**+{attacked_cost - clean_cost}**). '
                 + ('The plan shows true numbers: the best option was made to look worse (push).' if honest else
                    'The plan shows false numbers: a worse option was made to look cheaper (pull).'))

    # ---- how often, over all runs ----------------------------------------------
    st.subheader(f'How often: {n_seeds} runs')
    table = pd.DataFrame([{
        'Defense': name,
        'Attack success': 100 * r['success_rate'],
        'Decisions corrupted': 100 * r['corruption_rate'],
        'Avg extra real cost': '—' if r['avg_extra_cost'] is None else f"+{r['avg_extra_cost']:.0f}",
        'Typical attacked plan': plan_text(r['typical_plan']),
    } for name, r in reports.items()])
    st.dataframe(table, hide_index=True, width='stretch', column_config={
        'Attack success': st.column_config.ProgressColumn(format='%.0f%%', min_value=0, max_value=100,
                                                          help='Runs where the chosen plan changed'),
        'Decisions corrupted': st.column_config.ProgressColumn(format='%.1f%%', min_value=0, max_value=100,
                                                               help='Decisions that differ from the truth'),
        'Avg extra real cost': st.column_config.TextColumn(
            help='Average, over the runs where the plan changed, of (real cost of the attacked plan - real cost of the clean plan)'),
    })

    for name, r in reports.items():
        fooled = [run for run in r['runs'] if run['fooled']]
        if not fooled:
            st.markdown(f'**{name}:** 0 of {n_seeds} runs fooled, so there is no extra cost.')
            continue
        groups = Counter((run['plan'], run['extra_cost']) for run in fooled)
        priced = [(plan, extra, n) for (plan, extra), n in groups.most_common() if extra is not None]
        st.markdown(f'**{name}:** {len(fooled)} of {n_seeds} runs fooled ({100 * len(fooled) / n_seeds:.0f}% attack success).')
        st.dataframe(pd.DataFrame([{
            'Plan the attack forced': plan_text(plan), 'Runs': n,
            'Real cost': real_cost(plan, hospital), 'Clean cost': clean_cost, 'Extra per run': f'+{extra}',
        } for plan, extra, n in priced]), hide_index=True, width='stretch')
        if priced:
            total = sum(extra * n for _, extra, n in priced)
            count = sum(n for _, _, n in priced)
            terms = ' + '.join(f'{n}×{extra}' for _, extra, n in priced)
            st.markdown(f'Avg extra real cost = ({terms}) ÷ {count} = {total} ÷ {count} = **+{total / count:.0f}**')

    # ---- one run in detail ---------------------------------------------------
    with st.expander(f'Details of the run above ({defense_name}, seed {seed})'):
        st.caption('Options compared: believed cost vs real cost. Lowest believed cost wins.')
        rows = []
        for w in WAREHOUSES:
            for v in VEHICLE_TYPES:
                believed = channel.decisions.get(('Q5', (('hospital', hospital), ('vehicle', v), ('warehouse', w))))
                if believed is not None:
                    rows.append({'Option': f'{w} · {v}', 'Believed cost': believed,
                                 'Real cost': real_cost((w, v), hospital),
                                 'Chosen': '◀ attacked' if (w, v) == attacked_plan else
                                           ('clean' if (w, v) == clean_plan else '')})
        opts = pd.DataFrame(rows)
        if not opts.empty:
            st.dataframe(opts.style.apply(lambda r: [RED if r['Believed cost'] != r['Real cost'] else ''] * len(r),
                                          axis=1), hide_index=True, width='stretch')

        st.caption('Tampered readings (poisoned tool or lying agent).')
        poisoned = world['attack']['poisoned']
        tampered = []
        for claim in channel.claims:
            key = dict(zip(R.QUESTIONS[claim['question']]['key'], claim['key']))
            lied = claim in channel.lied
            for role, reading in zip(('main', 'backup'), claim['readings']):
                hit = any(p['tool_id'] == reading['tool_id'] and all(key.get(k) == x for k, x in p['key'].items())
                          for p in poisoned)
                if hit or lied:
                    tampered.append({'Q': claim['question'], 'Key': ' / '.join(claim['key']),
                                     'Agent': claim['agent_id'], 'Reading': role, 'Tool': reading['tool_id'],
                                     'Value': reading['value'], 'Truth': truth_value(claim['question'], key),
                                     'Cause': 'lying agent' if lied else 'poisoned tool'})
        if tampered:
            st.dataframe(pd.DataFrame(tampered), hide_index=True, width='stretch', height=300)
        else:
            st.write('None.')

# =============================================================================
# Attack map: every target x factor, for the current scenario
# =============================================================================
def map_cells():
    for tool in sorted(POISON_FIELDS):
        field = 'warehouse' if 'warehouse' in R.TOOL_KEYS[tool].values() else 'vehicle'
        for t in (list(WAREHOUSES) if field == 'warehouse' else VEHICLE_TYPES):
            for f in MAP_FACTORS:
                yield 'C1 · tool poisoning', f'{tool} · {t}', ('C1', tool, ((field, t),), f)
    for agent_id, agent in AGENTS.items():
        for w in WAREHOUSES:
            for f in MAP_FACTORS:
                yield ('C2 · lying agent', f"{agent_id} ({agent['primary_tool']}) · {w}",
                       ('C2', agent_id, tuple(agent_questions(agent_id)), (('warehouse', w),), f))


with tab_map:
    st.markdown('Every target and factor for **this scenario**, against every defense. '
                'Each cell is the % of runs where the attack changed the plan. '
                f'Red = the attack works, grey = it fails. ({MAP_SEEDS} seeds per cell.)')
    cells = list(map_cells())
    if st.session_state.get('map_for') != request:
        if st.button(f'Build the map ({len(cells)} combinations × {len(DEFENSES)} defenses, about 1 minute the first time)'):
            st.session_state['map_for'] = request
            st.rerun()
    else:
        bar = st.progress(0.0, text='Running every combination...')
        rows = []
        for i, (kind, label, cfg) in enumerate(cells):
            for name in DEFENSES:
                rows.append({'Attack': kind, 'Target': label, 'Factor': f'×{cfg[-1]}', 'Defense': name,
                             'Success': round(100 * measure(cfg, name, request, MAP_SEEDS)['success_rate'])})
            bar.progress((i + 1) / len(cells), text='Running every combination...')
        bar.empty()
        grid = pd.DataFrame(rows)

        summary = grid.assign(Works=grid['Success'] > 0).groupby(['Attack', 'Defense'])['Works'].agg(['sum', 'count'])
        cols = st.columns(len(summary))
        for col, ((kind, name), s) in zip(cols, summary.iterrows()):
            col.metric(f'{kind.split(" · ")[0]} vs {name}', f"{int(s['sum'])}/{int(s['count'])}",
                       help='Combinations where the attack changed the plan at least once')

        for kind in grid['Attack'].unique():
            part = grid[grid['Attack'] == kind]
            order = list(dict.fromkeys(part['Target']))
            base = alt.Chart().encode(x=alt.X('Factor:O', title='Factor', sort=[f'×{f}' for f in MAP_FACTORS]),
                                      y=alt.Y('Target:N', sort=order, title=None, axis=alt.Axis(labelLimit=400)))
            rect = base.mark_rect(stroke='#0e1117', strokeWidth=1).encode(
                color=alt.Color('Success:Q', scale=alt.Scale(domain=[0, 100], range=['#374151', '#dc2626']),
                                title='Attack success %'),
                tooltip=['Defense', 'Target', 'Factor', alt.Tooltip('Success:Q', title='Success %')])
            text = base.mark_text(fontSize=11, color='white').encode(text=alt.Text('Success:Q', format='.0f'))
            st.subheader(kind)
            st.altair_chart(alt.layer(rect, text, data=part).properties(width=260, height=20 * len(order))
                            .facet(column=alt.Column('Defense:N', title=None, sort=list(DEFENSES))))
