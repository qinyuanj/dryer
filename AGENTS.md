# AGENTS.md

## Agent skills

### Issue tracker

Issues live in GitHub Issues on this repo, via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default five-role vocabulary, label string equals role name. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `GLOSSARY.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.

## Host

dryer runs on native Windows x64, and only there. This repository has no POSIX
host to build or test on (ADR 0002 in home-uml-viewer).

CI runs `tests/test_guardrails.py` (process boundary, no CR in golden files) as part of the full suite on every push to main and every pull request; run `.venv/Scripts/python.exe -m pytest tests/test_guardrails.py` before a commit that changes those rules.
