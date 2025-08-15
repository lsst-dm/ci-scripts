#!/bin/bash

set -xeo pipefail

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

ARCH_VER=$(uname -m)

TARGET="${DATE_TAG}_${ARCH_VER}_lsstsw.tar.gz" 
mkdir -p "${TMP_FOLDER}"

gcloud storage ls "${GCP_BUCKET}/${TARGET}" || fail "failed file or tag doesn't exist"

cd "${ROOT_DIR}" || fail "Can't find ${ROOT_DIR}"
gcloud storage cp "${GCP_BUCKET}/${TARGET}" "${TARGET}" || fail "Download failed"
tar -xvzf "${TARGET}" || fail "Extraction failed"
[[ -d "$LSSTSW_DIR" ]] || fail "Can't find lsstsw dir"
[[ -d "$LSSTSW_DIR/miniconda" ]] || fail "Can't find miniconda dir"
[[ -d "$LSSTSW_DIR/stack" ]] || fail "Can't find stack dir"
rm "${TARGET}" || fail "Couldn't delete artifact"
cd "${LSSTSW_DIR}" || fail "Can't find ${LSSTSW_DIR}"
 
if [ "$ARCH_VER" = "x86_64" ]; then
  ARCH="linux-9-x86"
elif [ "$ARCH_VER" = "aarch64" ]; then
  ARCH="linux-9-aarch64"
fi
# clean up scripts to point to the right dir in jenkins
# Would like to find a dynamic way of doing this 
find . -type f -exec sed -i "s/sqre\/infra\/cache_lsstsw/stack-os-matrix\/$ARCH/g" {} +
