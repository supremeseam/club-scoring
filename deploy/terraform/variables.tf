variable "region" {
  description = "AWS region to deploy in (pick one near your sailors)."
  type        = string
  default     = "us-west-2"
}

variable "name" {
  description = "Prefix for everything created (letters, digits, hyphens). The backup bucket is named <name>-<account id>."
  type        = string
  default     = "club-scoring"
}

variable "instance_type" {
  description = "Server size. t4g.micro (1 GB, ARM) is enough for a club; the Ubuntu image used here is ARM, so keep a t4g/m6g/c6g type."
  type        = string
  default     = "t4g.micro"
}

variable "root_volume_gb" {
  description = "Size of the server's encrypted disk."
  type        = number
  default     = 10
}

variable "vpc_id" {
  description = "VPC to use. Leave empty for the account's default VPC."
  type        = string
  default     = ""
}

variable "subnet_id" {
  description = "Subnet to use (must be public). Leave empty to use the first subnet in the VPC."
  type        = string
  default     = ""
}

variable "snapshots_to_keep" {
  description = "How many weekly disk snapshots to keep."
  type        = number
  default     = 4
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
  default     = 12
}
