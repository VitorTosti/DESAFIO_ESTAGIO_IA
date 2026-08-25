import json
from pathlib import Path

import pandas as pd


RAIZ_PROJETO = Path(__file__).resolve().parent.parent
CAMINHO_RANKING = RAIZ_PROJETO / "outputs" / "ranking_top10.csv"
CAMINHO_PARECERES = RAIZ_PROJETO / "outputs" / "pareceres_agente.json"
CAMINHO_SAIDA = RAIZ_PROJETO / "outputs" / "confronto.csv"


def classificar_risco_regras(row: pd.Series) -> str:
    """Converte as sinalizações determinísticas em uma categoria de risco."""

    fracionamentos = int(row["qtd_fracionamentos"])
    atipicos = int(row["qtd_valores_atipicos"])
    total = int(row["total_sinalizacoes"])

    # Critério adotado para o confronto:
    # - alto: múltiplos tipos de alerta ou 3+ sinalizações;
    # - médio: 1 ou 2 sinalizações;
    # - baixo: nenhuma sinalização.
    if (fracionamentos > 0 and atipicos > 0) or total >= 3:
        return "alto"

    if total >= 1:
        return "médio"

    return "baixo"


def carregar_pareceres() -> pd.DataFrame:
    """Carrega os níveis de risco produzidos pelo agente."""

    with CAMINHO_PARECERES.open("r", encoding="utf-8") as arquivo:
        pareceres = json.load(arquivo)

    registros = []

    for resultado in pareceres:
        if resultado.get("status") != "sucesso":
            continue

        registros.append({
            "cliente_id": resultado["cliente_id"],
            "risco_agente": resultado["parecer"]["nivel_risco"],
            "tipologia_agente": resultado["parecer"]["tipologia_suspeita"],
            "justificativa_agente": resultado["parecer"]["justificativa"],
        })

    return pd.DataFrame(registros)


def gerar_confronto() -> pd.DataFrame:
    """Compara o risco determinístico com o risco atribuído pelo agente."""

    ranking = pd.read_csv(CAMINHO_RANKING)
    pareceres = carregar_pareceres()

    ranking["risco_regras"] = ranking.apply(
        classificar_risco_regras,
        axis=1,
    )

    confronto = ranking.merge(
        pareceres,
        on="cliente_id",
        how="left",
    )

    confronto["concorda"] = (
        confronto["risco_regras"]
        == confronto["risco_agente"]
    )

    return confronto


if __name__ == "__main__":
    confronto = gerar_confronto()

    confronto.to_csv(
        CAMINHO_SAIDA,
        index=False,
        encoding="utf-8",
    )

    taxa_concordancia = (
        confronto["concorda"].mean() * 100
    )

    print("\n--- Confronto regras x agente ---")
    print(
        confronto[
            [
                "cliente_id",
                "qtd_fracionamentos",
                "qtd_valores_atipicos",
                "total_sinalizacoes",
                "risco_regras",
                "risco_agente",
                "concorda",
            ]
        ].to_string(index=False)
    )

    print(
        f"\nTaxa de concordância: "
        f"{taxa_concordancia:.2f}%"
    )

    divergencias = confronto[
        ~confronto["concorda"]
    ]

    print("\n--- Divergências ---")

    if divergencias.empty:
        print("Nenhuma divergência encontrada.")
    else:
        print(
            divergencias[
                [
                    "cliente_id",
                    "risco_regras",
                    "risco_agente",
                    "tipologia_agente",
                ]
            ].to_string(index=False)
        )

    print(f"\nResultado salvo em: {CAMINHO_SAIDA}")