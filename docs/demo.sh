#!/bin/bash
# PatchPilot recorded demo: point at a buggy repo, describe the bug,
# get a sandbox-verified diff. Requires the stack (see README setup)
# with the API on http://localhost:8000.
# Recorded with: asciinema rec -c "bash docs/demo.sh" docs/demo.cast
set -u
API="${API:-http://localhost:8000}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FIXTURE="${FIXTURE:-$ROOT/fixtures/python-demo}"

say() { printf '\n\033[1;36m== %s ==\033[0m\n' "$1"; sleep 1; }

say "PatchPilot live demo — health check"
curl -s "$API/health"; echo; sleep 1

say "1. Index the buggy repo (AST functions, not raw files)"
curl -s -X POST "$API/repos/index" \
  -H 'Content-Type: application/json' \
  -d "{\"local_path\": \"$FIXTURE\", \"persist\": true}" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('repo:', d['repo_id']); print('files:', d['stats']['files'], '| functions:', d['stats']['functions'], '| tests:', d['stats']['tests'])"
sleep 1
REPO=$(curl -s -X POST "$API/repos/index" \
  -H 'Content-Type: application/json' \
  -d "{\"local_path\": \"$FIXTURE\", \"persist\": true}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['repo_id'])")

say "2. Retrieve the faulty hunks"
curl -s -X POST "$API/query" \
  -H 'Content-Type: application/json' \
  -d "{\"repo_id\": \"$REPO\", \"bug_text\": \"add is off by one\", \"top_k\": 3}" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); [print(f\"- {h['path']}::{h['name']} (score {h['score']})\") for h in d['hunks']]"
sleep 1

say "3. Propose + sandbox-verify the fix (fixer loop, up to 3 attempts)"
curl -s -X POST "$API/runs" \
  -H 'Content-Type: application/json' \
  -d "{\"repo_id\": \"$REPO\", \"bug_text\": \"add(a, b) returns a+b+1 instead of a+b, off by one\", \"timeout_s\": 120}" \
  -o /tmp/patchpilot-demo-run.json
python3 -c "
import json
d = json.load(open('/tmp/patchpilot-demo-run.json'))
print('status:', d['status'], '| attempts:', d['attempts'], '| tok/s:', d['usage']['tokens_per_sec'])
print()
print('--- proven diff ---')
print(d['diff'] or '(none)')
print('--- sandbox test proof ---')
print((d['test_log'] or '(none)')[-400:])
print()
print('full proof: GET $API/runs/' + d['run_id'])
"
