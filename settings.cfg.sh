# shellcheck shell=bash

# shellcheck disable=SC2034
# general
LSSTSW=${LSSTSW:-$HOME/lsstsw}
LSSTSW_BUILD_DIR=${LSSTSW_BUILD_DIR:-${LSSTSW}/build}

# lsstswBuild.sh
# options passed to ./create_xlinkdocs.sh as cli options
DOC_PUSH_PATH=${DOC_PUSH_PATH:-"$HOME/public_html/doxygen"}
# lsstcam
LSSTCAM_BUCKET=${LSSTCAM_BUCKET:-'rubin-ci-lsst/testdata_ci_lsstcam_m49'}
LSSTCAM_TESTDATA_DIR=${LSSTCAM_TESTDATA_DIR:-'/tmp/LSSTCAMData'}

# create_xlinkdocs.sh
DOC_REPO_URL=${DOC_REPO_URL:-"https://github.com/lsst/lsstDoxygen.git"}
DOC_REPO_NAME=${DOC_REPO_NAME:-"lsstDoxygen"}
DOC_REPO_DIR=${DOC_REPO_DIR:-"${LSSTSW_BUILD_DIR}/${DOC_REPO_NAME}"}

# ansi color codes
BLACK='\033[0;30m'
DARK_GRAY='\033[1;30m'
RED='\033[0;31m'
LIGHT_RED='\033[1;31m'
GREEN='\033[0;32m'
LIGHT_GREEN='\033[1;32m'
BROWN='\033[0;33m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
LIGHT_BLUE='\033[1;34m'
PURPLE='\033[0;35m'
LIGHT_PURPLE='\033[1;35m'
CYAN='\033[0;36m'
LIGHT_CYAN='\033[1;36m'
LIGHT_GRAY='\033[0;37m'
WHITE='\033[1;37m'
NO_COLOR='\033[0m'
