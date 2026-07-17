"""Orquestração dos disparos em massa: lotes, simulação e relatório."""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import csv

from .brevo_client import BrevoAPIError, BrevoClient

LOTE_EMAIL_PADRAO = 100  # destinatários por chamada (messageVersions)
LOTE_WHATSAPP_PADRAO = 50  # números por chamada


class _DicionarioTolerante(dict):
    """Para personalização: placeholder sem coluna correspondente vira ''."""

    def __missing__(self, chave):
        return ""


def personalizar(texto: str, contato: dict) -> str:
    """Substitui ``{COLUNA}`` pelo valor da coluna do contato (ou vazio)."""
    return texto.format_map(_DicionarioTolerante(contato))


@dataclass
class ResultadoEnvio:
    destino: str
    canal: str
    sucesso: bool
    detalhe: str = ""
    contato: dict = field(default_factory=dict)


def _em_lotes(itens: list, tamanho: int):
    for i in range(0, len(itens), tamanho):
        yield itens[i : i + tamanho]


def _params_do_contato(contato: dict) -> dict:
    """Colunas do CSV viram params do template ({{params.COLUNA}})."""
    return {k: v for k, v in contato.items() if not k.startswith("_") and v}


def contato_brevo_para_dict(contato_api: dict) -> dict:
    """Converte um contato retornado pela API do Brevo para o formato interno.

    Atributos (ESTADO, MUNICIPIO, NOME_ESCOLA...) viram chaves de topo,
    como nas planilhas CSV.
    """
    atributos = contato_api.get("attributes", {}) or {}
    contato = {
        chave.upper(): str(valor).strip()
        for chave, valor in atributos.items()
        if valor is not None
    }
    contato["EMAIL"] = (contato_api.get("email") or "").strip().lower()
    contato["_BLACKLISTED"] = bool(contato_api.get("emailBlacklisted"))
    return contato


# --------------------------------------------------------------------- e-mail

def disparar_emails(
    client: BrevoClient | None,
    contatos: list[dict],
    remetente: dict,
    assunto: str | None = None,
    html: str | None = None,
    template_id: int | None = None,
    tag: str | None = None,
    lote: int = LOTE_EMAIL_PADRAO,
    confirmar: bool = False,
) -> list[ResultadoEnvio]:
    """Dispara e-mails em lotes. Com ``confirmar=False`` apenas simula.

    ``contatos`` deve vir de ``filtrar_por_canal(..., "email")`` (com _DESTINO).
    """
    resultados: list[ResultadoEnvio] = []
    for grupo in _em_lotes(contatos, lote):
        destinatarios = [
            {
                "email": c["_DESTINO"],
                "nome": c.get("NOME", ""),
                "params": _params_do_contato(c),
                # assunto personalizado por contato ({COLUNA} do CSV)
                "assunto": personalizar(assunto, c) if assunto else None,
            }
            for c in grupo
        ]
        if not confirmar:
            resultados.extend(
                ResultadoEnvio(c["_DESTINO"], "email", True, "simulado", c)
                for c in grupo
            )
            continue
        try:
            client.enviar_email_lote(
                remetente=remetente,
                destinatarios=destinatarios,
                assunto=assunto,
                html=html,
                template_id=template_id,
                tag=tag,
            )
            resultados.extend(
                ResultadoEnvio(c["_DESTINO"], "email", True, "enviado", c)
                for c in grupo
            )
        except BrevoAPIError as erro:
            resultados.extend(
                ResultadoEnvio(c["_DESTINO"], "email", False, str(erro), c)
                for c in grupo
            )
    return resultados


# ------------------------------------------------------------------------ SMS

