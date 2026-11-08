data "aws_caller_identity" "current" {}

# result の保存先（CLAUDE.md §4.6）。results/<thing>/<cmd_id>.json
resource "aws_s3_bucket" "results" {
  bucket        = "physical-ai-so101-results-${data.aws_caller_identity.current.account_id}"
  force_destroy = true # 実験用。destroy で中身ごと消せるように
}

resource "aws_s3_bucket_public_access_block" "results" {
  bucket                  = aws_s3_bucket.results.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
