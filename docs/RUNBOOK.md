# Runbook

Ownership: the AWS account, domain and GitHub repo belong to **the club** (club email and billing, with the maintainers invited as admins). At least one other member has admin access to AWS and the app.

## Provision AWS and first deploy
There are two ways to host it; pick one. **Lightsail** (`deploy/terraform-lightsail/`, about $7/month, a flat price that includes the IP and disk) is the cheaper one: follow **`deploy/terraform-lightsail/README.md`**, which points back to the steps below. **EC2** (`deploy/terraform/`, about $10-11/month, uses an IAM role instead of an access key) is described here. Everything on AWS is created by Terraform; follow **`deploy/terraform/README.md`**. In short:

1. `terraform apply` creates the server (Ubuntu 24.04 ARM `t4g.micro`, encrypted disk, IMDSv2 required, fixed IP), a private versioned S3 backup bucket, an access role limited to that bucket and Session Manager, a firewall allowing only ports 80 and 443 (IPv4, no SSH), weekly disk snapshots (4 kept) and an optional budget alert.
2. Connect with **Session Manager** (the link Terraform prints), run `deploy/bootstrap.sh`, edit `/opt/scoring/.env` (Terraform prints the lines), then `bash deploy/deploy.sh`.
3. Create the first admin: `docker compose exec app python manage.py setup_club --username <you>`.
4. DNS when you have a domain: an **`A` record only** (IPv4) pointing at the Elastic IP. Don't add an `AAAA` record: see `docs/AUTHENTICATION.md` (client IPs). Until then use the free `<ip>.sslip.io` name Terraform prints (Let's Encrypt won't issue certificates for Amazon's own hostnames).

If you'd rather not use Terraform, create the same pieces by hand: S3 bucket (versioning on, public access blocked); an instance role with `AmazonSSMManagedInstanceCore` plus read/write on that bucket only; the EC2 instance as above; a Data Lifecycle Manager weekly-snapshot policy; an AWS Budgets alert.

## Routine deploy
`cd /opt/scoring && bash deploy/deploy.sh` (git pull, build both images, restart; migrations run on container start).

## Serve under a sub-path of your main website (optional)
To show the app at, say, `https://<club domain>/results/` instead of its own address, set `BASE_PATH=/results` in
`.env` (leading slash, no trailing slash) and rebuild: `bash deploy/deploy.sh`. The setting is baked into the front
end at build time, so changing it needs a rebuild. Caddy removes the prefix before Django sees the request, and
Django, the admin, the PDFs and the logo URLs all follow it. Leave it unset to serve at the site root (the default).
Local test: `BASE_PATH=/results npm run dev`, then open <http://localhost:5173/results/>.

**Behind CloudFront.** The route must pass `/results/*` through to this server unchanged, with these headers: the
visitor's `Authorization`, `Origin`, `Referer`, `X-CSRFToken`, cookies, and `CloudFront-Viewer-Address`; and CloudFront
must reach the server by its own HTTPS name (not forward the visitor's `Host`). The app takes the client IP for login
lockouts from the right-most `X-Forwarded-For` entry that Caddy writes, so by default every visitor would look like
CloudFront and lock each other out. To avoid that, give CloudFront a shared secret to send as `X-Origin-Verify` and
set the same value as `ORIGIN_VERIFY_SECRET` in `.env`: Caddy then reads the visitor's address from
`CloudFront-Viewer-Address`, but only on requests that carry the secret (a client cannot fake either header, and
with no secret set the header is never trusted). Also add the website's address to `CSRF_TRUSTED_ORIGINS`, because
the browser's requests come from the website, not from this server's own name. The website's Terraform
(`results.tf` in ayc-website) builds the route and prints all of these settings.

## Add a race committee (RC) account
1. Log in at `https://<site>/<ADMIN_URL>` as a superuser → Users → add user. Any active account can enter results; don't tick *Staff* or *Superuser* unless they also administer the site.
2. Set a **temporary** password (15+ characters; the same rules apply as for everyone). Make one with `python -c "import secrets;print(secrets.token_urlsafe(16))"` and send it privately.
3. At their first login they are required to choose their own password before they can do anything else.

## Skipper and crew logins
The race committee approves skipper logins in the app (*Crew board*); see `docs/CREW.md`. Reset or disable one in the site admin like any account. After upgrading, run the migrations (`deploy.sh` does) so existing accounts keep the race-committee role.

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
