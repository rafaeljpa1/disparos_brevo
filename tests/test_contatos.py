from pathlib import Path

import pytest

from disparos_brevo.contatos import (
    carregar_contatos,
    email_valido,
    filtrar_por_canal,
    normalizar_telefone,
)


class TestNormalizarTelefone:
    @pytest.mark.parametrize(
        "entrada,esperado",
        [
            ("(21) 99999-0001", "+5521999990001"),
            ("21999990001", "+5521999990001"),
            ("5521999990001", "+5521999990001"),
            ("+5521999990001", "+5521999990001"),
            ("005521999990001", "+5521999990001"),
            ("021999990001", "+5521999990001"),
            ("2133334444", "+552133334444"),  # fixo, 10 dígitos
            ("351912345678", "+351912345678"),  # outro país com código
        ],
    )
    def test_formatos_validos(self, entrada, esperado):
        assert normalizar_telefone(entrada) == esperado

    @pytest.mark.parametrize("entrada", ["", "abc", "123", "999", None and "" or ""])
    def test_formatos_invalidos(self, entrada):
        assert normalizar_telefone(entrada) is None


class TestEmailValido:
    def test_valido(self):
        assert email_valido("maria@exemplo.com.br")

    @pytest.mark.parametrize("entrada", ["", "sem-arroba", "a@b", "a b@c.com"])
    def test_invalido(self, entrada):
        assert not email_valido(entrada)


class TestCarregarContatos:
    def test_carrega_csv_e_normaliza_cabecalho(self, tmp_path: Path):
        csv_path = tmp_path / "contatos.csv"
        csv_path.write_text(
            "email,Nome,livro\nmaria@exemplo.com, Maria ,Matemática\n\n",
            encoding="utf-8",
        )
        contatos = carregar_contatos(csv_path)
        assert contatos == [
            {"EMAIL": "maria@exemplo.com", "NOME": "Maria", "LIVRO": "Matemática"}
        ]

    def test_arquivo_inexistente(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            carregar_contatos(tmp_path / "nao_existe.csv")

    def test_csv_de_exemplo_do_repositorio(self):
        exemplo = Path(__file__).parent.parent / "data" / "contatos.exemplo.csv"
        contatos = carregar_contatos(exemplo)
        assert len(contatos) == 3
        assert contatos[0]["NOME"] == "Maria Silva"


class TestFiltrarPorCanal:
    CONTATOS = [
        {"EMAIL": "Maria@Exemplo.com", "SMS": "(21) 99999-0001", "WHATSAPP": ""},
        {"EMAIL": "invalido", "SMS": "abc", "WHATSAPP": "21999990002"},
        {"EMAIL": "", "SMS": "", "WHATSAPP": ""},
    ]

    def test_email(self):
        validos, invalidos = filtrar_por_canal(self.CONTATOS, "email")
        assert [c["_DESTINO"] for c in validos] == ["maria@exemplo.com"]
        assert len(invalidos) == 2

    def test_sms(self):
        validos, _ = filtrar_por_canal(self.CONTATOS, "sms")
        assert [c["_DESTINO"] for c in validos] == ["+5521999990001"]

    def test_whatsapp(self):
        validos, _ = filtrar_por_canal(self.CONTATOS, "whatsapp")
        assert [c["_DESTINO"] for c in validos] == ["+5521999990002"]

    def test_canal_desconhecido(self):
        with pytest.raises(ValueError):
            filtrar_por_canal(self.CONTATOS, "pombo-correio")
