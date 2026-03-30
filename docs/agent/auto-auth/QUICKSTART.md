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
- **Feature Docs**: `/home/tunc/Sync/Programs/ytmpd/docs/agent/auto-auth`

### Path Usage Rules

1. **Stay in project root** - Do NOT `cd` to other directories
2. **All paths are relative to project root** - When you see `docs/agent/...`, it means `/home/tunc/Sync/Programs/ytmpd/docs/agent/...`
3. **If confused about location** - Run `pwd` to verify you're in `/home/tunc/Sync/Programs/ytmpd`
4. **Use relative paths in your work** - Reference files as `docs/agent/...` not absolute paths

**Example Path Reference:**
```
Relative path: docs/agent/auto-auth/STATUS.md
Absolute path: /home/tunc/Sync/Programs/ytmpd/docs/agent/auto-auth/STATUS.md
                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                Where pwd should output
```

---

## Your Mission

You are part of a phased development workflow. Your job is to:
1. **Verify your location** (run `pwd` -> should be `/home/tunc/Sync/Programs/ytmpd`)
2. Identify which phase you're responsible for
3. Gather minimal necessary context
4. Complete your phase according to the plan
5. Document your work
6. Update the status for the next agent

---

## File Structure

```
project-root/  <- /home/tunc/Sync/Programs/ytmpd (where pwd outputs)
|-- docs/
|   +-- agent/
|       |-- PHASE_SUMMARY_TEMPLATE.md      <- Shared template
|       +-- auto-auth/                     <- Your feature folder
|           |-- QUICKSTART.md              <- You are here
|           |-- PROJECT_PLAN.md            <- Detailed plan for all phases
|           |-- STATUS.md                  <- Current phase tracker
|           |-- CODEBASE_CONTEXT.md        <- Cumulative codebase knowledge
|           +-- summaries/                 <- Completed phase summaries
|               |-- PHASE_01_SUMMARY.md
|               |-- PHASE_02_SUMMARY.md
|               +-- ...
```

**All paths in this guide are relative to `/home/tunc/Sync/Programs/ytmpd`**

---

## Your Workflow

### Step 1: Find Your Phase

Read `docs/agent/auto-auth/STATUS.md` to identify:
- Which phase is current (marked as CURRENT)
- Your phase number and name

### Step 2: Get Context

**2a. Read the codebase context** (always, before anything else):
- Read `docs/agent/auto-auth/CODEBASE_CONTEXT.md`
- This contains cumulative knowledge about the codebase from all previous phases
- Use this instead of re-exploring the codebase from scratch
- Only explore further if you need information not covered in this document

**2b. Read recent phase summaries** (up to 2 most recent):
- If you're on Phase 5, read `PHASE_04_SUMMARY.md` and `PHASE_03_SUMMARY.md`
- If you're on Phase 1 or 2, read what's available (or nothing if Phase 1)

**Location**: `docs/agent/auto-auth/summaries/`

### Step 3: Read Your Phase Plan

Open `docs/agent/auto-auth/PROJECT_PLAN.md` and read **ONLY** your phase section:
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
- Edit `docs/agent/auto-auth/CODEBASE_CONTEXT.md`
- Add any new files you created (to "Key Files & Modules")
- Add any new APIs, classes, or interfaces you built (to "Important APIs & Interfaces")
- Add any new data models (to "Data Models")
- Update any entries that changed due to your work (renamed files, modified APIs, etc.)
- Remove entries for things that no longer exist
- Add a line to the "Update Log" noting what you changed
- Keep updates incremental -- do not rewrite sections that are still accurate

**5b. Create your phase summary**:
- **Template**: `docs/agent/PHASE_SUMMARY_TEMPLATE.md`
- **Output location**: `docs/agent/auto-auth/summaries/PHASE_XX_SUMMARY.md`
- **Length**: Keep it concise (~400-500 lines max)

Include:
- What you built
- Files created/modified
- Completion criteria status
- Any challenges or deviations
- Notes for future phases

### Step 6: Update Status

