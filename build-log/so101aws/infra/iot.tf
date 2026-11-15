# AWS IoT Core（CLAUDE.md §4.1・§4.2・§4.6・§4.7・§4.8）

data "aws_iot_endpoint" "ats" {
  endpoint_type = "iot:Data-ATS"
}

resource "aws_iot_thing" "edge" {
  name = var.thing_name
}

# CSR 方式：鍵と CSR は scripts/gen_csr.sh で手元に作る。CSR だけを渡すので、秘密鍵は state に入らない
resource "aws_iot_certificate" "edge" {
  csr    = file("${path.module}/../certs/edge.csr")
  active = true
}

resource "aws_iot_thing_principal_attachment" "edge" {
  thing     = aws_iot_thing.edge.name
  principal = aws_iot_certificate.edge.arn
}

locals {
  arn_prefix = "arn:aws:iot:${var.region}:${data.aws_caller_identity.current.account_id}"
  # IoT ポリシー変数。Terraform の補間と衝突するので $$ でエスケープする（§4.8）
  thing_var = "$${iot:Connection.Thing.ThingName}"
}

# エッジ用の最小権限（§4.7）。MQTT の + や # はポリシーではリテラル扱いなので使わない
resource "aws_iot_policy" "edge" {
  name = "so101-edge-policy"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Action    = "iot:Connect"
        Resource  = "${local.arn_prefix}:client/${local.thing_var}"
        Condition = { Bool = { "iot:Connection.Thing.IsAttached" = "true" } }
      },
      {
        Effect = "Allow"
        Action = "iot:Publish"
        Resource = [
          "${local.arn_prefix}:topic/so101/${local.thing_var}/status",
          "${local.arn_prefix}:topic/so101/${local.thing_var}/result",
        ]
      },
      {
        Effect   = "Allow"
        Action   = "iot:RetainPublish"
        Resource = "${local.arn_prefix}:topic/so101/${local.thing_var}/status"
      },
      {
        Effect   = "Allow"
        Action   = "iot:Subscribe"
        Resource = "${local.arn_prefix}:topicfilter/so101/${local.thing_var}/cmd"
      },
      {
        Effect   = "Allow"
        Action   = "iot:Receive"
        Resource = "${local.arn_prefix}:topic/so101/${local.thing_var}/cmd"
      },
    ]
  })
}

resource "aws_iot_policy_attachment" "edge" {
  policy = aws_iot_policy.edge.name
  target = aws_iot_certificate.edge.arn
}

# ---- result を S3 に保存するルール（§4.6） ----

resource "aws_iam_role" "iot_rule" {
  name = "so101-iot-rule-to-s3"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "iot.amazonaws.com" }
      Action    = "sts:AssumeRole"
      # confused deputy 対策：このアカウントの IoT からだけ引き受けられる
      Condition = { StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.current.account_id } }
    }]
  })
}

resource "aws_iam_role_policy" "iot_rule_s3" {
  name = "put-results"
  role = aws_iam_role.iot_rule.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = "s3:PutObject"
      Resource = [
        "${aws_s3_bucket.results.arn}/results/*",
        "${aws_s3_bucket.results.arn}/errors/*",
      ]
    }]
  })
}

resource "aws_iot_topic_rule" "result_to_s3" {
  name        = "so101_result_to_s3" # ルール名は英数字とアンダースコアのみ
  description = "so101/+/result to S3 results/<thing>/<cmd_id>.json"
  enabled     = true
  sql         = "SELECT * FROM 'so101/+/result'"
  sql_version = "2016-03-23"

  s3 {
    bucket_name = aws_s3_bucket.results.bucket
    # 置換テンプレート。topic(2) = モノ名、cmd_id = ペイロードのフィールド。$$ は Terraform のエスケープ
    key      = "results/$${topic(2)}/$${cmd_id}.json"
    role_arn = aws_iam_role.iot_rule.arn
  }

  error_action {
    s3 {
      bucket_name = aws_s3_bucket.results.bucket
      key         = "errors/$${topic(2)}/$${timestamp()}.json"
      role_arn    = aws_iam_role.iot_rule.arn
    }
  }

  depends_on = [aws_iam_role_policy.iot_rule_s3]
}
