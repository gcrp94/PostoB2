# B2 Gestão — resumo para outra conta do Claude assumir o projeto

> **Como usar:** cole este arquivo inteiro no começo da conversa (ou anexe-o)
> e diga o que quer fazer. Ele foi escrito para quem **não viu nada** do que
> aconteceu e **não tem acesso ao repositório**. Atualizado em **02/10/2026**.
> Não contém nenhum segredo: tokens, senhas e ids de conversa ficam fora de
> propósito. Se algo aqui contradisser o código, o código ganha — confira.

---

## 1. Quem é o usuário e como trabalhar com ele

* **Gustavo.** Faz BIs em **Streamlit** alimentados por planilhas Excel
  (planilha → ETL → Parquet → painel), em **Windows**. Já tem um BI
  municipal de finanças (pasta irmã `DASHBOARD FINANÇAS`, de onde este projeto
  herdou arquitetura, regras de formatação e várias lições).
* **Idioma: responda SEMPRE em português do Brasil**, em toda mensagem
  visível (inclusive os avisos curtos de andamento entre ferramentas). Já foi
  corrigido por isso. Código, variáveis, comentários e docstrings do projeto
  são em português: mantenha.
* Gosta de visual **"executivo", limpo e bonito**, uso no **celular**, números
  no padrão brasileiro (R$ 1.234,56 · 1,63 mi L), dados simulados prontos para
  **apresentar**, e **atalhos `.bat`** para tudo.
* Costuma colar propostas escritas por outra IA no meio da tarefa e espera que
  sejam incorporadas com critério ("veja o que faz sentido").
* **Pede explicações claras** e que o BI **não fique poluído**.
* **Regras de operação que ele impôs:**
  * **Confirmar antes de `git push`** (ele aprova push a push; commit local
    pode ser feito quando ele pede ou ao concluir um bloco).
  * **Nunca** digitar senha, token ou chave em campos de formulário na web — o
    usuário cola o segredo ele mesmo. Nunca gravar token em arquivo versionado.
  * Margem sempre **"margem bruta"**, nunca "lucro" (pedido explícito).
* **Git:** o repositório usa identidade própria (`user.name "Gustavo Paula"`).
  Conta do GitHub: **`gcrp94`** (a conta nova; há outra conta `xmsgtx94` que
  **não** é a certa — o login por navegador já confundiu as duas).

---

## 2. O projeto em cinco linhas

**B2 Gestão** é um sistema de gestão **sob medida para a rede B2 Postos**
(5 postos: B2 Centro, B2 Bonsucesso, B2 Primavera, B2 Índio — Guarapuava — e
B2 Candói — Candói/PR). A tese comercial: **"o sistema se adapta ao B2, não o
B2 ao sistema"** — ele lê o que a rede já produz, entende o modelo de gestão
do B2 e entrega **análises, alertas, sugestões e relatórios** ao gestor,
no painel e no Telegram. **Hoje é uma DEMONSTRAÇÃO com dados 100% simulados**
(12 meses, out/2025–set/2026), feita para **vender** o projeto ao dono da rede.
Nada nos dados é de posto real.

---

## 3. Estado em 02/10/2026

**Pronto e funcionando (testado, 105 testes passando):**

* Painel Streamlit completo: Central do Proprietário, Visão da Rede, 5 postos
  (6 abas cada), Reunião de Gerentes, Auditoria, Alertas, Alimentar dados,
  Atualizações, B2 Assistente, Administração; perfis Proprietário / Gerente /
  Administração (gerente só vê o próprio posto).
* **Painel antigo × novo** (botão no menu lateral; padrão = novo).
* Envio de planilha pelo painel com **conferência** antes de aceitar,
  versões restauráveis e histórico de envios.
* **Controle de fraudes:** trilha de auditoria (dado alterado depois de
  recebido, com gravidade) + cruzamentos (LMC, nota×tanque, nota repetida…).
* **Reunião de gerentes:** placar com metas, pauta por gerente, ficha HTML.
* **B2 Assistente no Telegram** (consulta direta, sem IA) + **disparos
  automáticos** (horário, "assim que os dados chegarem", cobrança com horário
  limite) para pessoas e grupos.
