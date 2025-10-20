# AI Agent Quickstart Guide

**Welcome, AI Agent!** This guide will help you navigate and complete your assigned phase efficiently.

---

## 📍 Location & Paths

**CRITICAL: Verify your location before starting!**

```bash
pwd  # Should output: /home/tunc/Sync/Programs/ytmpd
```

### Project Paths

- **Project Root**: `/home/tunc/Sync/Programs/ytmpd`
- **Feature Docs**: `/home/tunc/Sync/Programs/ytmpd/docs/agent/i3blocks-status`

### Path Usage Rules

1. **Stay in project root** - Do NOT `cd` to other directories
2. **All paths are relative to project root** - When you see `docs/agent/...`, it means `/home/tunc/Sync/Programs/ytmpd/docs/agent/...`
3. **If confused about location** - Run `pwd` to verify you're in `/home/tunc/Sync/Programs/ytmpd`
4. **Use relative paths in your work** - Reference files as `docs/agent/...` not absolute paths

**Example Path Reference:**
```
Relative path: docs/agent/i3blocks-status/STATUS.md
Absolute path: /home/tunc/Sync/Programs/ytmpd/docs/agent/i3blocks-status/STATUS.md
                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                Where pwd should output
```

---

## 🌿 Git Workflow - Feature Branch

**IMPORTANT: All work for this feature happens on the `feature/i3blocks-status` branch.**

### Before You Start

Verify you're on the correct branch:

```bash
git branch  # Should show: * feature/i3blocks-status
```

If the branch doesn't exist yet, create it:

```bash
git checkout -b feature/i3blocks-status
```

### After Each Phase Completion

**Do NOT commit automatically!** Follow this process:

1. **Complete your phase** according to PROJECT_PLAN.md
2. **Create your phase summary** in `docs/agent/i3blocks-status/summaries/PHASE_XX_SUMMARY.md`
3. **Update STATUS.md** to mark your phase complete and set next phase as current
4. **Stage your changes** but DO NOT commit yet:
   ```bash
   git add -A
   git status  # Show what will be committed
   ```
5. **Wait for user confirmation** before committing
6. **After user confirms**, create the commit with a clean, professional message

### Commit Message Guidelines

- Write clear, descriptive commit messages
- Focus on WHAT was done and WHY
- Use imperative mood ("Add", "Fix", "Implement", not "Added", "Fixed")
- **NEVER mention AI, Claude, or agent in commit messages**
- Keep first line under 72 characters
- Add details in body if needed

**Good Examples:**
```
Implement MPD status display with YouTube/local track detection

Add progress bar with configurable styles for different track types

Enhance i3blocks integration with click handlers and idle mode
```

**Bad Examples:**
```
Phase 1 complete (AI agent work)  ❌ - mentions AI
Claude implemented status display  ❌ - mentions Claude
WIP                                ❌ - not descriptive
```

### Commit Template

Use this structure:

```bash
git commit -m "Brief summary of changes

- Detail 1
- Detail 2
- Detail 3

Resolves phase X of i3blocks-status feature."
```

---

## 🎯 Your Mission

You are part of a phased development workflow. Your job is to:
1. **Verify your location** (run `pwd` → should be `/home/tunc/Sync/Programs/ytmpd`)
2. **Verify git branch** (run `git branch` → should be on `feature/i3blocks-status`)
3. Identify which phase you're responsible for
4. Gather minimal necessary context
5. Complete your phase according to the plan
6. Document your work
7. Update the status for the next agent
8. **Stage changes and wait for user confirmation before committing**

---

## 📁 File Structure

```
project-root/  ← /home/tunc/Sync/Programs/ytmpd (where pwd outputs)
├── docs/
│   └── agent/
│       ├── PHASE_SUMMARY_TEMPLATE.md      ← Shared template
│       └── i3blocks-status/               ← Your feature folder
│           ├── QUICKSTART.md              ← You are here
│           ├── PROJECT_PLAN.md            ← Detailed plan for all phases
│           ├── STATUS.md                  ← Current phase tracker
│           └── summaries/                 ← Completed phase summaries
│               ├── PHASE_01_SUMMARY.md
│               ├── PHASE_02_SUMMARY.md
│               └── ...
```

**All paths in this guide are relative to `/home/tunc/Sync/Programs/ytmpd`**

---

## 🔄 Your Workflow

### Step 1: Find Your Phase

Read `docs/agent/i3blocks-status/STATUS.md` to identify:
- Which phase is current (marked as 🔵 CURRENT)
- Your phase number and name

### Step 2: Get Context

