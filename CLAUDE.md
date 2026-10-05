# B2 Gestão — Painel da Rede B2 Postos

Painel Streamlit para o **proprietário de uma rede de 5 postos de
combustível** (B2 Centro, B2 Bonsucesso, B2 Primavera, B2 Índio — Guarapuava;
B2 Candói — Candói, PR). Nasceu em 28/09/2026 como evolução comercial do
**Painel de Finanças** (`../DASHBOARD FINANÇAS`), de quem herda a arquitetura,
as regras de formatação e várias lições. O [README.md](README.md) é o manual.

**Estado atual: DEMONSTRAÇÃO.** Todos os dados são simulados
(`gerar_dados_simulados.py`); `data/SIMULADO.txt` marca isso. Quando entrar
dado real: apagar as planilhas simuladas, o `SIMULADO.txt` e o
`exemplos_para_envio/`, e configurar usuários no `secrets.toml`.

---

## Regras de ouro

1. **Margem bruta, nunca "lucro".** Faturamento − litros × custo médio. É o
   que a planilha sustenta sozinha e é o número principal de todas as telas.
   O resultado depois das despesas só aparece em *Compras e Custos*, com esse
   nome, e é antes de IR/CSLL. Pedido explícito do usuário.
2. **O painel lê Parquet, não Excel.** `gerar_base.py` (ou o envio pelo
   painel) monta `data/base/`. A gravação é atômica (`base.gravar`): pasta
   temporária → troca. Planilha com erro nunca derruba o painel no ar.
3. **Comparação é sempre com os MESMOS DIAS**, e POSTO A POSTO
   (`analytics.fatias`): cada posto envia num dia; a Primavera parada no dia
   24 se compara com 1–24 de agosto, não com 1–27 (o atraso pareceria queda).
4. **Cor do combustível é identidade, fixa em todo lugar** (`theme.py`),
   validada no validador de paleta (daltonismo ΔE 9,2, visão normal ΔE 16,3,
   todos os pares): Comum `#eb6834`, Aditivada `#2a78d6`, Etanol `#1baf7a`,
   Diesel `#4a3aa7`. Verde/âmbar/vermelho são SÓ situação, sempre com ícone e
   palavra. Laranja da marca `#e4612a` e azul `#041243` saíram da logo.
5. **Painel e celular leem as mesmas regras** (`src/alertas.py`): o celular
   nunca mostra alerta que a Central não mostra.

---

## Mapa do código

```
app.py                  Login, menu por perfil e o corpo de todas as telas.
gerar_base.py           Planilhas -> data/base/*.parquet (+ _info.json).
motor_alertas.py        Roda as regras e manda o que é novo ao celular.
gerar_dados_simulados.py  12 meses simulados + exemplos de envio + histórico.
config_alertas.toml     Canal dos alertas (console | ntfy | pushover).

src/
  planilhas.py      O CONTRATO: abas, colunas, produtos, categorias, sinônimos.
  etl.py            Lê e confere as planilhas (só lê; nenhuma conta).
  base.py           Grava (atômico) e carrega a base Parquet.
  analytics.py      As contas: indicadores, fatias por posto, estoque,
                    autonomia, séries, perdas do LMC, resultado.
  alertas.py        O motor de regras (Alerta, gerar, situacao_posto).
  validacao.py      Conferência da planilha enviada pelo painel.
  armazenamento.py  Onde a planilha enviada mora (local ou GitHub) e o
                    histórico de envios (data/envios.csv).
  notificacoes.py   ntfy / Pushover / Telegram / console (alertas automáticos).
  assistente.py     B2 Assistente: entende a pergunta e monta a resposta.
  assistente_telegram.py / assistente_ntfy.py   os transportes do celular.
  assistente_whatsapp.py   WhatsApp por sessão logada (TESTE, chip dedicado; whatsapp_assistente.py).
  assistente_ui.py  tela 💬 B2 Assistente e os ouvintes (um por processo).
  assistente_agenda.py  disparos automáticos (horário, chegada, cobrança).
  mercado.py / radar_ui.py   Radar de Mercado: preços PÚBLICOS da ANP (ver seção abaixo).
  nota_parana.py     Menor Preço (preço da NFC-e): coleta diária LOCAL + análises (ver seção abaixo).
coletar_nota_parana.py  Roda a coleta (varre Guarapuava em grade, com pausas); `Coletar Menor Preco.bat`.
  auditoria.py      trilha do que mudou em dado já recebido.
  antifraude.py     sinais de fraude (tela 🛡️ Auditoria).
  reuniao.py        placar, metas e pauta da reunião de gerentes.
  auth.py           Usuários, perfis, PBKDF2, modo demonstração.
  charts.py         Plotly: gramática única, números em pt-BR via Python.
  ui.py             Cartões, tanques, tabelas, alertas em HTML.
  theme.py          Cores e ícones — fonte única de verdade.
  formatting.py     R$, L, %, p.p. no padrão brasileiro.
assets/style.css    O visual (variáveis vindas do theme.py).
tests/test_painel.py, test_controle.py, test_assistente*.py
.github/workflows/atualizar-base.yml
```

