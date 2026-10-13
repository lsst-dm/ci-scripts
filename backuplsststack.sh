#!/bin/bash

set -xeo pipefail

# This script creates a tarball of the lsstsw directory and copies it to GCP_BUCKET for later usage
# and is only intended to be useful when executed by jenkins.  It assumes that the `lsst/lsstsw`
# repo have already been cloned into the jenkins
# `$WORKSPACE`.

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

cd "$ROOT_DIR" || fail "Can't find ${ROOT_DIR}"

[[ -d "$LSSTSW_DIR" ]] || fail "Can't find lsstsw dir"
[[ -d "$LSSTSW_DIR/miniconda" ]] || fail "Can't find miniconda dir"
[[ -d "$LSSTSW_DIR/stack" ]] || fail "Can't find stack dir"
[[ -d "$LSSTSW_DIR/build" ]] || fail "Can't find build dir"

# lsstDoxygen is not an EUPS product -- create_xlinkdocs.sh clones the doc repo
# and generates HTML under lsstsw/build/, which bloats the tarball and shows up
# as a package to consumers that enumerate lsstsw/build/*.
#
# -T4 bounds compression to the sidecar's CPU allowance. `tar --zstd` passes no
# -T and zstd's no-flag default is ~4 threads, so this is about what we already
# got -- but stating it ties the thread count to the pod spec rather than to a
# zstd build default. Compression does parallelize (1.87 GiB: 11.9 s at -T1 vs
# 1.6 s at -T0); decompression doesn't, which is why loadlsststack.sh drops -T.
#
# Streamed to the bucket rather than staged in /tmp first: the old two-step
# wrote the whole multi-GB archive to the node root disk, read it back and rm'd
# it. Filling that disk is what triggers kubelet ephemeral-storage eviction of
# the agent, which is why /j is a dedicated volume to begin with.
#
# Uploaded under .incomplete and renamed only once tar AND the upload succeed. A
# streaming upload can't be aborted cleanly -- if tar dies partway, gcloud
# finalizes the bytes it already got -- so writing the final name directly could
# publish a truncated archive under a tag consumers trust. Staging made that
# safe implicitly (failed tar, no upload); the rename restores it, server side
# and metadata-only, as promotelsststack.sh does.
#
# pipefail (set above) is what surfaces a tar failure at all here, since gcloud
# is last in the pipeline and would otherwise mask it with its own exit 0.
STAGING="${GCP_BUCKET}/${TARGET}.incomplete"

# Best-effort sweep so a crashed run doesn't leave multi-GB garbage in the
# bucket; the staging object may not exist yet, hence the `|| true`.
cleanup_staging() {
  gcloud storage rm "${STAGING}" 2>/dev/null || true
}

if ! tar -I "zstd -T4" -cf - --exclude=lsstsw/build/lsstDoxygen lsstsw \
  | gcloud storage cp - "${STAGING}"; then
  cleanup_staging
  fail "Archive/upload failed"
fi

gcloud storage mv "${STAGING}" "${GCP_BUCKET}/${TARGET}" || {
  cleanup_staging
  fail "Failed to publish ${TARGET}"
}
