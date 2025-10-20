# AI Agent Quickstart Guide

**Welcome, AI Agent!** This guide will help you navigate and complete your assigned phase efficiently.

---

## 🎯 Your Mission

You are part of a phased development workflow. Your job is to:
1. Identify which phase you're responsible for
2. Gather minimal necessary context
3. Complete your phase according to the plan
4. Document your work
5. Update the status for the next agent

---

## 📁 File Structure

```
project-root/
├── docs/
│   └── agent/
│       ├── PHASE_SUMMARY_TEMPLATE.md      ← Shared template
│       └── project-initiation/            ← Your feature folder
│           ├── QUICKSTART.md              ← You are here
│           ├── PROJECT_PLAN.md            ← Detailed plan for all phases
│           ├── STATUS.md                  ← Current phase tracker
│           └── summaries/                 ← Completed phase summaries
│               ├── PHASE_01_SUMMARY.md
│               ├── PHASE_02_SUMMARY.md
│               └── ...
```

**Your working directory**: Project root
**All paths below are absolute from project root**

---

## 🔄 Your Workflow

### Step 1: Find Your Phase

Read `docs/agent/project-initiation/STATUS.md` to identify:
- Which phase is current (marked as 🔵 CURRENT)
- Your phase number and name

### Step 2: Get Context

Read **ONLY** the 2 most recent phase summaries:
- If you're on Phase 5, read `PHASE_04_SUMMARY.md` and `PHASE_03_SUMMARY.md`
- If you're on Phase 1 or 2, read what's available (or nothing if Phase 1)

**Location**: `docs/agent/project-initiation/summaries/`

### Step 3: Read Your Phase Plan

Open `docs/agent/project-initiation/PROJECT_PLAN.md` and read **ONLY** your phase section:
- Scroll to your phase number
- Read the objective, deliverables, and completion criteria
- Note any dependencies or integration points

**Do NOT read the entire file** - it will waste your context budget.

### Step 4: Complete Your Phase

Follow the plan for your phase. Work only on your assigned phase - do not:
- Start work on future phases
- Modify previous phases (unless explicitly required by your plan)
- Read unrelated code or documentation

### Step 5: Document Your Work

Create your phase summary:
- **Template**: `docs/agent/PHASE_SUMMARY_TEMPLATE.md`
- **Output location**: `docs/agent/project-initiation/summaries/PHASE_XX_SUMMARY.md`
- **Length**: Keep it concise (~400-500 lines max)

Include:
- What you built
- Files created/modified
- Completion criteria status
- Any challenges or deviations
- Notes for future phases

### Step 6: Update Status

Edit `docs/agent/project-initiation/STATUS.md`:
1. Mark your phase as ✅ Complete
2. Update "Current Phase" to next phase number
3. Update "Phase Name" to next phase name
4. Update "Last Updated" to today's date (YYYY-MM-DD format)

### Step 7: Stop

Your work is complete! The next agent will handle the next phase.

---

## ⚙️ Environment Setup

**This project uses Python 3.11+ with uv for environment management.**

### First-Time Setup

If this is your first time working on ytmpd:

```bash
# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create virtual environment with uv
uv venv

# Activate the virtual environment
source .venv/bin/activate

# Install dependencies
uv pip install -e ".[dev]"
```

### Before Each Session

**IMPORTANT**: Always activate the virtual environment before running any commands:

```bash
source .venv/bin/activate
```

### Common Commands

```bash
# Run tests
pytest

# Run tests with coverage
pytest --cov=ytmpd tests/

# Run type checking
mypy ytmpd/

# Run linting
ruff check ytmpd/

# Format code
ruff format ytmpd/

# Install new dependency
uv pip install <package-name>

# Run the daemon (once implemented)
python -m ytmpd.daemon

# Run the client (once implemented)
./ytmpctl status
```

### Dependencies

The project uses:
- **ytmusicapi**: YouTube Music API integration
- **pytest**: Testing framework
- **mypy**: Type checking
- **ruff**: Linting and formatting

---

## 💡 Context Budget

You have approximately **120k tokens** total (input + output + thinking).

**Be strategic**:
- ✅ Read only what you need
- ✅ Follow the workflow above exactly
- ✅ Keep summaries concise
- ❌ Don't read entire files when you need one function
- ❌ Don't read all phase plans when you need one phase
- ❌ Don't explore unrelated code

Each phase is designed to fit within one agent session. If you run out of context:
- Note this in your summary
- Document what's incomplete
- Suggest splitting the phase

---

## 🚨 Important Notes

### Phase Boundaries

**Respect phase boundaries**. Do not:
- Work on multiple phases at once
- Skip phases
- Go back and refactor previous phases (unless your phase plan says to)

### Testing

If your phase includes tests:
- Write tests as specified in the plan
- Run tests to verify they pass
- Include test output in your summary

### Dependencies

If your phase depends on previous phases:
- Check that those phases are marked complete in STATUS.md
- Read their summaries to understand what was built
- Note any blockers in your summary if dependencies are incomplete

### Blockers

If you encounter blockers:
- Document them clearly in your summary
- Mark affected completion criteria as incomplete
- Suggest solutions or next steps
- Do NOT mark your phase as complete if critical items are blocked

---

## 📋 Quick Checklist

Before you begin:
- [ ] Read `docs/agent/project-initiation/STATUS.md` to identify your phase
- [ ] Read the 2 most recent phase summaries from `docs/agent/project-initiation/summaries/`
- [ ] Read your phase section in `docs/agent/project-initiation/PROJECT_PLAN.md`
- [ ] Understand your deliverables and completion criteria

During your work:
- [ ] Stay within your phase boundaries
- [ ] Activate environment before running commands (`source .venv/bin/activate`)
- [ ] Write tests if required
- [ ] Keep context usage in mind

After completion:
- [ ] Create phase summary using the template
- [ ] Verify all completion criteria are met (or document why not)
- [ ] Update `docs/agent/project-initiation/STATUS.md`
- [ ] Do NOT start the next phase

---

## 🎬 Ready to Start?

1. Read `docs/agent/project-initiation/STATUS.md`
2. Follow the workflow above
3. Complete your phase
4. Document and update status

**Good luck, Agent!**

---

*This quickstart is designed for AI agents working in a phased development workflow. For human developers, see the standard project README.*
