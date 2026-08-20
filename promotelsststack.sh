#!/bin/bash

set -xeo pipefail

# Renames an lsstsw cache tarball in GCP_BUCKET from one tag to another. Used by
# the release pipelines: run-rebuild uploads the cache under a temporary
# per-build tag and this promotes it to the shared tag (eg. d_latest) once the
# release has succeeded. The move is server side, so the multi-GB tarball is
# never transferred. Every architecture variant present under the source tag is
# promoted.

GCP_BUCKET="gs://eups-lsstsw-cache"

fail() {
  echo "$1" >&2
  exit 1
}

[[ $# -eq 2 ]] || fail "usage: $0 <src_tag> <dst_tag>"
SRC_TAG=$1
DST_TAG=$2

[[ -n "$SRC_TAG" ]] || fail "src tag is empty"
[[ -n "$DST_TAG" ]] || fail "dst tag is empty"

[[ "$SRC_TAG" != "$DST_TAG" ]] || fail "src and dst tags are identical: ${SRC_TAG}"

# `ls` exits non-zero when nothing matches; report that as our own error rather
# than dying inside the command substitution.
objects=$(gcloud storage ls "${GCP_BUCKET}/${SRC_TAG}_*_lsstsw.tar.zst" || true)
[[ -n "$objects" ]] || fail "no cache tarball found for tag ${SRC_TAG}"

echo "$objects" | while read -r src; do
  arch=$(basename "$src")
  arch=${arch#"${SRC_TAG}_"}
  arch=${arch%_lsstsw.tar.zst}
  gcloud storage mv "$src" "${GCP_BUCKET}/${DST_TAG}_${arch}_lsstsw.tar.zst"
done