Separação mantida do Painel de Finanças: `etl` só lê, `analytics` só
calcula, `charts`/`ui` só desenham, `app.py` orquestra.

---

## Decisões e armadilhas

**A planilha segue o formato que o usuário propôs**: uma linha por dia e
produto com estoque inicial, compras, vendas, estoque final, custo médio e
preço médio — a conta do LMC que o posto já faz por obrigação. COMPRAS e
DESPESAS são abas opcionais.

**Perda/sobra = estoque final − (inicial + compras − vendas).** Fica FORA da
margem bruta (para a margem por litro continuar sendo preço − custo) e entra
no resultado depois das despesas. Tolerância de referência 0,6% do vendido.

**Autonomia = estoque ÷ média de venda dos 7 dias anteriores**, posto a
posto na última data DELE. A autonomia da rede (soma ÷ soma) esconde o pior
tanque — por isso o cartão diz qual é o menor.

**Gerente não escolhe posto.** O login define (`Usuario.posto`), e a
conferência ainda recusa arquivo cujo NOME cita outro posto.

**Conferência mostra TODOS os problemas de uma vez** (coluna faltando não
interrompe as outras verificações): quem corrige a planilha não pode
descobrir um erro por envio.

**Resultado compara em reais, não em %.** Com base pequena o percentual
mente ("−232%"). Mesma lição do Painel de Finanças.

**Streamlit 1.60 (preso no requirements):**
* o botão que ABRE o menu lateral fica dentro do `stToolbar` — esconder a
  barra inteira deixou o celular sem menu. Só `stMainMenu`/deploy saem;
* a opção de rádio é `label[data-testid="stRadioOption"] > div > div >
  div:first-child` (a bolinha) — é o que o CSS esconde no menu lateral;
* chave de widget não pode coincidir com chave do `session_state` que o
  código escreve (o form "login" colidiu com `session_state["login"]`);
* as abas do posto: o valor mora em `aba_<posto>`; o `segmented_control`
  só espelha, via `on_change` — clicar na aba marcada (que o Streamlit
  desmarca) não perde a escolha, e os botões "Abrir →" da Central escrevem
  direto em `aba_<posto>`;
* editar `src/` exige reiniciar o servidor.

**Gráficos:** rótulo de valor ao lado de marca colide quando os números se
aproximam — no gráfico "Onde a margem caiu?" os valores vão numa coluna à
direita. Eixo de 12 meses leva o ano só no 1º mês e em janeiro (cabe no
celular). Barra com texto fora usa `constraintext="none"` (senão o Plotly
encolhe o rótulo até sumir).

**Dados simulados** (`gerar_dados_simulados.py`): sorteio próprio por posto
(`zlib.crc32` do nome — mexer num não muda os outros). O diesel do Candói
precisa terminar com ~1 dia de autonomia: o gerador procura o tamanho da
carga parcial que produz isso (`simular_com_historia`). As 9 situações
plantadas estão no docstring do gerador e em `test_motor_acha_as_situacoes_da_demonstracao` e `test_auditoria_acha_as_fraudes_plantadas`.

