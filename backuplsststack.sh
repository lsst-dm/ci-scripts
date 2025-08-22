#!/bin/bash

set -xeo pipefail

# This script creates a tarball of the lsstsw directory and copies it to GCP_BUCKET for later usage
# and is only intended to be useful when executed by jenkins.  It assumes that the `lsst/lsstsw`
# repo have already been cloned into the jenkins
# `$WORKSPACE`.

ROOT_DIR="$(dirname "$(pwd)")"
LSSTSW_DIR="${ROOT_DIR}/lsstsw"

GCP_BUCKET="gs://eups-lsstsw-cache"
TMP_FOLDER="/tmp/lsstswcache"

fail() {
  echo "$1" >&2
  exit 1
}

[[ $# -eq 0 ]] && fail "No tag was passed" 
DATE_TAG=$1

mkdir -p "$TMP_FOLDER"
ARCH_VER=$(uname -m)

TARGET="${TMP_FOLDER}/${DATE_TAG}_${ARCH_VER}_lsstsw.tar.zst"

cd "$ROOT_DIR" || fail "Can't find ${ROOT_DIR}"

[[ -d "$LSSTSW_DIR" ]] || fail "Can't find lsstsw dir"
[[ -d "$LSSTSW_DIR/miniconda" ]] || fail "Can't find miniconda dir"
[[ -d "$LSSTSW_DIR/stack" ]] || fail "Can't find stack dir"
[[ -d "$LSSTSW_DIR/build" ]] || fail "Can't find build dir"

tar --zstd -cf "${TARGET}" lsstsw

gcloud storage cp "${TARGET}" "${GCP_BUCKET}"

rm "${TARGET}"
