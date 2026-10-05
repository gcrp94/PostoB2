#!/usr/bin/env bash
# Backup diário e consistente da sessão do WhatsApp (SQLite .backup), mantendo os últimos 7.
# A pasta é um SEGREDO (dá acesso à conta): fica só nesta VM, fora do Git.
set -euo pipefail
DIR=/opt/b2gestao/sessao_whatsapp
[ -f "$DIR/b2.db" ] || exit 0
install -d -m 700 -o b2 -g b2 "$DIR/backup"
sudo -u b2 sqlite3 "$DIR/b2.db" ".backup '$DIR/backup/b2-$(date +%F).db'"
find "$DIR/backup" -name 'b2-*.db' -mtime +7 -delete
