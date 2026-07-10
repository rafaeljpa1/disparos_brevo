from disparos_brevo.brevo_client import BrevoAPIError
from disparos_brevo.disparo import (
    disparar_emails,
    disparar_sms,
    disparar_whatsapp,
    personalizar,
    resumo,
    salvar_relatorio,
)


class ClienteFake:
    """Substitui BrevoClient nos testes, registrando as chamadas."""

    def __init__(self, falhar: bool = False):
        self.falhar = falhar
        self.chamadas_email: list = []
        self.chamadas_sms: list = []
        self.chamadas_whatsapp: list = []

    def enviar_email_lote(self, **kwargs):
        if self.falhar:
            raise BrevoAPIError(400, "erro de teste")
        self.chamadas_email.append(kwargs)
        return {"messageIds": ["abc"]}

    def enviar_sms(self, remetente, numero, conteudo, **kwargs):
        if self.falhar:
            raise BrevoAPIError(400, "erro de teste")
        self.chamadas_sms.append((remetente, numero, conteudo))
        return {"reference": "xyz"}

    def enviar_whatsapp(self, template_id, remetente_numero, numeros, **kwargs):
        if self.falhar:
            raise BrevoAPIError(400, "erro de teste")
        self.chamadas_whatsapp.append((template_id, remetente_numero, numeros))
        return {}


def contatos_email(n: int) -> list[dict]:
    return [
        {"EMAIL": f"p{i}@exemplo.com", "NOME": f"Pessoa {i}", "_DESTINO": f"p{i}@exemplo.com"}
        for i in range(n)
    ]


def contatos_telefone(n: int) -> list[dict]:
    return [
        {"NOME": f"Pessoa {i}", "LIVRO": "Matemática", "_DESTINO": f"+552199999{i:04d}"}
        for i in range(n)
    ]


REMETENTE = {"name": "Capela", "email": "tiago@capela.press"}


def test_personalizar_substitui_colunas_e_tolera_ausentes():
    contato = {"NOME": "Maria", "_DESTINO": "x"}
    assert personalizar("Olá {NOME}, veja {LIVRO}", contato) == "Olá Maria, veja "


def test_simulacao_nao_chama_api():
    resultados = disparar_emails(
        None, contatos_email(5), REMETENTE, assunto="Oi", html="<p>Olá</p>", confirmar=False
    )
    assert len(resultados) == 5
    assert all(r.sucesso and r.detalhe == "simulado" for r in resultados)


def test_email_envia_em_lotes():
    cliente = ClienteFake()
    resultados = disparar_emails(
        cliente,
        contatos_email(250),
        REMETENTE,
        assunto="Oi",
        html="<p>Olá</p>",
        lote=100,
        confirmar=True,
    )
    assert len(cliente.chamadas_email) == 3  # 100 + 100 + 50
    tamanhos = [len(ch["destinatarios"]) for ch in cliente.chamadas_email]
    assert tamanhos == [100, 100, 50]
    assert all(r.sucesso for r in resultados)


def test_email_params_vem_das_colunas_do_csv():
    cliente = ClienteFake()
    contatos = [{"EMAIL": "a@b.com", "NOME": "Ana", "LIVRO": "Ciências", "_DESTINO": "a@b.com"}]
    disparar_emails(cliente, contatos, REMETENTE, assunto="Oi", html="<p>x</p>", confirmar=True)
    destinatario = cliente.chamadas_email[0]["destinatarios"][0]
    assert destinatario["params"] == {"EMAIL": "a@b.com", "NOME": "Ana", "LIVRO": "Ciências"}


def test_email_erro_da_api_marca_lote_como_falha():
    resultados = disparar_emails(
        ClienteFake(falhar=True),
        contatos_email(3),
        REMETENTE,
        assunto="Oi",
        html="<p>x</p>",
        confirmar=True,
    )
    assert all(not r.sucesso for r in resultados)
    assert "erro de teste" in resultados[0].detalhe


def test_sms_personaliza_mensagem_por_contato():
    cliente = ClienteFake()
    disparar_sms(
        cliente, contatos_telefone(2), "Capela", "Olá {NOME}: {LIVRO}", confirmar=True
    )
    assert cliente.chamadas_sms[0][2] == "Olá Pessoa 0: Matemática"
    assert cliente.chamadas_sms[1][2] == "Olá Pessoa 1: Matemática"


def test_whatsapp_envia_numeros_em_lotes():
    cliente = ClienteFake()
    resultados = disparar_whatsapp(
        cliente, contatos_telefone(120), template_id=7, remetente_numero="+5521988887777",
        lote=50, confirmar=True,
    )
    assert len(cliente.chamadas_whatsapp) == 3  # 50 + 50 + 20
    assert cliente.chamadas_whatsapp[0][0] == 7
    assert len(resultados) == 120


def test_relatorio_e_resumo(tmp_path):
    resultados = disparar_sms(
        None, contatos_telefone(3), "Capela", "Oi {NOME}", confirmar=False
    )
    caminho = salvar_relatorio(resultados, pasta=tmp_path)
    conteudo = caminho.read_text(encoding="utf-8")
    assert "DESTINO,CANAL,STATUS,DETALHE" in conteudo
    assert conteudo.count("simulado") == 3
    assert resumo(resultados) == "3/3 envios ok, 0 com erro"
