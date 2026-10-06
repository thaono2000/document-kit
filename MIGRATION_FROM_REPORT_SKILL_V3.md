# Migration from report-skill-v3

`report-skill-v3` was an instruction bundle. `document-kit` keeps its high-trust principles but moves state and orchestration into executable code.

## Preserved

- CBM-first discovery.
- Mandatory source verification for business claims.
- Multi-repo anchors: `{"repo":"...","path":"file:line"}`.
- Symbol-level evidence cache, not use-case grouping.
- Input / Logic / Output completeness.
- Confidence + unknowns instead of guesses.
- `spec.json` as documentation source of truth.
- Markdown / XLSX rendering.

## Changed

- No `SKILL.md` entry point is required.
- Cache/state survive Cursor sessions by design.
- Incremental scope is calculated after a qualifying Git pull.
- Cursor Agent is invoked non-interactively in Ask/read-only mode and returns a JSON patch.
- DocumentKit, not the model, writes cache/spec/docs.
- Cache and docs are transactional: failed validation does not publish the proposed documentation.
- Endpoint grouping is not used as a token-saving strategy.

## Trigger policy

After the one-time initial `document-kit build`, automatic documentation updates can only occur through:

```bash
document-kit pull origin <allowed-branch>
```

Default allowed branches: `develop`, `dev`, `staging`, `stg`, `production`, `prod`.
