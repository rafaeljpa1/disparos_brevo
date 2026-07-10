"""CLI dos disparos em massa via Brevo.

Uso básico (na raiz do repositório)::

    python -m disparos_brevo verificar
    python -m disparos_brevo email --contatos data/contatos.csv \
        --assunto "Olá {NOME}" --template-html templates/email_exemplo.html
    python -m disparos_brevo sms --contatos data/contatos.csv \
        --mensagem "Olá {NOME}, chegou o livro {LIVRO}!"
    python -m disparos_brevo whatsapp --contatos data/contatos.csv --template-id 123

Por segurança, TODOS os comandos de envio rodam em modo SIMULAÇÃO por
padrão — nada é enviado sem a flag ``--confirmar``.
"""

import argparse
import sys
from pathlib import Path

from .brevo_client import BrevoClient
from .config import ErroDeConfiguracao, carregar_config
from .contatos import carregar_contatos, filtrar_por_canal
from .disparo import (
    LOTE_EMAIL_PADRAO,
    LOTE_WHATSAPP_PADRAO,
    disparar_emails,
    disparar_sms,
    disparar_whatsapp,
    personalizar,
    resumo,
    salvar_relatorio,
)


def _criar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="disparos_brevo",
        description="Disparos em massa de e-mail, SMS e WhatsApp via Brevo.",
    )
    sub = parser.add_subparsers(dest="comando", required=True)

    sub.add_parser("verificar", help="Testa a chave de API e mostra plano/créditos")

    def opcoes_comuns(p: argparse.ArgumentParser) -> None:
        p.add_argument("--contatos", required=True, help="Caminho do CSV de contatos")
        p.add_argument("--limite", type=int, default=None, help="Envia só para os N primeiros contatos válidos")
        p.add_argument("--tag", default=None, help="Tag para rastrear os envios no Brevo")
        p.add_argument(
            "--confirmar",
            action="store_true",
            help="Envia de verdade (sem esta flag, apenas simula)",
        )

    p_email = sub.add_parser("email", help="Disparo em massa de e-mails")
    opcoes_comuns(p_email)
    p_email.add_argument("--assunto", help="Assunto (aceita {COLUNA} do CSV)")
    p_email.add_argument("--template-html", help="Arquivo HTML local ({{params.COLUNA}} para personalizar)")
    p_email.add_argument("--template-id", type=int, help="ID de template já criado no Brevo (alternativa ao HTML)")
    p_email.add_argument("--remetente-nome", default=None)
    p_email.add_argument("--remetente-email", default=None)
    p_email.add_argument("--lote", type=int, default=LOTE_EMAIL_PADRAO, help=f"Destinatários por chamada (padrão {LOTE_EMAIL_PADRAO})")

    p_sms = sub.add_parser("sms", help="Disparo em massa de SMS")
    opcoes_comuns(p_sms)
    p_sms.add_argument("--mensagem", required=True, help="Texto do SMS (aceita {COLUNA} do CSV)")
    p_sms.add_argument("--remetente", default=None, help="Nome do remetente (máx. 11 caracteres alfanuméricos)")

    p_wpp = sub.add_parser("whatsapp", help="Disparo em massa de WhatsApp (template aprovado)")
    opcoes_comuns(p_wpp)
    p_wpp.add_argument("--template-id", type=int, required=True, help="ID do template de WhatsApp aprovado no Brevo")
    p_wpp.add_argument("--remetente", default=None, help="Número do remetente WhatsApp Business")
    p_wpp.add_argument("--lote", type=int, default=LOTE_WHATSAPP_PADRAO, help=f"Números por chamada (padrão {LOTE_WHATSAPP_PADRAO})")

    return parser


def _preparar_contatos(args, canal: str) -> list[dict]:
    contatos = carregar_contatos(args.contatos)
    validos, invalidos = filtrar_por_canal(contatos, canal)
    print(f"Contatos carregados: {len(contatos)} | válidos para {canal}: {len(validos)} | inválidos: {len(invalidos)}")
    if invalidos:
        for contato in invalidos[:5]:
            print(f"  - inválido: {contato}")
        if len(invalidos) > 5:
            print(f"  ... e mais {len(invalidos) - 5}")
    if args.limite:
        validos = validos[: args.limite]
        print(f"Limite aplicado: enviando para {len(validos)} contatos")
    return validos


