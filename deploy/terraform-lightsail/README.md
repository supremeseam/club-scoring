# AWS Lightsail in one command (Terraform)

The cheaper way to host the club's server: **about $7 a month** for a 1 GB Lightsail plan that already includes the disk, the fixed IP and the traffic, plus pennies for the S3 backups. (Plan prices change; `aws lightsail get-bundles --region us-east-1` lists the current ones. `bundle_id` in `terraform.tfvars` picks the plan.) The EC2 version in `../terraform` costs about $10-11 and uses an IAM role instead of an access key; pick one, not both.

It creates a Lightsail Ubuntu 24.04 server with a static IP, a web-only firewall (SSH only from the Lightsail console's browser terminal), a private versioned S3 bucket for database backups, an IAM user that can use only that bucket, and (optionally) a cost alert.

## One-time setup
1. **AWS account and a signed-in AWS CLI** (`aws sts get-caller-identity` shows who you are). Prefer a club-owned account.
2. **Install Terraform** (or OpenTofu): `winget install -e --id Hashicorp.Terraform`, then open a new terminal.
3. `cd deploy/terraform-lightsail`, copy `terraform.tfvars.example` to `terraform.tfvars` and edit it.

## Create it
```
terraform init
terraform plan      # read it: nothing is created yet
terraform apply     # type "yes"
```
It prints `public_hostname`, `connect_in_browser` and `backup_bucket`. Wait about a minute, then open the `connect_in_browser` link: you get a shell on the server from the Lightsail console.

## Put the app on the server
The steps are the same as for EC2, with two differences: you connect with the link above, and the `.env` lines include a backup access key, so print them with
```
terraform output -raw env_settings
```
Then follow **"Put the app on the server"** in [`../terraform/README.md`](../terraform/README.md) (bootstrap, edit `/opt/scoring/.env`, `deploy.sh`, `setup_club`), and the same sections there for moving existing data and for switching to your own domain.

## Good to know
- **The access key is in two places:** the Terraform state file (`terraform.tfstate`, which git ignores; keep it private and backed up) and `/opt/scoring/.env` on the server. To replace it, run `terraform apply -replace=aws_iam_access_key.backup`, then update `.env` and run `sudo docker compose --profile backup up -d`.
- **Backups:** the database is replicated to S3 continuously. Whole-disk Lightsail snapshots are off by default because they are billed per GB; set `automatic_snapshots = true` if you want them.
- **Cost alert:** the budget covers the whole AWS account, not just this project.
- **Tear down:** `terraform destroy`. It refuses to delete the backup bucket while it holds backups, on purpose.
- **Size:** `micro_3_0` has 1 GB of memory, like the EC2 `t4g.micro`. The smaller `nano_3_0` plan (512 MB) is untested.
- The server is x86, not ARM like the EC2 option; the app's Docker images build on both.
