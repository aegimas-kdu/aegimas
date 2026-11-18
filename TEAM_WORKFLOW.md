# Team Workflow — How Each Member Pushes Their Work

**Repository:** https://github.com/aegimas-kdu/Defense-systems.git  
**Organization:** aegimas-kdu

---

## Team Roles and What Each Person Pushes

| Role | Person | Folder / Files | What they push |
|---|---|---|---|
| **Simulator Dev** | (simulator team) | `simulator/` | The base simulator: agents, tools, coordinator, world data |
| **Attack Dev** | Crispin | `attacks/` | C0, C1, C2, C3 attacks, experiment runner, demo app, tests |
| **Defense Dev** | Precieuse | `defense/` | D1, D1b, D4-Base, D4+ defenses, trust memory, blame, cascade |
| **Experimenter** | (experimenter) | `attacks/results/`, `results/` | Experiment results and analysis |
| **Trust Ledger Dev** | (trust ledger team) | `defense/fake_ledger.py`, `defense/trust.py` | Trust scoring, ledger, quarantine logic |
| **Reporter** | (reporter) | `docs/` or root | Paper text, figures, final report |

---

## Step-by-Step: How to Push Your Work

### 1. First Time Setup (everyone does this once)

**A. Install Git** (if not already installed)
- Download from https://git-scm.com/downloads

**B. Set your identity** (use YOUR name and YOUR email so commits show as yours)
```
git config --global user.name "Your Full Name"
git config --global user.email "your.email@example.com"
```

**C. Clone the repository**
```
git clone https://github.com/aegimas-kdu/Defense-systems.git
cd Defense-systems
```

**D. Check that you have push access**
- The organization owner (Crispin) must add you as a collaborator
- Go to: GitHub repo > Settings > Collaborators > Add people
- Each team member needs at least "Write" access

---

### 2. Before You Start Working (every time)

Always pull the latest changes first:
```
git pull origin main
```

This avoids conflicts with other people's work.

---

### 3. Do Your Work

Work on YOUR files only. Each role has their own folder:
- Simulator Dev: only touch `simulator/`
- Attack Dev: only touch `attacks/`
- Defense Dev: only touch `defense/`
- Experimenter: only touch result files
- Reporter: only touch `docs/` or report files

---

### 4. Push Your Work

After you finish:

```
git add <your files>
git commit -m "Your descriptive commit message"
git push origin main
```

**Examples for each role:**

**Simulator Dev:**
```
git add simulator/
git commit -m "Add base simulator with 9 agents and 9 tools"
git push origin main
```

**Attack Dev (Crispin):**
```
git add attacks/
git commit -m "Add C3 coordinated attack with experiments and tests"
git push origin main
```

**Defense Dev (Precieuse):**
```
git add defense/
git commit -m "Add D4-Base and D4+ trust-ledger defenses"
git push origin main
```

**Experimenter:**
```
git add attacks/results/ results/
git commit -m "Add experiment results for C3 attack configurations"
git push origin main
```

**Trust Ledger Dev:**
```
git add defense/trust.py defense/fake_ledger.py
git commit -m "Add trust memory and ledger with quarantine logic"
git push origin main
```

**Reporter:**
```
git add docs/
git commit -m "Add final report with experimental analysis"
git push origin main
```

---

## Push Order (Recommended)

To make the git history show that everyone contributed, push in this order:

1. **Simulator Dev** pushes first — the base system everything depends on
2. **Attack Dev (Crispin)** pushes second — the attacks that work on the simulator
3. **Defense Dev (Precieuse)** pushes third — the defenses
4. **Trust Ledger Dev** pushes fourth — the trust scoring layer
5. **Experimenter** pushes fifth — runs experiments and saves results
6. **Reporter** pushes last — writes up the findings

Each person pulls before pushing:
```
git pull origin main
git push origin main
```

---

## How to Add Collaborators (Crispin does this)

Since you own the organization (aegimas-kdu):

1. Go to https://github.com/aegimas-kdu/Defense-systems
2. Click **Settings** (top menu)
3. Click **Collaborators** (left sidebar) or **Manage access**
4. Click **Add people**
5. Type each teammate's GitHub username or email
6. Set their role to **Write** (so they can push)
7. They will get an email invitation — they must accept it

If the repo is **private**, only invited collaborators can see and push.  
If it is **public**, anyone can see it but only collaborators can push.

---

## If Someone Doesn't Have GitHub

They can still contribute:
1. They do their work locally
2. They send you their files (zip, email, USB)
3. You commit on their behalf using:
   ```
   git add <their files>
   git commit --author="Their Name <their.email@example.com>" -m "Their commit message"
   git push origin main
   ```
   This makes the commit show as THEIR work in the git history.

---

## Checking Who Contributed (on GitHub)

After everyone pushes, go to the repository on GitHub:
- **Contributors tab**: shows each person's name and how many commits they made
- **Commits tab**: shows the timeline of who pushed what and when
- **Insights > Contributors**: shows a graph of contributions over time

---

## Troubleshooting

**"Permission denied" when pushing:**
- You need to be added as a collaborator (see above)
- Or you need to authenticate: run `git push` and enter your GitHub username + personal access token (not your password)
- To create a token: GitHub > Settings > Developer settings > Personal access tokens > Generate new token

**"Rejected — non-fast-forward" when pushing:**
- Someone else pushed before you. Run:
  ```
  git pull origin main
  ```
  Then push again.

**Merge conflicts:**
- This happens when two people edited the same file. Git will mark the conflicts.
- Open the file, look for `<<<<<<< HEAD` markers, choose which version to keep
- Then: `git add <file>`, `git commit`, `git push`
- To avoid this: each person works on their own folder only.

**VS Code Git integration:**
- Open VS Code in the Defense-systems folder
- The Source Control panel (left sidebar, branch icon) shows all changes
- Click + to stage files, type a message, click the checkmark to commit
- Click the sync/push button (bottom status bar) to push