---

## B2 Assistente — o celular (28–29/09/2026)

Pedido do usuário para a venda: mandar "resumo b2 centro" pelo celular e
receber vendas, litros e estoque com dias de autonomia. Ele achou o ntfy
complicado e pediu algo mais fácil "que permita interação".

* **Cérebro: `src/assistente.py`** — `entender()` (tolerante: sem acento, sem
  "B2", frase solta; só o posto = resumo; ação sem posto = rede) e
  `responder()`. Usa `alertas.gerar` — a MESMA regra da Central (a primeira
  versão tinha regras próprias, duplicadas; foi refeita). Texto não entendido
  = `ValueError` com a ajuda, que os transportes devolvem ao usuário.
* **Transportes:** `assistente_telegram.py` (recomendado: conversa com
  botões, @BotFather em 1 minuto, long polling — sem servidor, roda no
  notebook) e `assistente_ntfy.py` (alternativa; tópico `PostoB2`). Só
  biblioteca padrão. Token nunca aparece em mensagem de erro.
* **Ouvintes no processo do painel** (`assistente_ui.Controle`, via
  `st.cache_resource`), ligados ANTES do login no `app.py`: basta o `Abrir
  App.bat` abrir o navegador uma vez. Duas janelas do painel com o mesmo robô
  = erro 409 do Telegram, e a tela diz "feche a outra".
* **Só dados simulados:** os dois canais respondem só com `data/SIMULADO.txt`
  presente — quem achar o robô não chega a dado real.
* **Fila antiga é ignorada** ao ligar o robô: responder "a pergunta de ontem"
  na frente do comprador seria estranho.
* `config_assistente.local.json` (fora do Git) guarda token e conversas do
  Telegram e o tópico do ntfy. Alertas automáticos pelo robô: `canal =
  "telegram"` no `config_alertas.toml` (`notificacoes.telegram_destinos`).
* **WhatsApp:** a API oficial da Meta (empresa verificada, modelos aprovados, cobrança) ou intermediário pago é o caminho
  de PRODUÇÃO — só o transporte muda, o cérebro é o mesmo. Para TESTE existe a sessão logada (seção abaixo).
* O painel ficou fora do ar por um erro de sintaxe no `assistente.py` da
  primeira versão (o `app.py` importa o módulo). Os testes pegariam: rode
  `python -m pytest` antes de apresentar.

---

## B2 Assistente no WhatsApp — sessão logada, TESTE (05/10/2026)

Pedido do usuário: usar um chip de WhatsApp Business gratuito, logado por sessão, para conversar com o assistente pelo
WhatsApp em vez do Telegram ("fica mais na mão"). `src/assistente_whatsapp.py`, `whatsapp_assistente.py`,
`Iniciar WhatsApp.bat`, `tests/test_assistente_whatsapp.py`, `requirements-whatsapp.txt` (fora do requirements da nuvem).

* **Como liga:** biblioteca `neonize` 0.5.2 (Python sobre o *whatsmeow*, sem Node). O chip vira **aparelho vinculado**
  (QR em `http://127.0.0.1:8531/`, só localhost). Sessão em `sessao_whatsapp/b2.db`; `LoggedOut` = o celular desconectou:
  apagar a pasta e parear de novo. Sessão vinculada expira se o celular do chip ficar ~14 dias sem abrir o WhatsApp.
* **NÃO é oficial: risco de a Meta limitar/banir o número.** Por isso: chip DEDICADO, só responde (nunca inicia, nunca em
  massa), pausa de 1–2,5 s, máx. 8 mensagens/min por pessoa, texto simples. **Nunca com dado real** nem com o número do negócio.
