"""Cálculo dos cards de resumo exibidos na interface."""

from __future__ import annotations

from typing import Any

import pandas as pd

from .modelos import Alerta


def calcular_resumo(
    df_atual: pd.DataFrame,
    variacoes: pd.DataFrame,
    alertas: list[Alerta],
    periodo: str,
) -> dict[str, Any]:
    """Monta o dicionário usado pelos cards de resumo da interface (Miguel).

    Não inclui "economia estimada": esse valor é calculado pelo módulo de
    recomendações de fornecedores (João Thiago) a partir dos dados que este
    motor expõe (rankings e variações).
    """
    gasto_total = float(df_atual["valor"].sum())

    maior_aumento = None
    if not variacoes.empty:
        candidatos = variacoes[variacoes["variacao_percentual"] > 0]
        if not candidatos.empty:
            linha = candidatos.loc[candidatos["variacao_percentual"].idxmax()]
            maior_aumento = {
                "categoria": linha["categoria"],
                "variacao_percentual": round(float(linha["variacao_percentual"]), 2),
                "valor_atual": round(float(linha["valor_atual"]), 2),
                "valor_referencia": round(float(linha["valor_referencia"]), 2),
            }

    contagem_severidade = {nivel: 0 for nivel in ("baixa", "media", "alta", "critica")}
    for alerta in alertas:
        contagem_severidade[alerta.severidade] += 1

    return {
        "periodo": periodo,
        "gasto_total": round(gasto_total, 2),
        "quantidade_lancamentos": int(len(df_atual)),
        "maior_aumento": maior_aumento,
        "numero_alertas": len(alertas),
        "alertas_por_severidade": contagem_severidade,
    }
