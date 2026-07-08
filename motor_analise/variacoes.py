"""Cálculo de variações de gasto por categoria vs orçamento e/ou histórico."""

from __future__ import annotations

from typing import Optional

import pandas as pd


def _gasto_por_categoria(df: pd.DataFrame) -> pd.Series:
    return df.groupby("categoria")["valor"].sum()


def _montar_linha(categoria: str, atual: float, referencia: float, base: str) -> dict:
    variacao_absoluta = atual - referencia
    if referencia > 0:
        variacao_percentual = (variacao_absoluta / referencia) * 100
    elif atual > 0:
        variacao_percentual = 100.0  # gasto novo, sem referência anterior
    else:
        variacao_percentual = 0.0
    return {
        "categoria": categoria,
        "valor_atual": round(atual, 2),
        "valor_referencia": round(referencia, 2),
        "variacao_absoluta": round(variacao_absoluta, 2),
        "variacao_percentual": round(variacao_percentual, 2),
        "base_comparacao": base,
    }


def calcular_variacoes(
    df_atual: pd.DataFrame,
    df_orcamento: Optional[pd.DataFrame] = None,
    df_historico: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Compara o gasto por categoria do período atual contra orçamento e/ou histórico.

    Quando as duas bases são informadas, uma linha é gerada para cada uma
    (uma categoria pode aparecer duas vezes: uma vs orçamento, outra vs
    histórico). Quando nenhuma é informada, retorna um DataFrame vazio com
    as colunas esperadas — o motor continua funcionando (resumo/rankings),
    só não há variações/alertas.
    """
    colunas = [
        "categoria",
        "valor_atual",
        "valor_referencia",
        "variacao_absoluta",
        "variacao_percentual",
        "base_comparacao",
    ]

    if df_orcamento is None and df_historico is None:
        return pd.DataFrame(columns=colunas)

    gasto_atual = _gasto_por_categoria(df_atual)
    linhas: list[dict] = []

    if df_orcamento is not None:
        limites = df_orcamento.set_index("categoria")["limite"]
        categorias = sorted(set(gasto_atual.index) | set(limites.index))
        for categoria in categorias:
            atual = float(gasto_atual.get(categoria, 0.0))
            limite = float(limites.get(categoria, 0.0))
            linhas.append(_montar_linha(categoria, atual, limite, "orcamento"))

    if df_historico is not None:
        gasto_historico = _gasto_por_categoria(df_historico)
        categorias = sorted(set(gasto_atual.index) | set(gasto_historico.index))
        for categoria in categorias:
            atual = float(gasto_atual.get(categoria, 0.0))
            referencia = float(gasto_historico.get(categoria, 0.0))
            linhas.append(_montar_linha(categoria, atual, referencia, "historico"))

    return pd.DataFrame(linhas, columns=colunas)
