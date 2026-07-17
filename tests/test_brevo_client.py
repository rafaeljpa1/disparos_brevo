from unittest.mock import MagicMock

import pytest

from disparos_brevo.brevo_client import BrevoAPIError, BrevoClient


def cliente_com_resposta(status_code: int = 201, corpo: dict | None = None) -> tuple[BrevoClient, MagicMock]:
    cliente = BrevoClient("chave-teste", intervalo_entre_requisicoes=0)
    resposta = MagicMock()
    resposta.status_code = status_code
    resposta.content = b"{}"
    resposta.json.return_value = corpo or {}
    resposta.text = "{}"
    sessao = MagicMock()
    sessao.request.return_value = resposta
    cliente._sessao = sessao
    return cliente, sessao


def test_header_de_autenticacao():
    cliente = BrevoClient("minha-chave")
    assert cliente._sessao.headers["api-key"] == "minha-chave"


def test_enviar_email_lote_monta_message_versions():
    cliente, sessao = cliente_com_resposta()
    cliente.enviar_email_lote(
        remetente={"name": "Capela", "email": "tiago@capela.press"},
        destinatarios=[
            {"email": "a@b.com", "nome": "Ana", "params": {"NOME": "Ana"}},
            {"email": "c@d.com", "nome": "", "params": {}},
        ],
        assunto="Oi",
        html="<p>Olá {{params.NOME}}</p>",
        tag="pnld",
    )
    corpo = sessao.request.call_args.kwargs["json"]
    assert corpo["sender"] == {"name": "Capela", "email": "tiago@capela.press"}
    assert corpo["subject"] == "Oi"
    assert corpo["tags"] == ["pnld"]
    assert corpo["messageVersions"] == [
        {"to": [{"email": "a@b.com", "name": "Ana"}], "params": {"NOME": "Ana"}},
        {"to": [{"email": "c@d.com"}]},
    ]


def test_enviar_email_lote_com_template_id_nao_manda_html():
    cliente, sessao = cliente_com_resposta()
    cliente.enviar_email_lote(
        remetente={"email": "tiago@capela.press"},
        destinatarios=[{"email": "a@b.com"}],
        template_id=42,
    )
    corpo = sessao.request.call_args.kwargs["json"]
    assert corpo["templateId"] == 42
    assert "htmlContent" not in corpo
    assert "subject" not in corpo


def test_enviar_email_exige_conteudo():
    cliente, _ = cliente_com_resposta()
    with pytest.raises(ValueError):
        cliente.enviar_email_lote(
            remetente={"email": "x@y.com"}, destinatarios=[{"email": "a@b.com"}]
        )


def test_enviar_sms_monta_corpo():
    cliente, sessao = cliente_com_resposta()
    cliente.enviar_sms("Capela", "+5521999990001", "Olá!", tag="pnld")
    metodo, url = sessao.request.call_args.args[:2]
    corpo = sessao.request.call_args.kwargs["json"]
    assert metodo == "POST"
    assert url.endswith("/transactionalSMS/sms")
    assert corpo == {
        "sender": "Capela",
        "recipient": "+5521999990001",
        "content": "Olá!",
        "type": "marketing",
        "unicodeEnabled": True,
        "tag": "pnld",
    }


def test_enviar_whatsapp_monta_corpo():
    cliente, sessao = cliente_com_resposta()
    cliente.enviar_whatsapp(7, "+5521988887777", ["+5521999990001"])
    corpo = sessao.request.call_args.kwargs["json"]
    assert corpo == {
        "templateId": 7,
        "senderNumber": "+5521988887777",
        "contactNumbers": ["+5521999990001"],
    }


def test_remetentes_consulta_endpoint_senders():
    cliente, sessao = cliente_com_resposta(
        status_code=200,
        corpo={"senders": [{"id": 2, "email": "atendimento@casadeletras.com.br", "active": True}]},
    )
    remetentes = cliente.remetentes()
    metodo, url = sessao.request.call_args.args[:2]
    assert metodo == "GET"
    assert url.endswith("/senders")
    assert remetentes[0]["email"] == "atendimento@casadeletras.com.br"


def test_erro_http_vira_brevo_api_error():
    cliente, _ = cliente_com_resposta(status_code=401, corpo={"message": "Key not found"})
    with pytest.raises(BrevoAPIError) as excecao:
        cliente.conta()
    assert excecao.value.status_code == 401
    assert "Key not found" in str(excecao.value)


def test_retry_em_429_ate_sucesso(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _: None)
    cliente = BrevoClient("chave", intervalo_entre_requisicoes=0)
    resposta_429 = MagicMock(status_code=429, text="limite", content=b"limite")
    resposta_ok = MagicMock(status_code=200, content=b"{}")
    resposta_ok.json.return_value = {"ok": True}
    sessao = MagicMock()
    sessao.request.side_effect = [resposta_429, resposta_ok]
    cliente._sessao = sessao

    assert cliente.conta() == {"ok": True}
    assert sessao.request.call_count == 2