Edit `docs/agent/auto-auth/STATUS.md`:
1. Mark your phase as Complete
2. Update "Current Phase" to next phase number
3. Update "Phase Name" to next phase name
4. Update "Last Updated" to today's date (YYYY-MM-DD format)

### Step 7: Integration Updates

Check the **Integrations** section in `docs/agent/auto-auth/STATUS.md`.

**If Git is `enabled`:**

1. Stage all changes from this phase (including your summary and STATUS.md updates)
2. Commit with the message format: `Phase {N}: {brief description of what was built}`
   - Example: `Phase 3: Implement user authentication endpoints`
   - Use the phase name or objective as the description basis
3. Push to the remote branch: `git push origin {branch-name}`
   - The branch name is in the Integrations section of STATUS.md

**If Jira Issue is configured (not `disabled`):**

1. Get the short commit hash (if git is enabled): `git rev-parse --short HEAD`
2. Get the full commit hash (if GitHub Repo is configured): `git rev-parse HEAD`
3. Compose a plain-text comment summarizing the phase work. Remember: Jira uses plain text, not markdown. Use the following format:

   If git and GitHub Repo are both available:
   ```
   Phase {N} (commit {short-hash}): {description of work completed}

   {2-3 sentences about what was built and any notable decisions}

   https://github.com/{github-repo}/commit/{full-hash}
   ```

   If git is enabled but no GitHub Repo:
   ```
   Phase {N} (commit {short-hash}): {description of work completed}

   {2-3 sentences about what was built and any notable decisions}
   ```

   If git is disabled:
   ```
   Phase {N}: {description of work completed}

   {2-3 sentences about what was built and any notable decisions}
   ```

4. Post the comment using a heredoc for multiline text:
   ```
   acli jira workitem comment create --key "{issue-key}" --body "$(cat <<'EOF'
   {comment text here}
   EOF
   )"
   ```
   - The issue key is in the Integrations section of STATUS.md

**If neither is configured:** Skip this step.

### Step 8: Stop

Your work is complete! The next agent will handle the next phase.

---

## Environment Setup

**First-time setup:**
```bash
cd /home/tunc/Sync/Programs/ytmpd
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

**Before each session (activate venv):**
```bash
source /home/tunc/Sync/Programs/ytmpd/.venv/bin/activate
```

**Common commands:**
```bash
# Run tests
pytest

# Run tests with coverage
pytest --cov=ytmpd --cov-report=term-missing

# Run specific test file
pytest tests/test_ytmusic.py -v

# Linting
ruff check ytmpd/

# Formatting
ruff format ytmpd/

# Type checking
mypy ytmpd/

# Start daemon (for manual testing)
python -m ytmpd

# CLI client
bin/ytmpctl status
bin/ytmpctl auth
```

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
- [ ] Read `docs/agent/auto-auth/STATUS.md` to identify your phase
- [ ] Read `docs/agent/auto-auth/CODEBASE_CONTEXT.md` for codebase knowledge
- [ ] Read the 2 most recent phase summaries from `docs/agent/auto-auth/summaries/`
- [ ] Read your phase section in `docs/agent/auto-auth/PROJECT_PLAN.md`
- [ ] Understand your deliverables and completion criteria

During your work:
- [ ] Stay within your phase boundaries
- [ ] Activate environment before running commands (see Environment Setup section)
- [ ] Write tests if required
- [ ] Keep context usage in mind

After completion:
- [ ] Update `docs/agent/auto-auth/CODEBASE_CONTEXT.md` with new discoveries and changes
- [ ] Create phase summary using the template
- [ ] Verify all completion criteria are met (or document why not)
- [ ] Update `docs/agent/auto-auth/STATUS.md`
- [ ] Commit and push if git is enabled (see Step 7)
- [ ] Post Jira comment if Jira is configured (see Step 7)
- [ ] Do NOT start the next phase

---

## Ready to Start?

1. Read `docs/agent/auto-auth/STATUS.md`
2. Follow the workflow above
3. Complete your phase
4. Document and update status

**Good luck, Agent!**

---

*This quickstart is designed for AI agents working in a phased development workflow. For human developers, see the standard project README.*
