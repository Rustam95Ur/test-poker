#!/usr/bin/env bash
set -eu

CH_CMD='docker compose exec -T clickhouse clickhouse-client -u app --password app_pass_123 -d poker -q'

run_query() {
  local title="$1"
  local sql="$2"
  echo "============================================================"
  echo "$title"
  echo "============================================================"
  eval "$CH_CMD \"$sql\""
  echo
}

run_query "stat-001 | Flop bet frequency | gto" "
SELECT
  (SELECT coalesce(sum(cnt),0) FROM events_agg
   WHERE source_type='gto'
     AND spot='SRP' AND formation='BB_SB' AND position='OOP' AND role='PFR' AND street='flop') AS context_cnt,
  (SELECT coalesce(sum(cnt),0) FROM events_agg
   WHERE source_type='gto'
     AND spot='SRP' AND formation='BB_SB' AND position='OOP' AND role='PFR' AND street='flop'
     AND canAct=1) AS denominator_cnt,
  (SELECT coalesce(sum(cnt),0) FROM events_agg
   WHERE source_type='gto'
     AND spot='SRP' AND formation='BB_SB' AND position='OOP' AND role='PFR' AND street='flop'
     AND action='bet') AS numerator_cnt
FORMAT Vertical"

run_query "stat-002 | Triple barrel frequency | gto" "
SELECT
  (SELECT coalesce(sum(cnt),0) FROM events_agg
   WHERE source_type='gto'
     AND spot='SRP' AND formation='BB_SB' AND position='OOP' AND role='PFR' AND street='river') AS context_cnt,
  (SELECT coalesce(sum(cnt),0) FROM events_agg
   WHERE source_type='gto'
     AND spot='SRP' AND formation='BB_SB' AND position='OOP' AND role='PFR' AND street='river'
     AND canAct=1
     AND startsWith(line,'B-B')) AS denominator_cnt,
  (SELECT coalesce(sum(cnt),0) FROM events_agg
   WHERE source_type='gto'
     AND spot='SRP' AND formation='BB_SB' AND position='OOP' AND role='PFR' AND street='river'
     AND action='bet'
     AND line='B-B-B') AS numerator_cnt
FORMAT Vertical"

run_query "stat-003 | Delayed river bet frequency | gto" "
SELECT
  (SELECT coalesce(sum(cnt),0) FROM events_agg
   WHERE source_type='gto'
     AND spot='SRP' AND formation='BB_SB' AND position='OOP' AND role='PFR' AND street='river') AS context_cnt,
  (SELECT coalesce(sum(cnt),0) FROM events_agg
   WHERE source_type='gto'
     AND spot='SRP' AND formation='BB_SB' AND position='OOP' AND role='PFR' AND street='river'
     AND canAct=1
     AND startsWith(line,'X-X')) AS denominator_cnt,
  (SELECT coalesce(sum(cnt),0) FROM events_agg
   WHERE source_type='gto'
     AND spot='SRP' AND formation='BB_SB' AND position='OOP' AND role='PFR' AND street='river'
     AND action='bet'
     AND line='X-X-B') AS numerator_cnt
FORMAT Vertical"

echo "Done."
