# Rules for AI coding agents

This repo is an open-source race scoring app that any yacht club can deploy. Read `CONTRIBUTING.md` and
`README.md` first. These rules are what a careful maintainer would want every change to respect.

## Never commit club-specific or secret data
- No club names, logos, domains, IP addresses, bucket names, account IDs, admin URLs, usernames, passwords or keys
  in tracked files. Per-club values live in `.env` (git-ignored) and are documented generically in
  `docs/CONFIGURATION.md`.
- `.env`, `data/`, `club-data/` and `frontend/public/brand/*` stay local. Do not add, print or paste their contents.
- Use `seed_demo` data for examples and tests. Never use real boat owners' names or contact details.
- Do not weaken `.gitignore`.

## Verify before saying "done"
- Run `npm test` (pytest, `tsc`, Vitest). Report failures as they are; do not skip or loosen tests to get green.
- A change to scoring (`backend/scoring/`) needs a test with hand-checked expected values. Keep that package free of
  Django imports; the UI only displays what the API returns.
- After changing API schemas run `npm run gen:api` and commit `openapi.json` and `frontend/src/api/schema.d.ts`.
- New models need a migration; `makemigrations --check` must be clean.
- If a UI change can't be checked in a browser, say so instead of implying it was.

## Security rules that must keep holding
- Three login roles: race committee (`rc`), `skipper`, `crew`. Only `rc` may reach `/api/manage/*`. Skippers and
  crew never touch results, ratings, fees or payments. New endpoints get an explicit role; add a test that the
  other roles get 403.
- Public endpoints expose no contact details, payment data or account information. A test enforces it; keep it
  passing and extend it.
- Anonymous writes need the CSRF check, a honeypot and a rate limit. Never trust client-supplied IDs without
  checking ownership.
- Passwords follow `docs/AUTHENTICATION.md` (15+ characters, no composition rules, temporary passwords force a
  change). Never log passwords, tokens or full request bodies.
- Do not store personal data you don't need, and don't put it in URLs.

## Working style
- Match the surrounding code: naming, comment density, idiom. Prefer small, focused commits with a clear message.
- Don't add dependencies without a reason; major version bumps are done by hand, not by bots.
- Ask before anything destructive or outward-facing: deleting data, rewriting git history, force pushing,
  changing branch protection, touching the live server or AWS resources. Approval for one action isn't approval for
  the next.
- Never run against the real database. Use a throwaway `DATA_DIR` for experiments.
- Don't push unless asked. `main` is protected; pushes use the maintainer's bypass, so ask first.
- Documentation changes with behaviour: update `README.md`, the relevant file in `docs/`, and the race committee
  guide when screens change.
- Be honest in reports: say what was and wasn't tested, and flag anything left undone.

## Handy commands
| Task | Command |
|---|---|
| All tests | `npm test` |
| Backend tests only | `npm run test:py` |
| Regenerate API types | `npm run gen:api` |
| Run locally | `npm run dev` (see `README.md`) |
| Deploy (on the server) | `cd /opt/scoring && sudo bash deploy/deploy.sh` |
