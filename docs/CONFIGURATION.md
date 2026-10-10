# Configuring the app for your club

Each club runs **its own copy** (its own server, database and domain). Everything club-specific is either an environment setting in `.env` (below) or data you enter in the app under **Manage**. There is nothing to edit in the code.

## 1. Guided setup
```
npm install
npm run setup        # asks for club name, colour, logo, time zone, domain; writes .env
npm run migrate
npm run setup:club -- --fleets "PHRF A,PHRF B,Non-Spinnaker"    # creates your first admin login
npm run dev          # local preview at http://localhost:5173
```
Leave the domain blank for a local preview. Give a domain and `setup` writes production-safe settings (`DEBUG=0`, a random `SECRET_KEY`).

## 2. Settings (`.env`)
Changes need an app restart only; the front end reads branding from the server, so no rebuild.

| Setting | Meaning | Default |
|---|---|---|
| `CLUB_NAME` | Full name: home page heading, PDFs | `Your Yacht Club` |
| `CLUB_SHORT_NAME` | Header and browser tab title | club name |
| `CLUB_TAGLINE` | Line under the home heading | blank |
| `BRAND_COLOR` | Accent colour: blue, cyan, teal, green, lime, yellow, orange, red, pink, grape, violet, indigo | `blue` |
| `CLUB_LOGO_URL` | Header logo. A URL, or `/logo.png` with the file in `frontend/public/` (rebuild the front end to ship a new file) | blank |
| `TIME_ZONE` | IANA zone for race times, e.g. `America/Los_Angeles` | `America/New_York` |
| `PUBLIC_URL` | Public site address printed in PDF footers | `http://localhost:5173` |
| `ALLOWED_HOSTS` | Host names Django serves (your domain) | localhost |
| `CSRF_TRUSTED_ORIGINS` | `https://your.domain` in production | blank |
| `SITE_ADDRESS` | Domain Caddy gets a certificate for (`localhost` for a local HTTPS test) | `localhost` |
| `ADMIN_URL` | Path of the Django admin; move it off the default | `manage-admin/` |
| `DEBUG` / `SECRET_KEY` | In production use `0` and a long random value. Django refuses to start otherwise. | dev values |
| `REQUIRE_2FA` | Optional: require a TOTP code at login (password-only is the default; see `docs/AUTHENTICATION.md`) | `0` |
| `SESSION_ABSOLUTE_MAX_SECONDS` | Longest a login can last, however active (idle limit is fixed at 12 h) | 604800 (7 days) |
| `LITESTREAM_BUCKET`, `LITESTREAM_REGION` | Optional S3 backups | blank |

## 3. Data you enter in the app (Manage menu)
1. **Fleets & rating types.** WL and RL come pre-seeded. Add others (distance, non-spinnaker) and optional fallbacks, e.g. "RL missing → WL − 6 s/nm".
2. **Boats & ratings.** Add by hand or import a CSV (`sail,name,design,skipper,fleet,WL,RL`, one column per rating type code).
3. **Marks & courses.** Mark positions give distances; or enter a distance directly.
4. **Series.** Fleets, discards, scoring basis, RC-duty credit, combined overall, optional schedule, entry list. *Copy series* rolls a season forward.

## 4. Accounts
- First admin: `npm run setup:club` (or `npm run createsuperuser`).
- More race committee accounts: Django admin at `/<ADMIN_URL>` → Users. Any active account can enter results; there is no public signup. Set a temporary password; the person must choose their own at first login.
- Passwords: 15+ characters, any characters, no complexity rules; common and club-related passwords are refused. Forgotten passwords are reset by an administrator (no email). See `docs/AUTHENTICATION.md`.

## 5. Where to host
Any machine that runs Docker works: `docker compose up -d --build` with `SITE_ADDRESS` set to your domain gives HTTPS automatically. `docs/RUNBOOK.md` describes the AWS EC2 setup (about $9–11/month), but a small VPS from any provider is equivalent; skip the AWS-specific steps and the optional `backup` profile if you back up another way (the data is one SQLite file in the `data` volume).

## 6. Rules your club may need to change
Scoring rules live in `backend/scoring/` (pure Python, with golden tests in `backend/tests/`). Series options cover the common variations; for anything else, change the engine and add a test.

## 7. Importing what you already have
- **Excel scoring workbook** (boats list, one sheet per race): `python -m uv run --project backend python backend/manage.py import_workbook path/to/workbook.xlsx` (add `--races 1,2` for more races). Each imported finish is checked against the sheet's own corrected time and any difference is reported.
- **Course chart:** write marks and numbered courses to a JSON file (format in `backend/racing/management/commands/load_courses.py`) and run `manage.py load_courses file.json`.
- Keep real club data (workbooks, JSON with member details) out of the repository; `data/` and `club-data/` are git-ignored.

## 8. Handicap methods
Each rating type has a method: **time-on-distance** (corrected = elapsed − rating × distance, with the allowance rounded to a whole second like most club sheets) or **time-on-time** (corrected = elapsed × TCF, e.g. ORCA). Add types under *Fleets & rating types*.

