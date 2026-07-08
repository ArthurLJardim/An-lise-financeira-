"""Orquestrador do motor de análise financeira.

Ponto de entrada único do módulo: recebe os lançamentos já tratados
(módulo de Eduardo) e devolve um `ResultadoAnalise` pronto para a
interface (Miguel) e para o módulo de recomendações (João Thiago).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from .alertas import LIMIARES_SEVERIDADE_PADRAO, gerar_alertas
from .modelos import ResultadoAnalise, validar_lancamentos, validar_orcamento
from .rankings import calcular_rankings
from .resumo import calcular_resumo
from .variacoes import calcular_variacoes


@dataclass
class ConfiguracaoAnalise:
    """Parâmetros de configuração do motor.

    `limiares_severidade` define, em variação percentual acima da
    referência (orçamento ou histórico), a partir de que ponto cada
    severidade é atingida. Deve conter as quatro chaves em ordem
    crescente: baixa < media < alta < critica.
    """

    limiares_severidade: dict[str, float] = field(
        default_factory=lambda: dict(LIMIARES_SEVERIDADE_PADRAO)
    )

    def __post_init__(self) -> None:
        chaves_esperadas = {"baixa", "media", "alta", "critica"}
        if set(self.limiares_severidade) != chaves_esperadas:
            raise ValueError(
                f"limiares_severidade deve conter exatamente as chaves {chaves_esperadas}"
            )
        valores = [self.limiares_severidade[k] for k in ("baixa", "media", "alta", "critica")]
        if valores != sorted(valores):
            raise ValueError(
                "limiares_severidade deve ser crescente: baixa < media < alta < critica"
            )


class AnaliseFinanceira:
    """Motor de análise financeira: variações, rankings e alertas por severidade."""

    def __init__(self, config: Optional[ConfiguracaoAnalise] = None) -> None:
        self.config = config or ConfiguracaoAnalise()

    def analisar(
        self,
        lancamentos: pd.DataFrame,
        orcamento: Optional[pd.DataFrame] = None,
        historico: Optional[pd.DataFrame] = None,
        periodo: str = "periodo atual",
    ) -> ResultadoAnalise:
        """Executa a análise completa sobre os lançamentos de um período.

        Args:
            lancamentos: DataFrame de lançamentos do período a analisar
                (contrato em docs/CONTRATO_DADOS.md).
            orcamento: DataFrame opcional com limites por categoria.
            historico: DataFrame opcional de lançamentos de um período
                anterior, usado como referência quando não há orçamento
                (ou em conjunto com ele).
            periodo: rótulo livre do período analisado (ex.: "2026-06").

        Returns:
            ResultadoAnalise com resumo, rankings, variações e alertas.
        """
        df_atual = validar_lancamentos(lancamentos)
        df_orcamento = validar_orcamento(orcamento) if orcamento is not None else None
        df_historico = validar_lancamentos(historico) if historico is not None else None

        rankings = calcular_rankings(df_atual)
        variacoes = calcular_variacoes(df_atual, df_orcamento, df_historico)
        alertas = gerar_alertas(variacoes, self.config.limiares_severidade)
        resumo = calcular_resumo(df_atual, variacoes, alertas, periodo)

        return ResultadoAnalise(
            periodo=periodo,
            resumo=resumo,
            variacoes=variacoes,
            rankings=rankings,
            alertas=alertas,
        )