* **Segurança (testada):** só responde a quem está em `config_whatsapp.local.json` (`--autorizar NUMERO`); estranho, grupo e
  mensagem própria são ignorados em silêncio (log com número mascarado). Aceita o 9º dígito dos dois jeitos e o ID
  alternativo (LID) do remetente. Só com `data/SIMULADO.txt`, como o Telegram. `sessao_whatsapp/` e o config estão no
  `.gitignore`: **a sessão dá acesso à conta, nunca versionar**.
* **Diferenças do Telegram:** sem botões (as sugestões viram lista numerada; "2" executa a 2ª da última resposta), sem
  teclado fixo, sem grupos por enquanto, processo à parte do painel (não usa streamlit). Disparos programados
  (`assistente_agenda`) e alertas automáticos ainda NÃO usam este canal.

## Controle de fraudes, reunião e disparos (30/09/2026)

Pedido do usuário: disparos programados no B2 Assistente (horário, chegada
dos dados, cobrança com horário limite) para pessoas e grupos; alertas de
fraude, em especial **dado já recebido que foi alterado depois**; indicadores
para reunião com gerentes — **sem poluir o BI**.

* **`src/auditoria.py`** — `base.gravar` compara a base nova com a anterior
  (posto × dia × combustível) ANTES da troca e anota em `data/auditoria.csv`.
  Dia novo não é alteração; linha que sumiu é. Gravidade pela idade do dia
  (normal < 2 dias, atenção, crítico ≥ 7 dias ou mês fechado). A conferência
  do envio (`validacao`) avisa o gerente antes. O `.csv` vai para o Git (o
  Actions o publica junto com a base).
* **`src/antifraude.py`** — os cruzamentos (LMC, notas × tanque, nota repetida,
  valor de nota, custo médio × notas, abaixo do custo, números redondos).
  A 2ª via de nota repetida não vira também "nota sem entrada".
* **`src/reuniao.py`** — placar, metas, pauta e a ficha HTML. Margem e
  despesa contra a média da rede; perda, aditivada e pontualidade com meta.
* **Anti-poluição:** a Central recebe UM alerta por posto com dado alterado
  (`alertas.regra_auditoria`); o resto fica em 🛡️ Auditoria (Gestão). O
  placar fica em 📋 Reunião de Gerentes (Painéis) e só pinta as exceções. O
  alerta de auditoria NÃO aparece para o gerente (ele já foi avisado no envio).
* **`src/assistente_agenda.py`** — agenda em `data/assistente_agenda.json`
  (sem segredo), "já mandei hoje" no `config_assistente.local.json`. O
  `Agendador` é uma thread do painel (não chama Streamlit). Disparo de
  horário só sai até 15 min depois da hora. Na nuvem, o commit da base
  reinicia o app, então o Actions manda os de "chegada" (`--chegada`).
* **Grupos do Telegram:** `my_chat_member` registra o grupo (id negativo) e
  manda boas-vindas; teclado fixo só em conversa particular.
* `B2_ASSISTENTE_DESLIGADO=1` sobe um segundo painel (teste) sem ligar o
  robô — dois ouvintes no mesmo robô = 409 e respostas duplicadas.
* O gerador apaga `data/base` antes de remontar (senão a troca de cenário
  viraria "alteração" na auditoria) e semeia a trilha com a hora do envio.

---

## Painel novo × Painel antigo (01/10/2026)

Pedido do usuário: testar uma repaginação visual e poder alternar entre o
visual antigo e o novo para aprovar.

* **Botão "Painel antigo | Painel novo"** no topo do menu lateral; também
  `?visual=antigo` na URL. Padrão: novo. A escolha mora em
  `st.session_state["visual"]` e `ui.novo()` responde.
* **Só aparência.** O antigo é o `assets/style.css` intacto; o novo é o
  `assets/style_novo.css` por CIMA dele (mesmas cores da marca e dos
  combustíveis). Não há regra de negócio no visual.
