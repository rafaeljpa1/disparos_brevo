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

| Flag          | Efeito                                                  |
| ------------- | ------------------------------------------------------- |
| `--confirmar` | Envia de verdade (sem ela, apenas simula)               |
| `--limite N`  | Envia só para os N primeiros contatos válidos (testes)  |
| `--tag`       | Tag para rastrear a campanha nas estatísticas do Brevo  |

Todo disparo gera um relatório CSV em `relatorios/` com o status de cada
contato (enviado / erro / simulado).

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
