"""Carregamento de configuração via variáveis de ambiente / arquivo .env."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

URL_BASE_PADRAO = "https://api.brevo.com/v3"


class ErroDeConfiguracao(RuntimeError):
    pass


@dataclass
class Config:
    api_key: str
    remetente_nome: str
    remetente_email: str
    sms_remetente: str
    whatsapp_remetente: str
    url_base: str = URL_BASE_PADRAO
    # Disparos regionais (PNLD)
    link_lp_nacional: str = ""
    link_lp_regional: str = ""
    editora_endereco: str = ""
    editora_cnpj: str = ""
    editora_dominio: str = ""
    editora_email_contato: str = ""
    link_politica_privacidade: str = ""
    editora_razao_social: str = ""
    link_site: str = ""
    logo_url: str = ""


def carregar_config(exigir_api_key: bool = True) -> Config:
    """Lê o .env (se existir) e monta a configuração do projeto.

    Somente BREVO_API_KEY é obrigatória (dispensável para comandos que não
    falam com a API, ex.: previa); as demais variáveis têm padrão vazio e
    são validadas no momento do uso de cada canal.
    """
    load_dotenv()

    api_key = os.environ.get("BREVO_API_KEY", "").strip()
    if not api_key and exigir_api_key:
        raise ErroDeConfiguracao(
            "BREVO_API_KEY não definida. Copie .env.example para .env e "
            "preencha a chave de API (Brevo > Settings > SMTP & API > API Keys)."
        )

    return Config(
        api_key=api_key,
        remetente_nome=os.environ.get("REMETENTE_NOME", "").strip(),
        remetente_email=os.environ.get("REMETENTE_EMAIL", "").strip(),
        sms_remetente=os.environ.get("SMS_REMETENTE", "").strip(),
        whatsapp_remetente=os.environ.get("WHATSAPP_REMETENTE", "").strip(),
        url_base=os.environ.get("BREVO_URL_BASE", URL_BASE_PADRAO).strip(),
        link_lp_nacional=os.environ.get("LINK_LP_NACIONAL", "").strip(),
        link_lp_regional=os.environ.get("LINK_LP_REGIONAL", "").strip(),
        editora_endereco=os.environ.get("EDITORA_ENDERECO", "").strip(),
        editora_cnpj=os.environ.get("EDITORA_CNPJ", "").strip(),
        editora_dominio=os.environ.get("EDITORA_DOMINIO", "").strip(),
        editora_email_contato=os.environ.get("EDITORA_EMAIL_CONTATO", "").strip(),
        link_politica_privacidade=os.environ.get("LINK_POLITICA_PRIVACIDADE", "").strip(),
        editora_razao_social=os.environ.get("EDITORA_RAZAO_SOCIAL", "").strip(),
        link_site=os.environ.get("LINK_SITE", "").strip(),
        # LOGO_RODAPE_URL é o nome antigo, aceito por compatibilidade
        logo_url=(
            os.environ.get("LOGO_URL", "").strip()
            or os.environ.get("LOGO_RODAPE_URL", "").strip()
        ),
    )
