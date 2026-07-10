"""Carregamento e validação de contatos a partir de arquivos CSV.

O CSV deve ter cabeçalho; os nomes de coluna são normalizados para
MAIÚSCULAS. Colunas reconhecidas por canal:

- ``EMAIL``     — endereço de e-mail do destinatário
- ``SMS``       — telefone celular (formato brasileiro ou internacional)
- ``WHATSAPP``  — telefone do WhatsApp (idem)

Qualquer outra coluna (NOME, LIVRO, ESCOLA...) fica disponível para
personalização das mensagens.
"""

import csv
import re
from pathlib import Path

COLUNA_POR_CANAL = {"email": "EMAIL", "sms": "SMS", "whatsapp": "WHATSAPP"}

_RE_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalizar_telefone(valor: str) -> str | None:
    """Normaliza um telefone para o formato internacional +55DDDNÚMERO.

    Aceita formatos comuns no Brasil: ``(21) 99999-9999``, ``21999999999``,
    ``5521999999999``, ``+5521999999999``. Retorna ``None`` se inválido.
    """
    if not valor:
        return None
    digitos = re.sub(r"\D", "", valor)
    if not digitos:
        return None

    # Remove zeros de discagem internacional (0055...) ou de operadora (021...)
    if digitos.startswith("00"):
        digitos = digitos[2:]
    elif digitos.startswith("0") and len(digitos) in (11, 12):
        digitos = digitos[1:]

    if digitos.startswith("55") and len(digitos) in (12, 13):
        return f"+{digitos}"
    if len(digitos) in (10, 11):  # DDD + número, sem código do país
        return f"+55{digitos}"
    if 11 <= len(digitos) <= 15:  # outro país, já com código
        return f"+{digitos}"
    return None


def email_valido(valor: str) -> bool:
    return bool(valor and _RE_EMAIL.match(valor.strip()))


def carregar_contatos(caminho: str | Path) -> list[dict]:
    """Lê o CSV e retorna uma lista de dicts com chaves em MAIÚSCULAS."""
    caminho = Path(caminho)
    if not caminho.exists():
        raise FileNotFoundError(f"Arquivo de contatos não encontrado: {caminho}")

    contatos: list[dict] = []
    with caminho.open(newline="", encoding="utf-8-sig") as arquivo:
        leitor = csv.DictReader(arquivo)
        if not leitor.fieldnames:
            raise ValueError(f"CSV sem cabeçalho: {caminho}")
        for linha in leitor:
            contato = {
                (chave or "").strip().upper(): (valor or "").strip()
                for chave, valor in linha.items()
                if chave
            }
            if any(contato.values()):
                contatos.append(contato)
    return contatos


def filtrar_por_canal(contatos: list[dict], canal: str) -> tuple[list[dict], list[dict]]:
    """Separa (válidos, inválidos) para o canal informado.

    Para SMS/WhatsApp, adiciona a chave ``_DESTINO`` com o telefone
    normalizado; para e-mail, ``_DESTINO`` recebe o endereço.
    """
    coluna = COLUNA_POR_CANAL.get(canal)
    if coluna is None:
        raise ValueError(f"Canal desconhecido: {canal!r}")

    validos: list[dict] = []
    invalidos: list[dict] = []
    for contato in contatos:
        bruto = contato.get(coluna, "")
        if canal == "email":
            destino = bruto.strip().lower() if email_valido(bruto) else None
        else:
            destino = normalizar_telefone(bruto)
        if destino:
            validos.append({**contato, "_DESTINO": destino})
        else:
            invalidos.append(contato)
    return validos, invalidos