def _finalizar(resultados, confirmar: bool) -> int:
    if not resultados:
        print("Nenhum contato válido para envio.")
        return 1
    caminho = salvar_relatorio(resultados)
    print(resumo(resultados))
    print(f"Relatório: {caminho}")
    if not confirmar:
        print("MODO SIMULAÇÃO — nada foi enviado. Use --confirmar para enviar de verdade.")
    return 0 if all(r.sucesso for r in resultados) else 1


def _comando_verificar(config) -> int:
    client = BrevoClient(config.api_key, config.url_base)
    conta = client.conta()
    print(f"Conta: {conta.get('firstName', '')} {conta.get('lastName', '')} <{conta.get('email', '')}>")
    print(f"Empresa: {conta.get('companyName', '')}")
    for plano in conta.get("plan", []):
        print(f"Plano [{plano.get('type')}]: {plano.get('credits')} créditos ({plano.get('creditsType')})")
    return 0


def _comando_email(args, config) -> int:
    if args.template_id is None and not args.template_html:
        print("Informe --template-html ou --template-id.", file=sys.stderr)
        return 2
    if args.template_id is None and not args.assunto:
        print("--assunto é obrigatório com --template-html.", file=sys.stderr)
        return 2

    remetente_nome = args.remetente_nome or config.remetente_nome
    remetente_email = args.remetente_email or config.remetente_email
    if not remetente_email:
        print("Defina REMETENTE_EMAIL no .env ou use --remetente-email.", file=sys.stderr)
        return 2
    remetente = {"name": remetente_nome or remetente_email, "email": remetente_email}

    html = Path(args.template_html).read_text(encoding="utf-8") if args.template_html else None
    validos = _preparar_contatos(args, "email")
    client = BrevoClient(config.api_key, config.url_base) if args.confirmar else None
    resultados = disparar_emails(
        client,
        validos,
        remetente=remetente,
        assunto=args.assunto,
        html=html,
        template_id=args.template_id,
        tag=args.tag,
        lote=args.lote,
        confirmar=args.confirmar,
    )
    if not args.confirmar and validos:
        exemplo = validos[0]
        if args.assunto:
            print(f'Exemplo de assunto personalizado: "{personalizar(args.assunto, exemplo)}"')
    return _finalizar(resultados, args.confirmar)


def _comando_sms(args, config) -> int:
    remetente = args.remetente or config.sms_remetente
    if not remetente:
        print("Defina SMS_REMETENTE no .env ou use --remetente.", file=sys.stderr)
        return 2
    if len(remetente) > 11 and not remetente.isdigit():
        print("Remetente de SMS alfanumérico deve ter no máximo 11 caracteres.", file=sys.stderr)
        return 2

    validos = _preparar_contatos(args, "sms")
    if validos:
        print(f'Exemplo de mensagem: "{personalizar(args.mensagem, validos[0])}"')
    client = BrevoClient(config.api_key, config.url_base) if args.confirmar else None
    resultados = disparar_sms(
        client, validos, remetente, args.mensagem, tag=args.tag, confirmar=args.confirmar
    )
    return _finalizar(resultados, args.confirmar)


def _comando_whatsapp(args, config) -> int:
    remetente = args.remetente or config.whatsapp_remetente
    if not remetente:
        print("Defina WHATSAPP_REMETENTE no .env ou use --remetente.", file=sys.stderr)
        return 2

    validos = _preparar_contatos(args, "whatsapp")
    client = BrevoClient(config.api_key, config.url_base) if args.confirmar else None
    resultados = disparar_whatsapp(
        client,
        validos,
        template_id=args.template_id,
        remetente_numero=remetente,
        lote=args.lote,
        confirmar=args.confirmar,
    )
    return _finalizar(resultados, args.confirmar)


def main(argv: list[str] | None = None) -> int:
    args = _criar_parser().parse_args(argv)
    try:
        config = carregar_config()
    except ErroDeConfiguracao as erro:
        print(f"Erro de configuração: {erro}", file=sys.stderr)
        return 2

    if args.comando == "verificar":
        return _comando_verificar(config)
    if args.comando == "email":
        return _comando_email(args, config)
    if args.comando == "sms":
        return _comando_sms(args, config)
    if args.comando == "whatsapp":
        return _comando_whatsapp(args, config)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
