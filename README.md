# B2 Gestão — Painel da Rede B2 Postos

Sistema de gestão feito **sob medida para a rede B2 Postos** (B2 Centro,
B2 Bonsucesso, B2 Primavera, B2 Índio — Guarapuava — e B2 Candói — Candói, PR).

A ideia central: **o sistema se adapta ao B2, não o B2 ao sistema.** Ele lê o
que a rede já produz (planilhas, notas de compra, despesas), entende o modelo
de gestão do B2 e entrega **análises, alertas, sugestões e relatórios** para o
gestor decidir com segurança — no painel (computador e celular) e no Telegram.

> **Estado atual: DEMONSTRAÇÃO.** Todos os dados são **simulados** (12 meses,
> out/2025 a set/2026, 5 postos) e existem para apresentar o sistema. Nada
> ali é de posto real. O arquivo `data/SIMULADO.txt` marca isso e liga as
> proteções da demonstração (o robô do celular só responde com dado simulado).

| | |
|---|---|
| Painel publicado | https://b2gestao.streamlit.app (modo demonstração: qualquer um com o link entra) |
| Repositório | github.com/gcrp94/PostoB2 (**privado**, conta `gcrp94`) |
| Painel no notebook | `http://localhost:8520` (pelo `Abrir App.bat`) |
| Testes | 105 passando (`python -m pytest`) |
| Última atualização deste manual | 02/10/2026 |

Para entender o projeto em profundidade (decisões, armadilhas, histórico),
leia o **[CLAUDE.md](CLAUDE.md)**. Para passar o contexto a outra conta do
Claude, use o **[RESUMO_PARA_CLAUDE.md](RESUMO_PARA_CLAUDE.md)**.

---

## 1. Começo rápido

| Arquivo | Para quê |
|---|---|
| **`Abrir App.bat`** | Abre o painel (`http://localhost:8520`). Fecha antes qualquer painel antigo na mesma porta. Na primeira vez, gera os dados simulados e monta a base sozinho. Deixe a janela preta aberta. |
| **`Atualizar Dados.bat`** | Depois de pôr planilhas novas nas pastas: monta a base e roda o motor de alertas. |
| **`Gerar Dados Simulados.bat`** | Volta ao cenário original da demonstração. **Sobrescreve as planilhas simuladas — não rode com dados reais.** |
| **`Abrir Apresentacao.bat`** | Abre a apresentação comercial em HTML (ver seção 11). |
| **`Coletar Menor Preco.bat`** | *Teste local.* Coleta o preço das notas fiscais (Menor Preço do Paraná) de todos os postos de Guarapuava, com pausas, no máximo uma vez por dia. Alimenta a 2ª aba da tela 📡 Radar de Mercado; os dados ficam só neste computador. |

**Acesso de demonstração:** a tela de login tem botões de acesso rápido
(Proprietário, Gerente do Candói, Gerente da Primavera, Administração). A
senha de todos é `b2demo`.

**No celular (mesma rede Wi-Fi):** o `Abrir App.bat` mostra um endereço
"Network URL" (`http://192.168.x.x:8520`). Abra no celular e use *Adicionar à
tela inicial*. Ou use direto o painel publicado.

---

## 2. As telas

```
PROPRIETÁRIO / ADMINISTRAÇÃO                 GERENTE (só o próprio posto)
PAINÉIS                                      MENU
├─ Central do Proprietário                   ├─ Meu Posto
├─ Visão da Rede                             ├─ Enviar Planilha
├─ Reunião de Gerentes                       └─ Meus Envios
├─ B2 Centro … B2 Candói
│    Resumo | Vendas | Margens | Estoque |
│    Compras e Custos | Alertas
GESTÃO
├─ Alimentar dados
├─ Alertas
├─ Auditoria
├─ Atualizações
├─ B2 Assistente
└─ Administração
```

* **Central do Proprietário** — a tela de abertura. Diz em uma frase se a
  rede está normal, lista o que **exige ação** 🔴, o que **merece atenção** 🟡
  e os **destaques** 🟢 (cada um com o botão que abre o posto na aba certa) e
  mostra quando cada posto mandou a planilha pela última vez.
