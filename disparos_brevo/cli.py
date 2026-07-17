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
from .contatos import carregar_contatos, email_valido, filtrar_por_canal
from .disparo import (
    LOTE_EMAIL_PADRAO,
    LOTE_WHATSAPP_PADRAO,
    carregar_destinos_enviados,
    contato_brevo_para_dict,
    disparar_emails,
    disparar_sms,
    disparar_whatsapp,
    personalizar,
    resumo,
    salvar_relatorio,
)
from .montador import (
    LINK_LP_PADRAO,
    DadosEditora,
    aplicar_dados_de_exemplo,
    montar_template,
)
from .regioes import SLUG_POR_REGIAO, agrupar_por_regiao


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

    p_previa = sub.add_parser(
        "previa",
        help="Gera o HTML final dos templates regionais para conferir no navegador",
    )
    p_previa.add_argument("--templates", default="templates/pnld2027/email01", help="Pasta com <regiao>.html")
    p_previa.add_argument("--saida", default="previas", help="Pasta de saída dos HTML montados")
    p_previa.add_argument("--regiao", choices=sorted(SLUG_POR_REGIAO.values()), help="Gera só uma região")
    p_previa.add_argument("--tag", default="pnld2027-email01", help="Campanha usada nos parâmetros UTM dos links")

    p_reg = sub.add_parser(
        "email-regional",
        help="Disparo de e-mails com template por região (PNLD 2027)",
    )
    p_reg.add_argument("--lista-id", type=int, help="ID da lista de contatos no Brevo (ex.: 3 = PNLD)")
    p_reg.add_argument("--contatos", help="Alternativa à lista do Brevo: CSV local com coluna ESTADO")
    p_reg.add_argument("--templates", default="templates/pnld2027/email01", help="Pasta com <regiao>.html (norte, nordeste, centro-oeste, sudeste, sul)")
    p_reg.add_argument("--assunto", required=True, help="Assunto (aceita {NOME_ESCOLA}, {UF}, {REGIAO}...)")
    p_reg.add_argument("--regiao", choices=sorted(SLUG_POR_REGIAO.values()), help="Dispara só para uma região")
    p_reg.add_argument("--limite", type=int, default=None, help="Envia só para os N primeiros contatos de cada região")
    p_reg.add_argument(
        "--excluir-enviados",
        metavar="RELATORIO",
        help="Arquivo ou pasta de relatórios: pula contatos que já receberam "
        "com sucesso (para dividir o disparo em etapas, ex.: relatorios/)",
    )
    p_reg.add_argument("--tag", default="pnld2027-email01", help="Tag da campanha (rastreio no Brevo e UTM)")
    p_reg.add_argument("--lote", type=int, default=LOTE_EMAIL_PADRAO)
    p_reg.add_argument("--remetente-nome", default=None)
    p_reg.add_argument("--remetente-email", default=None)
    p_reg.add_argument("--confirmar", action="store_true", help="Envia de verdade (sem esta flag, apenas simula)")

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

    print()
    if not config.remetente_email:
        print("Remetente de envio: NÃO configurado — defina REMETENTE_NOME e "
              "REMETENTE_EMAIL no .env")
        return 1
    nome = config.remetente_nome or config.remetente_email
    print(f"Remetente de envio (.env): {nome} <{config.remetente_email}>")

    cadastrado = next(
        (
            r
            for r in client.remetentes()
            if (r.get("email") or "").lower() == config.remetente_email.lower()
        ),
        None,
    )
    if cadastrado is None:
        print("  ATENÇÃO: este remetente NÃO está cadastrado no Brevo — o envio "
              "será recusado. Cadastre em: Senders, Domains & Dedicated IPs > Senders")
        return 1
    if not cadastrado.get("active"):
        print("  ATENÇÃO: remetente cadastrado porém INATIVO — confirme o código "
              "de verificação enviado para a caixa dele.")
        return 1
    print("  OK: remetente cadastrado e ativo no Brevo.")
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


def _editora_da_config(config) -> DadosEditora:
    return DadosEditora(
        endereco=config.editora_endereco,
        cnpj=config.editora_cnpj,
        dominio=config.editora_dominio,
        email_contato=config.editora_email_contato,
        link_privacidade=config.link_politica_privacidade,
        razao_social=config.editora_razao_social,
        link_site=config.link_site,
        logo_url=config.logo_url,
    )


def _comando_previa(args, config) -> int:
    editora = _editora_da_config(config)
    link_nacional = config.link_lp_nacional or LINK_LP_PADRAO
    link_regional = config.link_lp_regional or link_nacional

    saida = Path(args.saida)
    saida.mkdir(parents=True, exist_ok=True)
    slugs = [args.regiao] if args.regiao else sorted(SLUG_POR_REGIAO.values())
    houve_pendencia = False
    for slug in slugs:
        montado = montar_template(
            args.templates,
            slug,
            editora,
            link_nacional=link_nacional,
            link_regional=link_regional,
            utm_campanha=args.tag or "",
        )
        for aviso in montado.avisos:
            print(f"[{montado.regiao}] AVISO: {aviso}")
        for impedimento in montado.impedimentos:
            houve_pendencia = True
            print(f"[{montado.regiao}] PENDÊNCIA: {impedimento}", file=sys.stderr)
        caminho = saida / f"{slug}.html"
        caminho.write_text(
            aplicar_dados_de_exemplo(montado.html, slug), encoding="utf-8"
        )
        print(f"[{montado.regiao}] prévia gerada: {caminho}")
    print(
        "Abra os arquivos no navegador para conferir textos, imagens e links "
        "(o link de descadastro só é gerado pelo Brevo no envio real)."
    )
    return 1 if houve_pendencia else 0


