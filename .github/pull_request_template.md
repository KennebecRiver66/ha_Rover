<!--
Thanks for contributing. Please keep the safety checklist honest - the cookie is a
full-access credential, and sitter names are someone else's personal data.
-->

## What this changes

<!-- What behaviour a user would notice. If it fixes an issue, link it. -->

## Why

<!--
The reasoning, not the diff. If it changes one of the decisions listed in
CONTRIBUTING.md (cookie auth, no booking times, the slow poll, the three distinct
failure modes, the session sensor staying available, diagnostics redaction,
read-only), say what new evidence justifies it.
-->

## How it was tested

<!-- Which tests were added, and anything checked by hand in a running Home Assistant. -->

## Checklist

- [ ] No real cookie value, sitter name, phone number, address, profile URL or account username anywhere — including tests, fixtures and commit messages
- [ ] `python -m pytest` passes, and new behaviour has a test
- [ ] `ruff check .` passes
- [ ] `python3 scripts/sync_translations.py` run if `strings.json` changed
- [ ] `manifest.json` version bumped and `CHANGELOG.md` updated, if this is user-visible
- [ ] README updated, if this changes setup or what the entities do
