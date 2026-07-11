"""Montagem dos templates HTML regionais antes do disparo.

Os templates (ex.: ``templates/pnld2027/email01/<regiao>.html``) chegam com
placeholders que precisam ser resolvidos:

- ``{{nome_escola}}`` / ``{{uf}}``  → viram ``{{params.*}}`` do Brevo,
  preenchidos por contato no envio
- ``{{regiao}}``                    → nome da região (fixo por template)
- ``{{link_lp_nacional}}`` / ``{{link_lp_regional}}`` → URL da landing page
  com parâmetros UTM por região
- ``[ENDEREÇO FÍSICO]`` / ``[CNPJ]`` / ``[DOMINIO]`` → dados da editora
  (obrigatórios no rodapé por lei anti-spam)
- imagens ``data:...;base64`` → URLs hospedadas (galeria do Brevo),
  configuradas em ``imagens.json`` na pasta dos templates

``{{ unsubscribe }}`` é mantido: o próprio Brevo o converte em link de
descadastro no envio.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .regioes import REGIAO_POR_SLUG, SLUG_POR_REGIAO

LINK_LP_PADRAO = "https://casadeletras.com.br/pnld-2027/"

# alt da imagem no template → chave em imagens.json ("{slug}" = região)
_CHAVE_POR_ALT = [
    (re.compile(r"^Capa do livro"), "capa-{slug}"),
    (re.compile(r"^Coleção Arte$"), "mini-arte"),
    (re.compile(r"^Coleção Inglês$"), "mini-ingles"),
    (re.compile(r"^Coleção Produção de Texto$"), "mini-prodtexto"),
    (re.compile(r"^Coleção Educação Digital e Midiática$"), "mini-eddigital"),
]

# comentários HTML comuns podem ser removidos; condicionais do Outlook
# (<!--[if mso]> ... <![endif]-->) precisam ser preservados
_RE_COMENTARIO = re.compile(r"<!--(?!\[if|<!\[endif)(.*?)-->", re.S)

_RE_IMG = re.compile(r"<img\b[^>]*>", re.S)
_RE_SRC_BASE64 = re.compile(r'src="data:[^"]*"')
_RE_ALT = re.compile(r'alt="([^"]*)"')


@dataclass
class DadosEditora:
    endereco: str = ""
    cnpj: str = ""
    dominio: str = ""


@dataclass
class TemplateMontado:
    html: str
    regiao: str
    avisos: list[str] = field(default_factory=list)
    impedimentos: list[str] = field(default_factory=list)


def _com_utm(url: str, campanha: str, conteudo: str) -> str:
    if not campanha:
        return url
    separador = "&" if "?" in url else "?"
    return (
        f"{url}{separador}utm_source=brevo&utm_medium=email"
        f"&utm_campaign={campanha}&utm_content={conteudo}"
    )


def carregar_mapa_imagens(pasta: str | Path) -> dict:
    """Lê ``imagens.json`` da pasta de templates (chave → URL hospedada)."""
    caminho = Path(pasta) / "imagens.json"
    if not caminho.exists():
        return {}
    return json.loads(caminho.read_text(encoding="utf-8"))


def _trocar_imagens(html: str, slug: str, mapa: dict) -> str:
    def substituir(match: re.Match) -> str:
        tag = match.group(0)
        alt = _RE_ALT.search(tag)
        if not alt:
            return tag
        for padrao, chave in _CHAVE_POR_ALT:
            if padrao.search(alt.group(1)):
                url = mapa.get(chave.format(slug=slug))
                if url:
                    return _RE_SRC_BASE64.sub(f'src="{url}"', tag)
                break
        return tag

    return _RE_IMG.sub(substituir, html)


def montar_template(
    pasta: str | Path,
    slug_regiao: str,
    editora: DadosEditora,
    link_nacional: str = LINK_LP_PADRAO,
    link_regional: str = "",
    utm_campanha: str = "",
) -> TemplateMontado:
    """Carrega ``<pasta>/<slug>.html`` e resolve todos os placeholders.

    Retorna o HTML pronto para envio junto com ``avisos`` (problemas de
    qualidade, ex.: imagens ainda em base64) e ``impedimentos`` (pendências
    que devem bloquear um envio real, ex.: CNPJ ausente no rodapé).
    """
    regiao = REGIAO_POR_SLUG.get(slug_regiao)
    if regiao is None:
        raise ValueError(f"Região desconhecida: {slug_regiao!r}")
    caminho = Path(pasta) / f"{slug_regiao}.html"
    if not caminho.exists():
        raise FileNotFoundError(f"Template não encontrado: {caminho}")

    html = caminho.read_text(encoding="utf-8")
    html = _RE_COMENTARIO.sub("", html)

    link_regional = link_regional or link_nacional
    html = html.replace("{{nome_escola}}", "{{params.NOME_ESCOLA}}")
    html = html.replace("{{uf}}", "{{params.UF}}")
    html = html.replace("{{regiao}}", regiao)
    html = html.replace(
        "{{link_lp_nacional}}",
        _com_utm(link_nacional, utm_campanha, f"{slug_regiao}-nacional"),
    )
    html = html.replace(
        "{{link_lp_regional}}",
        _com_utm(link_regional, utm_campanha, f"{slug_regiao}-regional"),
    )

    if editora.endereco:
        html = html.replace("[ENDEREÇO FÍSICO COMPLETO]", editora.endereco)
        html = html.replace("[ENDEREÇO FÍSICO]", editora.endereco)
    if editora.cnpj:
        html = html.replace("[CNPJ]", editora.cnpj)
        # variante usada nos templates reais: CNPJ-modelo entre colchetes
        html = html.replace("[00.000.000/0000-00]", editora.cnpj)
    if editora.dominio:
        html = html.replace("[DOMINIO]", editora.dominio)

    html = _trocar_imagens(html, slug_regiao, carregar_mapa_imagens(pasta))

    avisos: list[str] = []
    impedimentos: list[str] = []

    pendentes = sorted(
        set(
            re.findall(
                r"\[(ENDEREÇO FÍSICO[^\]]*|CNPJ|DOMINIO|00\.000\.000/0000-00)\]", html
            )
        )
    )
    if pendentes:
        impedimentos.append(
            "Rodapé incompleto (obrigatório em e-mail marketing): "
            + ", ".join(f"[{p}]" for p in pendentes)
            + " — defina EDITORA_ENDERECO, EDITORA_CNPJ e EDITORA_DOMINIO no .env"
        )

    sobras = sorted(set(re.findall(r"\{\{\s*link_[a-z_]+\s*\}\}", html)))
    if sobras:
        impedimentos.append(f"Links não resolvidos no template: {', '.join(sobras)}")

    n_base64 = len(re.findall(r'src="data:image/', html))
    if n_base64:
        avisos.append(
            f"{n_base64} imagem(ns) ainda em base64 (~{len(html) // 1024} KB no total): "
            "Gmail e Outlook costumam bloquear/cortar. Hospede as imagens de "
            "templates/pnld2027/email01/imagens/ na galeria do Brevo e preencha "
            "imagens.json na pasta dos templates."
        )

    return TemplateMontado(html=html, regiao=regiao, avisos=avisos, impedimentos=impedimentos)


def slug_da_regiao(regiao: str) -> str:
    return SLUG_POR_REGIAO[regiao]
