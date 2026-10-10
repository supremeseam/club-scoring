# Security policy

## Reporting a vulnerability
Please **don't open a public issue** for a security problem. Use GitHub's private vulnerability reporting
(Security tab -> *Report a vulnerability*) so it can be fixed before details are public.

## What to expect
This is a volunteer-run project. We aim to acknowledge reports within a week and to fix confirmed problems
as quickly as we reasonably can.

## Running your own copy safely
Each club hosts its own copy and is responsible for its server. See `docs/AUTHENTICATION.md` for what the
login protects against and what it doesn't, and `docs/RUNBOOK.md` for hosting hardening (HTTPS, closed ports,
backups). In particular: never publish the app container's port (the lockout logic trusts Caddy's
`X-Forwarded-For`), keep `.env` out of git, and use a long random `SECRET_KEY`.
