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
Lockouts are per IP. In production Caddy is the only way in and **overwrites `X-Forwarded-For`** with the real client address; the app uses the **right-most** entry (`accounts/ip.py`). IPv6 addresses are grouped by /64. **Never publish the app container's port** and don't put another proxy or CDN in front without revisiting this, or lockouts can be spoofed. In development there is no proxy and the header is ignored (`BEHIND_PROXY`).

## Configuration
| Setting | Default | Meaning |
|---|---|---|
| `REQUIRE_2FA` | `0` | Also require a TOTP code (add a device per user in the admin) |
| `SESSION_ABSOLUTE_MAX_SECONDS` | `604800` | Longest a login can last |
| `BEHIND_PROXY` | on when `DEBUG=0` | Trust the right-most `X-Forwarded-For` |
Fixed in `settings.py`: `PASSWORD_MIN_LENGTH` 15, `PASSWORD_MAX_LENGTH` 256, idle timeout 12 h (`SESSION_COOKIE_AGE`), `AXES_FAILURE_LIMIT` 10, `AXES_COOLOFF_TIME` 15 min, `ACCOUNT_FAILURE_LIMIT` 100 per `ACCOUNT_FAILURE_WINDOW_MINUTES` 60.

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