Read **ONLY** the 2 most recent phase summaries:
- If you're on Phase 5, read `PHASE_04_SUMMARY.md` and `PHASE_03_SUMMARY.md`
- If you're on Phase 1 or 2, read what's available (or nothing if Phase 1)

**Location**: `docs/agent/i3blocks-status/summaries/`

### Step 3: Read Your Phase Plan

Open `docs/agent/i3blocks-status/PROJECT_PLAN.md` and read **ONLY** your phase section:
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
- **Output location**: `docs/agent/i3blocks-status/summaries/PHASE_XX_SUMMARY.md`
- **Length**: Keep it concise (~400-500 lines max)

Include:
- What you built
- Files created/modified
- Completion criteria status
- Any challenges or deviations
- Notes for future phases

### Step 6: Update Status

Edit `docs/agent/i3blocks-status/STATUS.md`:
1. Mark your phase as ✅ Complete
2. Update "Current Phase" to next phase number
3. Update "Phase Name" to next phase name
4. Update "Last Updated" to today's date (YYYY-MM-DD format)
5. Update progress bar

### Step 7: Stage and Wait for Confirmation

```bash
git add -A
git status
```

**STOP HERE!** Inform the user that:
- Phase is complete
- Changes are staged
- Ready for user confirmation to commit

### Step 8: Commit (After User Approval)

Once user confirms, commit with a clean message:

```bash
git commit -m "Your clear, professional commit message"
```

---

## ⚙️ Environment Setup

### Python Environment (uv)

This project uses **uv** for Python package management.

#### First-Time Setup

```bash
# Ensure uv is installed
uv --version

# Activate virtual environment (created by uv)
source .venv/bin/activate

# Install dependencies (if not already installed)
uv pip install -e ".[dev]"
```

#### Before Each Session

```bash
# Always activate the virtual environment before working
source .venv/bin/activate

# Verify you're in the right environment
which python  # Should show: /home/tunc/Sync/Programs/ytmpd/.venv/bin/python
```

#### Common Commands

```bash
# Run tests
pytest

# Run tests for specific file
pytest tests/test_config.py

# Run tests with verbose output
pytest -v

# Check code formatting
black --check .

# Format code
black .

# Type checking
mypy ytmpd/

# Run the ytmpd daemon
python -m ytmpd

# Use ytmpctl commands
bin/ytmpctl status
bin/ytmpctl search "query"

# Test ytmpd-status locally
bin/ytmpd-status
```

#### Dependencies

Main dependencies:
- `python-mpd2` - MPD client library (to be added in Phase 1)
- `click` - CLI framework (already used in ytmpctl)
- `pytest` - Testing framework

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

### Committing Rules

- **NEVER commit without user approval**
- **NEVER mention AI/Claude/agent in commits**
- Always stage changes first (`git add -A`)
- Show user what will be committed (`git status`)
- Wait for explicit confirmation
- Use clear, professional commit messages

---

## 📋 Quick Checklist

Before you begin:
- [ ] **FIRST: Run `pwd` and verify you're in `/home/tunc/Sync/Programs/ytmpd`**
- [ ] **SECOND: Run `git branch` and verify you're on `feature/i3blocks-status`**
- [ ] Activate Python environment: `source .venv/bin/activate`
- [ ] Read `docs/agent/i3blocks-status/STATUS.md` to identify your phase
- [ ] Read the 2 most recent phase summaries from `docs/agent/i3blocks-status/summaries/`
- [ ] Read your phase section in `docs/agent/i3blocks-status/PROJECT_PLAN.md`
- [ ] Understand your deliverables and completion criteria

During your work:
- [ ] Stay within your phase boundaries
- [ ] Write tests if required
- [ ] Keep context usage in mind

After completion:
- [ ] Create phase summary using the template
- [ ] Verify all completion criteria are met (or document why not)
- [ ] Update `docs/agent/i3blocks-status/STATUS.md`
- [ ] Stage changes: `git add -A`
- [ ] Show status: `git status`
- [ ] **WAIT for user confirmation**
- [ ] Commit with clean message (no AI references)
- [ ] Do NOT start the next phase

---

## 🎬 Ready to Start?

1. Verify location: `pwd` → `/home/tunc/Sync/Programs/ytmpd`
2. Verify branch: `git branch` → `* feature/i3blocks-status`
3. Activate environment: `source .venv/bin/activate`
4. Read `docs/agent/i3blocks-status/STATUS.md`
5. Follow the workflow above
6. Complete your phase
7. Document and update status
8. Stage and wait for user approval to commit

**Good luck, Agent!**

---

*This quickstart is designed for AI agents working in a phased development workflow. For human developers, see the standard project README.*
