#!/usr/bin/env bash
# Puxa o que mudou no GitHub (a base dos postos e o código). Roda a cada 10 minutos (b2-atualizar.timer).
# A base é recarregada sozinha pelo robô; só reinicia o serviço se o CÓDIGO do robô mudou.
set -euo pipefail
DIR=/opt/b2gestao
USR=b2
antes=$(sudo -u "$USR" git -C "$DIR" rev-parse HEAD)
sudo -u "$USR" git -C "$DIR" pull --ff-only --quiet
depois=$(sudo -u "$USR" git -C "$DIR" rev-parse HEAD)
[ "$antes" = "$depois" ] && exit 0
if sudo -u "$USR" git -C "$DIR" diff --name-only "$antes" "$depois" | grep -qE '^(src/|whatsapp_assistente\.py|requirements)'; then
  sudo -u "$USR" "$DIR/.venv/bin/pip" install --quiet -r "$DIR/requirements.txt" -r "$DIR/requirements-whatsapp.txt" || true
  systemctl is-active --quiet b2-whatsapp && systemctl restart b2-whatsapp || true
fi