* **Visão da Rede** — o cockpit: faturamento, volume, margem bruta e postos
  em atenção (grandes) + margem %, margem/L, estoque e autonomia (leves); o
  quadro das unidades; e as quatro perguntas do dono: *onde ganhamos mais,
  onde a margem caiu, quanto combustível temos, qual posto corre risco de
  ficar sem produto*.
* **Cada posto** — o mesmo padrão nas cinco unidades, com seis abas. Os
  quatro combustíveis têm sempre a mesma cor: Gasolina Comum (laranja),
  Aditivada (azul), Etanol (verde), Diesel S10 (violeta).
* **Reunião de Gerentes** — o placar do mês (posto × indicador), a pauta
  sugerida de cada gerente e a ficha para imprimir (seção 7).
* **Auditoria** — o controle de fraudes (seção 6).
* **B2 Assistente** — o robô do celular e a agenda de disparos (seção 8).
* **Alimentar dados / Atualizações** — envio de planilhas, histórico de envios
  e restauração de versões.
* **Administração** — usuários, regras dos alertas, saúde da base e o botão
  "Restaurar os dados da demonstração".

### Painel antigo × Painel novo

No topo do menu lateral há o botão **Painel antigo | Painel novo** (ou
`?visual=antigo` / `?visual=novo` no endereço). Os **números e as telas são os
mesmos**; muda só a aparência. O novo traz ícones de traço único no lugar de
emojis, miniaturas de tendência (30 dias) nos cartões, Visão da Rede com 4
cartões grandes + 4 leves, alertas em linhas que abrem, etiquetas nos alertas
do posto e tabelas/gráficos mais leves. É o padrão; o antigo é o
`assets/style.css` intacto, e o novo é o `assets/style_novo.css` por cima.

### Margem bruta, nunca "lucro"

A margem bruta (faturamento − litros × custo médio) é o número principal de
todas as telas: é o que a planilha sustenta sozinha. O **resultado depois das
despesas** aparece só em *Compras e Custos*, quando a aba DESPESAS está
preenchida, e é antes de IR/CSLL.

---

## 3. A planilha de cada posto

Modelo em branco: `modelo/MODELO - Planilha Mensal do Posto.xlsx` (também no
painel, na tela de envio). **Uma planilha por posto por mês**, na pasta do
posto:

```
data/
├─ CADASTRO DOS POSTOS.xlsx     postos e capacidade de cada tanque
├─ b2_centro/       B2 Centro 09-2026.xlsx, B2 Centro 08-2026.xlsx, ...
├─ b2_bonsucesso/ · b2_primavera/ · b2_indio/ · b2_candoi/
├─ base/            a base Parquet que o painel lê (gerada, não editar)
├─ envios.csv       histórico de envios (quem, quando, resultado)
├─ auditoria.csv    trilha de alterações em dado já recebido
└─ alertas_enviados.csv   o que já foi mandado ao celular (não repete)
```

| Aba | Obrigatória? | Colunas |
|---|---|---|
| **MOVIMENTO DIÁRIO** | sim | Data · Produto · Estoque inicial (L) · Compras (L) · Vendas (L) · Estoque final (L) · Custo médio (R$/L) · Preço médio (R$/L) — uma linha por dia e combustível; é a conta do LMC |
| **COMPRAS** | não | Data · Produto · Litros · Custo (R$/L) · Valor da nota (R$) · Nota fiscal · Distribuidora |
| **DESPESAS** | não | Data · Categoria · Descrição · Valor (R$) |

O contrato mora em `src/planilhas.py`: o gerador de dados, o modelo em branco
e o ETL usam as mesmas definições. O painel calcula o resto (faturamento,
margem, perda/sobra, autonomia, alertas).

> **Para a versão B2:** esse modelo é só o formato da demonstração. Na
> implantação, o leitor (`src/etl.py` + `src/planilhas.py`) é construído para
> o formato real do B2 — a equipe continua trabalhando como hoje.

### Dois jeitos de a planilha chegar

