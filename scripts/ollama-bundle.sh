#!/usr/bin/env bash
# ollama-bundle.sh — build an offline install bundle (BL-20260502-06).
#
# Air-gapped deployment: this runs on a CONNECTED machine with the stack up,
# and writes everything the disconnected machine needs into dist/ —
#
#   dist/ollama-models.tar   the ollama named volume (blobs + manifests)
#   dist/images.tar          `docker save` of every pinned/built compose image
#   dist/images.txt          the image list, for auditing what is inside
#   dist/bundle.env          project name + ollama image, read by offline-install.sh
#   dist/SHA256SUMS          checksums over all of the above
#
# Copy dist/ to the target host and run scripts/offline-install.sh there.
#
# Usage:
#   make local-ai-bundle                  # every model in the volume + images
#   make local-ai-bundle ARGS='--dry-run' # print the plan, write nothing
#   OUT_DIR=/mnt/usb/bundle scripts/ollama-bundle.sh --models-only
#
#   # Only the named models (BL-20260906-45). Refreshing one model then costs
#   # one model, not the tens of GB the whole volume weighs. A bare name means
#   # `:latest`, exactly as `ollama pull` reads it.
#   scripts/ollama-bundle.sh --models 'mistral:7b-instruct-q4_K_M nomic-embed-text'
#   MODELS="$OLLAMA_BOOTSTRAP_MODELS" scripts/ollama-bundle.sh --models-only
#
# This is a host script on purpose: it drives `docker` itself, so it cannot
# live inside a container.
set -euo pipefail

OUT_DIR=${OUT_DIR:-dist}
DRY_RUN=0
WANT_MODELS=1
WANT_IMAGES=1
#: Space-separated model list; empty means "the whole volume" (the default,
#: and what every earlier bundle was).
MODELS=${MODELS:-}

