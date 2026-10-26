# Authentication

Scope: a public website where anyone can read results and a few trusted **race committee (RC)** accounts can change them. The goal is to stop casual tampering, not to defend nation-state targets. It follows **NIST SP 800-63B-4** at **AAL1** (a password, one factor) with no identity provider and no paid services. A TOTP code can be required as an extra (`REQUIRE_2FA=1`), but it is off by default.

## How it meets NIST SP 800-63B

| Requirement | How it's met | Status |
|---|---|---|
| Password length: 15+ when a password is the only factor; accept at least 64 | Minimum **15** (`PASSWORD_MIN_LENGTH`); up to **256** accepted and never truncated | Met |
| No composition rules; allow spaces and all Unicode; allow paste | None imposed. Spaces, any characters and pasting work; the password box has a show/hide toggle | Met |
| Blocklist of common/compromised and context-specific passwords | Django's 20,000 common-password list plus `accounts/validators.py`: blocks the username, name, club names, obvious words, repeated patterns and simple runs | Partial: offline lists only, no online breached-password lookup (a deliberate choice) |
| No periodic rotation, no hints, no security questions | None exist. Passwords change only on request or after an administrator-set temporary password | Met |
| Store passwords salted and hashed with an approved function | Django's salted **PBKDF2-SHA256**, upgraded automatically | Met |
| Rate-limit failed attempts (at most 100 consecutive failures per account) | 10 failures per IP address then a 15-minute wait; 100 failures per account across all addresses in an hour then a wait (`accounts/security.py`); a wrong current password in "change password" counts too | Met |
| TLS for all authentication traffic | HTTPS through Caddy, HSTS, `Secure` cookies, HTTP redirected | Met |
| Session management | Random server-side sessions; `HttpOnly`, `SameSite=Lax`, `Secure`; new session on login; **12 h idle** and **7 day absolute** limits; logout destroys the session; changing a password signs every other session out | Met |
| Changing a password requires the current one | `POST /api/auth/change-password` | Met |
| Authenticator lifecycle / recovery | An administrator sets a **temporary password**; the person must replace it at first login. No email recovery | Partial (admin-mediated by design) |
| Event logging | One line per login, failure, lockout, logout, password change and admin reset on the `auth` log; passwords are never logged | Met |
| Multi-factor | Not required. Optional TOTP via `REQUIRE_2FA=1` | Not at AAL2 (by choice) |

## What an attacker faces
- **Guessing from one address:** after 10 failed logins that address is blocked for 15 minutes. They only lock themselves out, never a real user on another address.
- **Guessing from many addresses at one account:** counted per account; at 100 failures in an hour the account is paused until the window clears or an administrator runs `unlock_account`.
- **Weak passwords:** 15+ characters and the blocklist make online guessing impractical.
- **Stolen/old sessions:** idle for 12 hours or 7 days old, and they die. Changing the password ends all other sessions.
- **Forged requests:** CSRF tokens on every write, strict `SameSite`, same-origin API, strict CSP.
- **Public endpoints can't change anything.** Only logged-in accounts can write, and payment and contact details are never in public responses.

## How client IPs are worked out (important)
Lockouts are per IP. In production Caddy is the only way in and **overwrites `X-Forwarded-For`** with the real client address; the app uses the **right-most** entry (`accounts/ip.py`). IPv6 addresses are grouped by /64. **Never publish the app container's port.** In development there is no proxy and the header is ignored (`BEHIND_PROXY`).