1. **Pelo painel** (Enviar Planilha): o gerente arrasta o arquivo e o painel
   **confere antes de aceitar** — posto certo, mês certo, colunas, estoque
   negativo, preço fora do normal, arquivo repetido e **alteração em dia já
   recebido** — e mostra o que muda. Com erro, a planilha é recusada e **o
   painel anterior continua intacto**; todos os erros aparecem de uma vez. A
   versão substituída fica guardada e pode ser restaurada em *Atualizações*.
2. **Na pasta**, à mão: salve em `data/<posto>/` e rode o `Atualizar Dados.bat`.

> ⚠️ **O painel lê a base Parquet (`data/base/`), não os Excel.** Planilha
> posta à mão só aparece depois do `Atualizar Dados.bat`.

Planilhas de exemplo para testar o envio em `exemplos_para_envio/`:
**GERENCIAL_B2_PRIMAVERA** (completa até 27/09: o alerta "dados desatualizados"
some), **ALTERADA - B2 Primavera** (a mesma, com a venda de 08 e 09/09
baixada: a conferência avisa e a auditoria registra) e **COM ERRO - B2 Candoi**
(sem a coluna de custo médio e com estoque negativo: é recusada). Depois:
*Administração → Restaurar os dados da demonstração*.

---

## 4. Os números em que o dono pode confiar

* **Margem bruta** = faturamento − litros × custo médio.
* **Perda/sobra no LMC** = estoque final − (inicial + compras − vendas). Fica
  **fora** da margem bruta e entra no resultado depois das despesas. Acima de
  0,6% do vendido vira alerta crítico.
* **Autonomia** = estoque ÷ média de venda dos 7 dias anteriores, **posto a
  posto**. A autonomia da rede esconde o pior tanque — por isso o painel diz
  qual é o menor.
* **Comparação com os mesmos dias**, posto a posto: a Primavera parada no dia
  24 se compara com 1–24 de agosto, não com o mês inteiro.
* **Resultado compara em reais, não em %** (com base pequena o percentual
  mente).

---

## 5. Alertas

O `motor_alertas.py` roda no fim do `Atualizar Dados.bat` e, publicado, no
GitHub Actions — **não depende de ninguém estar com o painel aberto**. Não
repete alerta (cada situação avisa uma vez por dia). **Painel e celular leem
as mesmas regras** (`src/alertas.py`).

| Alerta | Dispara quando |
|---|---|
| 🔴 Estoque crítico / 🟡 baixo | autonomia abaixo de 1,5 / 2,5 dias |
| 🔴 Perda acima da tolerância | perda do LMC acima de 0,6% do vendido no mês |
| 🟡 Margem em queda | margem/L dos últimos 7 dias 15% abaixo dos 30 anteriores (diz se foi custo não repassado) |
| 🟡 Margem abaixo do histórico | margem % do mês 1,2 p.p. abaixo da média de 12 meses |
| 🟡 Venda fora do padrão | últimos 7 dias 10% abaixo da média das 8 semanas |
| 🟡 Dados desatualizados | posto 2 dias ou mais atrás dos outros |
| 🔴 Dados alterados depois de recebidos | dia já recebido mudou 7+ dias depois, ou mês fechado |

Os limites são os da demonstração; na versão B2 são calibrados com o
histórico da rede.

**Canais** (`config_alertas.toml` ou variáveis de ambiente): `console`
(padrão), `telegram` (o robô do B2 Assistente), `ntfy` ou `pushover`. Teste com
`python motor_alertas.py --teste`; liste sem enviar com `--listar`.

---

## 6. 🛡️ Controle de fraudes

Nenhum sinal é acusação: é **"confira isto"**. Tudo sai do que o posto já
manda.

**Trilha de auditoria** (`src/auditoria.py`). Toda base nova é comparada com a
anterior, posto × dia × combustível, *antes* da troca. Dia novo é rotina; dia
que já tinha chegado e mudou (ou linha que sumiu) vai para
`data/auditoria.csv` com quem enviou, quando, por onde, valor antes e depois e
impacto em reais.

| Gravidade | Quando | O que acontece |
|---|---|---|
| normal | mexeu no dia de ontem | só fica na trilha |
| atenção | dia com 2+ dias | tela Auditoria |
| **crítico** | dia com 7+ dias, ou **mês já fechado** | alerta na Central e no celular |