usage() {
  sed -n '2,28p' "$0" | sed 's/^# \{0,1\}//'
}

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --models-only) WANT_IMAGES=0 ;;
    --images-only) WANT_MODELS=0 ;;
    --models)
      shift
      [ $# -gt 0 ] || { echo "--models needs a model list" >&2; exit 2; }
      MODELS=$1
      ;;
    --models=*) MODELS=${1#--models=} ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

PROJECT=${COMPOSE_PROJECT_NAME:-$(basename "$REPO_ROOT")}
VOLUME="${PROJECT}_ollama"
# Read the Ollama image out of the compose file rather than restating the pin,
# so a bump in docker-compose.yml cannot leave the bundle on an old server.
OLLAMA_IMAGE=$(docker compose config --images 2>/dev/null | grep '^ollama/ollama:' | head -n1 || true)
OLLAMA_IMAGE=${OLLAMA_IMAGE:-ollama/ollama:0.12.6}

say() { echo "[ollama-bundle] $*"; }

run() {
  if [ "$DRY_RUN" = "1" ]; then
    echo "  DRY-RUN: $*"
  else
    "$@"
  fi
}

say "project=$PROJECT volume=$VOLUME ollama_image=$OLLAMA_IMAGE out=$OUT_DIR"

OUT_ABS="$OUT_DIR"
if [ "$DRY_RUN" = "0" ]; then
  mkdir -p "$OUT_DIR"
  # Absolute, because it is bind-mounted into a container below and OUT_DIR
  # may be either relative to the repo root or an absolute path on a USB disk.
  OUT_ABS="$(cd "$OUT_DIR" && pwd)"
fi

# ---------------------------------------------------------------------------
# 1. Models. The blobs are content-addressed and immutable, so tarring a live
#    volume is safe — but a pull IN FLIGHT writes partial blobs, so wait for
#    `make local-ai-verify` to pass before bundling.
# ---------------------------------------------------------------------------
if [ "$WANT_MODELS" = "1" ]; then
  if docker compose ps --services --filter status=running 2>/dev/null | grep -qx ollama; then
    say "models present in the running container:"
    docker compose exec -T ollama /bin/ollama list || true
  else
    say "ollama is not running — tarring the volume directly"
  fi
  # Through a throwaway container so the volume can be read whether or not the
  # stack is up. `-C /models .` keeps paths relative for a clean restore.
  # --entrypoint tar / sh: the ollama image's entrypoint is /bin/ollama, so a
  # bare `tar` argument is parsed as an ollama subcommand and fails.
  if [ -z "$MODELS" ]; then
    say "writing $OUT_DIR/ollama-models.tar (whole volume; tens of GB)"
    run docker run --rm \
      -v "$VOLUME":/models:ro \
      -v "$OUT_ABS":/out \
      --entrypoint tar \
      "$OLLAMA_IMAGE" \
      -C /models -cf /out/ollama-models.tar .
  else
    # Subset (BL-20260906-45). Blobs are content-addressed and shared between
    # models, so the tar is assembled from each requested manifest plus the
    # digests it names, deduplicated — never by guessing at file sizes. A
    # model that is not in the volume is an error, not a silently thinner
    # bundle: offline-install.sh would otherwise restore a volume whose
    # manifest points at blobs that were never shipped.
    say "writing $OUT_DIR/ollama-models.tar (models: $MODELS)"
    run docker run --rm \
      -v "$VOLUME":/models:ro \
      -v "$OUT_ABS":/out \
      -e "WANTED=$MODELS" \
      --entrypoint sh \
      "$OLLAMA_IMAGE" \
      -euc '
        cd /models
        : > /tmp/paths
        for m in $WANTED; do
          case "$m" in *:*) name=${m%%:*}; tag=${m#*:} ;; *) name=$m; tag=latest ;; esac
          man="models/manifests/registry.ollama.ai/library/$name/$tag"
          if [ ! -f "$man" ]; then
            echo "ollama-bundle: $m is not in this volume ($man)" >&2
            exit 3
          fi
          echo "$man" >> /tmp/paths
          grep -o "sha256:[0-9a-f]\{64\}" "$man" \
            | tr ":" "-" \
            | sed "s|^|models/blobs/|" >> /tmp/paths
        done
        sort -u /tmp/paths > /tmp/files
        tar -C /models -cf /out/ollama-models.tar -T /tmp/files
      '
  fi
fi

# ---------------------------------------------------------------------------
# 2. Images. Locally built ones (backend/worker/frontend) must be built first —
#    `docker save` cannot export what was never built.
# ---------------------------------------------------------------------------
if [ "$WANT_IMAGES" = "1" ]; then
  IMAGES=$(docker compose config --images | sort -u)
  missing=""
  for img in $IMAGES; do
    docker image inspect "$img" >/dev/null 2>&1 || missing="$missing $img"
  done
  if [ -n "$missing" ]; then
    echo "[ollama-bundle] not built/pulled locally:$missing" >&2
    echo "[ollama-bundle] run 'make setup' (and 'docker compose pull') first." >&2
    # A dry run is a plan, not an install: report and keep going so the whole
    # plan is visible in one pass.
    [ "$DRY_RUN" = "1" ] || exit 1
  fi
  if [ "$DRY_RUN" = "1" ]; then
    echo "  DRY-RUN: docker save -o $OUT_DIR/images.tar$(echo " $IMAGES" | tr '\n' ' ')"
  else
    printf '%s\n' "$IMAGES" > "$OUT_DIR/images.txt"
    say "writing $OUT_DIR/images.tar"
    # shellcheck disable=SC2086
    docker save -o "$OUT_DIR/images.tar" $IMAGES
  fi
fi

# ---------------------------------------------------------------------------
# 3. Metadata + checksums. offline-install.sh verifies these before touching
#    anything on the target host.
# ---------------------------------------------------------------------------
if [ "$DRY_RUN" = "1" ]; then
  say "dry run complete — nothing written"
  exit 0
fi

cat > "$OUT_DIR/bundle.env" <<EOF
# Written by scripts/ollama-bundle.sh — read by scripts/offline-install.sh.
BUNDLE_PROJECT=$PROJECT
BUNDLE_VOLUME=$VOLUME
BUNDLE_OLLAMA_IMAGE=$OLLAMA_IMAGE
# Empty means the whole volume; otherwise the subset this bundle carries.
BUNDLE_MODELS=$MODELS
BUNDLE_CREATED=$(date -u +%Y-%m-%dT%H:%M:%SZ)
EOF

SUM=$(command -v sha256sum || command -v shasum)
(
  cd "$OUT_DIR"
  files=$(ls -1 ollama-models.tar images.tar images.txt bundle.env 2>/dev/null || true)
  # shellcheck disable=SC2086
  if [ "$(basename "$SUM")" = "shasum" ]; then
    "$SUM" -a 256 $files > SHA256SUMS
  else
    "$SUM" $files > SHA256SUMS
  fi
)

say "bundle ready in $OUT_DIR:"
ls -lh "$OUT_DIR"
say "copy the directory to the air-gapped host, then run scripts/offline-install.sh"
