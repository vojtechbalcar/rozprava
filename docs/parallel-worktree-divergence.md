---
type: problem
updated: 2026-11-21
status: current
---

# Parallel work in a stale worktree

Related: [[dev-environment]], [[functional-app-plan]], [[transcript-import]], [[local-app-verification]]

**Symptom.** On 21 Nov a push of `feature/functional-local-app` from this Mac was
rejected: the local branch had 1 commit the remote lacked, the remote 12 the local
branch lacked. The local commit added a second "revision-aware" schema and parser,
with an importer and search still untracked.

**Cause.** The approved plan was finished on 18–19 Nov on another machine and pushed
(181 tests, verified archive). T3 later resumed this thread in the 17 Nov worktree
on this Mac, which still pointed at the old commit. Nothing fetched first, so run 10
rebuilt parts of the plan from scratch under the same Alembic revision numbers
(0001, 0002) and ran them against this Mac's database.

**Fix (21 Nov).**
- Run 10's commit and its untracked files are kept on the local branch
  `wip/parallel-schema-run10` (not pushed); `feature/functional-local-app` was reset
  to `origin`.
- Its database, which held only open-data metadata in the incompatible schema, was
  renamed `rozprava_superseded_20261121` rather than dropped. `rozprava_test` was
  recreated empty. `local_db.py init` and `alembic upgrade head` then built fresh
  databases on the pushed schema; all 181 tests and checks pass on this Mac.
- The archive was rebuilt here from psp.cz; see [[transcript-import]].

**Tried first.** Nothing else: the remote line was verified and complete, so merging
two implementations of the same plan would only have added conflicts.

**How to apply.** Before resuming work in any checkout, run `git fetch` and compare
with `origin`, and read [[dev-environment]] for where work last continued. Drop the
superseded database and the WIP branch once nobody needs them:
`DROP DATABASE rozprava_superseded_20261121` (as the cluster owner over the private
socket) and `git branch -D wip/parallel-schema-run10`.
