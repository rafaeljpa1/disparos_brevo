"""Mapeamento UF → região do Brasil e agrupamento de contatos."""

UFS_POR_REGIAO = {
    "Norte": ["AC", "AP", "AM", "PA", "RO", "RR", "TO"],
    "Nordeste": ["AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE"],
    "Centro-Oeste": ["DF", "GO", "MT", "MS"],
    "Sudeste": ["ES", "MG", "RJ", "SP"],
    "Sul": ["PR", "RS", "SC"],
}

REGIAO_POR_UF = {
    uf: regiao for regiao, ufs in UFS_POR_REGIAO.items() for uf in ufs
}

SLUG_POR_REGIAO = {
    "Norte": "norte",
    "Nordeste": "nordeste",
    "Centro-Oeste": "centro-oeste",
    "Sudeste": "sudeste",
    "Sul": "sul",
}

REGIAO_POR_SLUG = {slug: regiao for regiao, slug in SLUG_POR_REGIAO.items()}


def regiao_da_uf(uf: str) -> str | None:
    """Retorna a região da UF ("SP" → "Sudeste") ou None se desconhecida."""
    return REGIAO_POR_UF.get((uf or "").strip().upper())


def agrupar_por_regiao(
    contatos: list[dict], campo_uf: str = "ESTADO"
) -> tuple[dict[str, list[dict]], list[dict]]:
    """Agrupa contatos por região a partir da coluna de UF.

    Retorna ``(por_regiao, sem_regiao)``. Cada contato agrupado ganha as
    chaves ``UF`` (normalizada) e ``REGIAO``, disponíveis para
    personalização das mensagens.
    """
    por_regiao: dict[str, list[dict]] = {}
    sem_regiao: list[dict] = []
    for contato in contatos:
        uf = (contato.get(campo_uf) or "").strip().upper()
        regiao = REGIAO_POR_UF.get(uf)
        if regiao is None:
            sem_regiao.append(contato)
            continue
        por_regiao.setdefault(regiao, []).append(
            {**contato, "UF": uf, "REGIAO": regiao}
        )
    return por_regiao, sem_regiao
