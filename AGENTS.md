# AGENTS.md

## Agent skills

### Issue tracker

Issues live in GitHub Issues on this repo, via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default five-role vocabulary, label string equals role name. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `GLOSSARY.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.

Enable the versioned pre-commit hook once per clone with `git config core.hooksPath .githooks`; it runs `tests/test_guardrails.py` (process boundary, no CR in golden files).
