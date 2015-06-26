#! /bin/bash

# general
LSSTSW=${LSSTSW:-$HOME/lsstsw}
LSSTSW_BUILD_DIR=${LSSTSW_BUILD_DIR:-${LSSTSW}/build}

BUILDBOT_SUCCESS=0
BUILDBOT_FAILURE=1
BUILDBOT_WARNING=2

# lsstswBuild.sh
# options passed to ./create_xlinkdocs.sh as cli options
DOC_PUSH_USER=${DOC_PUSH_USER:-"buildbot"}
DOC_PUSH_HOST=${DOC_PUSH_HOST:-"lsst-dev.ncsa.illinois.edu"}
DOC_PUSH_PATH=${DOC_PUSH_PATH:-"/lsst/home/buildbot/public_html/doxygen"}

# create_xlinkdocs.sh
DOC_REPO_URL=${DOC_REPO_URL:-"https://github.com/lsst/lsstDoxygen.git"}
DOC_REPO_NAME=${DOC_REPO_NAME:-"lsstDoxygen"}
DOC_REPO_DIR=${DOC_REPO_DIR:-"${LSSTSW_BUILD_DIR}/${DOC_REPO_NAME}"}

# runManifestDemo.sh
DEMO_ROOT=${DEMO_ROOT:-"https://github.com/lsst/lsst_dm_stack_demo/archive/master.tar.gz"}
DEMO_TGZ=${DEMO_TGZ:-"lsst_dm_stack_demo-master.tar.gz"}

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
