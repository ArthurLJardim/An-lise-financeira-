# -*- coding: utf-8 -*-
"""
graficos.py
===========
Geração de gráficos em PNG com matplotlib: ranking de fornecedores,
distribuição por categoria e (quando aplicável) evolução entre períodos.

Os gráficos são opcionais — se o matplotlib não estiver instalado no
ambiente do usuário, o restante do programa continua funcionando
normalmente (ver `main.py`), só sem essa saída específica.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from analisador import ResultadoAnalise
from analisador import VariacaoFornecedor

try:
    import matplotlib
    matplotlib.use("Agg")  # backend sem interface gráfica (servidor/headless)
    import matplotlib.pyplot as plt
    import matplotlib.ticker as mticker
    MATPLOTLIB_DISPONIVEL = True
except ImportError:
    MATPLOTLIB_DISPONIVEL = False

# Paleta simples e consistente entre os gráficos
_COR_PRINCIPAL = "#2563EB"
_COR_SECUNDARIA = "#F59E0B"
_COR_ALERTA = "#DC2626"
_PALETA_CATEGORIAS = [
    "#2563EB", "#F59E0B", "#10B981", "#8B5CF6", "#EC4899",
    "#14B8A6", "#F97316", "#6366F1", "#84CC16", "#EF4444",
]


def _formatador_reais(valor, pos=None) -> str:
    return f"R$ {valor:,.0f}".replace(",", ".")


class GeradorGraficos:
    """Produz arquivos .png a partir do resultado da análise."""

    def __init__(self, pasta_saida: str):
        self.pasta_saida = Path(pasta_saida)
        self.pasta_saida.mkdir(parents=True, exist_ok=True)

    @property
    def disponivel(self) -> bool:
        return MATPLOTLIB_DISPONIVEL

    def gerar_todos(
        self,
        analise: ResultadoAnalise,
        variacoes: Optional[List[VariacaoFornecedor]] = None,
    ) -> List[str]:
        """Gera todos os gráficos aplicáveis e devolve a lista de caminhos
        dos arquivos criados. Silenciosamente não faz nada se matplotlib
        não estiver disponível ou não houver fornecedores."""
        if not MATPLOTLIB_DISPONIVEL or not analise.fornecedores_ordenados:
            return []

        arquivos = [
            self._grafico_ranking_fornecedores(analise),
            self._grafico_categorias(analise),
        ]
        if variacoes:
            grafico_variacao = self._grafico_variacao_periodos(variacoes)
            if grafico_variacao:
                arquivos.append(grafico_variacao)

        return [a for a in arquivos if a]

    # ------------------------------------------------------------------

    def _grafico_ranking_fornecedores(self, analise: ResultadoAnalise) -> str:
        top = analise.fornecedores_ordenados[:10][::-1]  # menor->maior p/ barh
        nomes = [f.nome_curto for f in top]
        valores = [f.movimentacao_periodo for f in top]
        cores = [
            _COR_ALERTA if f.classe_abc and f.classe_abc.value == "A"
            else (_COR_SECUNDARIA if f.classe_abc and f.classe_abc.value == "B"
                  else _COR_PRINCIPAL)
            for f in top
        ]

        fig, ax = plt.subplots(figsize=(9, max(3, 0.5 * len(top) + 1)))
        barras = ax.barh(nomes, valores, color=cores)
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(_formatador_reais))
        ax.set_title("Ranking de Fornecedores por Movimentação no Período",
                      fontsize=13, fontweight="bold", loc="left")
        ax.spines[["top", "right"]].set_visible(False)

        for barra, valor in zip(barras, valores):
            ax.text(
                barra.get_width() + (max(valores) * 0.01 if valores else 0),
                barra.get_y() + barra.get_height() / 2,
                _formatador_reais(valor),
                va="center", fontsize=9,
            )

        fig.tight_layout()
        caminho = self.pasta_saida / "ranking_fornecedores.png"
        fig.savefig(caminho, dpi=150)
        plt.close(fig)
        return str(caminho)

    def _grafico_categorias(self, analise: ResultadoAnalise) -> str:
        resumo = analise.resumo_por_categoria
        rotulos = [f"{c.categoria}\n({c.percentual_do_total:.1f}%)" for c in resumo]
        valores = [c.total for c in resumo]
        cores = _PALETA_CATEGORIAS[: len(valores)]

        fig, ax = plt.subplots(figsize=(8, 7))
        ax.pie(
            valores,
            labels=rotulos,
            colors=cores,
            autopct=lambda p: _formatador_reais(p / 100 * sum(valores)),
            pctdistance=0.75,
            startangle=90,
            textprops={"fontsize": 9},
        )
        ax.set_title(
            "Distribuição de Gastos por Categoria",
            fontsize=13, fontweight="bold",
        )
        fig.tight_layout()
        caminho = self.pasta_saida / "categorias.png"
        fig.savefig(caminho, dpi=150)
        plt.close(fig)
        return str(caminho)

    def _grafico_variacao_periodos(
        self, variacoes: List[VariacaoFornecedor]
    ) -> Optional[str]:
        relevantes = [v for v in variacoes if v.variacao_absoluta != 0][:10]
        if not relevantes:
            return None

        nomes = [v.nome[:35] for v in relevantes][::-1]
        deltas = [v.variacao_absoluta for v in relevantes][::-1]
        cores = [_COR_ALERTA if d > 0 else _COR_PRINCIPAL for d in deltas]

        fig, ax = plt.subplots(figsize=(9, max(3, 0.5 * len(relevantes) + 1)))
        ax.barh(nomes, deltas, color=cores)
        ax.axvline(0, color="#333333", linewidth=0.8)
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(_formatador_reais))
        ax.set_title(
            "Variação de Movimentação entre Períodos (R$)",
            fontsize=13, fontweight="bold", loc="left",
        )
        ax.spines[["top", "right"]].set_visible(False)
        fig.tight_layout()

        caminho = self.pasta_saida / "variacao_periodos.png"
        fig.savefig(caminho, dpi=150)
        plt.close(fig)
        return str(caminho)
