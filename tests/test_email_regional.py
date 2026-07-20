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


def test_carregar_destinos_enviados(tmp_path):
    from disparos_brevo.disparo import carregar_destinos_enviados

    (tmp_path / "relatorio_email_1.csv").write_text(
        "DESTINO,CANAL,STATUS,DETALHE\n"
        "a@b.com,email,ok,enviado\n"
        "c@d.com,email,ok,simulado\n"
        "e@f.com,email,erro,HTTP 400: erro\n",
        encoding="utf-8",
    )
    (tmp_path / "relatorio_email_2.csv").write_text(
        "DESTINO,CANAL,STATUS,DETALHE\nG@H.com,email,ok,enviado\n",
        encoding="utf-8",
    )
    enviados = carregar_destinos_enviados(tmp_path)
    # só contam os enviados de verdade: simulação e erro ficam de fora
    assert enviados == {"a@b.com", "g@h.com"}

    apenas_um = carregar_destinos_enviados(tmp_path / "relatorio_email_1.csv")
    assert apenas_um == {"a@b.com"}


def test_acrescentar_relatorio(tmp_path):
    from disparos_brevo.disparo import (
        ResultadoEnvio,
        acrescentar_relatorio,
        carregar_destinos_enviados,
    )

    caminho = tmp_path / "relatorio_unificado.csv"
    r1 = ResultadoEnvio("a@b.com", "email", True, "enviado",
                        {"EMAIL": "a@b.com", "ESTADO": "SP", "REGIAO": "Sudeste"})
    acrescentar_relatorio([r1], caminho)

    # segunda leva: acrescenta sem repetir cabeçalho, mesmo com colunas diferentes
    r2 = ResultadoEnvio("c@d.com", "email", True, "enviado", {"EMAIL": "c@d.com"})
    r3 = ResultadoEnvio("e@f.com", "email", False, "HTTP 400", {"EMAIL": "e@f.com"})
    acrescentar_relatorio([r2, r3], caminho)

    linhas = caminho.read_text(encoding="utf-8").strip().splitlines()
    assert len(linhas) == 4  # 1 cabeçalho + 3 registros
    assert linhas[0].startswith("DESTINO,CANAL,STATUS,DETALHE")
    # integra com a exclusão: só os enviados de verdade contam
    assert carregar_destinos_enviados(caminho) == {"a@b.com", "c@d.com"}


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
