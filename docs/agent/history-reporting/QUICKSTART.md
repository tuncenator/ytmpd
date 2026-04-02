# AI Agent Quickstart Guide

**Welcome, AI Agent!** This guide will help you navigate and complete your assigned phase efficiently.

---

## Location & Paths

**CRITICAL: Verify your location before starting!**

```bash
pwd  # Should output: /home/tunc/Sync/Programs/ytmpd
```

### Project Paths

- **Project Root**: `/home/tunc/Sync/Programs/ytmpd`
- **Feature Docs**: `/home/tunc/Sync/Programs/ytmpd/docs/agent/history-reporting`

### Path Usage Rules

1. **Stay in project root** - Do NOT `cd` to other directories
2. **All paths are relative to project root** - When you see `docs/agent/...`, it means `/home/tunc/Sync/Programs/ytmpd/docs/agent/...`
3. **If confused about location** - Run `pwd` to verify you're in `/home/tunc/Sync/Programs/ytmpd`
4. **Use relative paths in your work** - Reference files as `docs/agent/...` not absolute paths

**Example Path Reference:**
```
Relative path: docs/agent/history-reporting/STATUS.md
Absolute path: /home/tunc/Sync/Programs/ytmpd/docs/agent/history-reporting/STATUS.md
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
               Where pwd should output
```

---

## Your Mission

You are part of a phased development workflow. Your job is to:
1. **Verify your location** (run `pwd` -- should be `/home/tunc/Sync/Programs/ytmpd`)
2. Identify which phase you're responsible for
3. Gather minimal necessary context
4. Complete your phase according to the plan
5. Document your work
6. Update the status for the next agent

---

## File Structure

```
project-root/  <-- /home/tunc/Sync/Programs/ytmpd (where pwd outputs)
+-- docs/
|   +-- agent/
|       +-- PHASE_SUMMARY_TEMPLATE.md      <-- Shared template
|       +-- history-reporting/             <-- Your feature folder
|           +-- QUICKSTART.md              <-- You are here
|           +-- PROJECT_PLAN.md            <-- Detailed plan for all phases
|           +-- STATUS.md                  <-- Current phase tracker
|           +-- CODEBASE_CONTEXT.md        <-- Cumulative codebase knowledge
|           +-- summaries/                 <-- Completed phase summaries
|               +-- PHASE_01_SUMMARY.md
|               +-- PHASE_02_SUMMARY.md
|               +-- ...
```

**All paths in this guide are relative to `/home/tunc/Sync/Programs/ytmpd`**

---

## Your Workflow

### Step 1: Find Your Phase

Read `docs/agent/history-reporting/STATUS.md` to identify:
- Which phase is current (marked as CURRENT)
- Your phase number and name

### Step 2: Get Context

**2a. Read the codebase context** (always, before anything else):
- Read `docs/agent/history-reporting/CODEBASE_CONTEXT.md`
- This contains cumulative knowledge about the codebase from all previous phases
- Use this instead of re-exploring the codebase from scratch
- Only explore further if you need information not covered in this document

**2b. Read recent phase summaries** (up to 2 most recent):
- If you're on Phase 2, read `PHASE_01_SUMMARY.md`
- If you're on Phase 1, there are no previous summaries

**Location**: `docs/agent/history-reporting/summaries/`

### Step 3: Read Your Phase Plan

Open `docs/agent/history-reporting/PROJECT_PLAN.md` and read **ONLY** your phase section:
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

**5a. Update the codebase context**:
- Edit `docs/agent/history-reporting/CODEBASE_CONTEXT.md`
- Add any new files you created (to "Key Files & Modules")
- Add any new APIs, classes, or interfaces you built (to "Important APIs & Interfaces")
- Add any new data models (to "Data Models")
- Update any entries that changed due to your work (renamed files, modified APIs, etc.)
- Remove entries for things that no longer exist
- Add a line to the "Update Log" noting what you changed
- Keep updates incremental -- do not rewrite sections that are still accurate

