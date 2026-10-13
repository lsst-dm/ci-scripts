#!/bin/bash

set -xeo pipefail

ROOT_DIR="$(dirname "$(pwd)")"
LSSTSW_DIR="${ROOT_DIR}/lsstsw"

GCP_BUCKET="gs://eups-lsstsw-cache"

fail() {
  echo "$1" >&2
  exit 1
}

[[ $# -eq 0 ]] && fail "No tag was passed"
DATE_TAG=$1

ARCH_VER=$(uname -m)

TARGET="${DATE_TAG}_${ARCH_VER}_lsstsw.tar.zst"

gcloud storage ls "${GCP_BUCKET}/${TARGET}" || fail "failed file or tag doesn't exist"

cd "${ROOT_DIR}" || fail "Can't find ${ROOT_DIR}"

# Stream the tarball straight into tar rather than `cp`ing it to disk and then
# extracting it. The old two-step wrote the whole multi-GB archive to the pod's
# workspace volume, read it back, then rm'd it -- a full extra write+read pass
# over a network-attached disk that bought nothing.
#
# `cat` does not compute checksums (unlike `cp`), but the zstd frame carries an
# XXH64 checksum that zstd verifies while decompressing, so a corrupted transfer
# still fails the pipeline rather than silently extracting garbage.
#
# No -T on decompress: zstd cannot parallelize decompression of a single-frame
# archive, so -T0 was a no-op here (measured identical wall time at -T1/-T4/-T0)
# while still spawning a thread per core inside the sidecar's CPU quota.
#
# pipefail (set above) is what makes a failed `cat` fail the whole pipeline.
gcloud storage cat "${GCP_BUCKET}/${TARGET}" \
  | tar -I zstd -x --checkpoint=500000 \
  || fail "Download/extraction failed"

[[ -d "$LSSTSW_DIR" ]] || fail "Can't find lsstsw dir"
[[ -d "$LSSTSW_DIR/miniconda" ]] || fail "Can't find miniconda dir"
[[ -d "$LSSTSW_DIR/stack" ]] || fail "Can't find stack dir"
cd "${LSSTSW_DIR}" || fail "Can't find ${LSSTSW_DIR}"

