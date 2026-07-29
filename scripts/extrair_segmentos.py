"""Extrai os segmentos de uma campanha a partir dos logs de eventos do Brevo.

Para cada evento (delivered, opened, clicks...), pagina
``GET /v3/smtp/statistics/events`` filtrando pela tag da campanha e salva
CSVs de e-mails únicos (cabeçalho EMAIL) + um ``resumo.json`` com contagens,
interseções úteis e os créditos restantes do plano.

Os CSVs servem de entrada para ``--somente-destinos`` nas campanhas
seguintes (ex.: enviar a próxima leva só para quem recebeu a anterior).

Uso, na raiz do repositório::

    python scripts/extrair_segmentos.py --tag pnld2027-email01 \
        --inicio 2026-07-14 [--fim 2026-07-29] [--saida PASTA]

Por padrão ``--fim`` é hoje e ``--saida`` é ``relatorios/<tag>/segmentos``.
"""

import argparse
import csv
import json
import sys
import time
from datetime import date
from pathlib import Path

import requests
from dotenv import dotenv_values

RAIZ = Path(__file__).resolve().parents[1]
BASE_URL = "https://api.brevo.com/v3"

EVENTOS = [
    "delivered",
    "opened",
    "clicks",
    "hardBounces",
    "softBounces",
    "blocked",
    "invalid",
    "error",
    "unsubscribed",
    "spam",
    "loadedByProxy",  # aberturas por proxy (ex.: Apple) — só entra no resumo
]


def coleta_evento(sessao, headers, evento, tag, inicio, fim, limite=5000):
    """Pagina todos os registros de um evento; retorna (total, set de e-mails)."""
    offset = 0
    total = 0
    emails = set()
    while True:
        params = {
            "limit": limite,
            "offset": offset,
            "tags": tag,
            "startDate": inicio,
            "endDate": fim,
            "event": evento,
        }
        resp = sessao.get(
            f"{BASE_URL}/smtp/statistics/events",
            headers=headers,
            params=params,
            timeout=120,
        )
        if resp.status_code == 429:
            print(f"  [{evento}] HTTP 429, aguardando 10s...")
            time.sleep(10)
            continue
        if resp.status_code == 400 and limite > 1000:
            print(f"  [{evento}] limit={limite} recusado (400), caindo para 1000")
            limite = 1000
            continue
        resp.raise_for_status()
        eventos = resp.json().get("events") or []
        if not eventos:
            break
        total += len(eventos)
        for ev in eventos:
            email = (ev.get("email") or "").strip().lower()
            if email:
                emails.add(email)
        print(f"  [{evento}] offset={offset} +{len(eventos)} (total={total})")
        offset += limite
        time.sleep(0.3)
    return total, emails


def salva_csv(caminho, emails):
    with open(caminho, "w", newline="", encoding="utf-8") as arq:
        escritor = csv.writer(arq)
        escritor.writerow(["EMAIL"])
        for email in sorted(emails):
            escritor.writerow([email])
    print(f"  gravado {caminho.name}: {len(emails)} e-mails")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tag", required=True, help="Tag da campanha no Brevo (ex.: pnld2027-email01)")
    parser.add_argument("--inicio", required=True, help="Data inicial dos eventos (AAAA-MM-DD)")
    parser.add_argument("--fim", default=date.today().isoformat(), help="Data final (padrão: hoje)")
    parser.add_argument("--saida", default=None, help="Pasta de saída (padrão: relatorios/<tag>/segmentos)")
    args = parser.parse_args()

    api_key = dotenv_values(RAIZ / ".env").get("BREVO_API_KEY")
    if not api_key:
        print("ERRO: BREVO_API_KEY não encontrada no .env", file=sys.stderr)
        return 2
    headers = {"api-key": api_key, "accept": "application/json"}

    saida = Path(args.saida) if args.saida else RAIZ / "relatorios" / args.tag / "segmentos"
    saida.mkdir(parents=True, exist_ok=True)

    sessao = requests.Session()
    contagens = {}
    conjuntos = {}
    for evento in EVENTOS:
        print(f"Coletando evento: {evento}")
        total, emails = coleta_evento(sessao, headers, evento, args.tag, args.inicio, args.fim)
        contagens[evento] = {"eventos": total, "unicos": len(emails)}
        conjuntos[evento] = emails
        time.sleep(0.3)

    entregues = conjuntos["delivered"]
    abriram = conjuntos["opened"]
    clicaram = conjuntos["clicks"]
    nao_entregues = (
        conjuntos["hardBounces"]
        | conjuntos["softBounces"]
        | conjuntos["blocked"]
        | conjuntos["invalid"]
        | conjuntos["error"]
    )
    descadastrados = conjuntos["unsubscribed"]
    spam = conjuntos["spam"]

    salva_csv(saida / "entregues.csv", entregues)
    salva_csv(saida / "abriram.csv", abriram)
    salva_csv(saida / "clicaram.csv", clicaram)
    salva_csv(saida / "nao_entregues.csv", nao_entregues)
    salva_csv(saida / "descadastrados.csv", descadastrados)
    salva_csv(saida / "marcaram_spam.csv", spam)

    creditos = None
    resp = sessao.get(f"{BASE_URL}/account", headers=headers, timeout=60)
    resp.raise_for_status()
    for plano in resp.json().get("plan", []):
        if plano.get("credits") is not None:
            creditos = plano.get("credits")
            break

    resumo = {
        "campanha": args.tag,
        "data_extracao": date.today().isoformat(),
        "periodo": {"startDate": args.inicio, "endDate": args.fim},
        "contagens_por_evento": contagens,
        "segmentos_unicos": {
            "entregues": len(entregues),
            "abriram": len(abriram),
            "clicaram": len(clicaram),
            "nao_entregues": len(nao_entregues),
            "descadastrados": len(descadastrados),
            "marcaram_spam": len(spam),
        },
        "intersecoes": {
            "abriram_e_entregues": len(abriram & entregues),
            "abriram_fora_de_entregues": len(abriram - entregues),
            "clicaram_e_abriram": len(clicaram & abriram),
            "entregues_menos_abriram": len(entregues - abriram),
            "entregues_menos_descadastrados_e_spam": len(entregues - descadastrados - spam),
        },
        "creditos_restantes_plano": creditos,
    }
    with open(saida / "resumo.json", "w", encoding="utf-8") as arq:
        json.dump(resumo, arq, ensure_ascii=False, indent=2)
    print(json.dumps(resumo["segmentos_unicos"], ensure_ascii=False, indent=2))
    print(f"Créditos restantes do plano: {creditos}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
