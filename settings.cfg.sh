#! /bin/bash

# general
LSSTSW=${LSSTSW:-$HOME}
BUILD_DIR=${BUILD_DIR:-${HOME}/build}

BUILDBOT_SUCCESS=0
BUILDBOT_FAILURE=1
BUILDBOT_WARNING=2

# lsstswBuild.sh
# options passed to ./create_xlinkdocs.sh as cli options
DOC_PUSH_USER=${DOC_PUSH_USER:-buildbot}
DOC_PUSH_HOST=${DOC_PUSH_HOST:-lsst-dev.ncsa.illinois.edu}
DOC_PUSH_PATH=${DOC_PUSH_PATH:-/lsst/home/buildbot/public_html/doxygen}

# create_xlinkdocs.sh
DOC_REPO_URL="https://github.com/lsst/lsstDoxygen.git"
DOC_REPO_NAME="lsstDoxygen"
DOC_REPO_DIR=${BUILD_DIR}/${DOC_REPO_NAME}

# runManifestDemo.sh
DEMO_ROOT="https://dev.lsstcorp.org/cgit/contrib/demos/lsst_dm_stack_demo.git/snapshot"
DEMO_TGZ="lsst_dm_stack_demo-master.tar.gz"
