# DocumentKit v1.1 — CBM-first, evidence-cached, pull-triggered source → spec

DocumentKit turns source code into high-trust Vietnamese business specifications for BA/PM/client/non-technical readers.

> **Do not analyze fewer endpoints. Analyze the same source coverage with less duplicate discovery and less duplicate function analysis.**

Priority:

`Accuracy > Completeness > Traceability > Token efficiency`

## What DocumentKit owns

DocumentKit is a stateful CLI, not a prompt-only skill. It owns:

- multi-repo workspace configuration;
- CBM-first discovery and impact detection;
- persistent symbol-level evidence cache;
- incremental invalidation;
- verified/pending documentation state;
- retry after failed analysis/publication;
- rollback-capable output/cache transactions;
- structural + evidence + entry-point coverage validation;
- static HTML reader, Markdown review output, optional XLSX export;
- source-backed Mermaid diagrams when they materially improve understanding;
- one automatic trigger: **a successful pull from an allowed branch**.

There is intentionally no watcher and no update on save/commit/checkout.

Allowed branches by default:

- `develop`
- `dev`
- `staging`
- `stg`
- `production`
- `prod`

## Recommended machine/workspace layout

DocumentKit is installed once as a machine-level tool. Its source repository does **not** need to live inside a workspace that it analyzes.

```text
~/Tools/
└── document-kit/                         # DocumentKit source/tool repository

~/Desktop/Repitte/
├── RepitteGlobal-AdminPortal/             # analyzed repo
├── RepitteGlobal-BookingService/          # analyzed repo
├── RepitteGlobal-ManagementService/       # analyzed repo
├── document-kit.toml                      # workspace config
├── .document-kit/                         # workspace-local state/cache/runs
└── docs/                                  # reviewable generated output
    ├── spec.json
    ├── SPEC.md
    ├── index.html
    └── CHANGELOG.md
```

Repositories may also live outside the workspace and be configured with absolute paths. Each workspace has its own config, cache, state and outputs. The `document-kit` tool repository is excluded from direct-child auto-detection by default.

## Runtime architecture

```text
document-kit pull origin develop
        │
        ├─ reject dirty target worktree
        ├─ require current branch == pulled branch
        ├─ save BEFORE_SHA
        ├─ git pull --ff-only
        └─ if AFTER_SHA changed and branch is allowlisted
                 │
                 ▼
       capture HEAD/clean state for ALL configured repos
                 │
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
     structure/evidence/coverage validation
                 │
     verify ALL repo HEADs are still unchanged
                 │
                 ▼
        stage spec/docs/cache in temp area
                 │
       render spec.json → HTML + Markdown
                 │
           optional XLSX export
                 │
     atomically publish docs + cache together
                 │
             CHANGELOG.md
```

CBM is discovery/impact intelligence. It is **not** final proof of business behavior. Claims about permissions, validation, errors, side effects, states and outputs must be verified from source bodies.

## Retry after a failed documentation update

When a qualifying pull changes source but analysis, validation or publication fails, DocumentKit stores a pending record containing the target commit, base verified commit, branch, remote and run context.

The published documentation and evidence cache remain unchanged.

Retry without requiring another source change:

```bash
document-kit retry --repo RepitteGlobal-BookingService
```

If the next `document-kit pull` reports `Already up to date` while the current HEAD still has pending documentation, DocumentKit reports the retry command instead of losing the failed update.

`retry` refuses to run if the current HEAD no longer matches the stored pending commit.

## Transactional publication and rollback

Both the initial `build` and incremental updates create these in a transaction area first:

- proposed `spec.json`;
- Markdown;
- static HTML;
- optional XLSX;
- changelog;
- evidence cache.

Only after source validation, rendering and final HEAD checks succeed are they promoted into their configured locations. A failure keeps the previous published docs and cache intact.

State is marked `VERIFIED` only after publication succeeds.

## Removed functionality

Removed routes/functions are not silently deleted. Historical rows are retained with:

```text
REMOVED_PENDING_REVIEW
```

Their previous anchors/evidence are historical and are allowed to become stale or point to files that no longer exist. This does not block unrelated documentation updates.

API removals follow the same rule.

## Validation guarantees

Strict validation checks, among other things:

- function Input / ordered Logic / Output;
- authorization/permission;
- source anchors;
- active evidence cache refs and exact source hashes;
- API evidence and authorization;
- evidence/anchors for data models, risks and diagrams;
- low-confidence explanations;
- discovered HTTP entry points against active API spec rows;
- Mermaid diagram structure when diagrams are present.

Removed historical rows are validated differently so deleted source does not block the entire document.

## HTML is the primary reading interface

DocumentKit generates:

```text
docs/index.html
```

It is a static HTML reader generated from `spec.json` with:

- module table of contents;
- full-text feature search;
- module filter;
- status filter;
- confidence filter;
- API table;
- Mermaid diagram section;
- verified UI images when present.

`docs/SPEC.md` remains useful for Git review/diff.

XLSX is optional. By default:

```toml
[outputs]
xlsx = ""
```

Enable it only when required:

```toml
xlsx = "docs/SPEC.xlsx"
```