* O que o novo muda: ícones de traço único (Material) no lugar dos emojis do
  menu e dos títulos; miniatura de tendência (30 dias) nos cartões
  principais; Visão da Rede com 4 cartões grandes + 4 leves; hero da Central
  em cartão claro; alertas em linhas que abrem (`<details>`) com o botão ao
  lado; etiquetas nos alertas do posto; tabelas e gráficos mais leves
  (dica escura, grade pontilhada, barras arredondadas).
* **Armadilhas:** `charts.NOVO` é um módulo global ligado a cada rerun pelo
  `app.py` — serve para a demonstração; se virar produto multiusuário, passe
  o visual por parâmetro. O ícone do menu entra por `format_func` do
  `st.radio` (`:material/nome:`); o VALOR do menu continua com o emoji, é ele
  que o roteamento usa (`pagina.startswith("🎯")`).

---

## Publicação e operação (no ar desde 29–30/09/2026)

* **Painel:** Streamlit Community Cloud, `https://b2gestao.streamlit.app`
  (app real em `/~/+/`, dentro de um iframe), repositório privado
  `gcrp94/PostoB2`. Sem `[usuarios]` nos Secrets, o app fica em modo
  demonstração — **qualquer um entra como proprietário** (proposital).
* **Envio pelo painel:** com `[github]` nos Secrets, a planilha vai ao
  repositório pela API (`armazenamento._github_put`) e o histórico fica em
  `data/envios.csv`. O disco da nuvem NÃO é permanente: sem `[github]`, o envio
  se perde; a agenda editada na nuvem (`data/assistente_agenda.json`) volta ao
  padrão no reinício.
* **Actions:** `atualizar-base.yml` (push de `data/**/*.xlsx` ou manual: base →
  testes → alertas → `--chegada` → publica `data/base`, `alertas_enviados.csv`,
  `auditoria.csv`) e `manter-app-acordado.yml` (despertador, cron de 4 h).
  O Actions também commita em `main`: faça `git pull --rebase` antes de enviar.
* **Segredos (só os nomes):** Actions — `B2_CANAL=telegram`,
  `B2_TELEGRAM_TOKEN`, `B2_TELEGRAM_CHATS`; Streamlit — `B2_TELEGRAM_TOKEN`
  (+ opcionais). Nunca versionar token, `secrets.toml` nem
  `config_assistente.local.json`.
* **O robô vive na nuvem.** O painel local está com o Telegram desligado
  (`telegram_ativo: false`): dois ouvintes no mesmo robô dão erro 409 e
  respostas em dobro. O `Abrir App.bat` fecha painel antigo na porta 8520 antes
  de subir (um painel antigo na memória já causou `AttributeError` no login).
* **Apresentação comercial:** `apresentacao/` (deck HTML de 27 slides, modo
  estudo com roteiro; `construir.py` gera o arquivo final). Está no `.gitignore`
  — é material de venda, fica só local.
* **Contexto para outra conta do Claude:** `RESUMO_PARA_CLAUDE.md` (autônomo,
  sem segredos). O manual de uso é o `README.md`.

## Radar de Mercado — protótipo (05/10/2026)

Pedido do usuário: um radar de concorrência com dado público. Tela **📡 Radar de Mercado** (Gestão, só
proprietário/administração), módulo `src/mercado.py`, tela `src/radar_ui.py`, coleta `atualizar_mercado.py`,
testes `tests/test_mercado.py`.

* **Fonte: ANP, dados abertos** (CSV por posto, pesquisa semanal). Zips semestrais (`dsas/ca/ca-AAAA-SS.zip`) para o
  que já fechou + CSVs mensais (`dsan/AAAA/...`, **nomes irregulares**, um de 2026 sem ".csv") para os meses que
  sobram. `descobrir_links`/`selecionar` leem a página; HEAD dá 403, **GET com User-Agent funciona**. Brutos (~70 MB)
  em `data/mercado/bruto/` (`.gitignore`); só o Parquet filtrado (Guarapuava e Candói, ~30 KB) vai para o Git.
