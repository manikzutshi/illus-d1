# 25 — Release Checkpoint: 2D Schematic Studio + Functional Validation

Date: 2026-09-25. Status: **frozen.** The decisions in §5 were made by the project owner: commit
the full milestone, and merge GitHub's initial commit into `main` without force-pushing.

## 1. Milestone

**v0.2.0-2d-studio**: 2D Schematic Studio (deterministic layout engine, schematic LVS, interactive
workspace, library and knowledge expansion, curriculum mapping) plus functional / behavioural intent
validation integrated into the AI repair loop and the studio. No tags exist in the repository yet,
and `pyproject.toml` says `0.1.0`, so `v0.2.0-…` follows on without conflicting with anything.

## 2. Verified test results (this session, current code)

| Suite | Result |
|---|---|
| `pytest` | **460 passed, 5 skipped** (opt-in live-provider tests) |
| vitest | **13 passed** (3 files) |
| `tsc -b` | clean |
| Browser E2E (`scripts/ui_e2e.py`, fresh server on port 8799 running the current code) | **16/16**. The first attempt stopped at 14/15: one click on the Inspector's disconnect ✕ did not register (no edit reached the backend), a UI-timing flake. The immediate re-run passed 16/16. |

Port 8765 was held by a studio server started at 03:13 with the system Python, not by this session.
It was left running and not used for verification.

## 3. README

`README.md` was rewritten from the current code. It covers: what the project is; the problem it
solves; the architecture (NL → requirements/functional intent → AI planning → knowledge ecosystem →
Engineering Design IR → electrical validation → functional validation → schematic generation → LVS →
studio) with a code map; the philosophy "AI proposes. Deterministic systems verify."; capabilities;
ecosystem numbers; curriculum integration (physical parts vs idealised primitives vs design patterns
vs engineering concepts); studio UX (AI Assistant, Library/Examples, canvas, Inspector, Electrical,
Function, Explain, editing, undo/redo, auto-arrange, export); architectural invariants; quick start
and CLI commands (checked against `cli.main --help`, `pyproject.toml`, `frontend/package.json`,
`studio.cmd`); testing; known limitations; roadmap (3D/physical is explicitly the **next** stage,
not done); repository layout. A scan found no API key or secret in it.

Verified numbers used: 86 component types = **69 physical + 17 idealised primitives** (16
`primitive:*` plus the jumper wire, typed CIRCUIT_PRIMITIVE), 53 families, 16 design patterns,
6 calculators, 53 curriculum concepts in 23 modules, 12 reference designs (10 with intents),
E001–E019 / W001–W007, F001–F011 / F101–F106.

**Correction:** `00_master_audit.md` (2D stage section) says "60 physical, 26 idealised
primitives". The registry has 69 physical and 17 non-physical types. It will be corrected when this
checkpoint is recorded there.

## 4. Git state found

| Item | State |
|---|---|
| Repository root | `X:/illus-d1-claude/illustration-engine` |
| Branch | `master` |
| Last commit | `7afa270` "Phase 4.3: Reference-Grade Visual Reset with GLB Asset Pipeline" (2026-09-18) |
| Tags | none |
| Remote | **none configured** |
| GitHub `manikzutshi/illus-d1` | `main` = `da02752` "Initial commit" (only `README.md`, `# illus-d1`). **No shared history** with local `master` (fetched to `FETCH_HEAD` only, read-only; no remote added) |
| Modified tracked files | 28 (README plus source, data, tests and frontend from the studio and functional stages) |
| Untracked | 149 milestone files (e.g. `src/studio/`, `src/schematic/`, `src/functional/`, `src/knowledge/`, `frontend/src/studio/`, `data/components/library/`, `data/knowledge/`, `data/examples/`, `tests/fixtures/functional/`, `reports/`, `scripts/`, `studio.cmd`) plus non-milestone items: `node_modules/` (empty), `package-lock.json` (empty lockfile at project root), `runs/` (21 AI trace files), `scratch/` (5.1 MB of live-run artifacts), `src/core/models.py.bak`, `temp_render.py` |
| Secrets | none found in any modified or untracked candidate file; no `.env` files |
| `.gitignore` | does not cover `node_modules/`, `scratch/`, `runs/`, `*.bak`, `.env` |

## 5. Decisions taken

The original plan was a README-only commit, and the instructions said to stop if unexpected
uncommitted changes existed. They did: **the entire milestone was uncommitted**, no remote was
configured, and the GitHub repository had unrelated history. Work stopped and two questions went to
the owner. The answers:

1. **Commit the full milestone.** `.gitignore` gained `node_modules/`, `.env`, `.env.*`, `runs/`,
   `scratch/`, `*.bak`. `temp_render.py` (an old stray script, referenced by nothing) and the empty
   root `package-lock.json` were deliberately left **uncommitted and untouched**.
   `reports/04_design_ir.zip` (the owner's archive of reports 00–13, no secrets inside) is included.
2. **Merge into GitHub `main`.** Add `origin`, merge its one-file initial commit with
   `--allow-unrelated-histories` keeping this README, and push `master` → `main` as a fast-forward
   (no force).

## 6. Commit / tag / push

| Item | Value |
|---|---|
| Milestone commit | `97c4f63` feat: 2D schematic studio and functional validation milestone (173 files) |
| Documentation commit | the commit that adds this report: README, reports 25 and 00 |
| Merge | GitHub `main` initial commit `da02752` merged into `master` (README kept from this project) |
| Tag | `v0.2.0-2d-studio` (annotated) on the merge commit, i.e. exactly the state pushed to `main` |
| Branch / remote | local `master` → `origin/main`, `origin` = https://github.com/manikzutshi/illus-d1 |
| Documentation commit hash | `b98c45f` docs: freeze current 2D schematic studio milestone |
| Merge commit (tagged) | `be9bac2` Merge GitHub initial commit into the milestone history (tree identical to `b98c45f`) |
| Push | **success**: `git push origin master:main` → `da02752..be9bac2 master -> main` (fast-forward, no force); `git push origin v0.2.0-2d-studio` → new tag |
| Upstream | local `master` tracks `origin/main` |

Files intentionally left out of Git: `temp_render.py`, root `package-lock.json`; ignored:
`node_modules/`, `scratch/`, `runs/`, `*.bak`, `.venv/`, `frontend/dist`.

## 7. Working tree after the checkpoint

Clean except two intentionally uncommitted, untracked files: `temp_render.py` and the empty root
`package-lock.json` (left on disk for the owner to keep or delete). This report's final table was
added in one follow-up documentation commit after the tag; the tag `v0.2.0-2d-studio` stays on
`be9bac2`, the frozen milestone state.