def _comando_email_regional(args, config) -> int:
    if bool(args.lista_id) == bool(args.contatos):
        print("Informe --lista-id OU --contatos (exatamente um dos dois).", file=sys.stderr)
        return 2

    remetente_email = args.remetente_email or config.remetente_email
    if not remetente_email:
        print("Defina REMETENTE_EMAIL no .env ou use --remetente-email.", file=sys.stderr)
        return 2
    remetente = {
        "name": args.remetente_nome or config.remetente_nome or remetente_email,
        "email": remetente_email,
    }

    # A conexão com o Brevo é necessária para buscar contatos da lista,
    # mesmo em simulação; para CSV local, só conecta em envio real.
    client = None
    if args.lista_id or args.confirmar:
        client = BrevoClient(config.api_key, config.url_base)

    if args.lista_id:
        print(f"Buscando contatos da lista {args.lista_id} no Brevo...")
        brutos = client.contatos_da_lista(args.lista_id)
        contatos = [contato_brevo_para_dict(c) for c in brutos]
    else:
        contatos = carregar_contatos(args.contatos)

    bloqueados = [c for c in contatos if c.get("_BLACKLISTED")]
    contatos = [c for c in contatos if not c.get("_BLACKLISTED")]
    sem_email = [c for c in contatos if not email_valido(c.get("EMAIL", ""))]
    contatos = [
        {**c, "_DESTINO": c["EMAIL"].strip().lower()}
        for c in contatos
        if email_valido(c.get("EMAIL", ""))
    ]

    if args.excluir_enviados:
        enviados = carregar_destinos_enviados(args.excluir_enviados)
        antes = len(contatos)
        contatos = [c for c in contatos if c["_DESTINO"] not in enviados]
        print(f"Já enviados em etapas anteriores (pulados): {antes - len(contatos)}")

    por_regiao, sem_regiao = agrupar_por_regiao(contatos)
    print(f"Contatos: {len(contatos)} válidos | {len(bloqueados)} descadastrados/bloqueados | "
          f"{len(sem_email)} sem e-mail válido | {len(sem_regiao)} sem UF reconhecida")
    for regiao in sorted(por_regiao):
        print(f"  {regiao}: {len(por_regiao[regiao])} contatos")

    editora = _editora_da_config(config)
    link_nacional = config.link_lp_nacional or LINK_LP_PADRAO
    link_regional = config.link_lp_regional or link_nacional

    resultados = []
    for regiao in sorted(por_regiao):
        slug = SLUG_POR_REGIAO[regiao]
        if args.regiao and slug != args.regiao:
            continue
        grupo = por_regiao[regiao]
        if args.limite:
            grupo = grupo[: args.limite]

        montado = montar_template(
            args.templates,
            slug,
            editora,
            link_nacional=link_nacional,
            link_regional=link_regional,
            utm_campanha=args.tag or "",
        )
        for aviso in montado.avisos:
            print(f"[{regiao}] AVISO: {aviso}")
        if montado.impedimentos:
            for impedimento in montado.impedimentos:
                print(f"[{regiao}] PENDÊNCIA: {impedimento}", file=sys.stderr)
            if args.confirmar:
                print(f"[{regiao}] Envio real BLOQUEADO até resolver as pendências acima.", file=sys.stderr)
                return 2

        # escolas sem nome cadastrado recebem um tratamento genérico
        grupo = [
            {**c, "NOME_ESCOLA": c.get("NOME_ESCOLA") or "sua escola"}
            for c in grupo
        ]
        print(f"[{regiao}] {'Enviando' if args.confirmar else 'Simulando'} "
              f"{len(grupo)} e-mails ({len(montado.html) // 1024} KB por mensagem)...")
        resultados.extend(
            disparar_emails(
                client,
                grupo,
                remetente=remetente,
                assunto=args.assunto,
                html=montado.html,
                tag=args.tag,
                lote=args.lote,
                confirmar=args.confirmar,
            )
        )

    if resultados and not args.confirmar:
        exemplo = resultados[0].contato
        print(f'Exemplo de assunto: "{personalizar(args.assunto, exemplo)}"')
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
        # a prévia não fala com a API, então não exige BREVO_API_KEY
        config = carregar_config(exigir_api_key=args.comando != "previa")
    except ErroDeConfiguracao as erro:
        print(f"Erro de configuração: {erro}", file=sys.stderr)
        return 2

    if args.comando == "verificar":
        return _comando_verificar(config)
    if args.comando == "previa":
        return _comando_previa(args, config)
    if args.comando == "email":
        return _comando_email(args, config)
    if args.comando == "email-regional":
        return _comando_email_regional(args, config)
    if args.comando == "sms":
        return _comando_sms(args, config)
    if args.comando == "whatsapp":
        return _comando_whatsapp(args, config)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