O gerente é avisado **no envio** de que a planilha altera dias já recebidos.
Baixar a venda sem mexer na régua também faz a perda do LMC subir: os sinais se
confirmam.

**Cruzamentos** (`src/antifraude.py`): perda/sobra no LMC · combustível que
entrou no tanque **sem nota** · nota **sem entrada** no tanque · **nota
repetida** · valor da nota ≠ litros × custo · **custo médio** fora do que as
notas dão · venda **abaixo do custo** · vendas "redondas" demais.

**Para não poluir:** a Central recebe só **um** alerta por posto com dado
alterado; o resto fica na tela Auditoria. O gerente não vê esse alerta (já foi
avisado no envio).

**Limite honesto:** a trilha pega alteração em dado *já recebido*. Número que
entra errado desde o primeiro envio é denunciado pelo LMC e pelos
cruzamentos; a próxima camada seriam os **encerrantes por bico**.

**História plantada na demonstração:** a Primavera baixou a venda de 03 e
04/09 em 1.200 L (R$ 7,4 mil) no envio de 22/09; o Bonsucesso recebeu 35 mil L
sem nota; o Índio lançou uma nota duas vezes.

---

## 7. 📋 Reunião de Gerentes

Placar do mês com o que o gerente controla (`src/reuniao.py`): volume (vs
mesmos dias), margem/L (vs média da rede), **aditivada na gasolina** (meta
20%), perda no LMC (meta 0,30%), despesa e resultado por litro, **planilha até
as 10h** (meta 90%), dias com estoque crítico e dias alterados depois de
enviados. Só as exceções ficam coloridas. Cada gerente tem a **pauta
sugerida** (do mais grave ao elogio) e a **ficha da reunião** em HTML para
imprimir, com espaço para combinados, responsável e prazo. As metas são da
demonstração e ficam no topo de `src/reuniao.py`.

---

## 8. 📱 B2 Assistente (celular)

O dono manda uma mensagem — **"estoque candói"**, **"resumo centro"**, ou toca
num botão — e recebe na hora, da **mesma base e das mesmas regras do painel**.
Não é IA e não tem custo de API: é consulta direta. Entende sem acento, sem
"B2" e com frase solta.

| Pergunte | Recebe |
|---|---|
| `resumo centro` (ou só `⛽ Centro`) | vendas e litros do mês, margem bruta, último dia, estoque com autonomia e alertas do posto |
| `estoque candói` | litros e dias de cada combustível |
| `vendas primavera` · `margem bonsucesso` | faturamento/litros/mix · margem em R$, %, por litro e contra a média de 12 meses |
| `resumo rede` · `estoque rede` · `vendas rede` · `margem rede` | a rede inteira, com ranking |
| `alertas` | o que exige ação, atenção e destaques |
| `reunião` | o placar das gerências |
| `auditoria` (ou `auditoria primavera`) | os sinais de fraude |
| `pendências` | quais postos ainda não mandaram a planilha |

### Disparos automáticos (sem ninguém perguntar)

Em **B2 Assistente → 3 · Disparos automáticos** você escolhe **o que** mandar
e **quando**:

* **Todo dia, no horário** — ex.: resumo da rede às 07:30; placar das gerências
  às 08:00 de segunda;
* **Assim que os dados chegarem** — a planilha entrou, a base foi montada, os
  alertas saem na hora;
* **Cobrar se não chegar até o horário** — às 10:00, se faltar posto, avisa quem
  está pendente (se todos mandaram, fica quieto).

Vai para **todas as conversas do robô — pessoas e grupos**: ao adicionar o
robô ao grupo da diretoria ele se registra sozinho. A agenda padrão fica em
`src/assistente_agenda.py`; quando editada pelo painel, grava em
`data/assistente_agenda.json`. Um disparo de horário só sai até 15 minutos
depois da hora (painel ligado às 14h não manda o bom-dia atrasado).

### Quem faz o quê (importante)

