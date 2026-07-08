"""Geração de alertas por severidade a partir das variações calculadas."""

from __future__ import annotations

import pandas as pd

from .modelos import Alerta

# Limiares padrão de variação percentual (acima da referência) para cada
# severidade. Configuráveis via `ConfiguracaoAnalise.limiares_severidade`.
LIMIARES_SEVERIDADE_PADRAO = {
    "baixa": 10.0,
    "media": 20.0,
    "alta": 35.0,
    "critica": 50.0,
}

_MENSAGENS_TIPO = {
    "orcamento": "estourou o orçamento",
    "historico": "aumentou frente ao período anterior",
}


def _classificar_severidade(variacao_percentual: float, limiares: dict[str, float]) -> str | None:
    severidade = None
    for nivel in ("baixa", "media", "alta", "critica"):
        if variacao_percentual >= limiares[nivel]:
            severidade = nivel
    return severidade


def gerar_alertas(
    variacoes: pd.DataFrame,
    limiares_severidade: dict[str, float] | None = None,
) -> list[Alerta]:
    """Converte cada linha de `variacoes` que ultrapassa o limiar mínimo em um Alerta.

    Só gera alerta para gasto acima do esperado (variação percentual
    positiva e acima do menor limiar configurado); economia/queda de gasto
    não gera alerta.
    """
    limiares = limiares_severidade or LIMIARES_SEVERIDADE_PADRAO
    alertas: list[Alerta] = []

    for _, linha in variacoes.iterrows():
        severidade = _classificar_severidade(linha["variacao_percentual"], limiares)
        if severidade is None:
            continue

        tipo = "estouro_orcamento" if linha["base_comparacao"] == "orcamento" else "variacao_historica"
        descricao_base = _MENSAGENS_TIPO[linha["base_comparacao"]]
        mensagem = (
            f"Categoria '{linha['categoria']}' {descricao_base}: "
            f"R$ {linha['valor_atual']:.2f} vs R$ {linha['valor_referencia']:.2f} "
            f"({linha['variacao_percentual']:+.1f}%)."
        )

        alertas.append(
            Alerta(
                categoria=linha["categoria"],
                tipo=tipo,
                severidade=severidade,
                valor_atual=linha["valor_atual"],
                valor_referencia=linha["valor_referencia"],
                variacao_percentual=linha["variacao_percentual"],
                mensagem=mensagem,
            )
        )

    ordem_severidade = {s: i for i, s in enumerate(("critica", "alta", "media", "baixa"))}
    alertas.sort(key=lambda a: (ordem_severidade[a.severidade], -a.variacao_percentual))
    return alertas
