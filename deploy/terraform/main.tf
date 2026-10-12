# Everything the club's server needs on AWS, in one place. See README.md in this folder.
#
#   S3 bucket (private, versioned)  -> continuous database backups (Litestream)
#   IAM role + instance profile     -> the server may use ONLY that bucket and AWS Session Manager (no SSH keys)
#   Security group                  -> inbound web traffic only (80 and 443, IPv4); no SSH port
#   EC2 instance + Elastic IP       -> Ubuntu 24.04 ARM, encrypted disk, IMDSv2 required
#   DLM policy                      -> weekly disk snapshots
#   Budget (optional)               -> email when spending passes the limit

data "aws_caller_identity" "me" {}

data "aws_vpc" "this" {
  default = var.vpc_id == "" ? true : null
  id      = var.vpc_id == "" ? null : var.vpc_id
}

data "aws_subnets" "this" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.this.id]
  }
}

data "aws_ssm_parameter" "ubuntu" {
  # Canonical's published pointer to the current Ubuntu 24.04 LTS ARM image.
  name = "/aws/service/canonical/ubuntu/server/24.04/stable/current/arm64/hvm/ebs-gp3/ami-id"
}

locals {
  subnet_id = var.subnet_id != "" ? var.subnet_id : sort(data.aws_subnets.this.ids)[0]
  bucket    = "${var.name}-${data.aws_caller_identity.me.account_id}"
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

# ---- the server's identity: this bucket + Session Manager, nothing else -------------------------------------
data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "server" {
  name               = "${var.name}-ec2"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
}

resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.server.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

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

resource "aws_iam_role_policy" "backup_access" {
  name   = "backup-bucket"
  role   = aws_iam_role.server.id
  policy = data.aws_iam_policy_document.backup_access.json
}

resource "aws_iam_instance_profile" "server" {
  name = "${var.name}-ec2"
  role = aws_iam_role.server.name
}

# ---- network: web traffic only ------------------------------------------------------------------------------
resource "aws_security_group" "web" {
  name        = "${var.name}-web"
  description = "Club scoring: HTTP and HTTPS only (no SSH)"
  vpc_id      = data.aws_vpc.this.id

  ingress {
    description = "HTTP (Caddy redirects to HTTPS and answers certificate challenges)"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "Outbound (package updates, certificates, backups, Session Manager)"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# ---- the server -----------------------------------------------------------------------------------------------
resource "aws_instance" "server" {
  ami                         = data.aws_ssm_parameter.ubuntu.value
  instance_type               = var.instance_type
  subnet_id                   = local.subnet_id
  vpc_security_group_ids      = [aws_security_group.web.id]
  iam_instance_profile        = aws_iam_instance_profile.server.name
  associate_public_ip_address = true

  # IMDSv2 only, one hop: containers can't reach the instance's credentials (Litestream runs on the host network).
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  root_block_device {
    volume_size           = var.root_volume_gb
    volume_type           = "gp3"
    encrypted             = true
    delete_on_termination = true

    tags = {
      Backup = "weekly"
    }
  }

  tags = {
    Name = var.name
  }

  lifecycle {
    # A newer Ubuntu image appearing must never replace (and wipe) a running server.
    ignore_changes = [ami]
  }
}

resource "aws_eip" "server" {
  domain = "vpc"
}

resource "aws_eip_association" "server" {
  instance_id   = aws_instance.server.id
  allocation_id = aws_eip.server.id
}

# ---- weekly disk snapshots ----------------------------------------------------------------------------------
data "aws_iam_policy_document" "dlm_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["dlm.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "dlm" {
  name               = "${var.name}-snapshots"
  assume_role_policy = data.aws_iam_policy_document.dlm_assume.json
}

resource "aws_iam_role_policy_attachment" "dlm" {
  role       = aws_iam_role.dlm.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSDataLifecycleManagerServiceRole"
}

resource "aws_dlm_lifecycle_policy" "weekly" {
  # AWS only allows letters, digits, spaces, hyphens and underscores here (no colons).
  description        = "${var.name} weekly disk snapshots"
  execution_role_arn = aws_iam_role.dlm.arn
  state              = "ENABLED"

  policy_details {
    resource_types = ["VOLUME"]

    target_tags = {
      Backup = "weekly"
    }

    schedule {
      name = "weekly"

      create_rule {
        cron_expression = "cron(0 10 ? * SUN *)"
      }

      retain_rule {
        count = var.snapshots_to_keep
      }

      copy_tags = true
    }
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
