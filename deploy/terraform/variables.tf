variable "region" {
  description = "AWS region. Mumbai is closest to the callers the demo is built for."
  type        = string
  default     = "ap-south-1"
}

variable "instance_type" {
  description = "4 vCPU / 8 GiB ARM: room for two calls at once with local speech models."
  type        = string
  default     = "c7g.xlarge"
}

variable "alert_email" {
  description = "Where the budget alarm goes. Empty: no budget is created."
  type        = string
  default     = ""
}

variable "monthly_budget_usd" {
  description = "Monthly spend that the alarm is measured against."
  type        = string
  default     = "25"
}
