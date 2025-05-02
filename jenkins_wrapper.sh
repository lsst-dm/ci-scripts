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
LSST_NO_BINARY_FETCH=${NO_BINARY_FETCH:-false}
LSST_PREP_ONLY=${LSST_PREP_ONLY:-false}
LSST_REFS=${LSST_REFS:-}
echo $NO_BINARY_FETCH

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

export LSST_CONDA_ENV_NAME

"${SCRIPT_DIR}/lsstswBuild.sh" "${ARGS[@]}"

# vim: tabstop=2 shiftwidth=2 expandtab
