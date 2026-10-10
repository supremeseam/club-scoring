# Club Scoring

PHRF **time-on-distance** race scoring for a yacht club: multiple fleets, saved boats/ratings/courses, Low Point series standings with discards, RC-duty credit, public results and printable podium sheets.

- **Back end:** Django 5 + Django Ninja (Python 3.12+), SQLite, password-only session login (NIST SP 800-63B AAL1), optional TOTP
- **Front end:** React 18 + TypeScript + Mantine, types generated from the API's OpenAPI schema
- **Scoring:** `backend/scoring/` is pure Python (no Django). All scoring happens on the server; the UI only displays it.
- **Hosting plan:** one EC2 t4g.micro running `compose.yml` (Caddy + Django + Litestream → S3), about $9–11/month. See `docs/RUNBOOK.md`.

## Deploy it for your club
This is open source: every club runs its own copy. Run `npm run setup` for a guided `.env`, then follow **[docs/CONFIGURATION.md](docs/CONFIGURATION.md)** (branding, accounts, what to enter in the app) and **[docs/RUNBOOK.md](docs/RUNBOOK.md)** (hosting). Branding (name, logo, colour, time zone) is just settings; no code changes.

## Quick start (local, no AWS)

### Option A: Docker only
```
docker compose -f compose.dev.yml up
```
Open <http://localhost:5173>. First start runs migrations and loads demo data.

### Option B: native (Python 3.12+, [uv](https://docs.astral.sh/uv/), Node 22+)
```
npm install      # also installs the backend with uv (python -m pip install uv if missing)
npm run seed     # migrate + load demo data  (add `-- --reset` to wipe and reseed)
npm run dev      # Django (:8000) and Vite (:5173) together
```
Open <http://localhost:5173>. Plain npm/uv commands, so they work in PowerShell.

**Demo logins** (local only, from `npm run seed`): `editor` / `editor`, `admin` / `admin`. For a real club skip the seed and use `npm run setup:club`.

### Demo data
~20 boats with WL and RL ratings (some missing RL to show the fallback, one negative rating, one mid-season re-rate), three fleets, marks and saved courses, and two series:

- **Wet Wednesdays 2026**: 8 W/L races + 1 abandoned, 1 discard after 5, RC duty credit on, with a tie, DNF, DNC, OCS, DSQ, RCD and RDG.
- **Island Series 2026**: 3 random-leg distance races, one finishing after midnight, combined overall on.

## Commands

| Command | What it does |
|---|---|
| `npm run dev` | Django + Vite with hot reload |
| `npm run seed` | migrate + demo data |
| `npm test` | pytest + `tsc` + Vitest |
| `npm run e2e` | Playwright (phone viewport) against the running dev stack |
| `npm run gen:api` | re-export `openapi.json` and regenerate `frontend/src/api/schema.d.ts` |
| `npm run createsuperuser` | create an editor/admin account |

Run `npm run gen:api` after changing API schemas.

## Production-like local test
```
SITE_ADDRESS=localhost docker compose up --build
```
Runs the production images (Caddy, gunicorn, built React) at <https://localhost> with Caddy's internal CA, so you can check CSP, HSTS, cookies and login. The local `.env` needs `DEBUG=0` and a real `SECRET_KEY`: Django **refuses to start** otherwise.

## Layout
```
backend/   config/ scoring/ boats/ courses/ racing/ api/ results/ tests/
frontend/  src/{api,pages/{public,rc,manage},components,lib}  e2e/
deploy/    Dockerfiles, Caddyfile, litestream.yml, bootstrap.sh, deploy.sh
docs/RUNBOOK.md
```

## Scoring rules implemented
- Corrected time = elapsed − rating × distance (rating in s/nm; can be negative), rounded to the second. Ties split points.
- Ratings are dated rows per rating type (WL, RL, add more in *Fleets & rating types*). Each finish **snapshots** its rating (`exact`, `fallback`, `manual`) so later re-rates never rewrite old results.
- RRS Appendix A Low Point: DNC/DNS/OCS/DNF/RET/DSQ/DNE/UFD/BFD, TLE (as DNF), SCP/ZFP percentage penalties, RDG (entered points or average), A8.1/A8.2 tie-breaks, discards (DNE never discarded).
- Scoring basis per series: entries + 1, or "came to the start" + 1 (DNC is always entries + 1).
- RC duty credit (RCD): off (scores DNC), average of all other races, or average of races before; capped per boat; credits are discarded only after sailed races.
- Abandoned/cancelled races don't count toward discard thresholds.

## Security notes
Same-origin SPA + API behind Caddy, `HttpOnly` session cookies with CSRF header, 15+ character passwords with a blocklist, per-address and per-account login throttling, 12 h idle / 7 day session limits, forced change of temporary passwords, an auth audit log (see `docs/AUTHENTICATION.md`), strict CSP, audit history on starts/finishes (`django-simple-history`), public API exposes only boat name, sail #, design and skipper. Draft series are not public.

## Known limitations
- Online only: if signal drops, use the paper finish sheet and enter times ashore.
- The deploy (EC2/S3/DLM/SSM) steps in `docs/RUNBOOK.md` are written but have not been exercised against a real AWS account.
