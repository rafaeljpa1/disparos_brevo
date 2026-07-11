from unittest.mock import MagicMock

from disparos_brevo.brevo_client import BrevoClient
from disparos_brevo.disparo import contato_brevo_para_dict, disparar_emails


def test_contato_brevo_para_dict():
    contato = contato_brevo_para_dict(
        {
            "email": "Escola@Exemplo.com",
            "emailBlacklisted": False,
            "attributes": {"ESTADO": "SP", "MUNICIPIO": "Osasco", "NOME_ESCOLA": "EMEF X"},
        }
    )
    assert contato["EMAIL"] == "escola@exemplo.com"
    assert contato["ESTADO"] == "SP"
    assert contato["NOME_ESCOLA"] == "EMEF X"
    assert contato["_BLACKLISTED"] is False


def test_contato_brevo_blacklisted():
    contato = contato_brevo_para_dict({"email": "a@b.com", "emailBlacklisted": True})
    assert contato["_BLACKLISTED"] is True


def test_contatos_da_lista_pagina_ate_o_fim():
    cliente = BrevoClient("chave", intervalo_entre_requisicoes=0)
    pagina1 = MagicMock(status_code=200, content=b"{}")
    pagina1.json.return_value = {
        "contacts": [{"email": f"c{i}@x.com"} for i in range(500)],
        "count": 780,
    }
    pagina2 = MagicMock(status_code=200, content=b"{}")
    pagina2.json.return_value = {
        "contacts": [{"email": f"c{i}@x.com"} for i in range(500, 780)],
        "count": 780,
    }
    sessao = MagicMock()
    sessao.request.side_effect = [pagina1, pagina2]
    cliente._sessao = sessao

    contatos = cliente.contatos_da_lista(3)
    assert len(contatos) == 780
    assert sessao.request.call_count == 2
    params1 = sessao.request.call_args_list[0].kwargs["params"]
    params2 = sessao.request.call_args_list[1].kwargs["params"]
    assert params1["offset"] == 0
    assert params2["offset"] == 500


def test_assunto_personalizado_por_destinatario():
    class ClienteFake:
        def __init__(self):
            self.chamadas = []

        def enviar_email_lote(self, **kwargs):
            self.chamadas.append(kwargs)
            return {}

    cliente = ClienteFake()
    contatos = [
        {"EMAIL": "a@b.com", "UF": "SP", "REGIAO": "Sudeste", "_DESTINO": "a@b.com"},
        {"EMAIL": "c@d.com", "UF": "PR", "REGIAO": "Sul", "_DESTINO": "c@d.com"},
    ]
    disparar_emails(
        cliente,
        contatos,
        remetente={"email": "x@y.com"},
        assunto="PNLD 2027 — {UF}",
        html="<p>x</p>",
        confirmar=True,
    )
    destinatarios = cliente.chamadas[0]["destinatarios"]
    assert destinatarios[0]["assunto"] == "PNLD 2027 — SP"
    assert destinatarios[1]["assunto"] == "PNLD 2027 — PR"
