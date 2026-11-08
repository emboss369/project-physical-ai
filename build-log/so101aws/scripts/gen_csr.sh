#!/usr/bin/env bash
# エッジの秘密鍵と CSR を手元で作る（CLAUDE.md §4.8 の CSR 方式）。
# 秘密鍵は certs/ から出さない。Terraform には CSR だけを渡すので、秘密鍵は state に入らない。
# Amazon Root CA 1 も公式の URL から取得する（server-authentication のページ）。
set -euo pipefail
THING="${THING:-so101-edge-01}"
DIR="$(cd "$(dirname "$0")/.." && pwd)/certs"
mkdir -p "$DIR"
chmod 700 "$DIR"
if [ -e "$DIR/edge.key" ]; then
  echo "既にある: $DIR/edge.key（作り直すなら手で消すこと）" >&2
else
  umask 077
  openssl req -new -newkey rsa:2048 -nodes \
    -keyout "$DIR/edge.key" -out "$DIR/edge.csr" -subj "/CN=$THING"
fi
[ -e "$DIR/AmazonRootCA1.pem" ] || curl -fsS https://www.amazontrust.com/repository/AmazonRootCA1.pem -o "$DIR/AmazonRootCA1.pem"
openssl req -in "$DIR/edge.csr" -noout -verify -subject
ls -l "$DIR"