| O quê | Quem faz | Depende do notebook? |
|---|---|---|
| Responder perguntas no Telegram | painel **da nuvem** (thread dentro do processo) | não |
| Disparos por horário (07:30, 10:00…) | agendador do painel **da nuvem** | não, mas o painel precisa estar acordado |
| Alertas e disparos "assim que chegar" | **GitHub Actions** (`motor_alertas.py` e `--chegada`) | não |

> ⚠️ **Nuvem OU notebook, nunca os dois** com o mesmo robô: o Telegram recusa a
> segunda conexão (erro 409, "robô já conectado em outra janela") e o ntfy
> responde em dobro. Hoje a nuvem é a dona do robô e o Telegram está **desligado
> no painel local** (`telegram_ativo: false` em `config_assistente.local.json`).
> Para testar o robô daqui, desligue o da nuvem antes.

### Como criar o robô (uma vez, 1 minuto)

1. No Telegram, procure **@BotFather** → **Iniciar** → **/newbot**. Nome: *B2
   Gestão*. Usuário terminado em *bot*.
2. Copie o **token** (`123456789:AA…`). **Nunca o coloque em arquivo versionado.**
3. Local: **B2 Assistente → Telegram → Conectar** e cole o token (fica em
   `config_assistente.local.json`, fora do Git). Nuvem: *Settings → Secrets*
   (seção 10).
4. Toque em **Abrir no Telegram** → **Iniciar**.

**ntfy** (tópico `PostoB2`) continua disponível como alternativa, mas é mais
trabalhoso e não tem botões. **WhatsApp** só existe pela API oficial da Meta
(conta empresarial verificada, número exclusivo, modelos aprovados, cobrança
por conversa) — fica para a versão contratada; as respostas são as mesmas, só
troca o transporte.

---

## 9. Usuários e segurança

Sem configuração, o painel roda em **modo demonstração** (usuários fictícios,
senha `b2demo`, acesso rápido). Para usuários de verdade, copie
`.streamlit/secrets.exemplo.toml` para `.streamlit/secrets.toml` e preencha — a
senha vai em hash:

```bash
python -c "from src.auth import gerar_hash; print(gerar_hash('a-senha'))"
```

* **Gerente** vê e alimenta só o posto dele — o login define; a conferência
  recusa arquivo cujo nome cita outro posto.
* **Proprietário** e **administração** veem a rede inteira.
* Senhas em PBKDF2; `secrets.toml` e `config_assistente.local.json` estão no
  `.gitignore` e **nunca** vão para o repositório.
* Na demonstração, o robô só responde se `data/SIMULADO.txt` existir.
* Antes de pôr dado real: configurar `[usuarios]`, apagar `SIMULADO.txt` e as
  planilhas simuladas, e limitar quem pode conversar com o robô.

---

## 10. Publicação (Streamlit Community Cloud + GitHub Actions)

```
Gerente envia a planilha ──► GitHub (commit) ──► Actions monta a base, roda os
testes, manda os alertas e publica ──► Streamlit Cloud atualiza o painel (2–3 min)
```

1. **Painel:** share.streamlit.io → repositório `gcrp94/PostoB2`, branch `main`,
   arquivo `app.py`, Python **3.12**.
2. **Segredos do Streamlit** (*Settings → Secrets*; chaves de primeiro nível
   viram variáveis de ambiente): `B2_TELEGRAM_TOKEN` (o robô) e, se quiser fixar
   o grupo da diretoria, `B2_TELEGRAM_CHATS` (ids separados por vírgula).
   Opcional: `[usuarios]` (versão contratada) e `[github]` (token *fine-grained*
   só deste repositório, *Contents: read and write*, para o envio pelo painel
   gravar no repositório).
3. **Segredos do GitHub Actions** (*Settings → Secrets and variables → Actions*):

   | Segredo | Para quê |
   |---|---|
   | `B2_CANAL` | `telegram` — canal dos alertas do `motor_alertas.py` |
   | `B2_TELEGRAM_TOKEN` | o robô |
   | `B2_TELEGRAM_CHATS` | conversas que recebem (pessoas e grupos), separadas por vírgula |
   | `B2_NTFY_TOPICO`, `B2_PUSHOVER_TOKEN`, `B2_PUSHOVER_USUARIO` | só se usar ntfy/Pushover |
   | variável `B2_URL_PAINEL` | endereço do painel no botão "Abrir" da notificação |

