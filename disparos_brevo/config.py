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


def carregar_config() -> Config:
    """Lê o .env (se existir) e monta a configuração do projeto.

    Somente BREVO_API_KEY é obrigatória; as demais variáveis têm padrão
    vazio e são validadas no momento do uso de cada canal.
    """
    load_dotenv()

    api_key = os.environ.get("BREVO_API_KEY", "").strip()
    if not api_key:
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
    )
