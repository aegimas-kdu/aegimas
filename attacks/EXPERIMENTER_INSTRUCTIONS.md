# Experimenter Instructions — C3 Attack Experiments

**Role:** Experimenter  
**What you do:** Run the attack experiments, analyze results, and report findings.  
**You do NOT need to modify any attack code.** Everything is ready to run.

---

## Step 1: Setup

1. Clone the repository (or pull the latest if you already have it):
   ```
   git clone https://github.com/aegimas-kdu/Defense-systems.git
   cd Defense-systems
   ```

2. Install Python dependencies:
   ```
   pip install streamlit altair pandas pytest
   ```

3. Verify everything works:
   ```
   python -m pytest attacks/tests/ -v
   ```
   You should see **33 tests passed**.

---

## Step 2: Understand the Attacks

Read `attacks/ATTACKS_README.md` for the full picture. Quick summary:

| Attack | File | What it does |
|---|---|---|
| C0 | c0_no_attack.py | Clean baseline (no attack) |
| C1 | c1_poison_tool.py | One tool returns wrong values |
| C2 | c2_byzantine_agent.py | One agent lies |
| C3 | c3_combined.py | Tool poisoned AND agent lies (the hardest) |

---

## Step 3: Run the Pre-Built Experiments

The experiment script runs 6 C3 configurations + 3 baselines automatically:

```
python -m attacks.run_c3_experiments
```

Results are saved to `attacks/results/c3_experiments.txt`.

---

## Step 4: Explore Interactively with the Demo App

```
python -m streamlit run attacks/demo_app.py
```

This opens a browser UI where you can:
- Select any attack type (C0, C1, C2, C3)
- Adjust parameters (which agent lies, which tool is poisoned, factors, target warehouses)
- See single-run details and multi-seed statistics
- Compare "No defense" vs "Majority vote"

### Suggested experiments to try in the demo:

**C3 experiments (combined attack):**
1. Set attack to "C3 - combined (tool + agent)"
2. Try these combinations:
   - L_Agent_1 lies x0.3 on W1 + gis_distance_matrix poisoned x0.5 on W1 (same target)
   - L_Agent_1 lies x0.3 on W1 + gis_distance_matrix poisoned x0.5 on W3 (split targets — most effective)
   - T_Agent_1 lies x0.3 (all) + fleet_specs_catalog poisoned x0.5 on Van (transport domain)
   - Vary the factors: try x0.1, x0.5, x2.0, x3.0

**Compare C3 vs C1 vs C2 alone:**
1. Run C1 alone: poison gis_distance_matrix x0.5 on W1
2. Run C2 alone: L_Agent_1 lies x0.3 on W1
3. Run C3: both together on W1
4. Compare the success rates — C3 should be worse (for the defense) than either alone

---

## Step 5: Write Your Own Experiment (Optional)

If you want to test specific configurations, create a Python script:

```python
from attacks import combined_attack, evaluate
from simulator.defense import MajorityVoteDefense
from simulator.nodefense import NoDefense

# Define your attack
world = combined_attack(
    agent_id='L_Agent_1', agent_factor=0.3,
    tool_id='gis_distance_matrix', tool_factor=0.5,
    agent_where={'warehouse': 'W1'},
    tool_where={'warehouse': 'W3'},
)

# Test against No Defense
request = ('Malaria Treatment', 50, 'Muyinga Health Centre')
report = evaluate(world, lambda s: NoDefense(seed=s), request, range(100))
print(f"No defense - Attack success: {report['success_rate']:.1%}")
print(f"No defense - Corruption rate: {report['corruption_rate']:.1%}")

# Test against Majority Vote
report = evaluate(world, lambda s: MajorityVoteDefense(), request, [0])
print(f"Majority vote - Attack success: {report['success_rate']:.1%}")
```

---

## Step 6: Save and Push Your Results

After running experiments, save your results and push:

```
git add attacks/results/
git commit -m "Add experiment results for C3 attack configurations"
git push origin main
```

---

## What to Report

For the research paper, the key metrics are:

1. **Attack success rate** — % of runs where the attack changed the delivery plan
2. **Decision corruption rate** — % of individual decisions that differ from truth
3. **Average extra cost** — how much more the NGO pays when the attack works
4. **Which configurations are most dangerous** — split targets vs same target, factor sensitivity
5. **C3 vs C1 vs C2 comparison** — does combining attacks make them stronger?

---

## Troubleshooting

- **ModuleNotFoundError**: Make sure you run from the `Defense-systems/` root folder
- **Tests fail**: Run `python -m pytest attacks/tests/ -v` and share the output
- **Streamlit not found**: Run `pip install streamlit`
- **Questions**: Read `attacks/ATTACKS_README.md` for the full technical documentation
