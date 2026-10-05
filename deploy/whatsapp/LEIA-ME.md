# Robô do WhatsApp numa VM gratuita (sempre ligado)

Objetivo: o robô logado **24 horas**, sem custo, sem depender do notebook. A VM entra como **2º aparelho vinculado**
(QR novo, feito lá); o notebook continua com a sessão dele. **A sessão nunca vai para o Git.**

> **Importante — resposta em dobro.** Com o notebook e a VM logados ao mesmo tempo, cada mensagem chega aos dois e
> **os dois respondem**. Deixe **um só respondendo**: a VM (normal) e o notebook desligado ou em modo mudo
> (`python whatsapp_assistente.py --mudo`, ou `B2_WHATSAPP_MUDO=1`).

> **Conexão não oficial.** A Meta pode limitar o número. Chip dedicado, só dados simulados, nada em massa.
> A sessão vinculada cai se o celular do chip ficar ~14 dias sem abrir o WhatsApp.

## Onde hospedar de graça (confirme os termos atuais na hora de criar a conta)

| Opção | Prós | Cuidados |
|---|---|---|
| **Oracle Cloud "Always Free"** (recomendada) | VM com disco próprio, sem prazo | Pede cartão só para verificar (não cobra se ficar no gratuito). Em contas gratuitas a Oracle **pode recuperar VM ociosa**: um robô quase parado entra nisso. Passar a conta para "Pay As You Go" evita, sem custo dentro dos limites gratuitos (confira na documentação). |
| Google Cloud `e2-micro` (Always Free) | Não recupera VM ociosa | Pede cartão/faturamento; só algumas regiões dos EUA; cuidado com o tráfego de saída (o robô quase não usa). |

O GitHub **não** serve como servidor: o Actions é para build/teste (rodar robô lá viola os termos) e o Codespaces para
quando fica parado. Ele só guarda o código e a base, e a VM os busca de lá.

## Passo a passo (Oracle como exemplo)

1. **Conta:** crie a conta Oracle Cloud (você mesmo, com os seus dados e cartão). Escolha a região principal com cuidado:
   não dá para trocar depois.
2. **VM:** *Compute → Instances → Create*. Imagem **Canonical Ubuntu 24.04**; forma **VM.Standard.E2.1.Micro** (AMD,
   Always Free) ou **VM.Standard.A1.Flex** (Arm, às vezes "sem capacidade"). Em *Add SSH keys* deixe gerar e **baixe a
   chave privada** (guarde bem). Anote o **IP público**. Não abra nenhuma porta além da 22 (SSH).
3. **Entrar na VM** (no PowerShell do notebook): `ssh -i caminho\da\chave.key ubuntu@IP_DA_VM`
4. **Instalar** (o repositório é privado, então primeiro uma chave de **leitura**; na VM, como `ubuntu`):
   ```bash
   sudo apt-get update && sudo apt-get install -y git
   ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519 && cat ~/.ssh/id_ed25519.pub
   ```
   Copie a chave pública que apareceu. No GitHub: repositório → **Settings → Deploy keys → Add deploy key**, cole e
   **deixe "Allow write access" desmarcado**. De volta à VM:
   ```bash
   ssh-keyscan -t ed25519 github.com >> ~/.ssh/known_hosts
   git clone git@github.com:gcrp94/PostoB2.git ~/b2
   sudo bash ~/b2/deploy/whatsapp/instalar.sh
   ```
   O instalador reaproveita a chave, instala tudo em `/opt/b2gestao` e liga a atualização e o backup (não liga o robô ainda).
5. **Números autorizados:** `sudo nano /etc/b2-whatsapp.env` e ponha os números (DDD + número, separados por vírgula).
6. **Parear a VM como 2º aparelho (uma vez):** no **celular do chip**, WhatsApp Business → ⋮ → *Aparelhos conectados* →
   *Conectar um aparelho*. Na VM:
   ```bash
   sudo -u b2 -H bash -c 'cd /opt/b2gestao && set -a && . /etc/b2-whatsapp.env && set +a && .venv/bin/python whatsapp_assistente.py --qr-terminal'
   ```
   O QR aparece no terminal: escaneie. Se ficar distorcido, abra um túnel no notebook (`ssh -i chave.key -L 8541:127.0.0.1:8531 ubuntu@IP`)
   e abra `http://127.0.0.1:8541/` (use 8541 porque a 8531 do notebook pode estar em uso).
   Quando aparecer **"Conectado"**, pare com `Ctrl+C`.
7. **Ligar de vez:** `sudo systemctl start b2-whatsapp` (já fica ligado no boot e reinicia sozinho se cair).
8. **Conferir:** `sudo journalctl -u b2-whatsapp -f` e mande uma mensagem do seu número.
9. **Notebook:** feche o `Iniciar WhatsApp.bat` (ou use `--mudo`) para não responder em dobro.

## No dia a dia

- **Base dos postos:** a VM puxa do GitHub a cada 10 minutos (`b2-atualizar.timer`); o robô recarrega sozinho.
- **Código novo:** se mudar `src/` ou o robô, o `b2-atualizar` reinicia o serviço.
- **Backup da sessão:** diário às 04:30, últimos 7, em `/opt/b2gestao/sessao_whatsapp/backup/` (só nessa VM).
- **Se o celular desconectar o aparelho** (log "DESCONECTADO"): `sudo systemctl stop b2-whatsapp`, apague
  `/opt/b2gestao/sessao_whatsapp/` e refaça o passo 6.
- **Autorizar/remover número:** edite `/etc/b2-whatsapp.env` e `sudo systemctl restart b2-whatsapp`.

## O que este kit NÃO faz

Não cria a conta nem a VM (é com você), não usa a API oficial, não manda alertas automáticos (a agenda ainda é do
Telegram) e não foi testado numa VM real: rode o passo a passo com calma e me mande o erro se algo falhar.
