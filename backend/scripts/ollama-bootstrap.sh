#!/bin/sh
# Spec 010 FR-7: idempotent Ollama bootstrap.
#
# Starts the Ollama server then pulls the Law AI default model set in the
# background. Re-running is safe: `ollama pull` is a no-op when the model
# is already present at the requested digest.
#
# Models (Apple Silicon laptop default tier):
#   - mistral:7b-instruct-q4_K_M     (~ 4 GB) — gates readiness (smallest)
#   - llama3.1:8b-instruct-q4_K_M    (~ 4.7 GB) — preferred analyst model
#   - nomic-embed-text               (~ 270 MB) — embeddings for GraphRAG
#
# Override the set with $OLLAMA_BOOTSTRAP_MODELS (whitespace-separated).
# Set OLLAMA_OFFLINE=1 on an air-gapped host to skip every pull
# (scripts/offline-install.sh restores the models into the volume instead).

set -eu

MODELS=${OLLAMA_BOOTSTRAP_MODELS:-"mistral:7b-instruct-q4_K_M llama3.1:8b-instruct-q4_K_M nomic-embed-text"}
GATE_MODEL=$(echo "$MODELS" | awk '{print $1}')

echo "[ollama-bootstrap] starting server"
/bin/ollama serve &
SERVER_PID=$!

# Wait until the API responds before issuing pulls.
for _ in $(seq 1 60); do
  if /bin/ollama list >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

# Air-gapped hosts (BL-20260502-06): the models arrived in the volume via
# scripts/offline-install.sh, and every `ollama pull` here would block on a
# registry this host cannot reach. Skip the pulls and report what is actually
# installed — the healthcheck still gates on the gate model being present, so a
# short bundle fails loudly rather than degrading in silence.
if [ "${OLLAMA_OFFLINE:-0}" = "1" ]; then
  echo "[ollama-bootstrap] OLLAMA_OFFLINE=1 — skipping pulls"
  for m in $MODELS; do
    if /bin/ollama list 2>/dev/null | awk '{print $1}' | grep -qx -e "$m" -e "${m}:latest"; then
      echo "[ollama-bootstrap] present: $m"
    else
      echo "[ollama-bootstrap] MISSING from the offline bundle: $m"
    fi
  done
  wait "$SERVER_PID"
  exit 0
fi

echo "[ollama-bootstrap] gating on first model: $GATE_MODEL"
/bin/ollama pull "$GATE_MODEL" || echo "[ollama-bootstrap] gate pull failed (continuing)"

# Background the rest so the container becomes "ready" quickly.
(
  for m in $MODELS; do
    if [ "$m" = "$GATE_MODEL" ]; then
      continue
    fi
    echo "[ollama-bootstrap] pulling $m"
    /bin/ollama pull "$m" || echo "[ollama-bootstrap] pull failed: $m"
  done
  echo "[ollama-bootstrap] all models present"
) &

wait "$SERVER_PID"
