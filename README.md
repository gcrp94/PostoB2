# B2 Gestão — Painel da Rede B2 Postos

Painel gerencial para o proprietário da rede **B2 Postos** (5 unidades:
B2 Centro, B2 Bonsucesso, B2 Primavera, B2 Índio e B2 Candói). Cada posto
alimenta o painel com **uma planilha Excel por mês**; o painel mostra venda,
margem, estoque e autonomia de cada combustível e avisa o que precisa de ação.

> **Hoje os dados são SIMULADOS** (12 meses, out/2025 a set/2026), para
> apresentação. Nada ali é de posto real.

Evolução comercial do Painel de Finanças: a mesma arquitetura (planilha →
ETL → Parquet → painel), a mesma separação de módulos e as mesmas regras de
formatação brasileira.

---

## Os três atalhos

| Arquivo | Para quê |
|---|---|
| **`Abrir App.bat`** | Abre o painel no navegador (`http://localhost:8520`). Deixe a janela preta aberta. Na primeira vez, gera os dados simulados e monta a base sozinho. |
| **`Atualizar Dados.bat`** | Depois de colocar planilhas novas nas pastas: monta a base e roda o motor de alertas. |
| **`Gerar Dados Simulados.bat`** | Volta ao cenário da demonstração (sobrescreve as planilhas simuladas). **Não rode quando houver dados reais.** |

**No celular (mesma rede Wi-Fi):** o `Abrir App.bat` mostra um endereço
"Network URL" (`http://192.168.x.x:8520`). Abra no celular e use
*Adicionar à tela inicial* — fica com cara de aplicativo.

**Acesso de demonstração:** na tela de login há botões de acesso rápido
(Proprietário, Gerente do Candói, Gerente da Primavera, Administração). A senha
de todos é `b2demo`.

---

## O que o painel mostra

```
PROPRIETÁRIO / ADMINISTRAÇÃO                 GERENTE (só o próprio posto)
├─ 🎯 Central do Proprietário                ├─ ⛽ Meu Posto
├─ 💬 B2 Assistente (demonstração)
├─ 🏠 Visão da Rede                          ├─ 📤 Enviar Planilha
├─ 📋 Reunião de Gerentes                    └─ 📑 Meus Envios
├─ ⛽ B2 Centro … B2 Candói
│    Resumo | Vendas | Margens | Estoque |
│    Compras e Custos | Alertas
├─ 📤 Alimentar dados
├─ 🔔 Alertas
├─ 🛡️ Auditoria
├─ 📑 Atualizações
└─ ⚙️ Administração
```

* **Central do Proprietário** — a tela de abertura. Responde em uma frase se
  a rede está normal, lista o que **exige ação** 🔴, o que **merece atenção**
  🟡 e os **destaques** 🟢, cada um com o botão que abre o posto na aba certa,
  e mostra quando cada posto mandou a planilha pela última vez.
* **Visão da Rede** — o cockpit: volume, faturamento, margem bruta (R$, % e
  por litro), estoque, autonomia e postos em atenção; o quadro das unidades; e
  as quatro perguntas — *onde ganhamos mais, onde a margem caiu, quanto
  combustível temos, qual posto corre risco de ficar sem produto*.
* **Cada posto** — o mesmo padrão nas cinco unidades, com os quatro produtos
  sempre com a mesma cor e ícone: ⛽ Gasolina Comum (laranja), ⛽ Gasolina
  Aditivada (azul), 🌱 Etanol (verde), 🚛 Diesel S10 (violeta).
* **🛡️ Auditoria** — o controle de fraudes (ver abaixo). A Central recebe só
  UM alerta por posto com dado alterado; o resto dos sinais fica aqui.
* **📋 Reunião de Gerentes** — o placar do mês, posto × indicador, com a
  pauta sugerida de cada gerente e a ficha para imprimir.

**Margem bruta, não "lucro".** A margem bruta (faturamento − custo do
combustível) é o número principal de todas as telas: é o que a planilha
sustenta sozinha. O **resultado depois das despesas** aparece só na aba
*Compras e Custos*, quando a aba DESPESAS da planilha está preenchida, e é
antes de IR/CSLL.

