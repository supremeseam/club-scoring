# Contributing

Thanks for helping!

**Improvements belong upstream.** If you fix a bug or add a feature in your club's copy, we ask that you send it
back as a pull request to this repository rather than keeping it only in your fork. Everyone then gets the fix, and
your club won't have to re-apply your changes every time we release an update. This is a request, not a condition of
using the software, which is MIT licensed. Small, focused pull requests are welcome.

Quick rules:

- `npm test` must pass (pytest, `tsc`, Vitest). Scoring changes need a test in `backend/tests/test_scoring.py` with hand-checked expected values.
- Keep scoring in `backend/scoring/` (no Django imports). The UI only displays what the API returns.
- After changing API schemas run `npm run gen:api` and commit `openapi.json` and `frontend/src/api/schema.d.ts`.
- Never put club-specific names, colours or domains in code; use settings in `.env` (see `docs/CONFIGURATION.md`).
- Public API responses must not expose contact details; a test enforces it.
- Report security issues privately to the maintainers rather than in a public issue.
