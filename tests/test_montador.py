import json
from pathlib import Path

import pytest

from disparos_brevo.montador import DadosEditora, montar_template

TEMPLATE_BASE = """<!DOCTYPE html>
<html><head><title>Teste</title></head>
<body>
<!-- comentário com instruções {{...}} e [SUBSTITUIR] -->
<!--[if mso]><table><tr><td><![endif]-->
<p>Olá, equipe da {{nome_escola}}! Escolas de {{uf}}, região {{regiao}}.</p>
<a href="{{link_lp_nacional}}">Nacional</a>
<a href="{{link_lp_regional}}">Regional</a>
<img src="data:image/jpeg;base64,AAAA" alt="Capa do livro Conheça o Brasil — Região Sul" />
<img src="data:image/jpeg;base64,BBBB" alt="Coleção Arte" />
<footer>[ENDEREÇO FÍSICO] — CNPJ [00.000.000/0000-00] — contato@novidades.[DOMINIO].com.br</footer>
<a href="{{ unsubscribe }}">Descadastrar</a>
<!--[if mso]></td></tr></table><![endif]-->
</body></html>
"""

EDITORA = DadosEditora(
    endereco="Rua X, 1 — Rio de Janeiro/RJ", cnpj="00.000.000/0001-00", dominio="casadeletras"
)


@pytest.fixture
def pasta(tmp_path: Path) -> Path:
    (tmp_path / "sul.html").write_text(TEMPLATE_BASE, encoding="utf-8")
    return tmp_path


def test_substitui_placeholders_e_links(pasta):
    montado = montar_template(
        pasta, "sul", EDITORA,
        link_nacional="https://casadeletras.com.br/pnld-2027/",
        utm_campanha="pnld2027-email01",
    )
    assert montado.regiao == "Sul"
    assert "{{params.NOME_ESCOLA}}" in montado.html
    assert "{{params.UF}}" in montado.html
    assert "região Sul." in montado.html
    assert (
        "https://casadeletras.com.br/pnld-2027/?utm_source=brevo&utm_medium=email"
        "&utm_campaign=pnld2027-email01&utm_content=sul-nacional" in montado.html
    )
    assert "utm_content=sul-regional" in montado.html
    assert "{{link_lp_nacional}}" not in montado.html
    assert montado.impedimentos == []


def test_link_regional_cai_no_nacional_quando_vazio(pasta):
    montado = montar_template(pasta, "sul", EDITORA, link_nacional="https://x.br/")
    assert 'href="https://x.br/"' in montado.html  # sem utm_campanha, url pura


def test_dados_da_editora_no_rodape(pasta):
    montado = montar_template(pasta, "sul", EDITORA)
    assert "Rua X, 1 — Rio de Janeiro/RJ" in montado.html
    assert "CNPJ 00.000.000/0001-00" in montado.html
    assert "contato@novidades.casadeletras.com.br" in montado.html


def test_rodape_incompleto_gera_impedimento(pasta):
    montado = montar_template(pasta, "sul", DadosEditora())
    assert len(montado.impedimentos) == 1
    assert "[00.000.000/0000-00]" in montado.impedimentos[0]
    assert "[DOMINIO]" in montado.impedimentos[0]


def test_preserva_unsubscribe_e_condicional_outlook_remove_comentarios(pasta):
    montado = montar_template(pasta, "sul", EDITORA)
    assert "{{ unsubscribe }}" in montado.html
    assert "<!--[if mso]>" in montado.html
    assert "instruções" not in montado.html  # comentário comum removido


def test_avisa_sobre_imagens_base64(pasta):
    montado = montar_template(pasta, "sul", EDITORA)
    assert any("base64" in aviso for aviso in montado.avisos)


def test_troca_imagens_por_urls_hospedadas(pasta):
    (pasta / "imagens.json").write_text(
        json.dumps({
            "capa-sul": "https://img.brevo.com/capa-sul.jpg",
            "mini-arte": "https://img.brevo.com/arte.jpg",
        }),
        encoding="utf-8",
    )
    montado = montar_template(pasta, "sul", EDITORA)
    assert 'src="https://img.brevo.com/capa-sul.jpg"' in montado.html
    assert 'src="https://img.brevo.com/arte.jpg"' in montado.html
    assert "data:image" not in montado.html
    assert montado.avisos == []


def test_regiao_desconhecida(pasta):
    with pytest.raises(ValueError):
        montar_template(pasta, "atlantida", EDITORA)


def test_template_inexistente(tmp_path):
    with pytest.raises(FileNotFoundError):
        montar_template(tmp_path, "norte", EDITORA)


def test_templates_reais_do_repositorio():
    """Os 5 templates reais montam sem impedimentos de link/placeholder."""
    reais = Path(__file__).parent.parent / "templates" / "pnld2027" / "email01"
    for slug in ["norte", "nordeste", "centro-oeste", "sudeste", "sul"]:
        montado = montar_template(reais, slug, EDITORA, utm_campanha="pnld2027-email01")
        assert montado.impedimentos == [], f"{slug}: {montado.impedimentos}"
        assert "{{nome_escola}}" not in montado.html
        assert "{{regiao}}" not in montado.html
        assert "{{params.NOME_ESCOLA}}" in montado.html
        # imagens ainda em base64 → deve avisar enquanto não houver imagens.json
        assert any("base64" in a for a in montado.avisos)