* **Publicado:** painel em `https://b2gestao.streamlit.app` (Streamlit
  Community Cloud, modo demonstração), repositório privado
  `github.com/gcrp94/PostoB2`, **GitHub Actions** (monta a base, roda testes,
  manda alertas, dispara "chegada") e **despertador** que mantém o app acordado.
* **Apresentação comercial em HTML** (27 slides, modo estudo com roteiro de
  fala, apêndice com perguntas difíceis) — pasta `apresentacao/`, **só local,
  fora do Git**.

**Não existe / pendente (ver seção 12):** dados reais; leitor sob medida para o
formato real do B2; usuários reais; lista de conversas autorizadas no robô;
WhatsApp; encerrantes por bico; relatórios em PDF; hospedagem dedicada.

**Último commit enviado ao GitHub:** `3f892d3` ("Painel novo x Painel antigo").
Depois dele há, **só no computador do usuário**, alterações ainda não
enviadas: README reescrito, este resumo, e `.gitignore` (ignora
`apresentacao/` e `Abrir Apresentacao.bat`).

---

## 4. Infraestrutura e acessos (sem segredos)

| Item | Valor |
|---|---|
| Pasta local | `C:\Users\gustavo.paula\Documents\Gustavo\CÓDIGOS\B\DASHBOARD B2 POSTOS\` |
| Python local | 3.14 em `C:\Users\gustavo.paula\AppData\Local\Python\pythoncore-3.14-64\python.exe` (no Actions/Cloud: **3.12**) |
| Streamlit | **1.60.0 fixo** no `requirements.txt` (versão nova muda o HTML e quebra o CSS) |
| Painel local | `Abrir App.bat` → `http://localhost:8520` |
| Painel publicado | `https://b2gestao.streamlit.app` (o app real fica em `/~/+/` dentro de um iframe) |
| Repositório | `github.com/gcrp94/PostoB2` (**privado**), branch `main` |
| Robô do Telegram | `@B2TesteExBot` (token só nos segredos e em `config_assistente.local.json`) |
| ntfy (alternativa) | servidor `https://ntfy.sh`, tópico `PostoB2` |
| Login de demonstração | botões de acesso rápido; senha de todos: `b2demo` |

**Segredos (nomes apenas):**

* GitHub Actions: `B2_CANAL` (= `telegram`), `B2_TELEGRAM_TOKEN`,
  `B2_TELEGRAM_CHATS`; opcionais `B2_NTFY_TOPICO`, `B2_PUSHOVER_*`; variável
  `B2_URL_PAINEL`.
* Streamlit Cloud (Settings → Secrets; chaves de 1º nível viram variáveis de
  ambiente): `B2_TELEGRAM_TOKEN` (o robô); opcionais `B2_TELEGRAM_CHATS`,
  `[usuarios]` (versão contratada), `[github]` (token fine-grained para o envio
  pelo painel gravar no repo). **Sem `[usuarios]`, o app publicado fica em modo
  demonstração: qualquer um com o link entra como proprietário** (proposital).
* Local: `config_assistente.local.json` (token, conversas, agenda_estado) e
  `.streamlit/secrets.toml` — **ambos no `.gitignore`; nunca versionar.**

**Quem faz o quê com o robô (decisão atual):**

* O **painel da nuvem** é o dono do robô: responde perguntas e roda o
  agendador (disparos por horário).
* O **GitHub Actions** manda os alertas e os disparos "assim que chegar"
  (`motor_alertas.py` e `motor_alertas.py --chegada`) via API HTTPS do Telegram
  — sem depender de computador do B2.
