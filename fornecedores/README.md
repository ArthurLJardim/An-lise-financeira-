# -*- coding: utf-8 -*-
"""
analisador.py
=============
Camada de cálculo: transforma um `Balancete` (já com fornecedores
categorizados) em métricas prontas para virar relatório — ranking,
curva ABC, índice de concentração, indicadores financeiros gerais e,
quando há mais de um período disponível, uma comparação entre eles.

Nenhuma função aqui produz texto ou formatação; a ideia é manter os
números "crus" (floats, listas, dicts) para que tanto o relatório de
console quanto o Excel consumam a mesma fonte de verdade.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from modelos import Balancete, ClasseABC, Fornecedor
from categorizador import categorizar_lista


@dataclass
class ResumoCategoria:
    categoria: str
    total: float = 0.0
    quantidade_fornecedores: int = 0
    percentual_do_total: float = 0.0
    fornecedores: List[Fornecedor] = field(default_factory=list)


@dataclass
class IndicadoresFinanceiros:
    ativo_circulante: float = 0.0
    passivo_circulante: float = 0.0
    caixa: float = 0.0
    estoque: float = 0.0
    patrimonio_liquido: float = 0.0
    receita_bruta: float = 0.0
    resultado_liquido: float = 0.0

    @property
    def capital_de_giro(self) -> float:
        return self.ativo_circulante - self.passivo_circulante

    @property
    def liquidez_corrente(self) -> Optional[float]:
        if self.passivo_circulante == 0:
            return None
        return self.ativo_circulante / self.passivo_circulante

    @property
    def grau_endividamento(self) -> Optional[float]:
        """Passivo Circulante sobre Patrimônio Líquido, em %."""
        if self.patrimonio_liquido == 0:
            return None
        return (self.passivo_circulante / self.patrimonio_liquido) * 100

    @property
    def margem_liquida(self) -> Optional[float]:
        """Resultado líquido sobre receita bruta, em %."""
        if self.receita_bruta == 0:
            return None
        return (self.resultado_liquido / self.receita_bruta) * 100

    @property
    def participacao_caixa_no_ativo(self) -> Optional[float]:
        if self.ativo_circulante == 0:
            return None
        return (self.caixa / self.ativo_circulante) * 100


@dataclass
class ResultadoAnalise:
    balancete: Balancete
    indicadores: IndicadoresFinanceiros
    fornecedores_ordenados: List[Fornecedor]
    resumo_por_categoria: List[ResumoCategoria]
    total_movimentado_fornecedores: float
    total_saldo_em_aberto: float
    indice_hhi: float
    top_3_percentual: float
    maior_fornecedor_percentual: float


class AnalisadorFinanceiro:
    """Calcula indicadores, ranking, curva ABC e análise por categoria."""

    def analisar(self, balancete: Balancete) -> ResultadoAnalise:
        categorizar_lista(balancete.fornecedores)

        indicadores = self._calcular_indicadores(balancete)
        fornecedores_ordenados = self._ranquear_e_classificar_abc(
            balancete.fornecedores
        )
        resumo_categorias = self._resumir_por_categoria(fornecedores_ordenados)

        total_movimentado = sum(
            f.movimentacao_periodo for f in fornecedores_ordenados
        )
        total_saldo_aberto = sum(
            f.saldo_em_aberto for f in fornecedores_ordenados
        )
        hhi = self._indice_hhi(fornecedores_ordenados)

        maior_percentual = (
            fornecedores_ordenados[0].percentual_do_total
            if fornecedores_ordenados else 0.0
        )
        top3_percentual = sum(
            f.percentual_do_total for f in fornecedores_ordenados[:3]
        )

        return ResultadoAnalise(
            balancete=balancete,
            indicadores=indicadores,
            fornecedores_ordenados=fornecedores_ordenados,
            resumo_por_categoria=resumo_categorias,
            total_movimentado_fornecedores=total_movimentado,
            total_saldo_em_aberto=total_saldo_aberto,
            indice_hhi=hhi,
            top_3_percentual=top3_percentual,
            maior_fornecedor_percentual=maior_percentual,
        )

    # ------------------------------------------------------------------

    @staticmethod
    def _calcular_indicadores(balancete: Balancete) -> IndicadoresFinanceiros:
        return IndicadoresFinanceiros(
            ativo_circulante=balancete.valor_conta("ATIVO", "CIRCULANTE"),
            passivo_circulante=balancete.valor_conta("PASSIVO", "CIRCULANTE"),
            caixa=(
                balancete.valor_conta("CAIXA", "GERAL")
                or balancete.valor_conta("DISPONIVEL")
                or balancete.valor_conta("DISPONÍVEL")
            ),
            estoque=balancete.valor_conta("ESTOQUE"),
            patrimonio_liquido=(
                balancete.valor_conta("PATRIMONIO", "LIQUIDO")
                or balancete.valor_conta("PATRIMÔNIO", "LÍQUIDO")
            ),
            receita_bruta=(
                balancete.valor_conta("RECEITA", "BRUTA")
                or balancete.valor_conta("RECEITA", "PRESTACAO")
                or balancete.valor_conta("RECEITA", "PRESTAÇÃO")
            ),
            resultado_liquido=(
                balancete.valor_conta("RESULTADO", "LIQUIDO", "PERIODO")
                or balancete.valor_conta("RESULTADO", "LÍQUIDO", "PERÍODO")
                or balancete.valor_conta("RESULTADO", "BRUTO")
            ),
        )

    @staticmethod
    def _ranquear_e_classificar_abc(
        fornecedores: List[Fornecedor],
    ) -> List[Fornecedor]:
        """
        Ordena fornecedores por movimentação no período (do maior para o
        menor) e aplica a clássica curva ABC (regra de Pareto):

            Classe A -> fornecedores que, somados, respondem por até 80%
                        do total (os poucos que concentram a maior parte
                        do gasto — prioridade máxima de negociação).
            Classe B -> a faixa seguinte, até 95% acumulado.
            Classe C -> o restante (cauda longa, geralmente muitos
                        fornecedores de baixo valor individual).
        """
        ordenados = sorted(
            fornecedores, key=lambda f: f.movimentacao_periodo, reverse=True
        )
        total = sum(f.movimentacao_periodo for f in ordenados)

        acumulado = 0.0
        for i, fornecedor in enumerate(ordenados, start=1):
            fornecedor.ranking = i
            fornecedor.percentual_do_total = (
                (fornecedor.movimentacao_periodo / total * 100) if total else 0.0
            )
            acumulado += fornecedor.percentual_do_total
            fornecedor.percentual_acumulado = acumulado

            if acumulado <= 80.0 or i == 1:
                fornecedor.classe_abc = ClasseABC.A
            elif acumulado <= 95.0:
                fornecedor.classe_abc = ClasseABC.B
            else:
                fornecedor.classe_abc = ClasseABC.C

        return ordenados

    @staticmethod
    def _resumir_por_categoria(
        fornecedores: List[Fornecedor],
    ) -> List[ResumoCategoria]:
        mapa: Dict[str, ResumoCategoria] = {}
        total_geral = sum(f.movimentacao_periodo for f in fornecedores)

        for fornecedor in fornecedores:
            resumo = mapa.setdefault(
                fornecedor.categoria, ResumoCategoria(categoria=fornecedor.categoria)
            )
            resumo.total += fornecedor.movimentacao_periodo
            resumo.quantidade_fornecedores += 1
            resumo.fornecedores.append(fornecedor)

        for resumo in mapa.values():
            resumo.percentual_do_total = (
                (resumo.total / total_geral * 100) if total_geral else 0.0
            )

        return sorted(mapa.values(), key=lambda r: r.total, reverse=True)

    @staticmethod
    def _indice_hhi(fornecedores: List[Fornecedor]) -> float:
        """
        Índice Herfindahl-Hirschman aplicado à base de fornecedores: soma
        do quadrado da participação percentual de cada um. Varia de perto
        de 0 (gasto pulverizado entre muitos fornecedores) a 10.000 (um
        único fornecedor concentra 100% do gasto). É a mesma métrica usada
        por órgãos antitruste para medir concentração de mercado —
        aqui usada "ao contrário": para medir a concentração de
        DEPENDÊNCIA da empresa em relação à sua própria base de
        fornecedores.
        """
        return sum(f.percentual_do_total ** 2 for f in fornecedores)


# --------------------------------------------------------------------------
# Comparação entre períodos (opcional, usada quando o usuário fornece mais
# de um balancete)
# --------------------------------------------------------------------------

@dataclass
class VariacaoFornecedor:
    nome: str
    categoria: str
    valor_periodo_anterior: float
    valor_periodo_atual: float

    @property
    def variacao_absoluta(self) -> float:
        return self.valor_periodo_atual - self.valor_periodo_anterior

    @property
    def variacao_percentual(self) -> Optional[float]:
        if self.valor_periodo_anterior == 0:
            return None  # fornecedor novo — "crescimento infinito" não é útil
        return (self.variacao_absoluta / self.valor_periodo_anterior) * 100

    @property
    def eh_fornecedor_novo(self) -> bool:
        return self.valor_periodo_anterior == 0 and self.valor_periodo_atual > 0

    @property
    def eh_fornecedor_descontinuado(self) -> bool:
        return self.valor_periodo_atual == 0 and self.valor_periodo_anterior > 0


def comparar_periodos(
    analise_anterior: ResultadoAnalise, analise_atual: ResultadoAnalise
) -> List[VariacaoFornecedor]:
    """
    Cruza os fornecedores de dois períodos (mais antigo -> mais recente)
    pelo nome e devolve a variação de movimentação de cada um, incluindo
    fornecedores novos (não existiam antes) e descontinuados (somem no
    período atual). Ordenado pela maior alta em R$ primeiro, o que tende
    a destacar exatamente os pontos que mais merecem atenção.
    """
    por_nome_anterior = {
        f.nome.strip().upper(): f
        for f in analise_anterior.fornecedores_ordenados
    }
    por_nome_atual = {
        f.nome.strip().upper(): f for f in analise_atual.fornecedores_ordenados
    }

    todos_nomes = set(por_nome_anterior) | set(por_nome_atual)
    variacoes = []
    for nome_norm in todos_nomes:
        anterior = por_nome_anterior.get(nome_norm)
        atual = por_nome_atual.get(nome_norm)
        referencia = atual or anterior
        variacoes.append(
            VariacaoFornecedor(
                nome=referencia.nome,
                categoria=referencia.categoria,
                valor_periodo_anterior=anterior.movimentacao_periodo if anterior else 0.0,
                valor_periodo_atual=atual.movimentacao_periodo if atual else 0.0,
            )
        )

    return sorted(variacoes, key=lambda v: v.variacao_absoluta, reverse=True)