* **É AMOSTRA.** A ANP colhe preço de uns 5 a 14 postos por semana em Guarapuava (51 cadastrados); **Candói não é
  pesquisado**. Dos 5 postos do B2 só **Centro** (CNPJ final 0001-77, bandeira branca) e **Conradinho** (0002-58,
  Raízen) têm preço. As outras unidades estão no cadastro: Primavera (0004-10), Bonsucesso (0003-39) e Candói (outra
  empresa, "B2 Comércio de Combustíveis"). O B2 de Guarapuava é achado pela raiz do CNPJ `09182266`.
* **Confirmado na ANP (05/10/2026, cadastro do Brasil inteiro):** "Begnini Comércio de Combustíveis LTDA" (CNPJ
  09.182.266) = os postos B2 de Guarapuava, **4 unidades**: Centro 0001-77 (Rua Guaíra, 3148, branca), **Índio** 0002-58
  (Av. Manoel Ribas, 2760, "Posto Índio", bairro Conradinho, Raízen), Bonsucesso 0003-39 (branca) e Primavera 0004-10
  (Rua João Fortkamp, 721, branca; vínculo de bandeira só em 07/04/2026). **Candói é outra empresa:** "B2 Comércio de
  Combustíveis LTDA" (10.592.615/0001-08, Av. XV de Novembro, 1571, branca). Existe também "Auto Posto Begnini" em
  Catanduvas-SC (outro CNPJ, Ipiranga): não é B2. O nome que o dono usa vem de `NOMES_B2` (CNPJ -> nome).
* **Comparar a MÉDIA entre duas datas engana** (a amostra muda): `variacao` só compara postos com preço nas duas pontas.
* **Dados reais num painel simulado.** A tela diz "dados públicos reais" e "protótipo". **B2 Índio = Posto Índio** (Av.
  Manoel Ribas, 2760, bairro Conradinho no cadastro) — confirmado pelo usuário; o nome vem de `NOMES_B2` (CNPJ).
* **Nota Paraná (Menor Preço):** não há API oficial documentada nem termos legíveis; ver a seção seguinte (coleta local
  de teste, com autorização do usuário). Caminho para virar produto: pedir o aval do estado
  (`atendimento-aplicativo@notaparana.pr.gov.br`).
* Achado sensível: a aditivada do B2 Centro custou **igual à comum em todas as coletas** (mercado: mediana +R$ 0,30).
  Mostrar como pergunta de estratégia, nunca como crítica ao dono.

## Menor Preço (Nota Paraná) — coleta local de teste (05/10/2026)

Pedido do usuário: "varrer a cidade inteira e coletar preço de todos os postos", com pausas, **só local, em outra aba**,
uma vez por dia. Módulo `src/nota_parana.py`, comando `coletar_nota_parana.py` (+ `Coletar Menor Preco.bat`), segunda aba
da tela 📡 (`radar_ui._aba_menor_preco`), testes `tests/test_nota_parana.py` (sem internet: `abrir` falso).

* **A fonte:** o app Angular `menorpreco.notaparana.pr.gov.br` chama `/api/v1/produtos?local=<geohash>&raio=<km>&tp_comb=<1..4>
  &offset=&data=-1&ordem=0` **sem login nem cookie**; devolve o último preço de cada combustível por posto, da NFC-e, com
  minutos de atraso (`datahora` é UTC — o módulo grava em Brasília, −3 h fixo). Traz razão social/fantasia, endereço, `local`
  (geohash do posto, aproximado) e `codigo` do estabelecimento (estável: é a chave `loja`). **Não traz CNPJ**: o B2 é
  reconhecido pelo endereço (`ENDERECOS_B2`, vindo do cadastro da ANP). `tp_comb` 1 gasolina, 2 aditivada, 3 etanol, 4 diesel.
