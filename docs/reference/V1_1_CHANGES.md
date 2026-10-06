# DocumentKit v1.1 hardening changes

This release implements nine reliability/usability corrections identified during design review.

1. **Pending retry** — failed pull-triggered documentation updates persist target/base commit and can be retried with `document-kit retry` even when the next pull is a no-op.
2. **Transactional outputs/cache** — build and incremental update stage spec/rendered docs/changelog/evidence cache and publish them together only after success.
3. **Historical removal state** — removed functions/API rows become `REMOVED_PENDING_REVIEW`; stale/deleted historical source does not block unrelated publication.
4. **Stricter validation** — authorization, structured evidence, anchors and discovered-route coverage are validated.
5. **Exact source snapshot** — all configured repository worktrees are checked before analysis and all HEADs are rechecked before publication.
6. **Failure/environment tests** — retry, render rollback, removed source, HTML rendering and environment checks are covered.
7. **Tool/workspace separation** — CLI is installed once; repositories may be selected from arbitrary paths; each workspace owns independent state/cache/output.
8. **HTML reader first** — `docs/index.html` is the primary reading interface with search/filter/TOC; Markdown remains review output; XLSX is opt-in.
9. **Source-backed diagrams** — optional Mermaid architecture/business-flow/state diagrams and verified UI images are supported in the spec.
