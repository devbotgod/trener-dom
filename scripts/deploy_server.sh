#!/bin/bash
# Деплой на свой сервер. Все адреса/учётки — только из env, без хардкода.
set -euo pipefail

HOST="${DEPLOY_HOST:?Set DEPLOY_HOST}"
USER="${DEPLOY_USER:-root}"
PASS="${DEPLOY_PASS:-}"
REMOTE_DIR="${DEPLOY_REMOTE_DIR:-/opt/youvsyou}"
LOCAL_DIR="$(cd "$(dirname "$0")/.." && pwd)"

if [ -z "$PASS" ] && [ -z "${SSH_AUTH_SOCK:-}" ]; then
  echo "Задайте DEPLOY_PASS или используйте SSH-ключ (ssh-agent)."
  exit 1
fi

ssh_base=(ssh -o StrictHostKeyChecking=accept-new)
rsync_ssh="ssh -o StrictHostKeyChecking=accept-new"

if [ -n "$PASS" ]; then
  if ! command -v sshpass >/dev/null 2>&1; then
    echo "Для пароля нужен sshpass, либо используйте SSH-ключ."
    exit 1
  fi
  export SSHPASS="$PASS"
  ssh_base=(sshpass -e ssh -o StrictHostKeyChecking=accept-new)
  rsync_ssh="sshpass -e ssh -o StrictHostKeyChecking=accept-new"
fi

echo "==> Sync files to ${USER}@${HOST}:${REMOTE_DIR}"
"${ssh_base[@]}" "${USER}@${HOST}" "mkdir -p ${REMOTE_DIR}/data"
rsync -az \
  --exclude venv --exclude .venv --exclude __pycache__ --exclude .git \
  --exclude data/*.db --exclude "*.log" --exclude .env \
  -e "$rsync_ssh" \
  "${LOCAL_DIR}/" "${USER}@${HOST}:${REMOTE_DIR}/"

echo "==> Install runtime on server"
"${ssh_base[@]}" "${USER}@${HOST}" "cd ${REMOTE_DIR} && python3 -m venv .venv && .venv/bin/pip install -q -U pip && .venv/bin/pip install -q -r requirements.txt && mkdir -p data"

echo "==> Install systemd unit (youvsyou.service)"
scp -o StrictHostKeyChecking=accept-new \
  "${LOCAL_DIR}/deploy/youvsyou.service" \
  "${USER}@${HOST}:/tmp/youvsyou.service"
"${ssh_base[@]}" "${USER}@${HOST}" \
  "mv /tmp/youvsyou.service /etc/systemd/system/youvsyou.service && systemctl daemon-reload && systemctl enable youvsyou && systemctl restart youvsyou && sleep 2 && systemctl --no-pager status youvsyou | head -15"

echo "==> Deploy complete. Не забудьте положить .env на сервер в ${REMOTE_DIR}/.env"
