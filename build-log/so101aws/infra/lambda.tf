# 判断役の Lambda（CLAUDE.md §4.5）。zip は scripts/build_lambda.sh で作る

variable "model_id" {
  # Haiku 5.5 はこのアカウントのクォータ（tokens per minute）が 0 で使えなかった（Build Log #022 節10-2）。
  # Claude 4 系には上限があるので Haiku 4.5 を使う。5.5 の上限が付いたら、ここを変えるだけで切り替わる
  description = "Bedrock の推論プロファイル ID。jp. は東京・大阪だけで推論する（2026-11-08 に list-inference-profiles で確認）"
  type        = string
  default     = "jp.anthropic.claude-haiku-4-5-20251001-v1:0"
}

locals {
  lambda_zip       = "${path.module}/../build/agent.zip"
  profile_arn      = "arn:aws:bedrock:${var.region}:${data.aws_caller_identity.current.account_id}:inference-profile/${var.model_id}"
  base_model       = replace(var.model_id, "jp.", "")
  model_regions    = ["ap-northeast-1", "ap-northeast-3"] # get-inference-profile の models（東京・大阪）
  foundation_arns  = [for r in local.model_regions : "arn:aws:bedrock:${r}::foundation-model/${local.base_model}"]
  topic_arn_prefix = "${local.arn_prefix}:topic/so101/${var.thing_name}"
}

resource "aws_iam_role" "judge" {
  name = "so101-judge-lambda"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

# 最小権限（§4.7 Lambda 用）
resource "aws_iam_role_policy" "judge" {
  name = "judge"
  role = aws_iam_role.judge.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "PublishCmdOnly"
        Effect   = "Allow"
        Action   = "iot:Publish"
        Resource = "${local.topic_arn_prefix}/cmd"
      },
      {
        Sid      = "ReadStatusOnly"
        Effect   = "Allow"
        Action   = "iot:GetRetainedMessage"
        Resource = "${local.topic_arn_prefix}/status"
      },
      {
        Sid      = "ReadResults"
        Effect   = "Allow"
        Action   = "s3:GetObject"
        Resource = "${aws_s3_bucket.results.arn}/results/*"
      },
      {
        # これがないと、まだ無いオブジェクトの取得が NoSuchKey ではなく AccessDenied になる
        Sid       = "ListResultsForNoSuchKey"
        Effect    = "Allow"
        Action    = "s3:ListBucket"
        Resource  = aws_s3_bucket.results.arn
        Condition = { StringLike = { "s3:prefix" = "results/*" } }
      },
      {
        Sid      = "InvokeViaProfile"
        Effect   = "Allow"
        Action   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
        Resource = local.profile_arn
      },
      {
        # 推論プロファイルの行き先の基盤モデル。プロファイル経由の呼び出しだけに絞る（cross-region-inference-prereq）
        Sid       = "InvokeFoundationModelsThroughProfileOnly"
        Effect    = "Allow"
        Action    = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
        Resource  = local.foundation_arns
        Condition = { StringLike = { "bedrock:InferenceProfileArn" = local.profile_arn } }
      },
      {
        Sid      = "Logs"
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${aws_cloudwatch_log_group.judge.arn}:*"
      },
    ]
  })
}

resource "aws_cloudwatch_log_group" "judge" {
  name              = "/aws/lambda/so101-judge"
  retention_in_days = 7
}

resource "aws_lambda_function" "judge" {
  function_name    = "so101-judge"
  role             = aws_iam_role.judge.arn
  runtime          = "python3.12"
  architectures    = ["x86_64"]
  handler          = "handler.lambda_handler"
  filename         = local.lambda_zip
  source_code_hash = filebase64sha256(local.lambda_zip)
  timeout          = 300 # dispatch → 実機の実行（起動 15 + 動作 20 + 後始末 6 秒）→ result を待つ
  memory_size      = 512

  environment {
    variables = {
      MODEL_ID       = var.model_id
      IOT_ENDPOINT   = data.aws_iot_endpoint.ats.endpoint_address
      RESULTS_BUCKET = aws_s3_bucket.results.bucket
      THING          = var.thing_name
    }
  }

  depends_on = [aws_cloudwatch_log_group.judge, aws_iam_role_policy.judge]
}

output "judge_function_name" {
  value = aws_lambda_function.judge.function_name
}