* O painel **local** está com o Telegram **desligado** (`telegram_ativo:
  false`). **Dois ouvintes no mesmo robô = erro 409** ("robô já conectado em
  outra janela") e respostas em dobro. Nunca ligue os dois.

**Workflows:** `atualizar-base.yml` (dispara em `push` de `data/**/*.xlsx` e
manual; monta base → testes → alertas → `--chegada` → publica `data/base`,
`alertas_enviados.csv`, `auditoria.csv`) e `manter-app-acordado.yml` (cron a
cada 4 h; Playwright abre o painel e clica em "Yes, get this app back up!").

---

## 5. Arquitetura (planilha → ETL → Parquet → painel)

```
Excel por posto/mês ─► etl.py (lê e confere) ─► base.py (compara com a base anterior,
grava a trilha de auditoria, troca ATÔMICA) ─► data/base/*.parquet ─► analytics.py (contas)
─► alertas.py / antifraude.py / reuniao.py ─► app.py (telas) · assistente*.py (celular)
```

Separação (herdada do projeto de Finanças): `etl` só lê, `analytics` só calcula,
`charts`/`ui` só desenham, `app.py` orquestra. **O painel lê Parquet, nunca
Excel.** Planilha com erro nunca derruba o painel.

| Arquivo | Papel |
|---|---|
| `app.py` | Login, menu por perfil e todas as telas |
| `gerar_base.py` | Planilhas → `data/base/` (+ `_info.json`) |
| `motor_alertas.py` | Roda as regras e manda o que é novo (`--listar`, `--teste`, `--chegada`) |
| `gerar_dados_simulados.py` | 12 meses simulados, exemplos de envio, histórico, trilha plantada |
| `src/planilhas.py` | **O contrato**: abas, colunas, produtos, sinônimos |
| `src/etl.py`, `base.py`, `validacao.py`, `armazenamento.py` | Ler, gravar/carregar base, conferir envio, guardar envios (local ou GitHub) |
| `src/analytics.py` | Indicadores, fatias por posto, estoque, autonomia, LMC, séries |
| `src/alertas.py` | Motor de regras (`Alerta`, `gerar`, `situacao_posto`) |
| `src/auditoria.py` | Trilha do que mudou em dado já recebido (`data/auditoria.csv`) |
| `src/antifraude.py` | Cruzamentos de fraude (`Sinal`) |
| `src/reuniao.py` | Placar, metas, pauta, ficha HTML |
| `src/assistente.py` | Entende a pergunta e monta a `Resposta` (sem rede, sem IA) |
| `src/assistente_agenda.py` | Disparos automáticos + `Agendador` (thread) |
| `src/assistente_telegram.py`, `assistente_ntfy.py` | Transportes |
| `src/assistente_ui.py` | Tela do assistente e os ouvintes (um por processo) |
| `src/notificacoes.py` | Console/ntfy/Pushover/Telegram (alertas automáticos) |
| `src/auth.py` | Usuários, perfis, PBKDF2, modo demonstração |
| `src/charts.py`, `ui.py`, `theme.py`, `formatting.py` | Gráficos Plotly, peças visuais, cores, formatação pt-BR |
| `assets/style.css` / `style_novo.css` | Painel antigo / camada do painel novo |
| `tests/` | `test_painel`, `test_controle`, `test_assistente*`, `test_visual` |
| `apresentacao/` | Deck HTML (`fonte.html` + `construir.py` → `Apresentacao B2 Gestao.html`) — fora do Git |

---

## 6. Dados e regras de negócio

**Contrato da planilha** (uma por posto por mês, em `data/<pasta_do_posto>/`,
nome `B2 Centro 09-2026.xlsx`):

* **MOVIMENTO DIÁRIO** (obrigatória): Data · Produto · Estoque inicial (L) ·
  Compras (L) · Vendas (L) · Estoque final (L) · Custo médio (R$/L) · Preço
  médio (R$/L). Uma linha por dia e combustível.
* **COMPRAS** (opcional): Data · Produto · Litros · Custo (R$/L) · Valor da nota
  (R$) · Nota fiscal · Distribuidora.
* **DESPESAS** (opcional): Data · Categoria · Descrição · Valor (R$).
* Produtos: Gasolina Comum, Gasolina Aditivada, Etanol, Diesel S10.
* `CADASTRO DOS POSTOS.xlsx` traz postos e capacidade dos tanques.
* **Cor do combustível é identidade fixa** (laranja `#eb6834`, azul `#2a78d6`,
  verde `#1baf7a`, violeta `#4a3aa7`); verde/âmbar/vermelho são **só** situação,
  sempre com ícone e palavra. Marca: azul `#041243`, laranja `#e4612a`.

**Conceitos e constantes:**

* **Margem bruta** = faturamento − litros × custo médio. Perda/sobra do LMC
  = estoque final − (inicial + compras − vendas); fica **fora** da margem bruta.
  Tolerância de perda 0,6% do vendido (`an.TOLERANCIA_PERDA`).
* **Autonomia** = estoque ÷ média de venda dos 7 dias anteriores, por posto;
  crítico < 1,5 dia, atenção < 2,5 dias.
* **Comparação sempre com os mesmos dias** do mês anterior, posto a posto
  (`analytics.fatias`) — a Primavera parada no dia 24 compara 1–24.
* **Alertas** (`src/alertas.py`): estoque, perda, margem em queda (−15%),
  margem abaixo do histórico (1,2 p.p.), venda fora do padrão (−10%), dados
  desatualizados (2 dias) e **dados alterados depois de recebidos** (um alerta
  por posto na Central).
* **Auditoria:** compara base nova × anterior (posto × dia × produto) *antes* da
  troca. Gravidade: normal (dia com menos de 2 dias de idade), atenção (2+ dias), **crítico** (dia
  com 7+ dias ou mês fechado). Linha apagada também é registrada.
  O gerente é avisado no envio (`Relatorio.alteracoes`).
* **Reunião:** metas aditivada 20%, perda 0,30%, planilha até as 10h em 90%
  dos dias; margem e despesa contra a média da rede (folga R$ 0,03/L).
* **Assistente** (`assistente.entender`): ações `alertas, auditoria,
  pendencias, reuniao, estoque, vendas, margem, resumo, ajuda`; tolera acento,
  "B2" opcional; só o nome do posto = resumo do posto. Texto não entendido =
  `ValueError` com a ajuda.
* **Agenda** (`assistente_agenda.PADRAO`): bom-dia 07:30 (resumo da rede, todo
  dia); chegada (alertas); cobrança 10:00 (pendências, seg–sáb); placar 08:00
  seg. Disparo de horário só sai até 15 min depois da hora. "Já mandei hoje"
  fica em `config_assistente.local.json`.

---

## 7. Decisões que não devem ser desfeitas sem conversar com o usuário

1. **"Margem bruta", nunca "lucro".** O resultado depois das despesas só
   aparece em *Compras e Custos* e é antes de IR/CSLL.
2. **O painel lê Parquet.** Gravação atômica; planilha com erro é recusada e o
   painel anterior continua no ar.
3. **Painel e celular leem as mesmas regras** (`alertas.py`): o celular nunca
   mostra algo que a Central não mostra.
4. **O robô só responde com dado simulado** enquanto existir
   `data/SIMULADO.txt` (quem achar o robô não chega a dado real).
5. **Gerente não escolhe posto**; o login define e o nome do arquivo é conferido.
6. **Anti-poluição:** a Central recebe **um** alerta de auditoria por posto; o
   resto dos sinais vive na tela Auditoria; o placar só pinta exceções; o
   gerente não vê o alerta de auditoria.
7. **Nenhum sinal de fraude é acusação** ("confira isto"). Nunca prometer
   "elimina fraude" — a trilha só pega alteração em dado *já recebido*.
8. **Sem IA** no assistente (consulta direta, explicável).
9. **WhatsApp** só pela API oficial da Meta (conta verificada, cobrança): fica
   para a versão contratada; hoje Telegram.
10. **Mensagem comercial honesta:** na demo o formato é um modelo enxuto; ler o
    formato real do B2 é o trabalho de conectores sob medida. O deck separa
    "já funciona" × "será construído".

---

## 8. Armadilhas técnicas (já custaram tempo)

* **Streamlit 1.60:** o botão que abre o menu lateral fica dentro do
  `stToolbar` (esconder a barra inteira tira o menu do celular); a opção de rádio
  é `label[data-testid="stRadioOption"]`; **chave de widget não pode coincidir
  com chave do `session_state` que o código escreve** (o form "login" colidiu);
  as abas do posto guardam o valor em `aba_<posto>` e o `segmented_control` só
  espelha via `on_change`.
* **Editar `src/` exige reiniciar o servidor.** Módulo recarregado deixa
  instância velha em `st.cache_resource` → `ouvintes()` troca a instância
  antiga e para os serviços dela.
* **Threads (agendador, Telegram) não podem chamar API do Streamlit**
  (`st.cache_resource` etc.). Por isso `enviar_programado` é método do
  `Controle`.
* **HTML em `st.markdown`:** linha em branco seguida de linha recuada vira
  bloco de código. Todo HTML do `ui.py` é montado em **uma linha**.
* **Telegram:** long polling (`getUpdates`), `allowed_updates` inclui
  `my_chat_member` (registro/remoção de grupos); teclado fixo só em conversa
  privada; fila antiga é ignorada ao ligar; token nunca aparece em erro.
* **Painel antigo na mesma porta** (8520) já causou `AttributeError` após login
  (código velho na memória) — o `Abrir App.bat` agora mata o processo da porta
  antes de subir.
* **`charts.NOVO` é variável global** ligada a cada rerun pelo `app.py`: ok para
  demonstração, errado para multiusuário.
* **Painel novo:** CSS em `style_novo.css` por cima do `style.css`; o ícone do
  menu entra por `format_func` do `st.radio` (`:material/nome:`), mas o **valor**
  do menu continua com emoji (o roteamento usa `pagina.startswith("🎯")`).
  `<details>` funciona dentro do `st.markdown` com HTML.
* **Windows/PowerShell:** o antivírus às vezes bloqueia o PowerShell da
  ferramenta ("conteúdo mal-intencionado") — repetir ou usar Bash costuma
  resolver. Em PowerShell, here-strings e aspas aninhadas falham: prefira editar
  arquivos com a ferramenta de edição. `git commit -F -` não funciona lá: use
  arquivo de mensagem. Saída com emoji no console Windows exige
  `PYTHONIOENCODING=utf-8`.
* **Streamlit Cloud:** disco **não permanente**; app dorme após 12 h sem visita
  (despertador a cada 4 h); um commit de dados reinicia o app, então o agendador
  interno não "vê" a chegada — daí o `--chegada` no Actions.
* **Gerador de dados:** apaga `data/base` antes de remontar (senão a troca de
  cenário viraria "alteração" na auditoria) e semeia a trilha com a hora do
  envio. O diesel do Candói precisa terminar com ~1 dia de autonomia (o gerador
  procura o tamanho da carga parcial).

---

## 9. As 9 histórias plantadas na demonstração

1. **Candói** — Diesel S10 quase no fim (0,9 dia) em plena safra.
2. **Primavera** — perda de ~1% na Gasolina Comum desde agosto (vazamento/desvio).
3. **Primavera** — guerra de preço: concorrente abriu em junho, margem cortada.
4. **Aumento do diesel (15/09, +R$ 0,28/L):** 4 postos repassaram; o
   **Bonsucesso** segurou o preço → margem do diesel caiu 33,5%.
5. **Índio** — perdendo volume (obras na saída da BR-277 desde 08/09).
6. **Bonsucesso** cresce; **Candói** tem a melhor margem/L; **Centro** é o maior
   faturamento.
7. **Primavera** — venda de Gasolina Comum de 03 e 04/09 **baixada depois de
   enviada** (−700 L e −500 L; registrada em 22/09 por `marcos.primavera`).
8. **Bonsucesso** — carga de 35.000 L em 12/09 **sem nota** na aba COMPRAS.
9. **Índio** — nota fiscal de etanol **lançada duas vezes**.

Além disso, a Primavera manda a planilha em horário irregular (pontualidade
baixa no placar) e parou de enviar no dia 24 ("3 dias sem enviar").
`exemplos_para_envio/` traz 3 planilhas para demonstrar o envio: **completa**,
**ALTERADA** (aviso de alteração em dia já recebido) e **COM ERRO** (recusada).

---

## 10. Como rodar, testar e demonstrar

```bash
pip install -r requirements.txt
python gerar_dados_simulados.py && python gerar_base.py   # cenário limpo
streamlit run app.py --server.port=8520                    # ou Abrir App.bat
python motor_alertas.py --listar                           # alertas sem enviar
python -m pytest                                           # 105 devem passar
```

* **Rode `pytest` antes de apresentar** (um erro de sintaxe em um módulo derruba
  o painel inteiro; já aconteceu).
* Para um segundo painel de teste sem brigar com o robô: variável
  `B2_ASSISTENTE_DESLIGADO=1` (liga o painel sem ligar os ouvintes).
* Os testes de histórias plantadas só rodam com `data/SIMULADO.txt` presente.
* Roteiro de demonstração (5 min): Central ("pede ação em 3 pontos") → Candói
  (diesel 0,9 dia) → celular `estoque candói` → Bonsucesso (margem do diesel) →
  Auditoria (1.200 L apagados) → Reunião → envio da planilha ALTERADA como
  gerente da Primavera. Depois: *Administração → Restaurar os dados da
  demonstração*.

---

## 11. Histórico resumido (28/09 → 02/10/2026)

* **28/09** — nasce o projeto como evolução comercial do Painel de Finanças:
  painel por perfis (Central, Visão da Rede, posto com 6 abas), contrato de
  planilha, 12 meses simulados, motor de alertas, envio pelo painel com
  conferência, versões e histórico.
* **28–29/09** — **B2 Assistente**: ntfy → Telegram (mais fácil, com botões,
  grupos); `Abrir App.bat`; subida ao GitHub; deploy no Streamlit Cloud.
* **30/09** — despertador (Playwright) copiado do projeto de Finanças.
* **30/09** — **disparos automáticos**, **controle de fraudes** (trilha de
  auditoria + cruzamentos), **reunião de gerentes**, exemplos ALTERADA, testes
  (76 → 96).
* **01/10** — Telegram passa a viver na **nuvem**; segredos do GitHub criados
  (`B2_CANAL`, `B2_TELEGRAM_*`); teste do workflow manual com sucesso (a
  mensagem chegou ao Telegram); **Painel novo × antigo** aprovado e enviado
  (105 testes); `Abrir App.bat` passa a fechar painel antigo.
* **01–02/10** — apresentação comercial em HTML (27 slides); README e este
  resumo.

---

## 12. Pendências e ideias (nada disto está feito)

* **Para vender/implantar:** definir preço e prazos (o deck não traz preço de
  propósito); imersão no B2 (fontes reais, metas, calendário de fechamento);
  construir o leitor para o formato real; usuários reais; limpar
  `SIMULADO.txt`, planilhas e `exemplos_para_envio/`.
* **Robô:** lista de conversas autorizadas; WhatsApp pela API oficial; (ideia)
  agendar disparos no próprio Actions (cron) para não depender do painel
  acordado.
* **Produto:** encerrantes por bico, previsão de compras, sugestão de preço de
  bomba, caixa/formas de pagamento, fluxo de caixa, loja/lava-jato, metas e
  bonificação por gerente, relatório executivo em PDF, tema escuro, tanques na
  horizontal, tela de telão, PWA com notificação nativa, banco de dados para
  20+ postos.
* **Higiene:** passar o visual por parâmetro (hoje `charts.NOVO` é global);
  `git pull` antes de `git push` (o Actions também commita em `main`).

---

## 13. Se você for continuar o trabalho (checklist para a outra conta)

1. Leia `README.md` (manual) e `CLAUDE.md` (decisões e armadilhas detalhadas)
   se tiver acesso aos arquivos; senão, trabalhe a partir deste resumo.
2. **Responda em português.** Seja direto; o usuário valora clareza.
3. Antes de mexer: `python -m pytest`. Depois de mexer em `src/`: reinicie o
   servidor.
4. **Não faça `git push` sem o usuário pedir.** Faça `git pull --rebase` antes
   (o Actions commita em `main`). Termine a mensagem de commit com a linha de
   atribuição indicada pela sua própria sessão.
5. **Nunca** grave token/senha em arquivo versionado, nem digite segredo em
   formulário na web. Peça ao usuário para colar.
6. Não ligue o robô do Telegram em dois lugares ao mesmo tempo.
7. Ao mostrar telas ou explicar ao dono, mantenha a honestidade: dados
   simulados; leitor do formato real = trabalho sob medida; a auditoria só pega
   alteração em dado já recebido.
