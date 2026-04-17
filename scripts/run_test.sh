#!/bin/bash
set -e

echo "=== APM QA Automation ==="

echo "[1/3] 환경 기동..."
docker compose up -d --build

echo "[2/3] Collector 헬스체크 대기..."
for i in $(seq 1 20); do
  if curl -sf http://localhost:8080/health > /dev/null; then
    echo "  Collector ready!"
    break
  fi
  echo "  대기중... ($i/20)"
  sleep 3
done

echo "[3/3] 테스트 실행..."
pip install -q pytest httpx
pytest tests/api/ -v

echo "=== 완료 ==="
