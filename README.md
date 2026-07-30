# disparos_brevo

Disparos em massa de **e-mail**, **SMS** e **WhatsApp** para divulgação dos
livros no PNLD, usando a plataforma [Brevo](https://developers.brevo.com/docs/getting-started).

## Como funciona

O projeto é uma CLI em Python que lê uma planilha CSV de contatos e dispara
mensagens pela API v3 do Brevo:

- **E-mail** — envio transacional em lote (`POST /smtp/email` com
  `messageVersions`), com HTML local ou template do Brevo e personalização
  por contato.
- **SMS** — envio transacional (`POST /transactionalSMS/sms`), um por
  contato, com mensagem personalizada.
- **WhatsApp** — envio de template aprovado (`POST /whatsapp/sendMessage`),
  em lotes de números.

Por segurança, **todo comando roda em modo simulação por padrão**: valida os
contatos, mostra exemplos de personalização e gera relatório, mas **não envia
nada** sem a flag `--confirmar`.

## Instalação

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Configuração

1. Copie o exemplo e preencha a chave de API:

   ```bash
   cp .env.example .env
   ```

2. Gere a chave em [Brevo → Settings → SMTP & API → API Keys](https://app.brevo.com/settings/keys/api)
   e cole em `BREVO_API_KEY` no `.env`.

3. Teste a conexão:

   ```bash
   python -m disparos_brevo verificar
   ```

Variáveis disponíveis no `.env`:

| Variável             | Descrição                                                        |
| -------------------- | ---------------------------------------------------------------- |
| `BREVO_API_KEY`      | Chave de API v3 do Brevo (obrigatória)                            |
| `REMETENTE_NOME`     | Nome do remetente de e-mail                                       |
| `REMETENTE_EMAIL`    | E-mail do remetente (precisa estar **verificado** no Brevo)       |
| `SMS_REMETENTE`      | Remetente de SMS (máx. 11 caracteres alfanuméricos)               |
| `WHATSAPP_REMETENTE` | Número WhatsApp Business conectado ao Brevo (ex.: +5521999999999) |

## Planilha de contatos

CSV com cabeçalho — veja [`data/contatos.exemplo.csv`](data/contatos.exemplo.csv):

```csv
EMAIL,NOME,SMS,WHATSAPP,LIVRO,ESCOLA
maria.silva@exemplo.com,Maria Silva,(21) 99999-0001,(21) 99999-0001,Matemática 6º ano,EM Prof. João Carlos
```

- `EMAIL`, `SMS` e `WHATSAPP` identificam o destino em cada canal — só é
  preciso preencher as colunas dos canais que serão usados.
- Telefones aceitam formatos comuns no Brasil (`(21) 99999-0001`,
  `21999990001`, `+5521999990001`...) e são normalizados automaticamente.
- **Qualquer outra coluna** (`NOME`, `LIVRO`, `ESCOLA`...) fica disponível
  para personalizar as mensagens.

## Uso

### E-mail

```bash
# Simulação (padrão — não envia nada)
python -m disparos_brevo email \
  --contatos data/contatos.csv \
  --assunto "Novidades do livro {LIVRO} no PNLD" \
  --template-html templates/email_exemplo.html

# Envio real
python -m disparos_brevo email \
  --contatos data/contatos.csv \
  --assunto "Novidades do livro {LIVRO} no PNLD" \
  --template-html templates/email_exemplo.html \
  --tag pnld-2026 \
  --confirmar
```

- No **assunto**, use `{COLUNA}` (ex.: `{NOME}`, `{LIVRO}`).
- No **HTML**, use `{{params.COLUNA}}` (ex.: `{{params.NOME}}`) — sintaxe de
  template do Brevo.
- Alternativa ao HTML local: `--template-id 42` usa um template criado no
  painel do Brevo.
- `--lote` controla quantos destinatários vão por chamada de API (padrão 100).

### E-mail regional (PNLD 2027)

Dispara o template certo para cada contato conforme a **região** da UF do
contato (atributo `ESTADO` no Brevo ou coluna `ESTADO` no CSV):

| Região       | UFs                                | Template                                 |
| ------------ | ---------------------------------- | ---------------------------------------- |
| Norte        | AC AP AM PA RO RR TO               | `templates/pnld2027/email01/norte.html`  |
| Nordeste     | AL BA CE MA PB PE PI RN SE         | `.../nordeste.html`                      |
| Centro-Oeste | DF GO MT MS                        | `.../centro-oeste.html`                  |
| Sudeste      | ES MG RJ SP                        | `.../sudeste.html`                       |
| Sul          | PR RS SC                           | `.../sul.html`                           |

```bash
# Simulação usando a lista PNLD do Brevo (id 3)
python -m disparos_brevo email-regional \
  --lista-id 3 \
  --assunto "Material aprovado no PNLD 2027 para os Anos Iniciais"

# Teste real pequeno: só Sul, 3 contatos por região
python -m disparos_brevo email-regional \
  --lista-id 3 --regiao sul --limite 3 \
  --assunto "Material aprovado no PNLD 2027 para os Anos Iniciais" \
  --confirmar
```

Antes do envio, cada template é montado automaticamente:

- `{{nome_escola}}` e `{{uf}}` viram personalização por contato (escolas sem
  nome cadastrado recebem "sua escola");
- `{{regiao}}` vira o nome da região;
- `{{link_lp_nacional}}` / `{{link_lp_regional}}` viram os links das landing
  pages (`LINK_LP_NACIONAL` e `LINK_LP_REGIONAL` no `.env`) com UTM por
  região (`utm_content=sul-nacional` etc.). No link regional, `{regiao}` é
  trocado pelo slug: `https://casadeletras.com.br/pnld-2027-{regiao}/` →
  `.../pnld-2027-norte/`;
- o rodapé espelha o do site da editora: faixa azul-marinho com o logo
  (`LOGO_RODAPE_URL`, clicável para `LINK_SITE`), razão social, endereço,
  CNPJ e e-mail de contato (`EDITORA_RAZAO_SOCIAL`, `EDITORA_ENDERECO`,
  `EDITORA_CNPJ`, `EDITORA_EMAIL_CONTATO` — o `.env.example` já vem
  preenchido com os dados confirmados do site). O envio real é
  **bloqueado** enquanto estiverem vazios (exigência anti-spam). O link
  "Política de privacidade" usa `LINK_POLITICA_PRIVACIDADE`;
- contatos descadastrados/bloqueados no Brevo são pulados;
- `{{ unsubscribe }}` é mantido para o Brevo gerar o link de descadastro.

**Imagens**: os templates vieram com imagens embutidas em base64 (~600 KB
por e-mail — Gmail e Outlook cortam/bloqueiam). As imagens estão extraídas
em `templates/pnld2027/email01/imagens/`; suba-as na galeria do Brevo, copie
as URLs para `imagens.json` (use `imagens.exemplo.json` como base) e o
montador troca automaticamente, reduzindo o e-mail para ~30 KB.

### SMS

```bash
python -m disparos_brevo sms \
  --contatos data/contatos.csv \
  --mensagem "Olá {NOME}! O livro {LIVRO} foi aprovado no PNLD. Saiba mais: capela.press" \
  --confirmar
```

Mensagens com mais de 160 caracteres são cobradas como mais de um SMS.

### WhatsApp

O WhatsApp exige uma conta **WhatsApp Business** conectada ao Brevo e um
**template aprovado pela Meta** (criado em Brevo → WhatsApp → Templates).

```bash
python -m disparos_brevo whatsapp \
  --contatos data/contatos.csv \
  --template-id 123 \
  --confirmar
```

### Opções comuns

| Flag                     | Efeito                                                        |
| ------------------------ | ------------------------------------------------------------- |
| `--confirmar`            | Envia de verdade (sem ela, apenas simula)                      |
| `--limite N`             | Envia só para os N primeiros contatos válidos (testes/etapas)  |
| `--excluir-enviados DIR` | Pula quem já recebeu com sucesso segundo os relatórios         |
| `--somente-destinos ARQ` | Restringe a um segmento: arquivo com coluna EMAIL ou um e-mail por linha (só no `email-regional`) |
| `--tag`                  | Tag para rastrear a campanha nas estatísticas do Brevo         |

### Disparo em etapas

Quando os créditos do mês não cobrem a base inteira (ex.: 20 mil créditos
para 35 mil contatos), divida o disparo mantendo os relatórios na pasta
`relatorios/`:

```bash
# Etapa 1: uma região por vez
python -m disparos_brevo email-regional --lista-id 3 --regiao norte --assunto "..." --confirmar

# Etapa 2 (outro dia): manda para quem ainda não recebeu
python -m disparos_brevo email-regional --lista-id 3 --regiao sudeste --limite 8000 \
  --excluir-enviados relatorios/ --assunto "..." --confirmar
```

Linhas de simulação e de erro nos relatórios **não** contam como enviadas —
só quem realmente recebeu é pulado.

Todo disparo gera um relatório CSV em `relatorios/` com o status de cada
contato (enviado / erro / simulado).

### Organização por campanha

Cada campanha (leva de e-mails) tem sua própria pasta de templates e de
relatórios, nomeadas pela tag:

```
templates/pnld2027/email01/      # HTMLs por região + imagens/ + imagens.json
relatorios/pnld2027-email01/     # relatórios da campanha (unificado + etapas)
```

A campanha **email01** (concluída em 23/07/2026, 35.078 contatos) está
arquivada nessas pastas. Já preparadas no formato padrão:

| Campanha | Conteúdo                                  | Origem (arquivos do designer) | Templates                          |
| -------- | ----------------------------------------- | ----------------------------- | ---------------------------------- |
| email02  | Coleção de Inglês (nacional)              | `email-05`                    | `nacional.html` (um só para todas as regiões) |
| email03  | Conheça o Brasil (regional)               | `email-06` a `email-10`       | `norte.html` ... `sul.html`        |

Para uma nova campanha, suba os HTMLs em `templates/pnld2027/<campanha>/`:
os cinco `<regiao>.html`, ou um único `nacional.html` quando o conteúdo é o
mesmo para o país inteiro (o montador usa ele como reserva de qualquer
região, mantendo personalização e UTM por região), mais `imagens.json` com
as URLs hospedadas. Depois rode:

```bash
mkdir -p relatorios/pnld2027-email02

python -m disparos_brevo email-regional --lista-id 3 \
  --templates templates/pnld2027/email02 \
  --tag pnld2027-email02 \
  --somente-destinos relatorios/pnld2027-email01/segmentos/pnld2027-email02_alvo_nao_abriram.csv \
  --excluir-enviados relatorios/pnld2027-email02/ \
  --acumular-em relatorios/pnld2027-email02/relatorio_unificado.csv \
  --assunto "..." --confirmar
```

- `--somente-destinos` restringe o disparo a um segmento (arquivo com uma
  coluna EMAIL ou um e-mail por linha) — ex.: só quem **recebeu** a campanha
  anterior, para não insistir em endereços que deram bounce.
- `--excluir-enviados` aponta só para a pasta da **própria** campanha — assim
  os contatos que receberam a email01 continuam recebendo as próximas.

**Antes de cada disparo**: as URLs em `imagens.json` das campanhas novas
apontam para o branch `main` do repositório no GitHub — faça commit + push
das imagens e troque as URLs para o **commit fixo** (como na email01), e
confira com `curl -I` que respondem 200.

### Segmentos da campanha anterior

`relatorios/pnld2027-email01/segmentos/` guarda os públicos extraídos dos
logs do Brevo (tag `pnld2027-email01`, gerados em 29/07/2026), nomeados
`<tag>_<segmento>.csv`: `pnld2027-email01_entregues.csv`,
`pnld2027-email01_abriram.csv`, `pnld2027-email01_clicaram.csv`,
`pnld2027-email01_nao_entregues.csv` (bounces),
`pnld2027-email01_descadastrados.csv`, `pnld2027-email01_marcaram_spam.csv`
e `resumo.json` com as contagens. Há também os públicos-alvo já montados
para as próximas campanhas (entregues menos descadastrados/spam, divididos
por engajamento): `pnld2027-email02_alvo_nao_abriram.csv` (24.637
não-abridores) e `pnld2027-email03_alvo_engajados.csv` (8.063 que abriram ou
clicaram). São a entrada de `--somente-destinos` nas próximas campanhas
(descadastrados e reclamações de spam já são pulados automaticamente pelo
Brevo/CLI; bounces ficam de fora porque os alvos partem dos entregues).

Para gerar os segmentos de qualquer campanha (ao encerrá-la):

```bash
python scripts/extrair_segmentos.py --tag pnld2027-email02 --inicio 2026-08-15
```

## Limites do plano atual (Brevo)

- **Plano gratuito**: 300 e-mails/dia.
- **SMS**: exige compra de créditos de SMS no Brevo (saldo atual: 0).
- **WhatsApp**: exige conexão de conta WhatsApp Business e templates
  aprovados; cobrança por conversa iniciada.
- A API tem limite de requisições por segundo — o cliente já aplica um
  intervalo entre chamadas e refaz automaticamente em caso de `429`.

## Boas práticas para disparos em massa

- Rode primeiro **sem** `--confirmar` e confira o relatório e os exemplos de
  personalização.
- Use `--limite 5` com seus próprios contatos para um teste real pequeno
  antes do disparo completo.
- Envie apenas para contatos que consentiram em receber comunicações (LGPD)
  e ofereça sempre um meio de descadastro.
- Use `--tag` para acompanhar cada campanha nas estatísticas do Brevo.

## Desenvolvimento

```bash
pip install -r requirements-dev.txt
pytest
```

Estrutura:

```
disparos_brevo/
├── disparos_brevo/          # pacote Python
│   ├── brevo_client.py      # cliente HTTP da API v3 (retry, rate limit)
│   ├── config.py            # carregamento do .env
│   ├── contatos.py          # leitura/validação do CSV, normalização de telefones
│   ├── disparo.py           # orquestração: lotes, simulação, relatório
│   └── cli.py               # interface de linha de comando
├── data/contatos.exemplo.csv
├── templates/email_exemplo.html
└── tests/
```
