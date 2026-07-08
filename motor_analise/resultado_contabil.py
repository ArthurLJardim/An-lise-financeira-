"""Cálculo do resultado contábil do período (lucro ou prejuízo)."""

from __future__ import annotations

from typing import Any

import pandas as pd


def calcular_resultado_contabil(df: pd.DataFrame) -> dict[str, Any]:
    """Calcula receita total, despesa total e o resultado (lucro/prejuízo) do período.

    `df` deve ser um DataFrame de lançamentos já normalizado por
    `modelos.validar_lancamentos` (precisa da coluna `tipo`, com valores
    "receita" ou "despesa" — lançamentos sem a coluna são tratados como
    despesa pelo próprio `validar_lancamentos`).
    """
    receita_total = float(df.loc[df["tipo"] == "receita", "valor"].sum())
    despesa_total = float(df.loc[df["tipo"] == "despesa", "valor"].sum())
    resultado = receita_total - despesa_total

    if resultado > 0:
        situacao = "lucro"
    elif resultado < 0:
        situacao = "prejuizo"
    else:
        situacao = "equilibrio"

    margem_percentual = (
        round((resultado / receita_total) * 100, 2) if receita_total > 0 else None
    )

    return {
        "receita_total": round(receita_total, 2),
        "despesa_total": round(despesa_total, 2),
        "resultado": round(resultado, 2),
        "situacao": situacao,
        "margem_percentual": margem_percentual,
    }
