variable "region" {
  description = "AWS リージョン"
  type        = string
  default     = "ap-northeast-1"
}

variable "thing_name" {
  description = "IoT のモノ名 = MQTT クライアント ID（CLAUDE.md §4.1）"
  type        = string
  default     = "so101-edge-01"
}

variable "budget_usd" {
  description = "月の予算（USD）。2026-11-08 決定"
  type        = number
  default     = 20
}

variable "alert_email" {
  description = "Budgets のアラートの送り先。terraform.tfvars で指定する（Git 管理外）"
  type        = string
}