**5b. Create your phase summary**:
- **Template**: `docs/agent/PHASE_SUMMARY_TEMPLATE.md`
- **Output location**: `docs/agent/history-reporting/summaries/PHASE_XX_SUMMARY.md`
- **Length**: Keep it concise (~400-500 lines max)

Include:
- What you built
- Files created/modified
- Completion criteria status
- Any challenges or deviations
- Notes for future phases

### Step 6: Update Status

Edit `docs/agent/history-reporting/STATUS.md`:
1. Mark your phase as Complete
2. Update "Current Phase" to next phase number
3. Update "Phase Name" to next phase name
4. Update "Last Updated" to today's date (YYYY-MM-DD format)

### Step 7: Integration Updates

Check the **Integrations** section in `docs/agent/history-reporting/STATUS.md`.

**If Git is `enabled`:**

1. Stage all changes from this phase (including your summary and STATUS.md updates)
2. Commit with the message format: `Phase {N}: {brief description of what was built}`
   - Example: `Phase 1: Implement history reporter module with MPD idle listener`
   - Use the phase name or objective as the description basis
3. Push to the remote branch: `git push origin feature/history-reporting`

**Jira is disabled for this feature.**

### Step 8: Stop

Your work is complete! The next agent will handle the next phase.

---

## Environment Setup

This is a Python 3.11+ project managed with pip/setuptools.

**First-time setup:**
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

**Activate environment (every session):**
```bash
source .venv/bin/activate
```

**Common commands:**
```bash
# Run tests
pytest tests/

# Run specific test file
pytest tests/test_history_reporter.py -v

# Type checking (strict mode enabled)
mypy ytmpd/

# Linting
ruff check ytmpd/

# Run the daemon (for manual testing)
ytmpd
```

**Key project settings:**
- Line length: 100 characters (ruff)
- Type hints required on all function signatures (mypy strict)
- Python 3.11+ features available (union types with `|`, etc.)

---

## Context Budget

You have approximately **120k tokens** total (input + output + thinking).

**Be strategic**:
- Read only what you need
- Follow the workflow above exactly
- Keep summaries concise
- Don't read entire files when you need one function
- Don't read all phase plans when you need one phase
- Don't explore unrelated code

Each phase is designed to fit within one agent session. If you run out of context:
- Note this in your summary
- Document what's incomplete
- Suggest splitting the phase

---

## Important Notes

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

## Quick Checklist

Before you begin:
- [ ] **FIRST: Run `pwd` and verify you're in `/home/tunc/Sync/Programs/ytmpd`**
- [ ] Read `docs/agent/history-reporting/STATUS.md` to identify your phase
- [ ] Read `docs/agent/history-reporting/CODEBASE_CONTEXT.md` for codebase knowledge
- [ ] Read the 2 most recent phase summaries from `docs/agent/history-reporting/summaries/`
- [ ] Read your phase section in `docs/agent/history-reporting/PROJECT_PLAN.md`
- [ ] Understand your deliverables and completion criteria

During your work:
- [ ] Stay within your phase boundaries
- [ ] Activate environment before running commands (see Environment Setup section)
- [ ] Write tests if required
- [ ] Keep context usage in mind

After completion:
- [ ] Update `docs/agent/history-reporting/CODEBASE_CONTEXT.md` with new discoveries and changes
- [ ] Create phase summary using the template
- [ ] Verify all completion criteria are met (or document why not)
- [ ] Update `docs/agent/history-reporting/STATUS.md`
- [ ] Commit and push if git is enabled (see Step 7)
- [ ] Do NOT start the next phase

---

## Ready to Start?

1. Read `docs/agent/history-reporting/STATUS.md`
2. Follow the workflow above
3. Complete your phase
4. Document and update status

**Good luck, Agent!**

---

*This quickstart is designed for AI agents working in a phased development workflow. For human developers, see the standard project README.*
