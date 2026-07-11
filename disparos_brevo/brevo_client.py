"""Cliente HTTP fino para a API v3 do Brevo.

Documentação: https://developers.brevo.com/docs/getting-started
Autenticação: header ``api-key`` (Brevo > Settings > SMTP & API > API Keys).
"""

import time

import requests

from .config import URL_BASE_PADRAO


class BrevoAPIError(RuntimeError):
    """Erro retornado pela API do Brevo (status HTTP >= 400)."""

    def __init__(self, status_code: int, mensagem: str):
        super().__init__(f"HTTP {status_code}: {mensagem}")
        self.status_code = status_code
        self.mensagem = mensagem


class BrevoClient:
    # Status que valem nova tentativa: limite de requisições e erros do servidor.
    _STATUS_RETENTAVEIS = {429, 500, 502, 503, 504}

    def __init__(
        self,
        api_key: str,
        url_base: str = URL_BASE_PADRAO,
        max_tentativas: int = 4,
        intervalo_entre_requisicoes: float = 0.15,
        timeout: float = 30.0,
    ):
        self.url_base = url_base.rstrip("/")
        self.max_tentativas = max_tentativas
        self.intervalo_entre_requisicoes = intervalo_entre_requisicoes
        self.timeout = timeout
        self._sessao = requests.Session()
        self._sessao.headers.update(
            {
                "api-key": api_key,
                "accept": "application/json",
                "content-type": "application/json",
            }
        )
        self._ultimo_envio = 0.0

    # ------------------------------------------------------------------ infra

    def _aguardar_intervalo(self) -> None:
        decorrido = time.monotonic() - self._ultimo_envio
        falta = self.intervalo_entre_requisicoes - decorrido
        if falta > 0:
            time.sleep(falta)

    def _requisitar(
        self,
        metodo: str,
        caminho: str,
        json: dict | None = None,
        params: dict | None = None,
    ) -> dict:
        url = f"{self.url_base}{caminho}"
        ultima_excecao: Exception | None = None

        for tentativa in range(1, self.max_tentativas + 1):
            self._aguardar_intervalo()
            try:
                resposta = self._sessao.request(
                    metodo, url, json=json, params=params, timeout=self.timeout
                )
            except requests.RequestException as exc:
                ultima_excecao = exc
                time.sleep(2 ** (tentativa - 1))
                continue
            finally:
                self._ultimo_envio = time.monotonic()

            if resposta.status_code in self._STATUS_RETENTAVEIS:
                if tentativa == self.max_tentativas:
                    raise BrevoAPIError(resposta.status_code, resposta.text)
                time.sleep(2 ** (tentativa - 1))
                continue

            if resposta.status_code >= 400:
                try:
                    detalhe = resposta.json().get("message", resposta.text)
                except ValueError:
                    detalhe = resposta.text
                raise BrevoAPIError(resposta.status_code, detalhe)

            if not resposta.content:
                return {}
            try:
                return resposta.json()
            except ValueError:
                return {}

        raise BrevoAPIError(0, f"Falha de rede após {self.max_tentativas} tentativas: {ultima_excecao}")

    # ------------------------------------------------------------------ conta

    def conta(self) -> dict:
        """GET /account — dados da conta, plano e créditos."""
        return self._requisitar("GET", "/account")

    # --------------------------------------------------------------- contatos

    def contatos_da_lista(self, lista_id: int, por_pagina: int = 500) -> list[dict]:
        """GET /contacts/lists/{id}/contacts — busca TODOS os contatos da lista.

        Percorre as páginas (máx. 500 por requisição) e retorna a lista
        completa de contatos como retornados pela API do Brevo.
        """
        contatos: list[dict] = []
        offset = 0
        while True:
            resposta = self._requisitar(
                "GET",
                f"/contacts/lists/{lista_id}/contacts",
                params={"limit": por_pagina, "offset": offset, "sort": "asc"},
            )
            pagina = resposta.get("contacts", [])
            contatos.extend(pagina)
            offset += len(pagina)
            if len(pagina) < por_pagina or offset >= resposta.get("count", 0):
                break
        return contatos

    # ----------------------------------------------------------------- e-mail

    def enviar_email_lote(
        self,
        remetente: dict,
        destinatarios: list[dict],
        assunto: str | None = None,
        html: str | None = None,
        template_id: int | None = None,
        tag: str | None = None,
    ) -> dict:
        """POST /smtp/email — envio transacional em lote via messageVersions.

        ``destinatarios``: lista de dicts ``{"email": ..., "nome": ...,
        "params": {...}, "assunto": ...}``. Cada destinatário vira uma
        messageVersion com seus próprios params (personalização via
        ``{{params.COLUNA}}`` no HTML) e, se presente, assunto próprio.
        Informe ``html`` + ``assunto`` OU ``template_id`` (template do Brevo).
        """
        if not destinatarios:
            raise ValueError("Lista de destinatários vazia.")
        if template_id is None and not (html and assunto):
            raise ValueError("Informe template_id ou html + assunto.")

        versoes = []
        for dest in destinatarios:
            to = {"email": dest["email"]}
            if dest.get("nome"):
                to["name"] = dest["nome"]
            versao: dict = {"to": [to]}
            if dest.get("params"):
                versao["params"] = dest["params"]
            if dest.get("assunto"):
                versao["subject"] = dest["assunto"]
            versoes.append(versao)

        corpo: dict = {"sender": remetente, "messageVersions": versoes}
        if template_id is not None:
            corpo["templateId"] = template_id
        else:
            corpo["subject"] = assunto
            corpo["htmlContent"] = html
        if tag:
            corpo["tags"] = [tag]

        return self._requisitar("POST", "/smtp/email", json=corpo)

    # -------------------------------------------------------------------- SMS

    def enviar_sms(
        self,
        remetente: str,
        numero: str,
        conteudo: str,
        tipo: str = "marketing",
        tag: str | None = None,
    ) -> dict:
        """POST /transactionalSMS/sms — envia um SMS para um número."""
        corpo: dict = {
            "sender": remetente,
            "recipient": numero,
            "content": conteudo,
            "type": tipo,
            "unicodeEnabled": True,
        }
        if tag:
            corpo["tag"] = tag
        return self._requisitar("POST", "/transactionalSMS/sms", json=corpo)

    # --------------------------------------------------------------- WhatsApp

    def enviar_whatsapp(
        self,
        template_id: int,
        remetente_numero: str,
        numeros: list[str],
        params: dict | None = None,
    ) -> dict:
        """POST /whatsapp/sendMessage — envia um template aprovado de WhatsApp.

        Requer conta WhatsApp Business conectada ao Brevo e template aprovado
        pela Meta. ``numeros`` no formato internacional, ex.: +5521999999999.
        """
        if not numeros:
            raise ValueError("Lista de números vazia.")
        corpo: dict = {
            "templateId": template_id,
            "senderNumber": remetente_numero,
            "contactNumbers": numeros,
        }
        if params:
            corpo["params"] = params
        return self._requisitar("POST", "/whatsapp/sendMessage", json=corpo)
