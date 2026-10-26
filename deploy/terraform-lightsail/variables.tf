variable "region" {
  description = "AWS region to deploy in (pick one near your sailors)."
  type        = string
  default     = "us-west-2"
}

variable "availability_zone_suffix" {
  description = "Letter of the availability zone inside the region (us-west-2a -> a). Change it only if Lightsail rejects the default."
  type        = string
  default     = "a"
}

variable "name" {
  description = "Prefix for everything created (letters, digits, hyphens). The backup bucket is named <name>-<account id>."
  type        = string
  default     = "club-scoring"
}

variable "bundle_id" {
  description = "Lightsail plan. micro_3_0 (1 GB RAM, includes the disk, IP and traffic) is enough for a club. List the current plans and prices with: aws lightsail get-bundles --region us-east-1"
  type        = string
  default     = "micro_3_0"
}

variable "automatic_snapshots" {
  description = "Daily Lightsail disk snapshots. Off by default: the database is already backed up continuously to S3, and snapshots of the whole disk are billed per GB."
  type        = bool
  default     = false
}

variable "backup_retention_days" {
  description = "How long old versions of the database backup are kept in S3."
  type        = number
  default     = 30
}

variable "budget_email" {
  description = "Email for cost alerts. Leave empty to skip creating a budget. NOTE: the budget covers the whole AWS account, not just this project."
  type        = string
  default     = ""
}

variable "monthly_budget_usd" {
  description = "Monthly cost (USD) that triggers the budget alerts."
  type        = number
  default     = 10
}