* **O servidor só enxerga perto do ponto** e limita o raio (~7 km) e a página (**50 ofertas**; `total` conta linhas brutas e
  a lista vem deduplicada, então com total ≤ 50 a 2ª página só repete; acima de 50, como no diesel, ela traz posto novo).
  **1ª varredura em grade (05/10/2026, 65 consultas, 14 min, sem bloqueio): 32 postos de Guarapuava — exatamente os mesmos
  que uma consulta larga a partir do centro (raio 8) já achava.** Por isso o dia a dia usa só `CENTRO_LARGO` (5 consultas,
  ~1 min, `modo="diaria"`) e a grade (`grade()`: caixa `CAIXA_GUARAPUAVA`, pontos a 4,5 km, raio 4 km, sem buraco — há teste)
  roda na 1ª vez e a cada 30 dias (`modo="completa"`, `precisa_varredura_completa`) para pegar posto novo na periferia.
  Ponto sem posto não pergunta os outros 3 combustíveis.
* **O app lista 32 dos 51 postos cadastrados na ANP em Guarapuava** (`conferir_cadastro`, tela mostra os 20 ausentes):
  os ausentes são sobretudo postos de rodovia (BR-277, PR-460) e uns do centro/Vila Carli que não aparecem. **B2 Primavera
  (Rua João Fortkamp, 721) NÃO aparece no Menor Preço** — nem na grade nem no raio largo; Centro, Bonsucesso e Índio aparecem.
  Hipóteses a conferir com o dono: o posto não emite NFC-e com o combustível codificado, ou foi (re)aberto há pouco (vínculo
  de bandeira só em 07/04/2026). **Candói:** o endereço da ANP para o B2 Candói (Av. XV de Novembro, 1571) aparece no app como
  "Rodoil – Vissoto & Ramos Comércio de Combustíveis" — conferir antes de incluir Candói (hoje fora da varredura).
* **Série = DIA DA COLETA, não data da nota.** O app só mostra a última nota de cada posto; um posto parado repete a mesma
  nota por dias. Por isso `_sem_repetidas` dedupa por (nota + dia da coleta) — cada coleta fica completa — e
  `historico_diario`/`estado` contam pelo `coletado_em`. A série só aparece a partir do 2º dia de coleta.
* **`tp_comb` mistura:** a V-Power vem na busca de comum e a "Gasolina Original" (comum) na de aditivada; e o `cdanp` do B2
  Centro marca "comum" com código de aditivada. Por isso `classificar` lê o **nome** que o posto escreveu na nota.
* **Conduta (não mexer sem falar com o usuário):** User-Agent honesto (`B2-Gestao ... teste local`), pausa sorteada de 8–20 s,
  uma coleta por dia (`ja_coletou_hoje`), e **parar ao primeiro sinal de bloqueio** (401/403/429, HTTP ≠ 200, JSON diferente):
  `ColetaInterrompida` — nunca contornar, nunca insistir. Rede que oscila: UMA nova tentativa depois de 45 s.
* **A foto vai ao Git (decisão do usuário em 05/10/2026):** `data/mercado/nota_parana/` (`ofertas.parquet`, `coletas.csv`) é
  versionada para a aba aparecer na demonstração da nuvem. **A coleta continua local** (nada coleta na nuvem): para atualizar,
  rode `Coletar Menor Preco.bat` e depois commit + push dos dois arquivos. A aba só aparece se `ofertas.parquet` existe. Os
  tempos "há 6 min" são contados a partir do momento da coleta (`_quando(dt, ref)`), não de agora. Agendar: `schtasks` no
  próprio `.bat` (não foi agendado). **Ainda falta o aval do estado** (e-mail ao suporte do Nota Paraná): hoje é um teste.
* **Paginação:** a coleta guarda `pagina` por oferta e informa quantos postos só vieram da 2ª página em diante
  (`extras_de_paginacao`). Em 05/10 foram 1 (diesel, total 56 > 50).

## Ideias para a fase 2 (conversadas, não feitas)

* PWA com Web Push (ícone "B2 Gestão" na tela do celular com notificação
  nativa) — hoje: "Adicionar à tela inicial" + ntfy/Pushover.
* Banco (PostgreSQL/Supabase) se virar produto para 20+ postos.
* Loja de conveniência, formas de pagamento, lava-jato.
