terraform {
  required_version = ">= 1.17.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.72"
    }
  }
}

provider "aws" {
  region = var.region

  # 全リソースにタグ project=physical-ai-so101 を付ける（CLAUDE.md §4.1）
  default_tags {
    tags = {
      project = "physical-ai-so101"
    }
  }
}