4. **Workflows** (`.github/workflows/`):
   * `atualizar-base.yml` — dispara ao chegar `data/**/*.xlsx` (e manualmente):
     monta a base, roda os testes, manda os alertas novos, dispara o
     "assim que chegar" do assistente e publica `data/base`,
     `alertas_enviados.csv` e `auditoria.csv`.
   * `manter-app-acordado.yml` — o **despertador**: a cada 4 h abre o painel
     num navegador de verdade (Playwright) e clica em *"Yes, get this app back
     up!"* se estiver dormindo (a plataforma hiberna após 12 h sem visita).
     Custa ~360 dos 2.000 minutos gratuitos de Actions por mês. Só funciona
     com o app aberto a visitantes.

> **O disco da Streamlit Cloud não é permanente.** Sem o `[github]`, planilha
> enviada pelo painel publicado se perde, e a agenda editada na nuvem
> (`data/assistente_agenda.json`) volta ao padrão no reinício — para mudar a
> agenda de verdade, edite localmente e faça o commit. Sem `[usuarios]`, o app
> publicado fica em modo demonstração.

---

## 11. Apresentação comercial (HTML, só local)

Em `apresentacao/` há uma apresentação de **27 slides** para vender o sistema
(`Abrir Apresentacao.bat`): a mensagem "o sistema se adapta ao B2", o método de
implantação, as telas, o controle de fraudes, a reunião, o celular, o que já
funciona × o que será construído, possibilidades, cronograma sugerido e um
**apêndice para estudo** (roteiro da demonstração ao vivo, 12 perguntas
difíceis e glossário). Atalhos: setas/espaço navegam, **N** liga o modo estudo
(roteiro de fala ao lado), **O** o índice, **F** tela cheia, **P** gera PDF.

O arquivo final é gerado por `apresentacao/construir.py` a partir de
`fonte.html` (embute o logo e a tendência real dos últimos 30 dias). A pasta
está no `.gitignore`: é material de venda, **não vai para o GitHub**.

### Roteiro da demonstração ao vivo (5 minutos)

1. Antes: **Gerar Dados Simulados.bat** → **Abrir App.bat**; celular com o
   Telegram aberto no robô.
2. **Central:** "a rede pede ação em 3 pontos".
3. **B2 Candói:** o diesel acaba em menos de 1 dia — no celular, `estoque candói`.
4. **B2 Bonsucesso:** `margem bonsucesso` — a margem do diesel caiu 33%: o custo
   subiu e o preço não acompanhou.
5. **Auditoria:** a Primavera baixou 1.200 L de venda depois de enviada.
6. **Reunião de Gerentes:** placar e ficha do gerente.
7. **Envio:** como gerente da Primavera, mande a planilha **ALTERADA** — o aviso
   aparece na hora. Depois, *Restaurar os dados da demonstração*.

---

## 12. Como o projeto é organizado

```
app.py                    Login, menu por perfil e o corpo de todas as telas.
gerar_base.py             Planilhas -> data/base/*.parquet (+ _info.json).
motor_alertas.py          Roda as regras e manda o que é novo ao celular (--chegada, --listar, --teste).
gerar_dados_simulados.py  12 meses simulados + exemplos de envio + histórico + trilha plantada.
keep_alive.py             O despertador (Playwright).
config_alertas.toml       Canal dos alertas.

src/
  planilhas.py   O CONTRATO: abas, colunas, produtos, sinônimos.
  etl.py         Lê e confere as planilhas (só lê).
  base.py        Grava (atômico) e carrega a base Parquet; chama a auditoria.
  analytics.py   As contas: indicadores, fatias por posto, estoque, autonomia, LMC.
  alertas.py     O motor de regras.
  auditoria.py   Trilha do que mudou em dado já recebido.
  antifraude.py  Os cruzamentos de fraude (tela Auditoria).
  reuniao.py     Placar, metas, pauta e ficha da reunião.
  validacao.py   Conferência da planilha enviada pelo painel.
  armazenamento.py  Onde a planilha enviada mora (local ou GitHub) + histórico de envios.
  assistente.py  Entende a pergunta e monta a resposta (sem rede, sem IA).
  assistente_agenda.py  Disparos automáticos (horário, chegada, cobrança) e o agendador.
  assistente_telegram.py / assistente_ntfy.py   Os transportes do celular.
  assistente_ui.py  A tela B2 Assistente e os ouvintes (um por processo).
  notificacoes.py  Console / ntfy / Pushover / Telegram.
  auth.py        Usuários, perfis, PBKDF2, modo demonstração.
  charts.py · ui.py · theme.py · formatting.py   Gráficos, peças visuais, cores, formatação pt-BR.
assets/          style.css (painel antigo), style_novo.css (painel novo), logos.
tests/           test_painel, test_controle, test_assistente*, test_visual.
.github/workflows/  atualizar-base.yml, manter-app-acordado.yml
apresentacao/    A apresentação comercial (fora do Git).
```