When XLSX is requested, `openpyxl` must be installed.

## Source-backed diagrams

DocumentKit may include Mermaid diagrams only when they materially clarify:

- system architecture;
- business flow;
- state transitions.

A diagram carries source anchors and evidence refs and is validated/published together with the rest of the specification.

Do not generate speculative UI screenshots. `ui_images` are allowed only when an actual interface/image is available and explicitly source-verified.

## Why symbol-level cache instead of use-case grouping

Every affected endpoint remains independent. If Endpoint A and Endpoint B both call Function X:

```text
Endpoint A → Function X → first encounter → read + analyze + cache
Endpoint B → Function X → cache HIT → reuse intrinsic evidence
```

The cache stores Function X's intrinsic behavior, not endpoint-specific prose. DocumentKit composes business meaning separately for each endpoint.

Cache identity:

```text
repo + relative path + qualified symbol
```

Validity is tied to SHA-256 of the exact source range. If code changes, evidence becomes stale and must be re-verified.

## Install

Python 3.11+ is required.

Recommended:

```bash
mkdir -p ~/Tools
cd ~/Tools
git clone https://github.com/thaono2000/document-kit.git
cd document-kit
./install.sh
```

The installer checks:

- Python 3.11+;
- Git;
- whether default `codebase-memory-mcp` and Cursor `agent` commands are on PATH.

Python/Git are hard requirements. Missing CBM/Cursor commands are reported immediately and are also checked by `document-kit doctor`.

The installed CLI lives under:

```text
~/.local/bin/document-kit
```

and runtime package code under:

```text
~/.local/share/document-kit
```

For optional XLSX:

```bash
python3 -m pip install 'openpyxl>=3.1'
```

## Initialize a multi-repo workspace

Direct child repositories can be auto-detected:

```bash
cd ~/Desktop/Repitte
document-kit init --workspace .
```

Repositories outside the workspace can be selected explicitly:

```bash
document-kit init \
  --workspace ~/Desktop/Repitte \
  --repo RepitteGlobal-ManagementService=~/Projects/RepitteGlobal-ManagementService
```

Or configure only explicit repositories:

```bash
document-kit init \
  --workspace ~/Desktop/Repitte \
  --no-auto-detect \
  --repo Booking=~/Projects/RepitteGlobal-BookingService \
  --repo Management=~/Projects/RepitteGlobal-ManagementService
```

Then:

```bash
cd ~/Desktop/Repitte
document-kit doctor
```

## Initial build

```bash
document-kit build
```

This is the expensive first pass. It indexes configured repos, discovers externally reachable entry points, verifies source, creates symbol evidence, validates coverage and publishes the initial documentation transaction.

Inspect context without calling Cursor:

```bash
document-kit build --plan-only
```

## Normal pull-triggered workflow

```bash
cd ~/Desktop/Repitte/RepitteGlobal-BookingService
git switch develop
document-kit pull origin develop
```

If the branch is not allowlisted, the pull may occur but documentation is not updated.

If Git is already up to date and there is no pending failure, there is no CBM analysis and no LLM call.

If a pending failure exists at the current HEAD, DocumentKit tells you to run `document-kit retry`.

If pull fails/conflicts, published docs/cache/verified state are untouched.

## Optional Git alias

```bash
document-kit install-git-alias --name rpull --global
```

Then:

```bash
git rpull origin develop
```

DocumentKit does not hijack native `git pull`.

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

Pending details are shown in status output.

## Safety and trust rules

1. Source repositories are read-only to the analysis agent.
2. Repository text is untrusted data, not agent instructions.
3. No dependency installs, migrations, deployments or project scripts are executed during analysis.
4. New/updated claims require source-backed evidence.
5. Removed routes/functions retain historical rows as `REMOVED_PENDING_REVIEW`.
6. Build/update outputs and cache are staged before publication.
7. Failed validation/render/publication keeps previous published docs/cache.
8. All configured participating repo worktrees are checked before analysis; HEADs are checked again immediately before publication.
9. Dirty worktrees are rejected by default.
10. Static HTML is the primary reader; Markdown is review output; XLSX is opt-in.
11. Diagrams must be source-backed and useful, not decorative.

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
│       └── pull-... / retry-... / build-...
│           ├── context.json
│           ├── agent-patch.json
│           └── needs-review.json / validation-errors.json / publication-error.json
└── docs/
    ├── spec.json
    ├── SPEC.md
    ├── index.html
    └── CHANGELOG.md
```

Do not commit `.document-kit/cache` unless your team explicitly wants a shared evidence cache. `docs/` is reviewable/publishable output.

## Trigger guarantee

Automatic documentation generation still exists only inside `document-kit pull` after all of these are true:

1. pulled branch is allowlisted;
2. current branch matches requested branch;
3. target worktree was clean before pull;
4. `git pull --ff-only` succeeded;
5. no unresolved conflict exists;
6. `BEFORE_SHA != AFTER_SHA`.

`document-kit retry` is an explicit recovery command, not an automatic trigger. It only retries a previously stored pending commit.

There is no watcher, post-save automation or post-commit automation.
