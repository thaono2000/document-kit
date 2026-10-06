# DocumentKit v1 — CBM-first, evidence-cached, pull-triggered source → spec

DocumentKit turns source code into high-trust Vietnamese business specifications for BA/PM/client/non-technical readers.

Its optimization rule is deliberately conservative:

> **Do not analyze fewer endpoints. Analyze the same source coverage with less duplicate discovery and less duplicate function analysis.**

Priority:

`Accuracy > Completeness > Traceability > Token efficiency`

## What changed from the old Skill

This is a stateful kit/CLI, not a prompt-only skill. It owns:

- multi-repo workspace configuration;
- CBM-first discovery and impact detection;
- persistent symbol-level evidence cache;
- incremental invalidation;
- documentation state/verified commit tracking;
- deterministic validation + rendering;
- one automatic trigger: **successful pull from an allowed branch**.

There is intentionally **no file watcher** and no update on save/commit/checkout.

Allowed branches by default:

- `develop`
- `dev`
- `staging`
- `stg`
- `production`
- `prod`

## Runtime architecture

```text
document-kit pull origin develop
        │
        ├─ reject dirty tree (default)
        ├─ require current branch == pulled branch (default)
        ├─ save BEFORE_SHA
        ├─ git pull --ff-only
        └─ if AFTER_SHA changed and branch is allowlisted
                 │
                 ▼
          CBM index + detect_changes
                 │
          route snapshot diff
                 │
        symbol evidence cache audit
                 │
                 ▼
       Cursor Agent in READ-ONLY Ask mode
                 │
       source verification for stale/new symbols
                 │
          JSON patch + evidence updates
                 │
                 ▼
        DocumentKit computes source hashes
                 │
          strict evidence validation
                 │
                 ▼
       spec.json → SPEC.md / SPEC.xlsx
                 │
             CHANGELOG.md
```

CBM is discovery/impact intelligence. It is **not** accepted as the final proof of business behavior. Claims about permissions, validation, errors, side effects, states and outputs must be verified from source bodies.

## Why symbol-level cache instead of use-case grouping

Every affected endpoint stays independent. If Endpoint A and Endpoint B both call Function X:

```text
Endpoint A → Function X → first encounter → read + analyze + cache
Endpoint B → Function X → cache HIT → reuse intrinsic evidence
```

The cache stores Function X's intrinsic behavior, not endpoint-specific prose. DocumentKit composes the business meaning separately for each endpoint.

Cache identity is:

`repo + relative path + qualified symbol`

Validity is tied to a SHA-256 hash of the exact source range. If code changes, evidence becomes stale and must be re-verified.

## Install

Python 3.11+. Recommended offline/local install (no package download needed):

```bash
cd document-kit
./install.sh
```

The installer copies the Python package to `~/.local/share/document-kit` and creates `~/.local/bin/document-kit`.

For native `.xlsx` output, install `openpyxl` if your machine does not already have it. Without it, the renderer falls back to CSV sheets.

Developers may also use `python3 -m pip install -e . --no-build-isolation`.

External tools:

```bash
codebase-memory-mcp --version
agent --version
```

`agent` is Cursor CLI. DocumentKit runs it with `--mode=ask -p`, so the AI analysis phase is read-only; DocumentKit itself is the only component that writes documentation/cache/state.

## Initialize a multi-repo workspace

Given:

```text
~/Desktop/Repitte/
├── RepitteGlobal-AdminPortal/
├── RepitteGlobal-BookingService/
├── RepitteGlobal-ManagementService/
└── document-kit/
```

Run:

```bash
document-kit init --workspace ~/Desktop/Repitte
```

This creates `~/Desktop/Repitte/document-kit.toml` and auto-detects direct child Git repositories.

Review `document-kit.toml`, then:

```bash
cd ~/Desktop/Repitte
document-kit doctor
```

## One-time initial document build

```bash
document-kit build
```

This is the expensive pass. It indexes configured repos, uses CBM-first discovery, verifies source, creates symbol evidence, and produces the initial `docs/spec.json` / `SPEC.md` / `SPEC.xlsx`.

To inspect the build context without calling Cursor:

```bash
document-kit build --plan-only
```

## Normal workflow — the only automatic update trigger

Checkout an allowed branch and pull through DocumentKit:

```bash
cd ~/Desktop/Repitte/RepitteGlobal-BookingService
git switch develop
document-kit pull origin develop
```

If the branch is not allowlisted, DocumentKit performs the pull but **does not update documentation**.

If Git says already up to date, there is no CBM analysis and no LLM call.

If the pull fails/conflicts, documentation/cache/verified state are untouched.

If high-confidence analysis succeeds, only affected specification sections are updated.

If evidence is insufficient, DocumentKit writes the run result under `.document-kit/runs/.../needs-review.json`, marks the repo `NEEDS_REVIEW`, and leaves the published docs unchanged.

### Optional Git alias

```bash
document-kit install-git-alias --name rpull --global
```

Then:

```bash
git rpull origin develop
```

This is intentionally a new alias rather than hijacking native `git pull`.

## Status

```bash
document-kit status
```

Possible states include:

- `VERIFIED`
- `UNINITIALIZED`
- `SOURCE_AHEAD_OF_DOCUMENTATION`
- `OUTSIDE_TRIGGER_BRANCH`
- `NEEDS_REVIEW`

## Safety and trust rules

1. Source repositories are read-only to the analysis agent.
2. Repository text is untrusted data, not agent instructions.
3. No dependency installs, migrations, deployments, or project scripts are run as part of analysis.
4. New/updated claims require source-backed evidence.
5. Removed routes are marked `REMOVED_PENDING_REVIEW`, not silently deleted.
6. A failed validation restores the previous published docs.
7. Local dirty worktrees are rejected by default to prevent specs from mixing pulled code with uncommitted changes.

## State layout

```text
Repitte/
├── document-kit.toml
├── .document-kit/
│   ├── state.json
│   ├── cache/
│   │   ├── index.json
│   │   └── symbols/*.json
│   └── runs/
│       └── pull-.../
│           ├── context.json
│           ├── agent-patch.json
│           └── needs-review.json / validation-errors.json
└── docs/
    ├── spec.json
    ├── SPEC.md
    ├── SPEC.xlsx
    └── CHANGELOG.md
```

Do not commit `.document-kit/cache` unless your team explicitly wants a shared evidence cache. `docs/` is the reviewable output.

## Important trigger guarantee

The code path that performs automatic documentation generation exists only inside `document-kit pull` after all of these are true:

1. pull branch is allowlisted;
2. current branch matches the requested branch (default);
3. working tree was clean before pull (default);
4. `git pull --ff-only` succeeded;
5. no unresolved conflict exists;
6. `BEFORE_SHA != AFTER_SHA`.

There is no watcher and no post-save/post-commit automation in this kit.