**Behind CloudFront** (the app served under the club's main domain) the only change is where Caddy reads the address from. When `ORIGIN_VERIFY_SECRET` is set, a request carrying `X-Origin-Verify` equal to it is treated as coming through CloudFront, and the visitor's address is taken from `CloudFront-Viewer-Address` (`ip:port` or `[ipv6]:port`, port removed). Everything else, including a request with a wrong or missing secret, a malformed address, or any request when no secret is set, is identified by its connecting address as before. Both CloudFront headers are removed before the request reaches the app, and `X-Forwarded-For` is always overwritten. `backend/tests/test_caddy_proxy.py` runs the real Caddy in Docker to check this. Don't put any other proxy in front without extending those tests.

**Use IPv4 only.** On a Linux server Docker preserves each visitor's real IPv4 address, but for IPv6 it can substitute its own gateway address, which would make every IPv6 visitor look like a single client to the lockout. The runbook creates an IPv4 address and an `A` record only: **don't add an `AAAA` (IPv6) record** or enable IPv6 on the instance unless you've verified the address the app logs (`docker compose logs app | grep AUTH`) is the visitor's.

This was checked in a production-style run: with Caddy in front, a forged `X-Forwarded-For` made no difference to the recorded address, and the lockout engaged on the 10th failed attempt.

## Configuration
| Setting | Default | Meaning |
|---|---|---|
| `REQUIRE_2FA` | `0` | Also require a TOTP code (add a device per user in the admin) |
| `SESSION_ABSOLUTE_MAX_SECONDS` | `604800` | Longest a login can last |
| `BEHIND_PROXY` | on when `DEBUG=0` | Trust the right-most `X-Forwarded-For` |
Fixed in `settings.py`: `PASSWORD_MIN_LENGTH` 15, `PASSWORD_MAX_LENGTH` 256, idle timeout 12 h (`SESSION_COOKIE_AGE`), `AXES_FAILURE_LIMIT` 10, `AXES_COOLOFF_TIME` 15 min, `ACCOUNT_FAILURE_LIMIT` 100 per `ACCOUNT_FAILURE_WINDOW_MINUTES` 60.

## Optional: sign in with Amazon Cognito
Everything above describes the default (`AUTH_MODE=password`). A club that already runs a Cognito user pool, for example
for its website, can let that pool sign people in instead, so a sailor has one account for both. Set `AUTH_MODE=cognito`:

| Setting | Meaning |
|---|---|
| `COGNITO_POOLS` | `userPoolId:appClientId`, comma separated (e.g. a members pool and an admins pool). Only ID tokens issued to those app clients are accepted |
| `COGNITO_RC_GROUPS` | Cognito groups whose members are race committee (default `admins`) |
| `COGNITO_SIGN_IN_URL` | The club website's sign-in page; the Sign in button sends people there |
| `COGNITO_TOKEN_STORAGE_KEYS` | Session-storage keys, in preference order, where that page keeps `{idToken, refreshToken, ...}` (first usable one wins) |
| `CSP_CONNECT_EXTRA` | Extra address Caddy lets the page call; for token renewal set it to `https://cognito-idp.<region>.amazonaws.com` |

How it works: the browser sends the person's **ID token** as `Authorization: Bearer ...` on every request. The server
checks its RS256 signature against the pool's published keys (fetched from the pool's own `cognito-idp` address, which is
built from `COGNITO_POOLS`, never from the token), the issuer, audience (our app clients), expiry and `token_use=id`.
Cookies and CSRF play no part, and a leftover Django session never authenticates a request in this mode.

- **Accounts:** the first valid token creates a local account keyed by the person's Cognito `sub` (never by email), with
  no usable password. Name and email are copied for display. Switching someone off in the Django admin (untick *Active*)
  blocks them here too.
- **Roles follow Cognito:** in a `COGNITO_RC_GROUPS` group means race committee, checked on every request, so removing
  the group takes effect immediately (until the token expires, the person is just crew). Everyone else is `crew`, or
  `skipper` once the committee links a boat to them (*Crew board, Boat links*); committee members can be linked too.
- **Switched off in this mode:** `/auth/login`, change password, crew self-registration, skipper login requests and
  creating or approving password skipper logins all return 404. The Django admin at `ADMIN_URL` keeps its own
  password login as a break-glass route; give it only to the people who need it.
- **MFA** is whatever the Cognito pool enforces (`REQUIRE_2FA` does not apply).
- **Renewal:** Cognito ID tokens are short-lived (15 minutes to an hour). When the stored one has expired, the page calls
  Cognito's `InitiateAuth` with the refresh token the website's sign-in page saved, stores the new tokens in the same place,
  and carries on; a 401 triggers one renewal and one retry. It only ever contacts a pool and app client listed in
  `COGNITO_POOLS` (sent to the browser in `/config`) and never changes the stored session when Cognito refuses. This needs
  Caddy's security policy to allow the call: set `CSP_CONNECT_EXTRA=https://cognito-idp.<region>.amazonaws.com`. A pool
  whose sign-in keeps no refresh token (the admins pool signs in through Cognito's hosted page) simply asks the person to
  sign in again when the token ends.
- **Sign out** only forgets the tokens in this browser tab; it does not revoke them at Cognito. Tokens expire on their own.
- **Keys:** a pool's keys are cached for an hour and re-fetched for an unknown key id at most every 10 seconds, so
  garbage tokens can't make the server hammer Cognito. If the keys can't be fetched, requests are refused, not trusted.
- Requires the `pyjwt[crypto]` package (in `pyproject.toml`).

## Everyday tasks (see `RUNBOOK.md`)
- **New RC account:** admin → Users → add (temporary password; the person is forced to choose their own).
- **Forgot password:** admin sets a new temporary password; the person is signed out everywhere.
- **Locked out:** `manage.py unlock_account <user>` (account) or `manage.py axes_reset_ip <ip>` (address).
- **Read the audit log:** `docker compose logs app | grep AUTH`.
- Don't tick *Staff*/*Superuser* for RC accounts: those are administrators who can reach the Django admin.

## Not covered (be aware)
- **No mandatory MFA** (AAL2). A guessed or phished password is enough to sign in. The 15-character rule and throttling make guessing impractical; phishing is not addressed.
- **No email self-service recovery.** An administrator is the recovery path, so keep at least two administrators.
- **No online breached-password check** (Have I Been Pwned), so a breached password that isn't on the offline list can still be chosen.
- **Public pages aren't rate-limited.** Scraping or hammering PDF generation is a nuisance, not an integrity risk; add a CDN or Caddy rate-limit module if it becomes one.
- **No CAPTCHA, no password-strength meter, no Unicode normalization of passwords.**
- **Distributed credential stuffing** is bounded only by the per-account limit.
- Anyone with access to the server or the SQLite file has everything; host hardening is covered in `RUNBOOK.md`.