## 9. Entry fees, payments and members
Fees are optional and set **per series** (Manage → Series → settings), so each series can charge differently:
- **Series fee** and **fee per race**, plus optional lower **member** fees.
- **Require payment to be scored:** a boat scores in a race only if it paid for the whole series or for that race. A boat that hasn't paid is shown as a *guest*: it appears in the results and is ranked "as if entered", but never changes a paying boat's score. A boat that paid for only some races gets DNC for the rest.
- **Members:** mark boats as members (Boats page; `import_workbook` marks boats whose home club matches `CLUB_SHORT_NAME`). On any race you can tick **Members race free**; members then need no payment for that race.
- **Recording payments:** Manage → Series → Payments, or the **Paid $40** button beside an unpaid boat on the RC screen. The amount defaults to the fee (the member fee for members) and the date to today; both can be changed, and a method (cash, check...) can be noted.
- Payment details are visible to editors only. Public pages say only "guest".
- A **single race** has its own fee, set when you create it.

## 10. Look and feel (branding)
Everything visual is driven by a few settings plus two small files, so restyling never means hunting through screens.

| Setting | What it does |
|---|---|
| `APP_NAME` | The product name in the header, hero banner and browser tab (e.g. `Harbor Race Hub`) |
| `BRAND_COLOR_HEX` | One exact colour (`#rrggbb`, e.g. your burgee's navy). The whole palette is derived from it: buttons, banner gradient, table headers, badges, links. Light and dark mode both work. |
| `CLUB_BURGEE_URL` | The burgee/flag on its own: header, browser-tab icon, sign-in page, home banner |
| `CLUB_LOGO_URL` | The full logo (flag + name). Use a **PNG or JPG** so it can also appear at the top of the printed podium/standings PDFs |

Put the image files in `frontend/public/brand/` and refer to them as `/brand/yourfile.png`. The folder's contents are **not tracked by git** (they are your club's, not the project's): in development they are served from there, and in production `compose.yml` mounts the same folder, so upload the files to that folder on the server and no rebuild is needed. Without a burgee a plain pennant is shown.

To change the design itself, edit **`frontend/src/theme.ts`** (fonts, rounding, colour scale) and **`frontend/src/styles.css`** (hero banner, medals, podium, tables). Reusable pieces live in `frontend/src/components/Brand.tsx` (burgee, hero, footer, medals) and `Podium.tsx`.

## 11. Penalties and protests
- **Standard codes only.** On the RC screen each boat's status list explains every code (OCS, UFD, BFD, DSQ, DNE, RET, TLE, RDG, SCP, ZFP, RCD...). Choosing a code pre-fills a standard reason (e.g. "Scoring Penalty taken (RRS 44.3)") and, for SCP, the standard 20%. Edit the wording in `frontend/src/lib/penalties.ts` to match your sailing instructions.
- **Reasons are public.** The reason you type on a finish appears on the public race page ("Penalties & notes"), on the printed podium sheet, and in the boat's history. Common RRS rules are offered as suggestions while you type.
- **Protest log (editors only).** Each race has a Protests panel: protestor (or race committee), protested boats, rules alleged, status (filed / heard / decided / withdrawn) and the decision. The public sees only "Protest pending" while one is open; names, rules and the decision stay private.
- **Results can't be marked final while a protest is pending.** After a decision, change the boat's status/penalty/points and add the reason; standings rescore immediately and the edit is recorded in the audit history (Django admin → Finishes / Protests → History).
- Time penalties (adding minutes to elapsed time) are not supported; the app uses the standard place-based penalties.

## 12. Changing a boat's fleet, or removing a boat from a race
On the RC screen every boat has a **⋯** menu:
- **Change fleet…**
  - *This race only:* the boat's result moves to the other fleet's start in this race and is rescored (start time, distance and rating type of that start). The boat's series fleet is unchanged, and the series standings still list it with its own fleet. The other fleet's start must exist, and the boat needs a result in this race.
  - *The rest of the series:* the boat's fleet changes in the standings. Results in earlier races stay in the starts where it raced; optionally this race's result moves too.
- **Remove from race…**
  - *Clear this race's result* deletes the finish time, status and penalty. The boat stays entered and scores DNC for the race (as any entrant that did not sail).
  - *Remove from the series* also takes it off the entry list. Refused while the boat has results in other races. Payments already recorded are kept.

## 13. Required fields and editing from the race screen
- **Nothing is saved without what the calculation needs.** Required fields are marked with a red `*` and the Save button stays disabled until they are valid (the server enforces the same rules):
  - *Start:* rating type, date, time, and (for time-on-distance) a distance greater than zero, from a course that has one or entered directly. Time-on-time (ORCA) needs no distance.
  - *Finish:* a valid time not before the start, and a rating for the boat. If it has none you can add it right there or type one for this race. A time-on-time rating (TCF) must be greater than zero. A scoring penalty needs its percentage.
  - *Series:* a name, at least one fleet, and a fee when payment is required. *Course:* a name, a type, and at least two marks or a distance. *Boat:* a name and sail number.
- **Boat details without leaving the race.** Each boat's **⋯** menu has *Edit boat details…* and *Ratings…*. When a start lists boats with no rating of its type, each gets an *Add … rating for <boat>* button that opens the ratings window with the right type and the race date already filled in.
