# Changelog

## 0.2.0 — DocumentKit v1.1 hardening

- Added persistent pending-update state and `document-kit retry`.
- Added rollback-capable transactional publication for build and incremental updates.
- Preserved removed functions/API rows as `REMOVED_PENDING_REVIEW` without blocking on deleted historical evidence.
- Added authorization/evidence/anchor/entry-point coverage validation.
- Added all-repository source snapshot and final HEAD stability checks.
- Added failure-path/environment tests and install-time runtime checks.
- Separated installed CLI from analyzed workspaces and added arbitrary external repository selection.
- Added static `docs/index.html` reader with search/filter/TOC; XLSX is now opt-in.
- Added source-backed Mermaid diagrams and verified UI-image metadata support.
