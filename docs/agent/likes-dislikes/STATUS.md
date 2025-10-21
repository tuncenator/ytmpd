# ytmpd likes-dislikes Project Status

## 📍 Project Location

**IMPORTANT: Verify your location before working!**

- **Project Root**: `/home/tunc/Sync/Programs/ytmpd`
- **Feature Docs**: `/home/tunc/Sync/Programs/ytmpd/docs/agent/likes-dislikes`
- **Verify with**: `pwd` → should output `/home/tunc/Sync/Programs/ytmpd`

**Always work from the project root directory. All paths below are relative to project root.**

---

**Last Updated:** 2025-10-21
**Current Phase:** 2 of 6
**Phase Name:** Core Toggle Logic & Rating Manager
**Progress:** 17% (1/6 phases complete)
**Git Branch:** feature/likes-dislikes

---

## Progress Bar

```
[███░░░░░░░░░░░░░░░░░] 17% (1/6)
```

---

## Quick Phase Reference

| Phase | Name | Status |
|-------|------|--------|
| 1 | API Research & Discovery | ✅ Complete |
| 2 | Core Toggle Logic & Rating Manager | 🔵 CURRENT |
| 3 | YouTube Music API Integration | ⏳ Pending |
| 4 | ytmpctl Command Implementation | ⏳ Pending |
| 5 | End-to-End Testing & Validation | ⏳ Pending |
| 6 | Documentation & Polish | ⏳ Pending |

---

## Instructions for Agents

**Before starting:**
1. Run `pwd` → verify you're in `/home/tunc/Sync/Programs/ytmpd`
2. Run `git branch --show-current` → verify you're on `feature/likes-dislikes`

**To work on current phase:**
1. Read `QUICKSTART.md` for workflow guidance
2. Read `PROJECT_PLAN.md` Phase 2 section for detailed requirements
3. Read `summaries/PHASE_01_SUMMARY.md` for context from previous phase
4. Complete the phase following the completion criteria
5. **Commit your work:** `git commit -m "Implement RatingManager with toggle state machine"`
6. Create `summaries/PHASE_02_SUMMARY.md`
7. Update this file:
   - Mark Phase 2 as ✅ Complete
   - Set Phase 3 as 🔵 CURRENT
   - Update "Current Phase" to "3 of 6"
   - Update "Progress" to "33% (2/6 phases complete)"
   - Update progress bar: `[██████░░░░░░░░░░░░░░] 33% (2/6)`
   - Update "Last Updated" to current date (YYYY-MM-DD)

**Full details:** See `PROJECT_PLAN.md`

---

## Legend

- ✅ Complete - Phase finished, committed to git, and summary created
- 🔵 CURRENT - Phase currently being worked on
- ⏳ Pending - Phase not yet started
- ⚠️ Blocked - Phase cannot proceed due to blocker
- 🔄 In Review - Phase complete but needs review

---

## Notes

- Feature branch: `feature/likes-dislikes`
- Each phase must be committed to git after completion
- Do NOT mention AI or automated tools in commit messages
- Focus commit messages on technical changes (e.g., "Add RatingManager with toggle logic")
