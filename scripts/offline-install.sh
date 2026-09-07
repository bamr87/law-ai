#!/usr/bin/env bash
# offline-install.sh — install a Law AI bundle on an air-gapped host
# (BL-20260502-06). Companion to scripts/ollama-bundle.sh.
#
# Runs on the DISCONNECTED machine, with Docker installed and this repo
# checked out, and needs no network at any point:
#
#   1. verifies dist/SHA256SUMS (a truncated USB copy is the common failure)
#   2. `docker load`s every image in the bundle
#   3. restores the Ollama models into the compose `ollama` volume
#   4. tells you to start the stack with OLLAMA_OFFLINE=1
#
# Usage:
#   scripts/offline-install.sh [BUNDLE_DIR]      # default: dist
#   scripts/offline-install.sh /mnt/usb/bundle --force
#
# --force overwrites a volume that already has models in it.
set -euo pipefail

BUNDLE_DIR=""
FORCE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --force) FORCE=1 ;;
    -h|--help) sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) BUNDLE_DIR="$1" ;;
  esac
  shift
done

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUNDLE_DIR=${BUNDLE_DIR:-$REPO_ROOT/dist}
[ -d "$BUNDLE_DIR" ] || { echo "no such bundle directory: $BUNDLE_DIR" >&2; exit 1; }
BUNDLE_DIR="$(cd "$BUNDLE_DIR" && pwd)"

say() { echo "[offline-install] $*"; }

# --- 1. integrity ----------------------------------------------------------
if [ -f "$BUNDLE_DIR/SHA256SUMS" ]; then
  SUM=$(command -v sha256sum || command -v shasum || true)
  if [ -n "$SUM" ]; then
    say "verifying checksums"
    if [ "$(basename "$SUM")" = "shasum" ]; then
      (cd "$BUNDLE_DIR" && "$SUM" -a 256 -c SHA256SUMS)
    else
      (cd "$BUNDLE_DIR" && "$SUM" -c SHA256SUMS)
    fi
  else
    say "WARNING: no sha256sum/shasum on this host — skipping verification"
  fi
else
  say "WARNING: no SHA256SUMS in the bundle — skipping verification"
fi

# --- 2. metadata -----------------------------------------------------------
BUNDLE_PROJECT=${COMPOSE_PROJECT_NAME:-$(basename "$REPO_ROOT")}
BUNDLE_VOLUME="${BUNDLE_PROJECT}_ollama"
BUNDLE_OLLAMA_IMAGE="ollama/ollama:0.12.6"
if [ -f "$BUNDLE_DIR/bundle.env" ]; then
  # shellcheck disable=SC1091
  . "$BUNDLE_DIR/bundle.env"
fi
say "project=$BUNDLE_PROJECT volume=$BUNDLE_VOLUME"

# --- 3. images -------------------------------------------------------------
if [ -f "$BUNDLE_DIR/images.tar" ]; then
  say "loading images (this is the slow part)"
  docker load -i "$BUNDLE_DIR/images.tar"
else
  say "no images.tar in the bundle — assuming images are already present"
fi

# --- 4. models -------------------------------------------------------------
if [ -f "$BUNDLE_DIR/ollama-models.tar" ]; then
  docker volume create "$BUNDLE_VOLUME" >/dev/null
  # --entrypoint: the ollama image runs /bin/ollama by default.
  existing=$(docker run --rm -v "$BUNDLE_VOLUME":/models:ro \
    --entrypoint sh "$BUNDLE_OLLAMA_IMAGE" \
    -c 'ls /models/models/manifests 2>/dev/null | head -n1' || true)
  if [ -n "$existing" ] && [ "$FORCE" = "0" ]; then
    say "volume $BUNDLE_VOLUME already holds models — pass --force to overwrite"
  else
    say "restoring models into $BUNDLE_VOLUME"
    docker run --rm \
      -v "$BUNDLE_VOLUME":/models \
      -v "$BUNDLE_DIR":/bundle:ro \
      --entrypoint tar \
      "$BUNDLE_OLLAMA_IMAGE" \
      -C /models -xf /bundle/ollama-models.tar
  fi
else
  say "no ollama-models.tar in the bundle — skipping model restore"
fi

cat <<EOF

[offline-install] done. Start the stack WITHOUT network access:

    OLLAMA_OFFLINE=1 make dev

OLLAMA_OFFLINE=1 stops ollama-bootstrap.sh from issuing 'ollama pull' — which
would otherwise sit there retrying a registry this host cannot reach — and the
healthcheck still gates on the gate model actually being present, so a bundle
that is missing a model fails loudly instead of degrading in silence.

Verify with:  make local-ai-verify
EOF
