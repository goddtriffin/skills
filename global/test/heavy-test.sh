#!/usr/bin/env bash
# Tests for global/bin/heavy (macOS: stubs top, memory_pressure, sysctl via PATH). Run: bash global/test/heavy-test.sh
set -u
here=$(cd "$(dirname "$0")" && pwd); heavy=$here/../bin/heavy
T=$(mktemp -d); pass=0; failn=0
trap 'rm -rf "$T"' EXIT
mkdir -p "$T/bin"
cat > "$T/bin/top" <<'S'
#!/bin/sh
# cpu busy % comes from the first line of $STUB/cpu_seq (popped while more lines remain), else $STUB/cpu
f=$STUB/cpu_seq; v=
if [ -s "$f" ]; then v=$(sed -n 1p "$f"); n=$(wc -l < "$f"); if [ "$n" -gt 1 ]; then sed 1d "$f" > "$f.n"; mv "$f.n" "$f"; fi; fi
[ -n "$v" ] || v=$(cat "$STUB/cpu")
echo "CPU usage: 1.0% user, 1.0% sys, $((100 - v)).0% idle"
S
cat > "$T/bin/memory_pressure" <<'S'
#!/bin/sh
echo "System-wide memory free percentage: 60%"
S
cat > "$T/bin/sysctl" <<'S'
#!/bin/sh
case "$2" in hw.ncpu) echo 16 ;; vm.loadavg) [ "$(cat "$STUB/load")" = none ] || echo "{ $(cat "$STUB/load") 1.0 1.0 }" ;; esac
S
chmod +x "$T/bin/"*
export STUB=$T PATH="$T/bin:$PATH"
newenv() { # fresh state per test
  d=$T/$1; mkdir -p "$d"; export HEAVY_DIR=$d/jobs HEAVY_ADMIT=$d/admit HEAVY_STAMP=$d/stamp HEAVY_RAMP=0 HEAVY_CONFIRM=1
  echo 10 > "$T/cpu"; echo 5 > "$T/load"; : > "$T/cpu_seq"; unset HEAVY_HELD HEAVY_MAX_LOAD
}
ok() { if [ "$2" = 1 ]; then pass=$((pass+1)); echo "ok   $1"; else failn=$((failn+1)); echo "FAIL $1"; fi; }

newenv a  # confirm-twice admit: runs, and takes at least CONFIRM seconds
s=$(date +%s); out=$(bash "$heavy" echo hi 2>&1); e=$(date +%s)
[ "$out" = hi ] && [ $((e - s)) -ge 1 ]; ok "admits after two samples" $(( $? == 0 ))

newenv b  # flaky: first sample ok, second fails, then ok again -> must wait, not run on the first pass
printf '10\n95\n10\n10\n' > "$T/cpu_seq"
out=$(bash "$heavy" echo ran 2>&1)
case "$out" in *"second sample"*ran*) ok "flaky second sample waits" 1 ;; *) echo "$out"; ok "flaky second sample waits" 0 ;; esac

newenv c  # no job cap: 6 concurrent jobs all running at once
for i in 1 2 3 4 5 6; do bash "$heavy" sleep 40 & done
sleep 30; n=$(bash "$heavy" --status | sed -n 's/^running: //p'); wait
[ "$n" -ge 5 ]; ok "6 concurrent jobs admitted, no cap (saw $n)" $(( $? == 0 ))

newenv d  # future stamp counts as 0, with a real ramp
echo $(( $(date +%s) + 100000 )) > "$HEAVY_STAMP"; HEAVY_RAMP=20
out=$(timeout 30 bash "$heavy" echo go 2>&1); [ "$out" = go ]; ok "future stamp ignored" $(( $? == 0 ))

newenv e  # ramp spacing still enforced
date +%s > "$HEAVY_STAMP"; HEAVY_RAMP=20
out=$(timeout 8 bash "$heavy" echo go 2>&1); case "$out" in *"ramp spacing"*) ok "ramp spacing enforced" 1 ;; *) ok "ramp spacing enforced" 0 ;; esac

newenv f  # high load blocks; default limit is 2 x ncpu = 32
echo 31 > "$T/load"; out=$(bash "$heavy" echo a 2>&1); [ "$out" = a ]; r1=$?
echo 33 > "$T/load"; out=$(timeout 8 bash "$heavy" echo b 2>&1); case "$out" in *"load 33 >= 32"*) r2=0 ;; *) r2=1 ;; esac
ok "load limit is 2 x cores" $(( r1 == 0 && r2 == 0 ))

newenv g  # unreadable metric is exit 3
echo none > "$T/load"; bash "$heavy" echo a >/dev/null 2>&1; [ $? = 3 ]; ok "unreadable metric exits 3" $(( $? == 0 ))

newenv h  # exit code passthrough and registry cleanup
bash "$heavy" sh -c 'exit 7'; r=$?; [ "$r" = 7 ] && [ -z "$(ls "$HEAVY_DIR")" ]; ok "exit code and cleanup" $(( $? == 0 ))

newenv i  # nested call passes through
out=$(bash "$heavy" bash "$heavy" echo nested 2>&1); [ "$out" = nested ]; ok "nested call passes through" $(( $? == 0 ))

echo "passed $pass, failed $failn"; [ "$failn" = 0 ]
