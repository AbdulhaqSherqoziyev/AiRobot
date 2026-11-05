#!/usr/bin/env bash
# Runs the whole stack on this machine, for ML training and paper trials: deploy/local.sh start|stop|status
# Virtual money only: the live worker is never started here. Web: http://127.0.0.1:3100
set -u
cd "$(dirname "$0")/.."
PIDS=quantlab_data/local.pids
case "${1:-status}" in
  start)
    . quantlab_data/local.env
    .venv/bin/python -m quantlab.cli migrate
    : > "$PIDS"
    nohup .venv/bin/uvicorn --factory quantlab.api.app:app_factory --host 127.0.0.1 --port 8100 >> quantlab_data/api.log 2>&1 &
    echo $! >> "$PIDS"
    for r in market paper jobs trainer; do
      nohup .venv/bin/python -m quantlab.worker $r >> quantlab_data/worker-$r.log 2>&1 &
      echo $! >> "$PIDS"
    done
    (cd web && QL_API_URL=http://127.0.0.1:8100 exec nohup npx next start -H 127.0.0.1 -p 3100 >> ../quantlab_data/web.log 2>&1) &
    echo $! >> "$PIDS"
    echo started ;;
  stop)
    [ -f "$PIDS" ] && while read -r p; do kill "$p" 2>/dev/null; done < "$PIDS"
    rm -f "$PIDS"
    # npx hands off to a child process, so also stop whatever of ours holds the web port.
    web="$(ss -ltnp 'sport = :3100' 2>/dev/null | grep -oE 'pid=[0-9]+' | head -1 | cut -d= -f2)"
    if [ -n "$web" ] && [ "$(readlink "/proc/$web/cwd")" = "$PWD/web" ]; then kill "$web"; fi
    echo stopped ;;
  status)
    ss -ltn | grep -E ':(3100|8100) ' || echo 'web and api are down'
    [ -f "$PIDS" ] && while read -r p; do [ -d "/proc/$p" ] && tr '\0' ' ' < "/proc/$p/cmdline" | cut -c1-60 && echo; done < "$PIDS" ;;
esac
