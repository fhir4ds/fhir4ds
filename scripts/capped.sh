#!/bin/bash
# capped.sh — run a command with a HARD memory ceiling + CPU affinity so a
# leak dies as a clean MemoryError in that process instead of taking WSL down.
#   capped.sh <mem_gb> <cpus> <cmd...>
# RLIMIT_AS (virtual memory) is the enforceable limit for an unprivileged
# user here; cgroup v2 delegation is not writable for us (mkdir fails).
MEM_GB="$1"; CPUS="$2"; shift 2
# NEVER use less than 16 GB: RLIMIT_AS also caps mmap, and loading the
# ~12 MB native extension bundles under the cap fails with
# "failed to map segment from shared object" (phantom test failures).
if [ "$MEM_GB" -lt 16 ]; then MEM_GB=16; fi
ulimit -v $((MEM_GB * 1048576))
CORES=$(nproc); START=$((CORES - CPUS)); [ $START -lt 0 ] && START=0
exec taskset -c ${START}-$((CORES - 1)) "$@"
