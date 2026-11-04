#!/usr/bin/env bash
# update.sh - update adsb_radar on the server from GitHub, after asking you first.
#
# Run on the AWS server as the "ubuntu" user, from /home/ubuntu/adsb_radar:
#   bash update.sh            show what is new on GitHub and ask: Update? [y/N]
#   bash update.sh --check    only show what is new, change nothing
#   bash update.sh --yes      update without asking
#   bash update.sh --force    reinstall packages and restart even if nothing is new (asks first)
#   bash update.sh --status   show running version and service state
#
# Nothing runs automatically: the server changes only when you run this script and answer y.
# An update: git fetch -> reset to origin/main -> pip install if requirements.txt changed ->
# Python syntax check -> restart service -> health check. If the new version does not start,
# it rolls back to the previous commit by itself.
# Local edits to tracked files are saved as a .patch in .update_state/ before they are replaced.
set -uo pipefail
export GIT_PAGER=cat PAGER=cat   # never stop in a pager (less) before the question

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$REPO_DIR/adsb_radar_ui"
VENV="$APP_DIR/venv"
SERVICE="${ADSB_SERVICE:-adsb-radar}"
BRANCH="${ADSB_BRANCH:-main}"
PORT="${ADSB_PORT:-5300}"
STATE_DIR="$REPO_DIR/.update_state"

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
        | python3 -c 'import sys,json; print(json.load(sys.stdin).get("version") or "an older version without a version number")' 2>/dev/null \
        || echo "not answering"
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
    local force="$1" ask="$2" check_only="$3"
    mkdir -p "$STATE_DIR"
    exec 9>"$STATE_DIR/update.lock"
    if ! flock -n 9; then
        log "another update is already running"
        return 1
    fi
    cd "$REPO_DIR" || return 1

    if ! git fetch --quiet origin "$BRANCH"; then
        log "ERROR: git fetch failed (network or GitHub problem)"
        return 1
    fi
    local old new
    old="$(git rev-parse HEAD)"
    new="$(git rev-parse "origin/$BRANCH")"

    echo "Running : $(running_version)  ($(git log -1 --format='%h %ci' "$old"))"
    if [ "$old" = "$new" ]; then
        echo "GitHub  : no new commits - already up to date"
        [ "$force" -eq 1 ] || return 0
    else
        echo "GitHub  : $(git rev-list --count "$old..$new") new commit(s):"
        git log --format='          %h %ci  %s' "$old..$new"
        echo "Changes : $(git diff --shortstat "$old" "$new")"
        git diff --quiet "$old" "$new" -- adsb_radar_ui/requirements.txt \
            || echo "          (requirements.txt changed - Python packages will be installed)"
    fi
    if [ -f "$STATE_DIR/bad_commit" ] && [ "$(cat "$STATE_DIR/bad_commit")" = "$new" ]; then
        echo "NOTE    : commit ${new:0:7} already failed to start once and was rolled back"
    fi
    if ! git diff --quiet HEAD; then
        echo "NOTE    : files were edited by hand on this server; they will be saved as a .patch and replaced:"
        git diff --stat HEAD | sed 's/^/          /'
    fi
    [ "$check_only" -eq 1 ] && return 0

    if [ "$ask" -eq 1 ]; then
        if [ ! -t 0 ]; then
            log "not asking without a terminal - run it yourself, or use --yes"
            return 1
        fi
        local prompt="Update to ${new:0:7}?"
        [ "$old" = "$new" ] && prompt="Reinstall packages and restart ${new:0:7}?"
        local ans
        read -r -p "$prompt [y/N] " ans
        case "$ans" in
            y|Y|yes|YES|Yes) ;;
            *) echo "Cancelled - nothing changed."; return 0 ;;
        esac
    fi

    log "updating ${old:0:7} -> ${new:0:7} ($(git log -1 --format='%s' "$new"))"

    local patch=""
    if ! git diff --quiet HEAD; then
        patch="$STATE_DIR/local-changes-$(date +%Y%m%d-%H%M%S).patch"
        git diff --binary HEAD > "$patch"
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
    # put the hand edits back too, so the server is exactly as it was before the update
    if [ -n "$patch" ]; then
        if git apply --whitespace=nowarn "$patch"; then
            log "local edits restored from $patch"
        else
            log "WARNING: could not restore the local edits - they are in $patch"
        fi
    fi
    if [ "$reqs_changed" -eq 1 ]; then install_requirements || true; fi
    restart_service || true
    if health_check; then
        log "rollback OK - running $(running_version) (${old:0:7}) again; fix the problem and push a new commit"
    else
        log "ERROR: rollback did not come up either - check: journalctl -u $SERVICE -n 50"
    fi
    return 1
}

show_status() {
    cd "$REPO_DIR" || return 1
    echo "Running version : $(running_version)"
    echo "Checked out     : $(git log -1 --format='%h %ci %s')"
    echo "Service         : $(systemctl is-active "$SERVICE")"
    [ -f "$STATE_DIR/bad_commit" ] && echo "Failed commit   : $(cut -c1-7 "$STATE_DIR/bad_commit") (rolled back)"
    return 0
}

main() {
    case "${1:-}" in
        "")          do_update 0 1 0 ;;
        --yes|-y)    do_update 0 0 0 ;;
        --force)     do_update 1 1 0 ;;
        --check)     do_update 0 0 1 ;;
        --status)    show_status ;;
        -h|--help)   sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//' ;;
        *)           echo "unknown option: $1 (see: bash update.sh --help)"; return 2 ;;
    esac
}

# Everything runs from main(), so bash has read the whole script before git replaces this file.
main "$@"
exit $?
