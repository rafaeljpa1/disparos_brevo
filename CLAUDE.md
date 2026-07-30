# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Visão geral

CLI em Python para disparos em massa de e-mail, SMS e WhatsApp pela API v3 do Brevo, usada nas campanhas do PNLD da editora Casa de Letras. Todo o código, comentários, testes e mensagens são em **português** — mantenha o padrão.

Atenção: o diretório pai (`capela-pnld/`) **não** é um repositório git — a raiz do repositório é esta pasta (`disparos_brevo/`). Rode comandos git e a CLI a partir daqui.

## REGRA CRÍTICA: `--confirmar` envia de verdade

Todos os comandos de envio rodam em **modo simulação** por padrão. A flag `--confirmar` dispara e-mails/SMS reais para milhares de contatos. **Nunca execute um comando com `--confirmar` sem autorização explícita do usuário naquele momento** — simulações e `previa` podem rodar livremente.

## Comandos

```bash
source .venv/bin/activate            # venv já existe no repositório

pytest                               # todos os testes
pytest tests/test_montador.py        # um arquivo
pytest -k "nome_do_teste"            # um teste

python -m disparos_brevo verificar   # testa API key, plano e remetente
python -m disparos_brevo previa --templates templates/pnld2027/email02 --tag pnld2027-email02
                                     # gera HTML final em previas/ para conferir no navegador (não usa a API)
python -m disparos_brevo email-regional --lista-id 3 --templates ... --assunto "..."
                                     # simulação (sem --confirmar não envia nada)
python scripts/extrair_segmentos.py --tag pnld2027-emailNN --inicio AAAA-MM-DD
                                     # ao encerrar uma campanha: extrai segmentos dos logs do Brevo
```

Dependências: `pip install -r requirements.txt` (execução) e `requirements-dev.txt` (pytest). Configuração via `.env` (copie de `.env.example`); só `BREVO_API_KEY` é obrigatória — o comando `previa` dispensa até ela.

## Arquitetura

Pipeline de um disparo regional (`email-regional`, o comando principal):

1. **`cli.py`** — subcomandos (`verificar`, `previa`, `email`, `email-regional`, `sms`, `whatsapp`), validação de flags e orquestração geral.
2. **Origem dos contatos** — lista do Brevo (`--lista-id`, via `brevo_client.py`) ou CSV local (`--contatos`, via `contatos.py`, que normaliza colunas para MAIÚSCULAS e telefones para +55...). Descadastrados/bloqueados no Brevo são pulados automaticamente.
3. **`regioes.py`** — agrupa contatos por região a partir da UF (coluna/atributo `ESTADO`); adiciona `UF` e `REGIAO` ao contato.
4. **`montador.py`** — monta o HTML de cada região: resolve placeholders (`{{nome_escola}}` → `{{params.NOME_ESCOLA}}` do Brevo), injeta links de landing page com UTM por região, preenche o rodapé legal com dados da editora do `.env` e troca imagens base64 por URLs hospedadas conforme `imagens.json`. Distingue **avisos** (qualidade, ex.: imagem ainda em base64) de **impedimentos** (bloqueiam envio real com exit 2, ex.: CNPJ ausente no rodapé — exigência anti-spam). Campanha nacional: um único `nacional.html` serve de fallback para todas as regiões.
5. **`disparo.py`** — envio em lotes (`messageVersions`, padrão 100/chamada), personalização `{COLUNA}` no assunto, relatórios CSV em `relatorios/` (com `--acumular-em`, um relatório único acumulado). Linhas de simulação/erro não contam como "enviado".
6. **`brevo_client.py`** — cliente HTTP fino: intervalo entre requisições e retry automático em 429/5xx.

## Fluxo de campanha (PNLD 2027)

Cada campanha tem `templates/pnld2027/<campanha>/` (cinco `<regiao>.html` ou um `nacional.html`, + `imagens.json`) e `relatorios/pnld2027-<campanha>/`. O README documenta o fluxo completo; pontos que causam erro se ignorados:

- `--somente-destinos` restringe a um segmento (ex.: `relatorios/pnld2027-email01/segmentos/pnld2027-email01_entregues.csv` — só quem recebeu a campanha anterior, evitando bounces).
- `--excluir-enviados` aponta para a pasta da **própria** campanha (para retomar em etapas), não para as campanhas anteriores.
- Antes de qualquer envio real: as URLs em `imagens.json` devem apontar para um **commit fixo** do GitHub (não `main`) e responder 200 (`curl -I`).
- Segmentos em `relatorios/*/segmentos/` são gerados por `scripts/extrair_segmentos.py` ao encerrar cada campanha.

## Testes

Testes em `tests/`, sem chamadas reais à API (o cliente é substituído por dublês). Ao mexer no `montador.py`, rode `test_montador.py` e `test_email_regional.py`; a prévia (`python -m disparos_brevo previa`) é a forma rápida de validar o HTML resultante visualmente.
