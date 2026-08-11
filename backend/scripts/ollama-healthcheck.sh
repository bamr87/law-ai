#!/bin/sh
# Ollama healthcheck: the server is up AND the gate model is actually pulled.
#
# BL-20260810-12. The previous check was `ollama list`, which succeeds the
# moment the server answers — even with zero models installed. `docker
# compose up --wait` therefore reported a healthy stack to the nightly
# LegalBench job, which then scored every item against a model that did not
# exist. Readiness has to mean "can serve a request", not "is listening".
#
# The gate model is the FIRST entry of $OLLAMA_BOOTSTRAP_MODELS, matching
# ollama-bootstrap.sh, so the two cannot disagree about what gates readiness.

set -eu

MODELS=${OLLAMA_BOOTSTRAP_MODELS:-"mistral:7b-instruct-q4_K_M llama3.1:8b-instruct-q4_K_M nomic-embed-text"}
GATE_MODEL=$(echo "$MODELS" | awk '{print $1}')

# 1. Server responding?
/bin/ollama list >/dev/null 2>&1 || exit 1

# 2. Gate model present? `ollama list` prints NAME in the first column;
#    match on the exact tag, and also accept the ":latest" form Ollama
#    displays for tag-less pulls (e.g. "nomic-embed-text:latest").
if /bin/ollama list 2>/dev/null | awk '{print $1}' | grep -qx -e "$GATE_MODEL" -e "${GATE_MODEL}:latest"; then
  exit 0
fi

echo "gate model '$GATE_MODEL' not pulled yet" >&2
exit 1
