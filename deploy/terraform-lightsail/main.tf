# The club's server on Amazon Lightsail (flat monthly price that includes the IP address, disk and traffic).
# See README.md in this folder. The EC2 version lives in ../terraform; use one or the other, not both.
#
#   S3 bucket (private, versioned)  -> continuous database backups (Litestream)
#   IAM user + access key           -> may use ONLY that bucket (Lightsail servers cannot have an IAM role)
#   Lightsail instance + static IP  -> Ubuntu 24.04, IPv4
#   Firewall                        -> 80 and 443 for everyone; 22 only for the Lightsail console's browser terminal
#   Budget (optional)               -> email when spending passes the limit

data "aws_caller_identity" "me" {}

locals {
  bucket = "${var.name}-${data.aws_caller_identity.me.account_id}"
}

# ---- backups bucket -------------------------------------------------------------------------------------
resource "aws_s3_bucket" "backup" {
  bucket = local.bucket
}

resource "aws_s3_bucket_public_access_block" "backup" {
  bucket                  = aws_s3_bucket.backup.id
  block_public_acls       = true
  ignore_public_acls      = true
  block_public_policy     = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "backup" {
  bucket = aws_s3_bucket.backup.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "backup" {
  bucket = aws_s3_bucket.backup.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "backup" {
  bucket     = aws_s3_bucket.backup.id
  depends_on = [aws_s3_bucket_versioning.backup]

  rule {
    id     = "expire-old-versions"
    status = "Enabled"

    filter {}

    noncurrent_version_expiration {
      noncurrent_days = var.backup_retention_days
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

# ---- the server's identity: this bucket and nothing else --------------------------------------------------
data "aws_iam_policy_document" "backup_access" {
  statement {
    actions   = ["s3:ListBucket", "s3:GetBucketLocation"]
    resources = [aws_s3_bucket.backup.arn]
  }

  statement {
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["${aws_s3_bucket.backup.arn}/*"]
  }
}

resource "aws_iam_user" "backup" {
  name = "${var.name}-backup"
}

resource "aws_iam_user_policy" "backup" {
  name   = "backup-bucket"
  user   = aws_iam_user.backup.name
  policy = data.aws_iam_policy_document.backup_access.json
}

# The secret ends up in the Terraform state file: keep terraform.tfstate private.
resource "aws_iam_access_key" "backup" {
  user = aws_iam_user.backup.name
}

# ---- the server -----------------------------------------------------------------------------------------------
resource "aws_lightsail_instance" "server" {
  name              = var.name
  availability_zone = "${var.region}${var.availability_zone_suffix}"
  blueprint_id      = "ubuntu_24_04"
  bundle_id         = var.bundle_id
  ip_address_type   = "ipv4"

  dynamic "add_on" {
    for_each = var.automatic_snapshots ? [1] : []

    content {
      type          = "AutomaticSnapshot"
      snapshot_time = "10:00"
      status        = "Enabled"
    }
  }
}

resource "aws_lightsail_static_ip" "server" {
  name = "${var.name}-ip"
}

resource "aws_lightsail_static_ip_attachment" "server" {
  static_ip_name = aws_lightsail_static_ip.server.name
  instance_name  = aws_lightsail_instance.server.name
}

resource "aws_lightsail_instance_public_ports" "server" {
  instance_name = aws_lightsail_instance.server.name

  port_info {
    protocol  = "tcp"
    from_port = 80
    to_port   = 80
    cidrs     = ["0.0.0.0/0"]
  }

  port_info {
    protocol  = "tcp"
    from_port = 443
    to_port   = 443
    cidrs     = ["0.0.0.0/0"]
  }

  # Only the Lightsail console's own browser terminal can reach SSH; no key files to look after.
  port_info {
    protocol          = "tcp"
    from_port         = 22
    to_port           = 22
    cidr_list_aliases = ["lightsail-connect"]
  }
}

# ---- cost alerts (optional) -----------------------------------------------------------------------------------
resource "aws_budgets_budget" "monthly" {
  count = var.budget_email == "" ? 0 : 1

  name         = "${var.name}-monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.budget_email]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.budget_email]
  }
}
