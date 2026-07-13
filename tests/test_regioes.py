from disparos_brevo.regioes import (
    REGIAO_POR_UF,
    UFS_POR_REGIAO,
    agrupar_por_regiao,
    regiao_da_uf,
)


def test_dicionario_cobre_as_27_ufs():
    assert len(REGIAO_POR_UF) == 27
    assert sum(len(ufs) for ufs in UFS_POR_REGIAO.values()) == 27


def test_regiao_da_uf():
    assert regiao_da_uf("SP") == "Sudeste"
    assert regiao_da_uf(" pr ") == "Sul"
    assert regiao_da_uf("DF") == "Centro-Oeste"
    assert regiao_da_uf("XX") is None
    assert regiao_da_uf("") is None


def test_agrupar_por_regiao():
    contatos = [
        {"EMAIL": "a@b.com", "ESTADO": "SP"},
        {"EMAIL": "c@d.com", "ESTADO": "ba"},
        {"EMAIL": "e@f.com", "ESTADO": ""},
        {"EMAIL": "g@h.com", "ESTADO": "ZZ"},
    ]
    por_regiao, sem_regiao = agrupar_por_regiao(contatos)
    assert set(por_regiao) == {"Sudeste", "Nordeste"}
    assert por_regiao["Sudeste"][0]["UF"] == "SP"
    assert por_regiao["Sudeste"][0]["REGIAO"] == "Sudeste"
    assert por_regiao["Nordeste"][0]["UF"] == "BA"
    assert len(sem_regiao) == 2
