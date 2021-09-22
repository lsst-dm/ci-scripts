#!/bin/bash

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


check_env_vars() {
  local req_vars=(
    LSST_VERIFY_DRP_METRICS_DATASET
    LSST_VERIFY_DRP_METRICS_DATASET_DIR
  )

  local err
  for v in "${req_vars[@]}"; do
    [[ ! -v $v ]] && err="${err}Missing required env variable: ${v}\\n"
  done

  [[ -n $err ]] && fail "$err"

  return 0
}

find_mem() {
  # Find system available memory in GiB
  local os
  os=$(uname)

  local sys_mem=""
  case $os in
    Linux)
      [[ $(grep MemAvailable /proc/meminfo) =~ \
         MemAvailable:[[:space:]]*([[:digit:]]+)[[:space:]]*kB ]]
      sys_mem=$((BASH_REMATCH[1] / 1024**2))
      ;;
    Darwin)
      # I don't trust this fancy greppin' an' matchin' in the shell.
      local free
      free=$(vm_stat | grep 'Pages free:' | tr -c -d '[:digit:]')
      local inac
      inac=$(vm_stat | grep 'Pages inactive:' | tr -c -d '[:digit:]')
      sys_mem=$(( (free + inac) / ( 1024 * 256 ) ))
      ;;
    *)
      >&2 echo "Unknown uname: $os"
      exit 1
      ;;
  esac

  echo "$sys_mem"
}

# find the maximum number of processes that may be run on the system
# given the the memory per core ratio in GiB -- may be expressed in
# floating point.
target_cores() {
  local mem_per_core=${1:-1}

  local sys_mem
  sys_mem=$(find_mem)
  local sys_cores
  sys_cores=$(getconf _NPROCESSORS_ONLN)

  local target_cores
  target_cores=$(awk "BEGIN{ print int($sys_mem / $mem_per_core) }")
  [[ $target_cores -gt $sys_cores ]] && target_cores=$sys_cores
  # Jenkins sees all the hardware cores rather than the number configured
  # for a worker, so limit to the number configured or a max of 8
  [[ $target_cores -gt ${K8S_DIND_LIMITS_CPU:=8} ]] && target_cores=${K8S_DIND_LIMITS_CPU}

  echo "$target_cores"
}

check_env_vars

set +o xtrace

# if _CODE_DIR is defined, set that up instead of the default verify_drp_metrics
# product
if [[ -n $LSST_VERIFY_DRP_METRICS_CODE_DIR ]]; then
  setup -k -r "$LSST_VERIFY_DRP_METRICS_CODE_DIR"
else
  setup faro
fi

setup -k -r "$LSST_VERIFY_DRP_METRICS_DATASET_DIR"

set -o xtrace

############ This is a hack to get around the fact that jointcal uses configs that are stripped in the container

git clone https://github.com/lsst/jointcal
(
setup -k -r .
cd jointcal
scons
)
setup -k -r jointcal
########### 

case "$LSST_VERIFY_DRP_METRICS_DATASET" in
  validation_data_cfht)
    RUN="$FARO_DIR/bin/measureCFHTMetrics.sh"
    ;;
  validation_data_decam)
    RUN="$FARO_DIR/bin/measureDecamMetrics.sh"
    ;;
  rc2_subset)
    RUN="$LSST_VERIFY_DRP_METRICS_DATASET_DIR/bin/measureHscRC2Metrics.sh"
    ;;
  *)
    >&2 echo "Unknown DATASET: ${LSST_VERIFY_DRP_METRICS_DATASET}"
    exit 1
    ;;
esac

# pipe_drivers mpi implementation uses one core for orchestration, so we
# need to set NUMPROC to the number of cores to utilize + 1
MEM_PER_CORE=2.0
export NUMPROC=$(($(target_cores $MEM_PER_CORE) + 1))

set +e
"$RUN"
run_status=$?
set -e

echo "${RUN##*/} - exit status: ${run_status}"
RESULTS=(validate_drp*)
# bail out if the drp output file is missing
if [[ ! -e "${RESULTS[0]}" ]]; then
  echo "drp result files do not exist"
  exit 1
fi

exit $run_status

# vim: tabstop=2 shiftwidth=2 expandtab
