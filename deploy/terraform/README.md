# AWS in one command (Terraform)

Creates everything the club's server needs on AWS, about **$10-11 a month**: a small Ubuntu ARM server with a fixed IP, a private versioned S3 bucket for database backups, an access role limited to that bucket and Session Manager (no SSH keys, no port 22), a web-only firewall, weekly disk snapshots, and (optionally) a cost alert.

## One-time setup
1. **AWS account and a signed-in AWS CLI** (`aws sts get-caller-identity` shows who you are). Prefer a club-owned account.
2. **Install Terraform** (or OpenTofu): `winget install -e --id Hashicorp.Terraform`, then open a new terminal.
3. `cd deploy/terraform`, copy `terraform.tfvars.example` to `terraform.tfvars` and edit it (region, budget email).

## Create it
```
terraform init
terraform plan      # read it: nothing is created yet
terraform apply     # type "yes"
```
When it finishes it prints `public_hostname`, `connect_in_browser`, `backup_bucket` and `env_settings`. Wait about a minute, then open the `connect_in_browser` link: you get a shell on the server through the AWS console.

## Put the app on the server
In that browser shell (it runs as a normal user, so use `sudo`):
```
curl -fsSL https://raw.githubusercontent.com/<owner>/<repo>/main/deploy/bootstrap.sh -o bootstrap.sh
sudo bash bootstrap.sh https://github.com/<owner>/<repo>.git
sudo nano /opt/scoring/.env     # paste the lines from `env_settings`, then set CLUB_NAME, TIME_ZONE, ...
cd /opt/scoring && sudo bash deploy/deploy.sh
sudo docker compose exec app python manage.py setup_club --username <you>
```
`bootstrap.sh` installs Docker, automatic security updates, swap and a nightly session cleanup, and writes `.env` with a random `SECRET_KEY`. Caddy then gets a real HTTPS certificate for `public_hostname`, which is a free `<ip>.sslip.io` name pointing at the server's fixed IP (Let's Encrypt refuses certificates for Amazon's own `*.amazonaws.com` hostnames). Open `https://<public_hostname>` to check.

## Moving your existing data and logos up
On your computer, from the project folder (the bucket name comes from `terraform output backup_bucket`):
```
python -c "import sqlite3; s=sqlite3.connect('data/db.sqlite3'); d=sqlite3.connect('db-upload.sqlite3'); s.backup(d); d.close(); s.close()"
aws s3 cp db-upload.sqlite3 s3://<bucket>/transfer/db.sqlite3
aws s3 cp frontend/public/brand/ s3://<bucket>/transfer/brand/ --recursive --exclude README.md
```
On the server:
```
sudo snap install aws-cli --classic
cd /opt/scoring && sudo docker compose stop app
sudo mkdir -p /tmp/transfer && sudo aws s3 cp s3://<bucket>/transfer/ /tmp/transfer/ --recursive
sudo docker run --rm -v scoring_data:/data -v /tmp/transfer:/src:ro alpine sh -c "cp /src/db.sqlite3 /data/db.sqlite3 && chown 10001 /data/db.sqlite3"
sudo mkdir -p frontend/public/brand && sudo cp /tmp/transfer/brand/* frontend/public/brand/
sudo docker compose --profile backup up -d
sudo aws s3 rm s3://<bucket>/transfer/ --recursive && sudo rm -rf /tmp/transfer
```
The database contains boat owners' contact details: delete `db-upload.sqlite3` from your computer afterwards.

## Switching to your own domain later
Point an **`A` record (IPv4 only, no `AAAA`)** at `public_ip`, then change `SITE_ADDRESS`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` and `PUBLIC_URL` in `/opt/scoring/.env` and run `sudo docker compose --profile backup up -d`. Everyone is signed in again once.

## Good to know
- **State:** Terraform keeps what it created in `terraform.tfstate` here (git ignores it). Back that file up and keep it private. Lose it and Terraform no longer knows the resources exist.
- **Cost alert:** the budget covers the whole AWS account, not just this project.
- **Tear down:** `terraform destroy`. It refuses to delete the backup bucket while it holds backups, on purpose.
- The server image is ARM (`t4g`); changing `instance_type` to an x86 type needs a different image.
- A newer Ubuntu image never replaces a running server (the image is ignored after creation). Patches arrive through automatic security updates.