---

## A planilha de cada posto

Modelo em branco: `modelo/MODELO - Planilha Mensal do Posto.xlsx` (também
disponível para baixar dentro do painel, na tela de envio).

**Uma planilha por posto por mês**, na pasta do posto:

```
data/
├─ CADASTRO DOS POSTOS.xlsx     postos e capacidade de cada tanque
├─ b2_centro/       B2 Centro 09-2026.xlsx, B2 Centro 08-2026.xlsx, ...
├─ b2_bonsucesso/
├─ b2_primavera/
├─ b2_indio/
└─ b2_candoi/
```

| Aba | Obrigatória? | Conteúdo |
|---|---|---|
| **MOVIMENTO DIÁRIO** | sim | Uma linha por dia e combustível: estoque inicial, compras, vendas, estoque final (régua), custo médio e preço médio. É a conta do LMC. |
| **COMPRAS** | não | Uma linha por nota fiscal: litros, custo, distribuidora. Alimenta a comparação entre distribuidoras. |
| **DESPESAS** | não | Despesas do mês por categoria. Alimenta o resultado depois das despesas. |

O painel calcula o resto: faturamento, margem, perda/sobra do LMC,
autonomia e os alertas.

### Dois jeitos de a planilha chegar

1. **Pelo próprio painel** (📤 Enviar Planilha): o gerente arrasta o arquivo;
   o painel **confere antes de aceitar** — posto certo, mês certo, colunas,
   estoque negativo, preço fora do normal, arquivo repetido — e mostra o que
   muda em relação à versão anterior. Com erro, a planilha é recusada e **o
   painel anterior continua intacto**. A versão substituída fica guardada e
   pode ser restaurada em *Atualizações*.
2. **Na pasta**, à mão: salve em `data/<posto>/` e rode o `Atualizar Dados.bat`.

> ⚠️ **O painel lê a base Parquet (`data/base/`), não os Excel.** Planilha
> colocada à mão na pasta só aparece depois do `Atualizar Dados.bat`.

Para testar o envio na apresentação há três planilhas em
`exemplos_para_envio/`: a da **Primavera completa até 27/09** (entre como
*Gerente · B2 Primavera* e envie — o alerta "dados desatualizados" some), a
**ALTERADA da Primavera** (a mesma, com a venda de 08/09 e 09/09 baixada: a
conferência avisa e a auditoria registra na hora) e uma do **Candói com erros
de propósito** (é recusada, com a lista dos problemas). Depois,
*Administração → Restaurar os dados da demonstração*.

---

## 🛡️ Controle de fraudes

Nenhum sinal é acusação: é **"confira isto"**. Tudo sai do que o posto já
manda.

**1. Trilha de auditoria (dado alterado depois de recebido).** Toda base nova
é comparada com a anterior, posto × dia × combustível. Dia novo é rotina; dia
que já tinha chegado e mudou vai para `data/auditoria.csv` com quem enviou,
quando, por onde, valor antes e depois e o impacto em reais.

| Gravidade | Quando | O que acontece |
|---|---|---|
| normal | mexeu no dia de ontem | só fica na trilha |
| atenção | dia com 2+ dias | tela 🛡️ Auditoria |
| **crítico** | dia com 7+ dias, ou **mês já fechado** | alerta na Central e no celular |

O gerente é avisado **no envio** de que a planilha altera dias já recebidos e
que isso fica registrado — só esse aviso já desencoraja o "ajuste". Baixar a
venda sem mexer na régua aparece também como **perda no LMC**: os dois sinais
se confirmam.

**2. Cruzamentos.** Perda/sobra no LMC acima da tolerância · combustível que
entrou no tanque **sem nota** · nota **sem entrada** no tanque · **nota
repetida** · valor da nota ≠ litros × custo · **custo médio** informado fora
do que as notas dão · venda **abaixo do custo** · vendas "redondas" demais
(digitadas de cabeça, não lidas do encerrante).

