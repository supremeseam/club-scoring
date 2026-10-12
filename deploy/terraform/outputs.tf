locals {
  ip = aws_eip.server.public_ip
  # Let's Encrypt refuses certificates for Amazon's own names (*.amazonaws.com), so until you have a domain use
  # sslip.io, a free service that turns an IP into a name (34.215.78.72 -> 34-215-78-72.sslip.io).
  hostname = "${replace(local.ip, ".", "-")}.sslip.io"
}

output "instance_id" {
  value = aws_instance.server.id
}

output "public_ip" {
  value = local.ip
}

output "public_hostname" {
  description = "Use as SITE_ADDRESS until you have your own domain (a free <ip>.sslip.io name; Amazon hostnames cannot get certificates)."
  value       = local.hostname
}

output "backup_bucket" {
  value = aws_s3_bucket.backup.id
}

output "connect_in_browser" {
  description = "Opens a shell on the server through the AWS console (no SSH needed). Wait a minute after the first apply."
  value       = "https://${var.region}.console.aws.amazon.com/systems-manager/session-manager/${aws_instance.server.id}?region=${var.region}"
}

output "env_settings" {
  description = "Lines to set in /opt/scoring/.env on the server (see the runbook)."
  value       = <<-EOT
    SITE_ADDRESS=${local.hostname}
    ALLOWED_HOSTS=${local.hostname}
    CSRF_TRUSTED_ORIGINS=https://${local.hostname}
    PUBLIC_URL=https://${local.hostname}
    LITESTREAM_BUCKET=${aws_s3_bucket.backup.id}
    LITESTREAM_REGION=${var.region}
  EOT
}
