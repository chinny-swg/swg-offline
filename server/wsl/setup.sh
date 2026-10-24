#!/bin/bash
#
# One-time setup of the offline server inside WSL (Debian 11/12). Run as root:
#
#   ./setup.sh [--commit <sha>] [--repo https://github.com/chinny-swg]
#
# This is the only step that needs the internet. It:
#   1. runs Core3's own linux/bootstrap.sh at the pinned commit (core3/pin): packages, MariaDB,
#      schema, config-local.lua, and copying the client's TRE files to /tre,
#   2. applies swg-offline's patches (core3/patches) to that checkout, so your Core3 fork itself
#      never needs changing,
#   3. builds Core3 (RelWithDebInfo, no core3client),
#   4. makes config-local.lua load the launcher's conf/config-offline.lua,
#   5. installs swg-offline-server and /etc/swg-offline.conf.
#
# Re-running it is safe: bootstrap skips what exists, patches already applied are skipped, and the
# build is incremental. After the pin changes, re-running moves the checkout to the new commit.

set -eu

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATCHES="${HERE}/../../core3"

# shellcheck source=../../core3/pin
source <(tr -d '\r' < "${PATCHES}/pin")

REPO_URL="$(dirname "${CORE3_REPO}")"
COMMIT="${CORE3_COMMIT}"
SKIP_BUILD=false

while [ $# -gt 0 ]; do
    case "$1" in
        --repo ) REPO_URL="$2"; shift ;;
        --commit ) COMMIT="$2"; shift ;;
        --skip-build ) SKIP_BUILD=true ;;
        * ) echo "unknown argument: $1" >&2; exit 1 ;;
    esac
    shift
done

msg() {
    echo -e "\033[42;30m>> $*\033[0m" >&2
}

[ "$(id -u)" = 0 ] || { echo "Must run as root (wsl.exe -u root ...)" >&2; exit 1; }

if ! type -P wget > /dev/null || ! type -P git > /dev/null; then
    apt-get update -qq
    apt-get install -y -qq wget git
fi

msg "Running Core3 bootstrap from ${REPO_URL}/Core3 at ${COMMIT}"
BOOTSTRAP="$(mktemp)"
wget -qO "${BOOTSTRAP}" "${REPO_URL/github.com/raw.githubusercontent.com}/Core3/${COMMIT}/linux/bootstrap.sh"
# bootstrap clones the repo and checks out REPO_PUBLIC_BRANCH, which may be a commit
REPO_PUBLIC_URL="${REPO_URL}" REPO_PUBLIC_BRANCH="${COMMIT}" bash "${BOOTSTRAP}"
rm -f "${BOOTSTRAP}"

# bootstrap picks the WSL default user as RUN_USER and records it in ~/.env
RUN_USER="$(wsl.exe id -u -n 2> /dev/null | tr -d '\r' || true)"
RUN_USER="${RUN_USER:-$(awk -F: '$3 > 999 && $3 < 60000 { print $1; exit }' /etc/passwd)}"
HOME_DIR="$(getent passwd "${RUN_USER}" | cut -d: -f6)"
CORE3_DIR="${HOME_DIR}/workspace/Core3"
CORE3_BIN="${CORE3_DIR}/MMOCoreORB/bin"

[ -d "${CORE3_BIN}" ] || { echo "Core3 not found in ${CORE3_DIR}, bootstrap failed?" >&2; exit 1; }

as_user() {
    su - "${RUN_USER}" -c "set -e; $1"
}

# An existing checkout from an older pin: take our patches out, then move to the pinned commit
if [ "$(as_user "git -C '${CORE3_DIR}' rev-parse HEAD")" != "$(as_user "git -C '${CORE3_DIR}' rev-parse '${COMMIT}^{commit}' 2> /dev/null || echo none")" ]; then
    msg "Moving ${CORE3_DIR} to ${COMMIT}"
    as_user "git -C '${CORE3_DIR}' submodule update --init --recursive"
    as_user "bash '${PATCHES}/apply-patches.sh' --reverse '${CORE3_DIR}'"
    as_user "git -C '${CORE3_DIR}' fetch --quiet origin && git -C '${CORE3_DIR}' checkout --quiet '${COMMIT}'"
fi

msg "Applying swg-offline patches"
as_user "git -C '${CORE3_DIR}' submodule update --init --recursive"
as_user "bash '${PATCHES}/apply-patches.sh' '${CORE3_DIR}'"

if ! ${SKIP_BUILD}; then
    msg "Building Core3 as ${RUN_USER} (this takes a while)"
    as_user "cd '${CORE3_DIR}/MMOCoreORB'
        make build-ninja-debugoptimized CMAKE_ARGS='-DENABLE_BUILD_CLIENT=OFF'"
fi

[ -x "${CORE3_BIN}/core3" ] || ${SKIP_BUILD} || { echo "Build did not produce ${CORE3_BIN}/core3" >&2; exit 1; }

CONFIG_LOCAL="${CORE3_BIN}/conf/config-local.lua"
MARKER="-- swg-offline: launcher settings"

if ! grep -qF -- "${MARKER}" "${CONFIG_LOCAL}" 2> /dev/null; then
    msg "Hooking conf/config-offline.lua into ${CONFIG_LOCAL}"
    cat >> "${CONFIG_LOCAL}" <<EOF

${MARKER} (zones, etc.), rewritten by the launcher on every start
local offlineConfig = loadfile("conf/config-offline.lua")

if offlineConfig ~= nil then
	offlineConfig()
end
EOF
    chown "${RUN_USER}:" "${CONFIG_LOCAL}"
fi

msg "Installing /usr/local/bin/swg-offline-server"
tr -d '\r' < "${HERE}/swg-offline-server" > /usr/local/bin/swg-offline-server
chmod 755 /usr/local/bin/swg-offline-server

cat > /etc/swg-offline.conf <<EOF
# Written by swg-offline setup.sh
RUN_USER='${RUN_USER}'
CORE3_BIN='${CORE3_BIN}'
MYSQL_DEFAULTS='${HOME_DIR}/.my.cnf'
EOF

service mariadb stop > /dev/null 2>&1 || true

msg "Offline server installed. Start the game with the SWG Offline launcher."
