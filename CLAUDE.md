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
  assistente_ui.py  tela 💬 B2 Assistente e os ouvintes (um por processo).
  auth.py           Usuários, perfis, PBKDF2, modo demonstração.
  charts.py         Plotly: gramática única, números em pt-BR via Python.
  ui.py             Cartões, tanques, tabelas, alertas em HTML.
  theme.py          Cores e ícones — fonte única de verdade.
  formatting.py     R$, L, %, p.p. no padrão brasileiro.
assets/style.css    O visual (variáveis vindas do theme.py).
tests/test_painel.py
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
carga parcial que produz isso (`simular_com_historia`). As 6 situações
plantadas estão no docstring do gerador e em `test_motor_acha_as_situacoes_da_demonstracao`.

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
* **WhatsApp ficou de fora de propósito:** só pela API oficial da Meta
  (empresa verificada, modelos aprovados, cobrança) ou intermediário pago.
  É troca de transporte para a versão contratada — o cérebro é o mesmo.
* O painel ficou fora do ar por um erro de sintaxe no `assistente.py` da
  primeira versão (o `app.py` importa o módulo). Os testes pegariam: rode
  `python -m pytest` antes de apresentar.

---

## Publicação (desenhada, não feita)

Streamlit Community Cloud + repositório privado. Com `[github]` no secrets,
o envio pelo painel grava a planilha no repositório pela API
(`armazenamento._github_put`) e registra no `data/envios.csv`; o Actions
monta a base, roda os testes, dispara os alertas e publica
(`data/alertas_enviados.csv` vai junto, senão reenviaria tudo). Sem
`[usuarios]` no secrets, o app fica em modo demonstração — **qualquer um
entra como proprietário**.

## Ideias para a fase 2 (conversadas, não feitas)

* PWA com Web Push (ícone "B2 Gestão" na tela do celular com notificação
  nativa) — hoje: "Adicionar à tela inicial" + ntfy/Pushover.
* Banco (PostgreSQL/Supabase) se virar produto para 20+ postos.
* Loja de conveniência, formas de pagamento, lava-jato.
