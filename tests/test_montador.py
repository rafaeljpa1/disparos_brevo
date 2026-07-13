import json
from pathlib import Path

import pytest

from disparos_brevo.montador import DadosEditora, montar_template

TEMPLATE_BASE = """<!DOCTYPE html>
<html><head><title>Teste</title></head>
<body>
<!-- comentário com instruções {{...}} e [SUBSTITUIR] -->
<!--[if mso]><table><tr><td><![endif]-->
<span style="font-family:'Poppins',Arial; font-size:22px; font-weight:700; color:#1E3F58;">
  Casa de Letras
</span>
<p>Olá, equipe da {{nome_escola}}! Escolas de {{uf}}, região {{regiao}}.</p>
<a href="{{link_lp_nacional}}">Nacional</a>
<a href="{{link_lp_regional}}">Regional</a>
<img src="data:image/jpeg;base64,AAAA" alt="Capa do livro Conheça o Brasil — Região Sul" />
<img src="data:image/jpeg;base64,BBBB" alt="Coleção Arte" />
<footer><a href="{{link_site}}" target="_blank" style="text-decoration:none;"><img src="{{logo_rodape}}" width="84" alt="Casa de Letras" style="border:0;"></a><br>
[ENDEREÇO FÍSICO COMPLETO] &middot; CNPJ [00.000.000/0000-00]<br>
<a href="mailto:contato@novidades.[DOMINIO].com.br">contato@novidades.[DOMINIO].com.br</a></footer>
<a href="{{ unsubscribe }}">Descadastrar</a> &middot; <a href="#">Política de privacidade</a>
<!--[if mso]></td></tr></table><![endif]-->
</body></html>
"""

EDITORA = DadosEditora(
    endereco="Rua X, 1 — Rio de Janeiro/RJ", cnpj="00.000.000/0001-00", dominio="casadeletras"
)

EDITORA_COMPLETA = DadosEditora(
    razao_social="Casa de Letras e Gráfica Ltda",
    cnpj="48.764.955/0001-41",
    endereco="Rua Fradique Coutinho, 1139 – Pinheiros · CEP 05416-011 · São Paulo – SP",
    email_contato="comercial@casadeletras.com.br",
    link_privacidade="https://casadeletras.com.br/politica-de-privacidade/",
    link_site="https://casadeletras.com.br/",
    logo_url="https://casadeletras.com.br/logo.png",
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


def test_email_de_contato_real_no_rodape(pasta):
    editora = DadosEditora(
        endereco="Rua X", cnpj="11.222.333/0001-44",
        email_contato="comercial@casadeletras.com.br",
    )
    montado = montar_template(pasta, "sul", editora)
    assert "contato@novidades" not in montado.html
    assert 'href="mailto:comercial@casadeletras.com.br"' in montado.html
    assert montado.impedimentos == []  # e-mail real dispensa [DOMINIO]


def test_link_de_privacidade(pasta):
    sem_link = montar_template(pasta, "sul", EDITORA)
    assert any("privacidade" in a for a in sem_link.avisos)

    com_link = montar_template(
        pasta, "sul",
        DadosEditora(endereco="x", cnpj="y", dominio="z",
                     link_privacidade="https://casadeletras.com.br/privacidade/"),
    )
    assert 'href="https://casadeletras.com.br/privacidade/"' in com_link.html
    assert not any("privacidade" in a for a in com_link.avisos)


def test_links_com_padrao_regiao(pasta):
    montado = montar_template(
        pasta, "sul", EDITORA,
        link_nacional="https://casadeletras.com.br/pnld-2027/",
        link_regional="https://casadeletras.com.br/pnld-2027-{regiao}/",
    )
    assert 'href="https://casadeletras.com.br/pnld-2027-sul/"' in montado.html
    assert 'href="https://casadeletras.com.br/pnld-2027/"' in montado.html


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
    assert not any("base64" in aviso for aviso in montado.avisos)


def test_linha_institucional_na_ordem_do_site(pasta):
    montado = montar_template(pasta, "sul", EDITORA_COMPLETA)
    assert (
        "Casa de Letras e Gráfica Ltda &middot; CNPJ 48.764.955/0001-41 "
        "&middot; Rua Fradique Coutinho, 1139 – Pinheiros · CEP 05416-011 "
        "· São Paulo – SP" in montado.html
    )
    assert montado.impedimentos == []


def test_logo_com_link_para_o_site(pasta):
    import re

    montado = montar_template(pasta, "sul", EDITORA_COMPLETA)
    assert re.search(
        r'<a href="https://casadeletras\.com\.br/" target="_blank"[^>]*>\s*'
        r"<span[^>]*>\s*Casa de Letras\s*</span></a>",
        montado.html,
    )


def test_logo_do_rodape_preenchido(pasta):
    montado = montar_template(pasta, "sul", EDITORA_COMPLETA)
    assert 'src="https://casadeletras.com.br/logo.png"' in montado.html
    assert '<a href="https://casadeletras.com.br/" target="_blank"' in montado.html
    assert "{{logo_rodape}}" not in montado.html
    assert "{{link_site}}" not in montado.html


def test_rodape_sem_logo_quando_nao_configurado(pasta):
    montado = montar_template(pasta, "sul", EDITORA)
    assert 'alt="Casa de Letras"' not in montado.html
    assert "{{logo_rodape}}" not in montado.html
    assert "{{link_site}}" not in montado.html
    assert any("LOGO_RODAPE_URL" in aviso for aviso in montado.avisos)


def test_logo_sem_link_quando_nao_configurado(pasta):
    montado = montar_template(pasta, "sul", EDITORA)
    assert 'target="_blank" style="text-decoration:none;"' not in montado.html


def test_aplicar_dados_de_exemplo(pasta):
    from disparos_brevo.montador import aplicar_dados_de_exemplo

    montado = montar_template(pasta, "sul", EDITORA)
    previa = aplicar_dados_de_exemplo(montado.html, "sul")
    assert "{{params.NOME_ESCOLA}}" not in previa
    assert "{{params.UF}}" not in previa
    assert "{{ unsubscribe }}" not in previa
    assert "Escola Municipal Monteiro Lobato" in previa
    assert "PR" in previa


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
        montado = montar_template(
            reais, slug, EDITORA_COMPLETA, utm_campanha="pnld2027-email01"
        )
        assert montado.impedimentos == [], f"{slug}: {montado.impedimentos}"
        assert "{{nome_escola}}" not in montado.html
        assert "{{regiao}}" not in montado.html
        assert "{{params.NOME_ESCOLA}}" in montado.html
        # rodapé espelhando o site
        assert "Casa de Letras e Gráfica Ltda &middot; CNPJ 48.764.955/0001-41" in montado.html
        assert 'href="https://casadeletras.com.br/" target="_blank"' in montado.html
        assert "prerrogativa exclusiva dos educadores" in montado.html
        assert 'href="https://casadeletras.com.br/politica-de-privacidade/"' in montado.html
        # rodapé em faixa azul-marinho com o logo do site, sem título de texto
        assert 'src="https://casadeletras.com.br/logo.png"' in montado.html
        assert "background-color:#1E3F58; border-radius:16px;" in montado.html
        assert ">Editora Casa de Letras</span>" not in montado.html
        assert "{{link_site}}" not in montado.html
        # imagens ainda em base64 → deve avisar enquanto não houver imagens.json
        assert any("base64" in a for a in montado.avisos)
