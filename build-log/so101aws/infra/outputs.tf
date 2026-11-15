output "budget_name" {
  value = aws_budgets_budget.monthly.name
}

output "iot_endpoint" {
  description = "エッジと send_cmd.py が使う Data-ATS エンドポイント"
  value       = data.aws_iot_endpoint.ats.endpoint_address
}

output "thing_name" {
  value = aws_iot_thing.edge.name
}

output "certificate_pem" {
  description = "terraform output -raw certificate_pem > ../certs/edge.crt"
  value       = aws_iot_certificate.edge.certificate_pem
  sensitive   = true
}

output "results_bucket" {
  value = aws_s3_bucket.results.bucket
}
