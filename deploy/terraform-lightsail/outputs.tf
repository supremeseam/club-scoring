locals {
  ip = aws_lightsail_static_ip.server.ip_address
  # Let's Encrypt refuses certificates for bare IPs, so until you have a domain use sslip.io, a free service that
  # turns an IP into a name (203.0.113.7 -> 203-0-113-7.sslip.io).
  hostname = "${replace(local.ip, ".", "-")}.sslip.io"
}

output "public_ip" {
  value = local.ip
}

output "public_hostname" {
  description = "Use as SITE_ADDRESS until you have your own domain (a free <ip>.sslip.io name)."
  value       = local.hostname
}

output "backup_bucket" {
  value = aws_s3_bucket.backup.id
}

output "connect_in_browser" {
  description = "Opens a shell on the server from the Lightsail console (no SSH keys needed)."
  value       = "https://lightsail.aws.amazon.com/ls/webapp/${var.region}/instances/${aws_lightsail_instance.server.name}/connect"
}

output "env_settings" {
  description = "Lines to set in /opt/scoring/.env on the server. Contains the backup access key: show it with `terraform output -raw env_settings`."
  sensitive   = true
  value       = <<-EOT
    SITE_ADDRESS=${local.hostname}
    ALLOWED_HOSTS=${local.hostname}
    CSRF_TRUSTED_ORIGINS=https://${local.hostname}
    PUBLIC_URL=https://${local.hostname}
    LITESTREAM_BUCKET=${aws_s3_bucket.backup.id}
    LITESTREAM_REGION=${var.region}
    AWS_ACCESS_KEY_ID=${aws_iam_access_key.backup.id}
    AWS_SECRET_ACCESS_KEY=${aws_iam_access_key.backup.secret}
  EOT
}
