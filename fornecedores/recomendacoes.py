"""Recomendações de economia e renegociação com fornecedores.

Consome os `alertas` que o `motor_analise` já calculou (estouro de
orçamento/histórico por categoria) e sugere ações — em vez de recalcular
variação e severidade do zero. A lógica de "qual ação sugerir por tipo de
gasto" é adaptada de `sugerir_recomendacao()` em
`fornecedores/analisador_balancete_standalone.py` (João Thiago Peixoto
Luzine), só que aqui mapeada pelas categorias padronizadas do contrato
(`mercadorias`, `energia`, `aluguel`, `folha`, `transporte`, `servicos`,
`outros`) em vez de busca por palavra-chave em texto livre — já que o
motor entrega a categoria pronta, não precisamos adivinhar de novo.

`economia estimada` (ver docs/CONTRATO_DADOS.md, seção 4) é aproximada
aqui como o quanto a categoria gastou acima da referência (orçamento ou
histórico) — ou seja, "se voltar ao patamar de referência, é
aproximadamente isso que economiza". Não há uma base de fornecedores
alternativos cadastrada ainda; a ação recomendada aponta o que fazer
(cotar, renegociar etc.), não um nome de fornecedor concreto.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from motor_analise import Alerta

_ACOES_POR_CATEGORIA: dict[str, tuple[str, ...]] = {
    "mercadorias": (
        "Cotar preços com pelo menos 2-3 fornecedores alternativos.",
        "Negociar prazos de pagamento e descontos por volume com o fornecedor atual.",
    ),
    "energia": (
        "Avaliar migração para mercado livre de energia ou fontes alternativas.",
        "Auditar consumo e identificar equipamentos ineficientes.",
    ),
    "aluguel": ("Renegociar valor de locação ou avaliar espaços alternativos.",),
    "folha": ("Revisar estrutura de cargos, horas extras e benefícios.",),
    "transporte": (
        "Cotar frete com transportadoras alternativas.",
        "Avaliar consolidação de cargas para reduzir custo por entrega.",
    ),
    "servicos": ("Revisar contrato de prestação de serviço e buscar propostas concorrentes.",),
    "outros": ("Investigar causa do aumento e buscar alternativas de redução de custo.",),
}

_PREFIXO_PRIORIDADE = {
    "critica": "PRIORIDADE CRÍTICA: ação imediata recomendada.",
    "alta": "PRIORIDADE ALTA: ação imediata recomendada.",
    "media": "Prioridade média: monitorar de perto no próximo período.",
}

COLUNAS_RECOMENDACOES = [
    "fornecedor",
    "categoria",
    "severidade",
    "acao_recomendada",
    "economia_estimada",
]


def _acoes_por_categoria(categoria: str, severidade: str) -> str:
    acoes = list(_ACOES_POR_CATEGORIA.get(categoria, _ACOES_POR_CATEGORIA["outros"]))
    prefixo = _PREFIXO_PRIORIDADE.get(severidade)
    if prefixo:
        acoes.insert(0, prefixo)
    return " | ".join(acoes)


def _fornecedor_principal(lancamentos: Optional[pd.DataFrame], categoria: str) -> Optional[str]:
    """Fornecedor com maior gasto na categoria do alerta, se houver lançamentos disponíveis."""
    if lancamentos is None or lancamentos.empty:
        return None
    if not {"categoria", "fornecedor", "valor"}.issubset(lancamentos.columns):
        return None

    despesas = lancamentos
    if "tipo" in despesas.columns:
        despesas = despesas[despesas["tipo"] == "despesa"]

    gasto_por_fornecedor = despesas.loc[despesas["categoria"] == categoria].groupby("fornecedor")["valor"].sum()
    if gasto_por_fornecedor.empty:
        return None
    return str(gasto_por_fornecedor.idxmax())


def gerar_recomendacoes(
    alertas: list[Alerta],
    lancamentos: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Gera uma recomendação por alerta (categoria com estouro de orçamento/histórico).

    Args:
        alertas: `resultado.alertas` do motor de análise financeira.
        lancamentos: DataFrame de lançamentos do período (opcional). Quando
            informado, usa-se para apontar o fornecedor de maior gasto
            dentro de cada categoria alertada; sem ele, a linha usa a
            categoria no lugar do fornecedor.

    Returns:
        DataFrame com colunas `COLUNAS_RECOMENDACOES`, uma linha por
        alerta, ordenado por severidade (mais grave primeiro — os
        alertas já chegam nessa ordem do motor).
    """
    linhas = []
    for alerta in alertas:
        economia_estimada = round(max(alerta.valor_atual - alerta.valor_referencia, 0.0), 2)
        fornecedor = alerta.fornecedor or _fornecedor_principal(lancamentos, alerta.categoria) or alerta.categoria
        linhas.append(
            {
                "fornecedor": fornecedor,
                "categoria": alerta.categoria,
                "severidade": alerta.severidade,
                "acao_recomendada": _acoes_por_categoria(alerta.categoria, alerta.severidade),
                "economia_estimada": economia_estimada,
            }
        )
    return pd.DataFrame(linhas, columns=COLUNAS_RECOMENDACOES)