## 📋 Reunião de gerentes

Placar do mês com o que o gerente controla: volume (vs mesmos dias),
margem/L (vs média da rede), **aditivada na gasolina** (meta 20%), perda no
LMC (meta 0,30%), despesa e resultado por litro, **planilha até as 10h**
(meta 90%), dias com estoque crítico e dias alterados depois de enviados. Só
as exceções ficam coloridas. Cada gerente tem a **pauta sugerida** (do mais
grave ao elogio) e a **ficha da reunião** para imprimir, com espaço para os
combinados. Metas em `src/reuniao.py`.

---

## 📱 O assistente no celular (o ponto alto da demonstração)

O dono manda uma mensagem pelo celular — **"resumo b2 centro"**, **"estoque
candói"**, ou toca num botão — e recebe na hora:

```
📦 Estoque — B2 Candói
📅 Medição de 27/09 · dados simulados

⛽ Gasolina Comum: 16.872 L — 4,6 dias
⛽ Gasolina Aditivada: 5.066 L — 5,3 dias
🌱 Etanol: 9.649 L — 9,4 dias
🚛 Diesel S10: 6.617 L — 0,9 dia 🔴

🔴 Diesel S10 acaba em cerca de 0,9 dia. Confirme hoje a entrega com a distribuidora.
```

Os números saem da **mesma base e das mesmas regras de alerta do painel**.
Não é IA e não tem custo de API: é consulta direta. Entende sem acento, sem
"B2" e com frases soltas ("como está o estoque do candoi?").

| Pergunte | Recebe |
|---|---|
| `resumo centro` (ou só `⛽ Centro`) | vendas e litros do mês (vs mesmos dias do mês anterior), margem bruta, o último dia, estoque com dias de autonomia e os alertas do posto |
| `estoque candói` | litros e dias de cada combustível, com o que está em risco |
| `vendas primavera` | faturamento, litros, preço médio e mix por combustível |
| `margem bonsucesso` | margem bruta em R$, %, por litro e por combustível, contra a média de 12 meses |
| `resumo rede` · `estoque rede` · `vendas rede` · `margem rede` | a rede inteira, com o ranking dos postos |
| `alertas` | o que exige ação 🔴, o que merece atenção 🟡 e os destaques 🟢 |
| `reunião` | o placar das gerências |
| `auditoria` (ou `auditoria primavera`) | os sinais de fraude para conferir |
| `pendências` | quais postos ainda não mandaram a planilha |

### Disparos automáticos (sem ninguém perguntar)

Em **💬 B2 Assistente → 3 · Disparos automáticos** você escolhe **o que**
mandar e **quando**:

* **Todo dia, no horário** — ex.: 🏪 resumo da rede às 07:30; 📋 placar das
  gerências às 08:00 de segunda;
* **Assim que os dados chegarem** — a planilha entrou, a base foi montada, os
  🚨 alertas saem na hora;
* **Cobrar se não chegar até o horário** — às 10:00, se algum posto não mandou
  a planilha, avisa quem está pendente (se todos mandaram, fica quieto).

Vai para **todas as conversas do robô — pessoas e grupos**: adicione o robô
ao grupo da diretoria e ele se registra sozinho. Ninguém precisa abrir o
Telegram. O assistente fica no ar enquanto o painel roda (notebook com o
`Abrir App.bat`, ou a nuvem, que o despertador mantém acordada); na nuvem, os
dados novos também disparam pelo GitHub Actions (`motor_alertas.py --chegada`,
segredos `B2_TELEGRAM_TOKEN` e `B2_TELEGRAM_CHATS`). A agenda fica em
`data/assistente_agenda.json`.

### Telegram — o recomendado (1 minuto para montar)

O Telegram vira um "WhatsApp do posto": conversa de verdade, **com botões**
(⛽ Centro, ⛽ Candói, 🚨 Alertas…) e gratuito. Não precisa de servidor: o
notebook da apresentação responde enquanto o `Abrir App.bat` estiver aberto.