def disparar_sms(
    client: BrevoClient | None,
    contatos: list[dict],
    remetente: str,
    mensagem: str,
    tag: str | None = None,
    confirmar: bool = False,
) -> list[ResultadoEnvio]:
    """Dispara SMS um a um, personalizando ``{COLUNA}`` na mensagem."""
    resultados: list[ResultadoEnvio] = []
    for contato in contatos:
        destino = contato["_DESTINO"]
        conteudo = personalizar(mensagem, contato)
        if not confirmar:
            resultados.append(ResultadoEnvio(destino, "sms", True, "simulado", contato))
            continue
        try:
            client.enviar_sms(remetente, destino, conteudo, tag=tag)
            resultados.append(ResultadoEnvio(destino, "sms", True, "enviado", contato))
        except BrevoAPIError as erro:
            resultados.append(ResultadoEnvio(destino, "sms", False, str(erro), contato))
    return resultados


# ------------------------------------------------------------------- WhatsApp

def disparar_whatsapp(
    client: BrevoClient | None,
    contatos: list[dict],
    template_id: int,
    remetente_numero: str,
    lote: int = LOTE_WHATSAPP_PADRAO,
    confirmar: bool = False,
) -> list[ResultadoEnvio]:
    """Dispara um template aprovado de WhatsApp em lotes de números."""
    resultados: list[ResultadoEnvio] = []
    for grupo in _em_lotes(contatos, lote):
        numeros = [c["_DESTINO"] for c in grupo]
        if not confirmar:
            resultados.extend(
                ResultadoEnvio(n, "whatsapp", True, "simulado", c)
                for n, c in zip(numeros, grupo)
            )
            continue
        try:
            client.enviar_whatsapp(template_id, remetente_numero, numeros)
            resultados.extend(
                ResultadoEnvio(n, "whatsapp", True, "enviado", c)
                for n, c in zip(numeros, grupo)
            )
        except BrevoAPIError as erro:
            resultados.extend(
                ResultadoEnvio(n, "whatsapp", False, str(erro), c)
                for n, c in zip(numeros, grupo)
            )
    return resultados


def carregar_destinos_enviados(caminho: str | Path) -> set[str]:
    """Lê relatórios de envio (um CSV ou uma pasta deles) e retorna os
    destinos que já receberam com sucesso (STATUS ok + DETALHE enviado).

    Usado para dividir um disparo grande em etapas sem duplicar envios:
    linhas de simulação e de erro não contam como enviadas.
    """
    caminho = Path(caminho)
    if not caminho.exists():
        raise FileNotFoundError(f"Relatório(s) não encontrado(s): {caminho}")
    arquivos = sorted(caminho.glob("*.csv")) if caminho.is_dir() else [caminho]
    enviados: set[str] = set()
    for arquivo in arquivos:
        with arquivo.open(newline="", encoding="utf-8") as f:
            for linha in csv.DictReader(f):
                if linha.get("STATUS") == "ok" and linha.get("DETALHE") == "enviado":
                    destino = (linha.get("DESTINO") or "").strip().lower()
                    if destino:
                        enviados.add(destino)
    return enviados


# -------------------------------------------------------------------relatório

def salvar_relatorio(
    resultados: list[ResultadoEnvio], pasta: str | Path = "relatorios"
) -> Path:
    """Grava um CSV com o resultado de cada envio e retorna o caminho."""
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    momento = datetime.now().strftime("%Y%m%d_%H%M%S")
    canal = resultados[0].canal if resultados else "envio"
    caminho = pasta / f"relatorio_{canal}_{momento}.csv"

    colunas_extras = sorted(
        {
            chave
            for r in resultados
            for chave in r.contato
            if not chave.startswith("_")
        }
    )
    with caminho.open("w", newline="", encoding="utf-8") as arquivo:
        escritor = csv.writer(arquivo)
        escritor.writerow(["DESTINO", "CANAL", "STATUS", "DETALHE", *colunas_extras])
        for r in resultados:
            escritor.writerow(
                [
                    r.destino,
                    r.canal,
                    "ok" if r.sucesso else "erro",
                    r.detalhe,
                    *[r.contato.get(c, "") for c in colunas_extras],
                ]
            )
    return caminho


def resumo(resultados: list[ResultadoEnvio]) -> str:
    total = len(resultados)
    ok = sum(1 for r in resultados if r.sucesso)
    return f"{ok}/{total} envios ok, {total - ok} com erro"
