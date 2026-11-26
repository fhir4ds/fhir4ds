#!/bin/bash
# capped.sh — run a command under an ADDRESS-SPACE ceiling + CPU affinity so a
# runaway cannot exhaust the machine.
#   capped.sh <addr_space_gb> <cpus> <cmd...>
#
# READ THIS BEFORE TRUSTING THE CAP (WP-9, 2026-11-25):
# RLIMIT_AS caps ADDRESS SPACE, not resident memory. DuckDB + Arrow map large
# arenas (a full pytest tree reserves ~25 GB of address space while using far
# less RSS), so too low a cap aborts the process at mmap time — the symptom is
# an exit 127 / "failed to map segment" about 150 s in, NOT a clean
# MemoryError. Measured: the full pytest tree needs >= 40 GB here (16 GB kills
# it, 40 GB completes). So this is a best-effort guard against a pathological
# runaway, not a memory-leak detector: a clean run under it does NOT prove the
# absence of a leak.
# cgroup v2 memory.max would cap RSS properly, but delegation is not writable
# for an unprivileged user here (mkdir fails).
MEM_GB="$1"; CPUS="$2"; shift 2
# Floor raised to 40 GB: below that, loading the native extension bundles AND
# DuckDB/Arrow arenas fails with "failed to map segment from shared object"
# (phantom failures, exit 127). See the header.
if [ "$MEM_GB" -lt 40 ]; then MEM_GB=40; fi
ulimit -v $((MEM_GB * 1048576))
CORES=$(nproc); START=$((CORES - CPUS)); [ $START -lt 0 ] && START=0
exec taskset -c ${START}-$((CORES - 1)) "$@"
