"""Cálculo de rankings de gastos a partir dos lançamentos já validados."""

from __future__ import annotations

import pandas as pd


def _ranking(df: pd.DataFrame, coluna_agrupamento: str) -> pd.DataFrame:
    agrupado = (
        df.groupby(coluna_agrupamento, as_index=False)["valor"]
        .agg(total="sum", quantidade="count")
        .sort_values("total", ascending=False)
        .reset_index(drop=True)
    )
    total_geral = agrupado["total"].sum()
    agrupado["percentual_do_total"] = (
        (agrupado["total"] / total_geral * 100).round(2) if total_geral else 0.0
    )
    agrupado.insert(0, "posicao", agrupado.index + 1)
    return agrupado


def calcular_rankings(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Gera rankings de maiores gastos por categoria, fornecedor e produto.

    `df` deve ser um DataFrame de lançamentos já normalizado por
    `modelos.validar_lancamentos`. A chave "por_produto" só aparece no
    resultado se a coluna `produto` estiver presente na entrada.
    """
    rankings = {
        "por_categoria": _ranking(df, "categoria"),
        "por_fornecedor": _ranking(df, "fornecedor"),
    }
    if "produto" in df.columns:
        rankings["por_produto"] = _ranking(df, "produto")
    return rankings