1. No Telegram do celular, procure **@BotFather** → **Iniciar** → envie
   **/newbot**. Nome: **B2 Gestão**. Usuário: algo terminado em *bot*
   (ex.: `B2GestaoDemoBot`).
2. Copie o **token** que ele devolve (`123456789:AA…`).
3. No painel, como proprietário: **💬 B2 Assistente → Telegram → Conectar**
   e cole o token.
4. Toque em **Abrir no Telegram** (aparece no painel) → **Iniciar**. Pronto.

O botão **📣 Disparar os alertas críticos no celular** faz o telefone tocar
com o alerta, na frente do comprador. Para os alertas automáticos também irem
pelo robô, ponha `canal = "telegram"` no `config_alertas.toml`.

### ntfy — a alternativa

Também funciona (o tópico `PostoB2` já está configurado): no painel,
**💬 B2 Assistente → ntfy → Salvar e conectar**; no app ntfy, assine o tópico
e publique a pergunta. É mais trabalhoso e não tem botões — por isso o
Telegram é o recomendado.

### E o WhatsApp?

É onde o dono já está, mas o WhatsApp **não tem** um jeito simples e gratuito
de robô: exige a API oficial da Meta (conta empresarial verificada, número
exclusivo, modelos de mensagem aprovados, cobrança por conversa) ou um
intermediário pago (Z-API, Twilio…). Serve para a versão contratada — as
respostas são as mesmas, só troca o "transporte". Para demonstrar, Telegram.

### Roteiro da demonstração (5 minutos)

1. Antes: **Gerar Dados Simulados.bat** (cenário limpo) → **Abrir App.bat** →
   confira no painel que o robô está 🟢 no ar.
2. **Central do Proprietário** no telão: "hoje sua rede pede ação em 3 pontos".
3. Pegue o celular e toque **🚨 Alertas** → a mesma lista chega na conversa.
4. Toque **⛽ Candói** → **📦 Estoque**: o diesel acaba em menos de 1 dia.
5. Digite **"margem bonsucesso"**: a margem do diesel caiu 33% — o custo subiu
   e o preço não acompanhou.
6. **🛡️ Auditoria**: em 22/09 o envio da Primavera baixou a venda de 03 e
   04/09 em 1.200 L (R$ 7,4 mil) — e a perda do LMC denuncia o mesmo. Envie a
   planilha **ALTERADA** como gerente da Primavera: a conferência avisa e o
   alerta aparece na hora.
7. **📋 Reunião de Gerentes**: o placar e a ficha do gerente para imprimir.
8. No painel, **📣 Disparar os alertas críticos**: o celular vibra.
9. Feche com **Visão da Rede** e com a tela de **Enviar Planilha** (o gerente
   alimenta pelo celular, o sistema confere e recusa planilha errada).
10. Deixe o comprador perguntar pelo celular dele: o robô responde qualquer um
   que abrir o link — e só com os dados simulados.
## 🔔 Alertas automáticos

O `motor_alertas.py` roda sozinho no fim do `Atualizar Dados.bat` (e,
publicado, no GitHub Actions) — **não depende de ninguém estar com o painel
aberto**. Não repete alerta: cada situação avisa uma vez por dia.

Por padrão ele só mostra no terminal. Para mandar ao celular, edite
`config_alertas.toml`:

* **ntfy** (gratuito, código aberto): instale o app ntfy, assine um tópico
  com nome difícil de adivinhar e ponha `canal = "ntfy"` e o `topico`.
* **Pushover** (pago uma vez por plataforma): `canal = "pushover"`, com o
  token do aplicativo e a chave do usuário.

Teste com `python motor_alertas.py --teste`.

