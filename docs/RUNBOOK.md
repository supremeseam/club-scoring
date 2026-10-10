# Runbook

Ownership: the AWS account, domain and GitHub repo belong to **the club** (club email and billing, with the maintainers invited as admins). At least one other member has admin access to AWS and the app.

## Provision AWS (one time)
1. **S3 bucket** for Litestream backups: versioning on, block all public access.
2. **IAM role** for the instance: `AmazonSSMManagedInstanceCore` plus an inline policy allowing `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject`, `s3:ListBucket` on that bucket only.
3. **EC2**: Ubuntu 24.04 LTS arm64, `t4g.micro`, encrypted 10 GB gp3 root volume, the role above, **IMDSv2 required**, hop limit 1.
   Security group: inbound **80 and 443 only** (no port 22). Attach an Elastic IP.
4. **Data Lifecycle Manager** policy: weekly EBS snapshots, retain 4.
5. **AWS Budgets** alert at $12/month.
6. DNS: A record `results.yourclub.org` → the Elastic IP (club's existing DNS, or Route 53).

## First deploy
1. Connect with **SSM Session Manager** (Systems Manager → Session Manager).
2. `sudo bash deploy/bootstrap.sh https://github.com/<club>/<repo>.git` (installs Docker, unattended-upgrades, 1 GB swap, a nightly `clearsessions` job, and writes `/opt/scoring/.env` mode 600 with `DEBUG=0` and a random `SECRET_KEY`).
3. Edit `/opt/scoring/.env`: `SITE_ADDRESS`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS=https://results.yourclub.org`, `PUBLIC_URL`, `CLUB_NAME`, `TIME_ZONE`, `ADMIN_URL`, `LITESTREAM_BUCKET`, `LITESTREAM_REGION`.
4. `cd /opt/scoring && bash deploy/deploy.sh`. Caddy obtains the Let's Encrypt certificate automatically.
5. Create the first admin: `docker compose exec app python manage.py createsuperuser`.

## Routine deploy
`cd /opt/scoring && bash deploy/deploy.sh` (git pull, build both images, restart; migrations run on container start).

## Add a race committee (RC) account
1. Log in at `https://<site>/<ADMIN_URL>` as a superuser → Users → add user. Any active account can enter results; don't tick *Staff* or *Superuser* unless they also administer the site.
2. Set a **temporary** password (15+ characters; the same rules apply as for everyone). Make one with `python -c "import secrets;print(secrets.token_urlsafe(16))"` and send it privately.
3. At their first login they are required to choose their own password before they can do anything else.

## Forgotten password
Admin → Users → the person → *this form* link next to Password → set a new temporary password. They are signed out everywhere and must choose a new one at next login. From a shell: `docker compose exec app python manage.py changepassword <user>` then `... force_password_change <user>`.

## Locked out
After 10 failed logins from one address that address waits 15 minutes; after 100 failures against one account (any addresses) the account waits up to an hour. To clear it now: `docker compose exec app python manage.py unlock_account <user>`; for an address: `... axes_reset_ip <ip>`.

## Read the login audit log
`docker compose logs app | grep AUTH` shows logins, failures, lockouts, password changes and admin resets (never passwords).

## Optional: require a TOTP code (2FA)
Set `REQUIRE_2FA=1` in `.env`, restart, then Admin → *TOTP devices* → add a confirmed device per user and share the key privately. Reset it by deleting their device and adding a new one.

## Restore from backup
Litestream (continuous, point-in-time):
```
docker compose --profile backup stop litestream app
docker compose run --rm --no-deps -v scoring_data:/data litestream restore -if-replica-exists -o /data/db.sqlite3 -config /etc/litestream.yml /data/db.sqlite3
docker compose --profile backup up -d
```
(Prove it works: run `litestream restore` onto a laptop from the bucket and open the file with `sqlite3`.) Fallback: restore the latest weekly EBS snapshot.

## Season rollover
Manage → Series → select the series → **Copy series (no results)**. Copies fleets, rules, entry list and a schedule shifted by 364 days (same weekday). Review dates and the entry list, then set status to *active*.

## Renewing the domain
Renew with the club's registrar account; the TLS certificate renews itself via Caddy.

## Verification checklist after deploy
- `https://<site>` loads; `http://<site>` redirects to HTTPS; response headers include CSP and HSTS.
- Race committee (RC) login works with a 15+ character password; 10 bad logins from one address are locked out for 15 minutes; a temporary password forces a change.
- From outside: `nmap -p 22,80,443 <ip>` shows only 80 and 443 open. SSM shell works with port 22 closed.
- `systemctl status unattended-upgrades` is active.
- IMDSv1 rejected: `curl -s -o /dev/null -w "%{http_code}" http://169.254.169.254/latest/meta-data/` returns 401.
- Backups work (restore test above); Budgets alert exists.
