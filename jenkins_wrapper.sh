#!/bin/bash

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null && pwd )"
# shellcheck source=./ccutils.sh
source "${SCRIPT_DIR}/ccutils.sh"

set -xeo pipefail

# This script is a thin wrapper around `lsstswBuild.sh` and is only intended to
# be useful when executed by jenkins.  It assumes that the `lsst/lsstsw` and
# `lsst-sqre/buildbot-script` repos have already been cloned into the jenkins
# `$WORKSPACE`.

# The following environment variables are assumed to be declared by the caller:
#
# * LSST_COMPILER
# * LSST_PRODUCTS
# * LSST_SPLENV_REF
#
# optional:
#
# * LSST_BUILD_DOCS
# * LSST_DEPLOY_MODE
# * LSST_NO_FETCH
# * LSST_PREP_ONLY
# * LSST_REFS
#
# removed/fatal:
#
# * BRANCH
# * deploy
# * NO_FETCH
# * PRODUCT
# * SKIP_DEMO
# * SKIP_DOCS

LSST_COMPILER=${LSST_COMPILER?LSST_COMPILER is required}
LSST_PRODUCTS=${LSST_PRODUCTS?LSST_PRODUCTS is required}
LSST_SPLENV_REF=${LSST_SPLENV_REF?LSST_SPLENV_REF is required}

LSST_BUILD_DOCS=${LSST_BUILD_DOCS:-false}
LSST_DEPLOY_MODE=${LSST_DEPLOY_MODE:-}
LSST_NO_FETCH=${LSST_NO_FETCH:-false}
LSST_NO_BINARY_FETCH=${LSST_NO_BINARY_FETCH:-true}
LSST_PREP_ONLY=${LSST_PREP_ONLY:-false}
LSST_GLIBC_FLAG=${LSST_GLIBC_FLAG:-false}
LSST_REFS=${LSST_REFS:-}

fatal_vars() {
  local verboten=(
    BRANCH
    deploy
    NO_FETCH
    PRODUCT
    SKIP_DEMO
    SKIP_DOCS
  )
  local found=()

  for v in "${verboten[@]}"; do
    if [[ -n ${!v+1} ]]; then
      found+=("$v")
      >&2 echo -e "${v} is not supported"
    fi
  done

  [[ ${#found[@]} -ne 0 ]] && exit 1
  return 0
}
fatal_vars

ARGS=()
ARGS+=('--color')

[[ -n $LSST_REFS ]] &&     ARGS+=('--refs' "$LSST_REFS")
[[ -n $LSST_PRODUCTS ]] && ARGS+=('--products' "$LSST_PRODUCTS")

[[ $LSST_BUILD_DOCS == true ]] && ARGS+=('--docs')
[[ $LSST_NO_FETCH == true ]] &&   ARGS+=('--no-fetch')
[[ $LSST_NO_BINARY_FETCH == true ]] &&   ARGS+=('--no-binary-fetch')
[[ $LSST_PREP_ONLY == true ]] &&  ARGS+=('--prepare-only')

cc::setup_first "$LSST_COMPILER"

export LSSTSW=${LSSTSW:-$WORKSPACE/lsstsw}

cd "$LSSTSW"

OPTS=()

# shellcheck disable=SC2154
if [[ $LSST_DEPLOY_MODE == bleed ]]; then
  OPTS+=('-b')
fi

# Force the conda solver to target glibc 2.17 so the rebuild's conda env
# (captured in stack/src/env/<tag>.env via `conda list --explicit`) resolves
# packages that run on RHEL7-era hosts such as USDF cvmfs. Only affects the
# env create/install done by ./bin/deploy; unset before the build runs so it
# never influences runtime. Linux/x86_64 only -- irrelevant on macOS, and we
# don't override glibc on aarch64. We also need to pass a flag from Jenkins to
# avoid false positives.
if [[ $LSST_GLIBC_FLAG = "true" && $(uname -s) == Linux && $(uname -m) == x86_64 ]] && \
  [[ $(printf '%s\n' "13.0.0" "$LSST_SPLENV_REF" | sort -V | tail -n1) == "$LSST_SPLENV_REF" ]]; then
  export CONDA_OVERRIDE_GLIBC=2.17
fi

if [[ -z "$RUBINENV_ORG_FORK" ]]; then
  # The LSST_SPLENV_REF can refer to a rubin-env version
  #  or to an old scipipe_conda_env SHA1
  #  or to an eups tag
  if [[ $LSST_SPLENV_REF =~ [0-9]+\.[0-9]+\.[0-9A-Za-z-]+ ]]; then
    ./bin/deploy -v "$LSST_SPLENV_REF" "${OPTS[@]}"
  elif [[ $LSST_SPLENV_REF == [0-9a-f]* ]]; then
    # this may be required in case we want to do a patch on a major release
    #  pre instroduction of rubin-env
    ./bin/deploy -r "$LSST_SPLENV_REF" "${OPTS[@]}"
  elif [[ $LSST_SPLENV_REF == [dsvw]* ]]; then
    ./bin/deploy -x "$LSST_SPLENV_REF" "${OPTS[*]}"
  else
    echo "Unrecognized environment reference: $LSST_SPLENV_REF"
    exit 1
  fi
  LSST_CONDA_ENV_NAME="lsst-scipipe-${LSST_SPLENV_REF}"
else
  # build and deploy a rubinenv environment from fork/branch
  ./bin/deploy -v "$LSST_SPLENV_REF" "${OPTS[@]}"
  ./bin/set_prereleased_env "$RUBINENV_ORG_FORK" "$RUBINENV_BRANCH"
  LSST_CONDA_ENV_NAME="$(cat rubinenv-feedstock/env.name)"
fi

# glibc override applies only to the env-create step above, never at build/runtime
unset CONDA_OVERRIDE_GLIBC

export LSST_CONDA_ENV_NAME

"${SCRIPT_DIR}/lsstswBuild.sh" "${ARGS[@]}"

# vim: tabstop=2 shiftwidth=2 expandtab
