#!/bin/bash

# build eups products using lsstsw

SCRIPT_DIR=$(cd "$(dirname "$0")"; pwd)
# shellcheck source=./settings.cfg.sh
source "${SCRIPT_DIR}/settings.cfg.sh"
# shellcheck source=/dev/null
source "${LSSTSW}/bin/setup.sh"

set -eo pipefail

# Reuse an existing lsstsw installation
BUILD_DOCS=true
GIT_REFS=''
PRODUCTS=''
NO_FETCH=false
COLORIZE=false

# Buildbot remotely invokes scripts with a stripped down environment.
umask 002

# shellcheck disable=SC2183
sbar=$(printf %78s |tr " " "-")
# shellcheck disable=SC2183
tbar=$(printf %78s |tr " " "~")

set_color() {
  if [[ $COLORIZE == true ]]; then
    echo -ne "$@"
  fi
}

no_color() {
  if [[ $COLORIZE == true ]]; then
    echo -ne "$NO_COLOR"
  fi
}

print_success() {
  set_color "$LIGHT_GREEN"
  echo -e "$@"
  no_color
}

print_info() {
  set_color "$YELLOW"
  echo -e "$@"
  no_color
}

# XXX this script is very inconsistent about what is sent to stdout vs stderr
print_error() {
  set_color "$LIGHT_RED"
  >&2 echo -e "$@"
  no_color
}

fail() {
  local code=${2:-1}
  [[ -n $1 ]] && print_error "$1"
  # shellcheck disable=SC2086
  exit $code
}

start_section() {
  print_info "### $*"
  print_info "$tbar"
}

end_section() {
  print_info "$sbar"
  # print a newline
  echo
}

# XXX PRODUCT would be better handled as arrays
# shellcheck disable=SC2054 disable=SC2034
options=(getopt --long refs:,products:,skip_docs,no-fetch,print-fail,color,prepare-only -- "$@")
while true
do
  case "$1" in
    --refs)         GIT_REFS=$2       ; shift 2 ;;
    --products)     PRODUCTS=$2       ; shift 2 ;;
    --skip_docs)    BUILD_DOCS=false  ; shift 1 ;;
    --no-fetch)     NO_FETCH=true     ; shift 1 ;;
    --color)        COLORIZE=true     ; shift 1 ;;
    --prepare-only) PREP_ONLY=true    ; shift 1 ;;
    --) shift; break;;
    *) [[ "$*" != "" ]] && fail "Unknown option: $1"
       break;;
  esac
done

IFS=' ' read -r -a REF_LIST <<< "$GIT_REFS"

#
# display configuration
#
start_section "configuration"

# print "settings"
settings=(
  BUILD_DOCS
  COLORIZE
  DOC_PUSH_PATH
  DOC_REPO_DIR
  DOC_REPO_NAME
  DOC_REPO_URL
  GIT_REFS
  LSSTSW
  LSSTSW_BUILD_DIR
  NO_FETCH
  PRODUCTS
)

set_color "$LIGHT_CYAN"
for i in ${settings[*]}
do
  echo "${i}: ${!i}"
done
no_color

end_section # configuration


#
# display environment variables
#
start_section "environment"
set_color "$LIGHT_CYAN"
printenv
no_color
end_section # environment


#
# build with <lsstsw>/bin/rebuild
#
start_section "build"

if [[ ! -x ${LSSTSW}/bin/rebuild ]]; then
  fail "Failed to find 'rebuild'."
fi

print_info "Rebuild is commencing....stand by; using $REF_LIST"

ARGS=()
if [[ $NO_FETCH == true ]]; then
  ARGS+=("-n")
fi
if [[ $PREP_ONLY == true ]]; then
  ARGS+=("-p")
fi
[[ ${#REF_LIST[@]} -ne 0 ]] &&
  for r in ${REF_LIST[*]}; do
    ARGS+=('-r' "$r")
  done
if [[ ! -z $PRODUCTS ]]; then
  # XXX intentionally not quoted to allow word splitting
  # shellcheck disable=SC2206
  ARGS+=($PRODUCTS)
fi

if ! "${LSSTSW}/bin/rebuild" "${ARGS[@]}"; then
  fail 'Failed during rebuild of DM stack.'
fi

# manifest.txt generated by lsst_build
MANIFEST=${LSSTSW_BUILD_DIR}/manifest.txt

# Set current build tag (also used as eups tag per installed package).
eval "$(grep -E '^BUILD=' "$MANIFEST" | sed -e 's/BUILD/MANIFEST_ID/')"

print_success "The DM stack has been installed at: ${LSSTSW}"
print_success "    with tag: ${MANIFEST_ID}."

end_section # build

#
# Build doxygen documentation
#
if [[ $BUILD_DOCS == true ]]; then
  start_section "doc build"

  print_info "Start Documentation build at: $(date)"
  if ! "${SCRIPT_DIR}/create_xlinkdocs.sh" \
    --type "master" \
    --path "$DOC_PUSH_PATH"; then
    fail "*** FAILURE: Doxygen document was not installed."
  fi
  print_success "Doxygen Documentation was installed successfully."

  end_section # doc build"
else
  print_info "Skipping Documentation build."
fi

# vim: tabstop=2 shiftwidth=2 expandtab
