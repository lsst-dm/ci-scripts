#!/bin/bash

# Build cross linked doxygen documents and load into directory hierarchy
# intended to be exposed via a web-server.

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null && pwd )"
# shellcheck source=./settings.cfg.sh
source "${SCRIPT_DIR}/settings.cfg.sh"
# shellcheck source=/dev/null
source "${LSSTSW}/bin/setup.sh"

set -eo pipefail

print_error() {
  >&2 echo -e "$@"
}

fail() {
  local code=${2:-1}
  [[ -n $1 ]] && print_error "$1"
  # shellcheck disable=SC2086
  exit $code
}

usage() {
  # note that heredocs are prefixed with tab chars
  fail "$(cat <<-EOF
		Usage: $0 --type <type> --path <doxy docs path>

		 Build crosslinked doxygen documentation and install on LSST website.

		 type: either <git-branch>,  \"stable\", or \"beta\"
		 path: actual path to the publicly accessible DM doxygen documentation

		 Example: $0 --type main --path /home/foo/public_html/doxygen
		 Example: $0 --type Winter2012 ---path /home/foo/public_html/doxygen
		 Example: $0 --type stable --path /home/foo/public_html/doxygen

		EOF
  )"
}

# shellcheck disable=SC2034 disable=SC2054
options=(getopt --long type:,path: -- "$@")
while true
do
  case "$1" in
    --type) DOXY_TYPE="$2";   shift 2 ;;
    --path) INSTALL_ROOT="$2"; shift 2 ;;
    --) shift ; break ;;
    *) [[ "$*" != "" ]] && fail "Parsed options; arguments left are: $*"
        break;;
  esac
done

if [[ -z $DOXY_TYPE || -z $INSTALL_ROOT ]]; then
  print_error "***  Missing a required input parameter."
  usage
fi

DATE="$(date +%Y)_$(date +%m)_$(date +%d)_$(date +%H.%M.%S)"

# Normative doxy_type needs to be one of {normative(<branch>), beta, stable}
#   but doxy_type for main branch will now change to the tag name used
#   for a main build
NORMATIVE_DOXY_TYPE=$(echo "$DOXY_TYPE" | tr  "/" "_")
if [[ $DOXY_TYPE == main ]]; then
  eval "$(grep -E '^BUILD=' "$LSSTSW_BUILD_DIR"/manifest.txt)"
  echo "BUILD: $BUILD"
  if [[ -z $BUILD ]]; then
    fail "*** Failed: to determine most recent main build number."
  else
    DOXY_TYPE=$BUILD
  fi
fi

SYM_LINK_NAME="x_${NORMATIVE_DOXY_TYPE}DoxyDoc"
SYM_LINK_PATH="${INSTALL_ROOT}/${SYM_LINK_NAME}"
DOC_NAME="xlink_${NORMATIVE_DOXY_TYPE}_$DATE"
DOC_INSTALL_DIR="${INSTALL_ROOT}/${DOC_NAME}"
HTML_DIR="${DOC_REPO_DIR}/doc/html"
DOC_PKG='lsst_distrib'

# print "settings"
settings=(
  DATE
  DOC_INSTALL_DIR
  DOC_NAME
  DOC_PKG
  DOC_REPO_DIR
  DOC_REPO_URL
  DOXY_TYPE
  HTML_DIR
  INSTALL_ROOT
  LSSTSW_BUILD_DIR
  NORMATIVE_DOXY_TYPE
  SYM_LINK_NAME
  SYM_LINK_PATH
)

for i in ${settings[*]}
do
  echo "${i}: ${!i}"
done

if ! ( set -e
  # Ensure fresh extraction
  rm -rf "$DOC_REPO_DIR"

  # SCM clone lsstDoxygen ** from default branch **
  git clone "$DOC_REPO_URL" "$DOC_REPO_DIR"
); then
  fail "*** Failed to clone '$DOC_REPO_URL'."
fi

# setup all packages required by lsstDoxygen's eups
cd "$DOC_REPO_DIR"
# XXX can not run setup in a subshell for error handling
setup -t "$DOXY_TYPE" -r .
eups list -s

# Create doxygen docs for ALL setup packages; following is magic environment var
export xlinkdoxy=1

if ! scons; then
  fail "*** Failed to build lsstDoxygen package."
fi

# Now setup for build of Data Release library documentation
DOC_PKG_VERSION=$(eups list -t "$DOXY_TYPE" "$DOC_PKG" | awk '{print $1}')
if [[ -z $DOC_PKG_VERSION ]]; then
  fail "*** Failed to find \"${DOC_PKG}\" \"${DOXY_TYPE}\" version."
fi
echo "${DOC_PKG} VERSION: ${DOC_PKG_VERSION}"

# XXX can not run setup in a subshell for error handling
setup "$DOC_PKG" "$DOC_PKG_VERSION"
eups list -s

if ! "${DOC_REPO_DIR}/bin/makeDocs" \
  --nodot \
  --htmlDir "$HTML_DIR" \
  "$DOC_PKG" "$DOC_PKG_VERSION" > MakeDocs.out; then
  fail "*** Failed to generate complete makeDocs output for \"$DOXY_TYPE\" source."
fi

if ! doxygen MakeDocs.out; then
  fail "*** Failed to generate doxygen documentation for \"$DOXY_TYPE\" source."
fi

# install built doxygen

if ! ( set -e
  mkdir -p "$INSTALL_ROOT"
  chmod o+rx "$INSTALL_ROOT"
); then
  fail "*** Failed to prepare install root: ${INSTALL_ROOT}"
fi

if ! ( set -e
  cp -a "$HTML_DIR" "$DOC_INSTALL_DIR"
  chmod o+rx "$DOC_INSTALL_DIR"
); then
  fail "*** Failed to copy doxygen documentation to ${DOC_INSTALL_DIR}"
fi
echo "INFO: Doxygen documentation copied to \"$DOC_INSTALL_DIR\""

# symlink the default xlinkdoxy name to new directory.
if ! ln -snf "$DOC_INSTALL_DIR" "$SYM_LINK_PATH"; then
  fail "*** Failed to symlink: \"$SYM_LINK_PATH\", to new doxygen documentation: \"$DOC_INSTALL_DIR\""
fi
echo "INFO: Updated symlink: \"$SYM_LINK_PATH\", to point to new doxygen documentation: $DOC_INSTALL_DIR."

# vim: tabstop=2 shiftwidth=2 expandtab