Separação mantida do Painel de Finanças: `etl` só lê, `analytics` só calcula,
`charts`/`ui` só desenham, `app.py` orquestra. A gravação da base é atômica
(pasta temporária → troca): planilha com erro nunca derruba o painel.

---

## 13. Problemas comuns

| Sintoma | Causa e solução |
|---|---|
| "Este robô já está conectado em outra janela" | Dois ouvintes no mesmo robô (nuvem + notebook, ou dois painéis). Deixe só um — hoje a nuvem; o `Abrir App.bat` já fecha painel antigo na 8520. |
| `AttributeError` logo após o login | Há um painel antigo na memória. Feche tudo e rode o `Abrir App.bat` de novo. |
| "A base ainda não foi montada" | Rode o `Atualizar Dados.bat` (ou o `Gerar Dados Simulados.bat`). |
| Planilha colocada na pasta não aparece | Rode o `Atualizar Dados.bat`; o painel lê o Parquet. |
| O painel publicado "dormiu" | O despertador acorda a cada 4 h; ou abra o link. Teste: GitHub → Actions → *Manter o painel acordado* → Run workflow. |
| Alertas não chegam ao celular pelo GitHub | Confira os 3 segredos (`B2_CANAL`, `B2_TELEGRAM_TOKEN`, `B2_TELEGRAM_CHATS`) e se o robô já recebeu um "Iniciar" da conversa. Alertas já marcados em `alertas_enviados.csv` não repetem. |
| Mexi em `src/` e nada mudou | Editar `src/` exige reiniciar o servidor do Streamlit. |

---

## 14. Rodando à mão e testando

```bash
pip install -r requirements.txt        # streamlit 1.60.0 é fixo de propósito
python gerar_dados_simulados.py        # só para a demonstração
python gerar_base.py                   # planilhas -> data/base/*.parquet
python motor_alertas.py --listar       # os alertas, sem enviar
streamlit run app.py --server.port=8520
python -m pytest                       # os números fecham? a conferência funciona?
```

Rode `python -m pytest` **antes de apresentar**: um erro de sintaxe num módulo
derruba o painel inteiro (já aconteceu).

---

## 15. Limitações conhecidas e próximos passos

* **Dados simulados:** o formato da planilha é o da demonstração; o leitor sob
  medida para os arquivos reais do B2 é o primeiro passo da implantação.
* **Robô aberto:** hoje qualquer conversa que fale com o robô é registrada (ele
  só responde dado simulado). Na versão B2: lista de conversas autorizadas.
* **Agendador dentro do painel:** os disparos por horário dependem do painel da
  nuvem estar acordado. Na versão contratada: hospedagem dedicada (ou cron).
* **`charts.NOVO` é global por processo:** serve à demonstração; em produto
  multiusuário o visual deve ser passado por parâmetro.
* **Possibilidades (não prometidas):** encerrantes por bico, previsão de
  compras, sugestão de preço de bomba, caixa e formas de pagamento, fluxo de
  caixa, loja/lava-jato, metas e bonificação por gerente, relatório executivo em
  PDF, WhatsApp pela API oficial, PWA com notificação nativa, banco de dados
  (PostgreSQL/Supabase) para 20+ postos.