| Alerta | Dispara quando |
|---|---|
| 🔴 Estoque crítico / 🟡 baixo | autonomia abaixo de 1,5 / 2,5 dias (estoque ÷ venda média de 7 dias) |
| 🔴 Perda acima da tolerância | perda do LMC acima de 0,6% do vendido no mês |
| 🟡 Margem em queda | margem/L dos últimos 7 dias 15% abaixo dos 30 dias anteriores (diz se foi custo não repassado) |
| 🟡 Margem abaixo do histórico | margem % do mês 1,2 p.p. abaixo da média de 12 meses |
| 🟡 Venda fora do padrão | últimos 7 dias 10% abaixo da média das 8 semanas anteriores |
| 🟡 Dados desatualizados | posto 2 dias ou mais atrás dos outros no envio |
| 🔴 Dados alterados depois de recebidos | dia já recebido mudou 7+ dias depois, ou mês já fechado (trilha de auditoria) |

---

## Usuários

Sem configuração, o painel roda em **modo demonstração** (usuários fictícios).
Para usuários de verdade, copie `.streamlit/secrets.exemplo.toml` para
`.streamlit/secrets.toml` e preencha — a senha vai em hash:

```bash
python -c "from src.auth import gerar_hash; print(gerar_hash('a-senha'))"
```

O **gerente** vê e alimenta só o posto dele — não escolhe o posto, o login
define. Proprietário e administração veem a rede inteira.

---

## Publicar (Streamlit Community Cloud, gratuito)

Repositório: **github.com/gcrp94/PostoB2**.

1. Em **share.streamlit.io**, entre com o GitHub (conta *gcrp94*) → **Create
   app** → repositório `gcrp94/PostoB2`, branch `main`, arquivo `app.py`.
   Em *Advanced settings*, Python **3.12**.
2. **Assistente no celular pela nuvem** — em *Settings → Secrets*, só um dos
   dois (as chaves de primeiro nível viram variáveis de ambiente):

   ```toml
   B2_TELEGRAM_TOKEN = "123456789:AA..."   # o robô do @BotFather
   # ou
   B2_ASSISTENTE_TOPICO = "PostoB2"        # o ntfy
   ```

   ⚠️ **Nuvem OU notebook, nunca os dois ao mesmo tempo** com o mesmo robô ou
   tópico: o Telegram recusa a segunda conexão, e o ntfy responde em dobro.
   O app da nuvem dorme depois de 12 horas sem visita — abra o link antes da
   apresentação para acordar o robô.
3. **Versão contratada:** usuários reais (`[usuarios]`, ver *Usuários*) e a
   seção `[github]` (token *fine-grained* só deste repositório, permissão
   *Contents: read and write*): as planilhas enviadas pelo painel vão para o
   repositório e o `.github/workflows/atualizar-base.yml` monta a base, roda
   os testes, manda os alertas e publica. O disco da Streamlit Cloud não é
   permanente — sem o `[github]`, planilha enviada lá se perde.

**Despertador (o mesmo do B.I. de Finanças):** o app dorme depois de 12 horas
sem visita. O `.github/workflows/manter-app-acordado.yml` roda o
`keep_alive.py` a cada 4 horas: abre o painel num navegador de verdade, sem
tela, e clica em *"Yes, get this app back up!"* se ele estiver dormindo. Não
faz login — chegar à tela de login já conta como visita. Custa ~360 dos 2.000
minutos gratuitos de Actions por mês. Para testar na hora: GitHub → **Actions →
Manter o painel acordado → Run workflow**. Só funciona com o app aberto a
visitantes; se um dia ele for restrito a e-mails em *Settings → Sharing*, o
robô não entra.

> Sem a seção `[usuarios]` no Secrets, o app publicado fica em **modo
> demonstração**: qualquer um com o link entra como proprietário. Para mostrar
> os dados simulados ao comprador, é exatamente o que se quer; antes de pôr
> dado real, configure os usuários.

---
## Manual (terminal)

```bash
pip install -r requirements.txt
python gerar_dados_simulados.py     # só para a demonstração
python gerar_base.py                # planilhas -> data/base/*.parquet
python motor_alertas.py --listar    # os alertas, sem enviar
streamlit run app.py
python -m pytest                    # os números fecham? a conferência funciona?
```
