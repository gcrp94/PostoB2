#!/usr/bin/env bash
# Instala o robô do WhatsApp (B2 Assistente) numa VM Ubuntu 22.04/24.04 sempre ligada.
#
#   sudo bash instalar.sh            # 1ª vez: prepara tudo e pede a chave de leitura do GitHub
#   sudo bash instalar.sh            # 2ª vez (depois de cadastrar a chave): clona, instala e liga os timers
#
# Idempotente: pode rodar de novo sem estragar nada. NÃO liga o robô sozinho: antes é preciso parear o QR
# (veja LEIA-ME.md). Não grava nenhum segredo no repositório.
set -euo pipefail

REPO="${B2_REPO:-git@github.com:gcrp94/PostoB2.git}"
DIR=/opt/b2gestao
USR=b2

[ "$(id -u)" = 0 ] || { echo "Rode com sudo:  sudo bash instalar.sh"; exit 1; }

echo "==> Pacotes do sistema"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y python3 python3-venv python3-pip git sqlite3 openssh-client

echo "==> Swap de 1 GB (a VM gratuita tem pouca memória)"
MEM_MB=$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo)
if [ "$MEM_MB" -lt 2000 ] && ! swapon --show | grep -q .; then
  fallocate -l 1G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

echo "==> Usuário do robô ($USR) e chave de LEITURA do GitHub"
id "$USR" >/dev/null 2>&1 || useradd --system --create-home --shell /bin/bash "$USR"
HOME_B2=$(getent passwd "$USR" | cut -d: -f6)
install -d -m 700 -o "$USR" -g "$USR" "$HOME_B2/.ssh"
# reaproveita a chave que você criou para clonar (LEIA-ME, passo 4); se não houver, cria uma nova
if [ ! -f "$HOME_B2/.ssh/id_ed25519" ] && [ -n "${SUDO_USER:-}" ] && [ -f "/home/$SUDO_USER/.ssh/id_ed25519" ]; then
  install -m 600 -o "$USR" -g "$USR" "/home/$SUDO_USER/.ssh/id_ed25519" "$HOME_B2/.ssh/id_ed25519"
  install -m 644 -o "$USR" -g "$USR" "/home/$SUDO_USER/.ssh/id_ed25519.pub" "$HOME_B2/.ssh/id_ed25519.pub"
fi
[ -f "$HOME_B2/.ssh/id_ed25519" ] || sudo -u "$USR" ssh-keygen -q -t ed25519 -N "" -C "b2-whatsapp-vm" -f "$HOME_B2/.ssh/id_ed25519"
sudo -u "$USR" bash -c 'ssh-keyscan -t ed25519 github.com 2>/dev/null >> ~/.ssh/known_hosts && sort -u -o ~/.ssh/known_hosts ~/.ssh/known_hosts'

if ! sudo -u "$USR" git ls-remote "$REPO" >/dev/null 2>&1; then
  echo
  echo "------------------------------------------------------------------------------"
  echo " FALTA UM PASSO SEU (uma vez só): cadastrar esta chave PÚBLICA no GitHub como"
  echo " 'Deploy key' SOMENTE LEITURA do repositório (Settings > Deploy keys > Add):"
  echo
  cat "$HOME_B2/.ssh/id_ed25519.pub"
  echo
  echo " Não marque 'Allow write access'. Depois rode de novo:  sudo bash instalar.sh"
  echo "------------------------------------------------------------------------------"
  exit 0
fi

echo "==> Código em $DIR"
if [ -d "$DIR/.git" ]; then
  sudo -u "$USR" git -C "$DIR" pull --ff-only
else
  install -d -o "$USR" -g "$USR" "$DIR"
  sudo -u "$USR" git clone "$REPO" "$DIR"
fi

echo "==> Ambiente Python (demora alguns minutos na 1ª vez)"
sudo -u "$USR" python3 -m venv "$DIR/.venv"
sudo -u "$USR" "$DIR/.venv/bin/pip" install --quiet --upgrade pip
sudo -u "$USR" "$DIR/.venv/bin/pip" install --quiet -r "$DIR/requirements.txt" -r "$DIR/requirements-whatsapp.txt"

echo "==> Serviço, atualização e backup (systemd)"
install -m 755 "$DIR/deploy/whatsapp/atualizar.sh" /usr/local/bin/b2-atualizar
install -m 755 "$DIR/deploy/whatsapp/backup-sessao.sh" /usr/local/bin/b2-backup-sessao
for u in b2-whatsapp.service b2-atualizar.service b2-atualizar.timer b2-backup.service b2-backup.timer; do
  install -m 644 "$DIR/deploy/whatsapp/$u" "/etc/systemd/system/$u"
done
if [ ! -f /etc/b2-whatsapp.env ]; then
  install -m 640 -o root -g "$USR" "$DIR/deploy/whatsapp/b2-whatsapp.env.exemplo" /etc/b2-whatsapp.env
  echo "    criado /etc/b2-whatsapp.env (edite: números autorizados)"
fi
systemctl daemon-reload
systemctl enable --now b2-atualizar.timer b2-backup.timer
systemctl enable b2-whatsapp.service          # liga no boot; só é INICIADO depois de parear (LEIA-ME.md, passo 6)

echo
echo "Pronto. Próximos passos (LEIA-ME.md, a partir do passo 5):"
echo "  1) sudo nano /etc/b2-whatsapp.env            # números autorizados"
echo "  2) parear o QR como 2º aparelho (uma vez)    # comando no LEIA-ME"
echo "  3) sudo systemctl start b2-whatsapp          # liga de vez"
