#!/usr/bin/env bash
# update.sh - update adsb_radar on the server from GitHub.
#
# Run on the AWS server as the "ubuntu" user, from /home/ubuntu/adsb_radar:
#   bash update.sh                  update now if GitHub has new commits (quiet if nothing new)
#   bash update.sh --force          reinstall packages and restart even if nothing is new
#   bash update.sh --install-timer  check GitHub automatically every 2 minutes (systemd timer)
#   bash update.sh --remove-timer   stop the automatic checks
#   bash update.sh --status         show running version, timer state and recent update log
#
# What an update does: git fetch -> reset to origin/main -> pip install if requirements.txt
# changed -> Python syntax check -> restart service -> health check. If the new version does
# not start, it rolls back to the previous commit and skips that commit until a newer one arrives.
# Local edits to tracked files are saved as a .patch in .update_state/ before they are discarded.
set -uo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$REPO_DIR/adsb_radar_ui"
VENV="$APP_DIR/venv"
SERVICE="${ADSB_SERVICE:-adsb-radar}"
BRANCH="${ADSB_BRANCH:-main}"
PORT="${ADSB_PORT:-5300}"
STATE_DIR="$REPO_DIR/.update_state"
TIMER_NAME="adsb-radar-update"

log() { echo "[update] $*"; }

health_check() {
    local i
    for i in $(seq 1 15); do
        sleep 1
        if curl -fsS -m 3 "http://127.0.0.1:$PORT/api/aircraft" >/dev/null 2>&1 \
           && curl -fsS -m 3 -o /dev/null "http://127.0.0.1:$PORT/"; then
            return 0
        fi
    done
    return 1
}

running_version() {
    curl -fsS -m 3 "http://127.0.0.1:$PORT/api/aircraft" 2>/dev/null \
        | python3 -c 'import sys,json; print(json.load(sys.stdin).get("version","?"))' 2>/dev/null || echo "?"
}

install_requirements() {
    if [ ! -x "$VENV/bin/python" ]; then
        log "creating virtualenv $VENV"
        python3 -m venv "$VENV" || return 1
    fi
    "$VENV/bin/pip" install -q -r "$APP_DIR/requirements.txt"
}

restart_service() {
    # 9>&- : the service must never inherit the update lock
    sudo -n systemctl restart "$SERVICE" 9>&-
}

do_update() {
    local force="$1"
    mkdir -p "$STATE_DIR"
    exec 9>"$STATE_DIR/update.lock"
    if ! flock -n 9; then
        log "another update is already running"
        return 0
    fi
    cd "$REPO_DIR" || return 1

    if ! git fetch --quiet origin "$BRANCH"; then
        log "ERROR: git fetch failed (network or GitHub problem); will try again next time"
        return 1
    fi
    local old new
    old="$(git rev-parse HEAD)"
    new="$(git rev-parse "origin/$BRANCH")"

    if [ "$old" = "$new" ] && [ "$force" -eq 0 ]; then
        return 0   # nothing new
    fi
    if [ "$force" -eq 0 ] && [ -f "$STATE_DIR/bad_commit" ] && [ "$(cat "$STATE_DIR/bad_commit")" = "$new" ]; then
        return 0   # this commit already failed once; wait for a newer push
    fi

    log "updating ${old:0:7} -> ${new:0:7} ($(git log -1 --format='%s' "$new"))"

    if ! git diff --quiet HEAD; then
        local patch="$STATE_DIR/local-changes-$(date +%Y%m%d-%H%M%S).patch"
        git diff HEAD > "$patch"
        log "local edits saved to $patch"
    fi
    git reset --hard --quiet "$new" || { log "ERROR: git reset failed"; return 1; }

    local reqs_changed=0
    if [ "$force" -eq 1 ] || [ ! -x "$VENV/bin/python" ] \
       || ! git diff --quiet "$old" "$new" -- adsb_radar_ui/requirements.txt; then
        reqs_changed=1
    fi

    local reason=""
    if [ "$reqs_changed" -eq 1 ]; then
        log "installing Python packages"
        install_requirements || reason="pip install failed"
    fi
    if [ -z "$reason" ] && ! "$VENV/bin/python" -m py_compile "$APP_DIR"/*.py; then
        reason="Python syntax check failed"
    fi
    if [ -z "$reason" ]; then
        restart_service || reason="service restart failed (sudo/systemctl)"
    fi
    if [ -z "$reason" ] && ! health_check; then
        reason="service did not answer on port $PORT after restart"
    fi

    if [ -z "$reason" ]; then
        rm -f "$STATE_DIR/bad_commit"
        log "OK - now running $(running_version) (${new:0:7})"
        return 0
    fi

    # ---- roll back ----
    log "ERROR: $reason - rolling back to ${old:0:7}"
    echo "$new" > "$STATE_DIR/bad_commit"
    git reset --hard --quiet "$old"
    if [ "$reqs_changed" -eq 1 ]; then install_requirements || true; fi
    restart_service || true
    if health_check; then
        log "rollback OK - running $(running_version) (${old:0:7}); commit ${new:0:7} will be skipped until a newer push"
    else
        log "ERROR: rollback did not come up either - check: journalctl -u $SERVICE -n 50"
    fi
    return 1
}

install_timer() {
    local user
    user="$(id -un)"
    sudo -n tee "/etc/systemd/system/$TIMER_NAME.service" >/dev/null <<EOF
[Unit]
Description=adsb_radar update from GitHub
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=$user
ExecStart=/bin/bash $REPO_DIR/update.sh
EOF
    sudo -n tee "/etc/systemd/system/$TIMER_NAME.timer" >/dev/null <<EOF
[Unit]
Description=Check GitHub for adsb_radar updates every 2 minutes

[Timer]
OnBootSec=1min
OnCalendar=*:0/2
AccuracySec=10s

[Install]
WantedBy=timers.target
EOF
    sudo -n systemctl daemon-reload
    sudo -n systemctl enable --now "$TIMER_NAME.timer"
    log "automatic updates enabled (every 2 minutes)"
    systemctl list-timers "$TIMER_NAME.timer" --no-pager
}

remove_timer() {
    sudo -n systemctl disable --now "$TIMER_NAME.timer" 2>/dev/null || true
    sudo -n rm -f "/etc/systemd/system/$TIMER_NAME.timer" "/etc/systemd/system/$TIMER_NAME.service"
    sudo -n systemctl daemon-reload
    log "automatic updates removed"
}

show_status() {
    cd "$REPO_DIR" || return 1
    echo "Running version : $(running_version)"
    echo "Checked out     : $(git log -1 --format='%h %ci %s')"
    echo "Service         : $(systemctl is-active "$SERVICE")"
    echo "Auto-update     : $(systemctl is-active "$TIMER_NAME.timer" 2>/dev/null)"
    [ -f "$STATE_DIR/bad_commit" ] && echo "Skipped commit  : $(cut -c1-7 "$STATE_DIR/bad_commit") (failed to start)"
    echo
    journalctl -u "$TIMER_NAME.service" -n 15 --no-pager -o short-iso 2>/dev/null | grep '\[update\]' || true
}

main() {
    case "${1:-}" in
        "")              do_update 0 ;;
        --force)         do_update 1 ;;
        --install-timer) install_timer ;;
        --remove-timer)  remove_timer ;;
        --status)        show_status ;;
        -h|--help)       sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//' ;;
        *)               echo "unknown option: $1 (see: bash update.sh --help)"; return 2 ;;
    esac
}

# Everything runs from main(), so bash has read the whole script before git replaces this file.
main "$@"
exit $?
