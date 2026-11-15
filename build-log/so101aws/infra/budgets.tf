# 月の予算アラート（CLAUDE.md §7 段階 0）
# 引数は provider のドキュメント（website/docs/r/budgets_budget.html.markdown）で確認済み
resource "aws_budgets_budget" "monthly" {
  name         = "physical-ai-so101-monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  # 実績が予算の 80% を超えたら
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.alert_email]
  }

  # 月末までの予測が予算を超えそうなら
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.alert_email]
  }
}
