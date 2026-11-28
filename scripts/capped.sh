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
#
# A SECOND failure mode, measured 2026-11-28: when the ADDRESS SPACE crosses the
# cap LATE in a long run, the first allocation to fail can be the one inside
# LOAD of a native extension into a fresh connection, and that ABORTS — "Fatal
# Python error: Aborted", exit 134, at fhirpath/duckdb/extension.py — which
# looks exactly like the intermittent native crash of BUGFIX-019. A 69-file
# focused list crossed 40 GB at 1797 s and peaked at 41.7 GB of address space
# while its resident memory never passed 2.9 GB; two runs of it under the old
# 40 GB floor died at 1894 s and 1933 s, and the identical list under a 100 GB
# cap passed. So an abort at that site late in a run means THIS CAP, not the
# code under test: rerun with a larger first argument before investigating a
# crash. Pass 100 for a list of more than a few dozen integration files.
# cgroup v2 memory.max would cap RSS properly, but delegation is not writable
# for an unprivileged user here (mkdir fails).
MEM_GB="$1"; CPUS="$2"; shift 2
# Floor is 64 GB: below 40 GB, loading the native extension bundles AND
# DuckDB/Arrow arenas fails with "failed to map segment from shared object"
# (phantom failures, exit 127), and at exactly 40 GB a long run aborts as
# described above. See the header.
if [ "$MEM_GB" -lt 64 ]; then MEM_GB=64; fi
ulimit -v $((MEM_GB * 1048576))
CORES=$(nproc); START=$((CORES - CPUS)); [ $START -lt 0 ] && START=0
exec taskset -c ${START}-$((CORES - 1)) "$@"
