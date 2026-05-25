#!/bin/bash
# Smoke test rapido — verifica che il sistema risponda
set -e
HOST=${1:-localhost}
PORT=${API_PORT:-8080}
BASE="http://$HOST:$PORT/api/v1"
echo "Smoke test su $BASE..."
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/health" || echo "000")
if [ "$STATUS" != "200" ]; then
  echo "FAIL: /health ha risposto $STATUS"; exit 1
fi
echo "  /health OK"
RESPONSE=$(curl -s -X POST "$BASE/query" \
  -H "Content-Type: application/json" \
  -d '{"question": "test", "top_k": 1}' || echo '{}')
if echo "$RESPONSE" | grep -q '"answer"'; then
  echo "  /query OK"
else
  echo "FAIL: /query non ha ritornato answer"; exit 1
fi
echo "Smoke test PASSED."
