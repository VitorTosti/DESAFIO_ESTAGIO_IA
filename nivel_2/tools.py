import json
from pathlib import Path

import numpy as np
import pandas as pd


def carregar_dados(caminho: str | Path) -> tuple[pd.DataFrame, float]:
    """Carrega as operações e a taxa de câmbio fornecida no arquivo."""
    
    caminho = Path(caminho)

    with caminho.open("r", encoding="utf-8") as arquivo:
        dados = json.load(arquivo)

    df = pd.DataFrame(dados["operacoes"])
    taxa_cambio = float(dados["taxa_cambio_usd_brl"])

    return df, taxa_cambio


def limpar_dados(
    df: pd.DataFrame,
    taxa_cambio: float
) -> pd.DataFrame:
    """Remove duplicatas, trata datas e normaliza os valores para BRL."""

    # Trabalha sobre uma cópia para não modificar o DataFrame original.
    df_limpo = df.copy()

    # Remove operações duplicadas mantendo a primeira ocorrência de cada ID.
    df_limpo = df_limpo.drop_duplicates(
        subset=["id"],
        keep="first"
    )

    # Datas inválidas ou ausentes são convertidas para NaT.
    # A operação é mantida, pois ainda contribui para análises que não dependem da data.
    df_limpo["data"] = pd.to_datetime(
        df_limpo["data"],
        errors="coerce"
    )

    # Preserva o valor original e cria uma coluna normalizada em BRL.
    # Operações em USD utilizam a taxa fornecida no próprio arquivo.
    df_limpo["valor_brl"] = np.where(
        df_limpo["moeda"] == "USD",
        df_limpo["valor"] * taxa_cambio,
        df_limpo["valor"]
    )

    return df_limpo

def aplicar_regras(df: pd.DataFrame) -> pd.DataFrame:
    """Aplica as regras determinísticas de fracionamento e valor atípico."""

    resultado = df.copy()

    # Regra 1 — Fracionamento
    # Agrupa as operações por cliente e data para calcular as métricas
    # necessárias sem delegar cálculos à LLM.
    agrupado_dia = (
        resultado.dropna(subset=["data"])
        .groupby(["cliente_id", "data"])
        .agg(
            qtd_operacoes=("id", "count"),
            soma_valores=("valor_brl", "sum"),
            maior_operacao=("valor_brl", "max"),
        )
        .reset_index()
    )

    # Um grupo é sinalizado quando:
    # - possui pelo menos 3 operações;
    # - soma mais de R$ 50 mil;
    # - nenhuma operação individual atinge R$ 20 mil.
    agrupado_dia["flag_fracionamento"] = (
        (agrupado_dia["qtd_operacoes"] >= 3)
        & (agrupado_dia["soma_valores"] > 50000)
        & (agrupado_dia["maior_operacao"] < 20000)
    )

    # Leva a sinalização calculada por dia de volta para cada operação.
    resultado = resultado.merge(
        agrupado_dia[
            ["cliente_id", "data", "flag_fracionamento"]
        ],
        on=["cliente_id", "data"],
        how="left",
    )

    # Operações sem data não participam da regra temporal e,
    # portanto, recebem False em vez de permanecerem como valor ausente.
    resultado["flag_fracionamento"] = (
        resultado["flag_fracionamento"]
        .fillna(False)
        .astype(bool)
    )

    # Regra 2 — Valor atípico
    # transform() mantém uma métrica por cliente em cada linha do DataFrame.
    resultado["qtd_operacoes_cliente"] = (
        resultado.groupby("cliente_id")["id"]
        .transform("count")
    )

    resultado["mediana_cliente"] = (
        resultado.groupby("cliente_id")["valor_brl"]
        .transform("median")
    )

    # A regra só se aplica a clientes com pelo menos 4 operações.
    resultado["flag_valor_atipico"] = (
        (resultado["qtd_operacoes_cliente"] >= 4)
        & (
            resultado["valor_brl"]
            > 5 * resultado["mediana_cliente"]
        )
    )

    return resultado

if __name__ == "__main__":
    # Carrega os dados do Nível 2.
    df, taxa_cambio = carregar_dados(
        "../dados/dados_nivel_2.json"
    )

    # Aplica o mesmo tratamento definido no Nível 1.
    df_limpo = limpar_dados(df, taxa_cambio)

    # Aplica as duas regras determinísticas sobre os dados tratados.
    df_regras = aplicar_regras(df_limpo)

    # Exibe informações básicas para validar a execução.
    print(f"Operações brutas: {len(df)}")
    print(f"Operações após limpeza: {len(df_limpo)}")
    print(f"Clientes únicos: {df_limpo['cliente_id'].nunique()}")

    print(
        f"Operações associadas a fracionamento: "
        f"{df_regras['flag_fracionamento'].sum()}"
    )

    print(
        f"Operações com valor atípico: "
        f"{df_regras['flag_valor_atipico'].sum()}"
    )