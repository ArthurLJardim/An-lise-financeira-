# -*- coding: utf-8 -*-
"""
relatorio_console.py
=====================
Gera um relatório legível diretamente no terminal, sem depender de
bibliotecas externas de formatação (como `rich`) — só Python padrão. Isso
mantém o projeto fácil de instalar (menos dependências) e funcional em
qualquer terminal, inclusive os mais simples.

Usa códigos ANSI para cor quando o terminal parece suportá-los, e cai
graciosamente para texto simples quando não (ex.: saída redirecionada
para um arquivo).
"""

from __future__ import annotations

import sys
from typing import List, Optional

from analisador import ResultadoAnalise
from modelos import ClasseABC
from recomendador import Prioridade, Recomendacao
from utils import formatar_moeda as _fmt_moeda

_SUPORTA_COR = sys.stdout.isatty()


def _cor(texto: str, codigo: str) -> str:
    if not _SUPORTA_COR:
        return texto
    return f"\033[{codigo}m{texto}\033[0m"


def _negrito(t: str) -> str:
    return _cor(t, "1")


def _verde(t: str) -> str:
    return _cor(t, "32")


def _amarelo(t: str) -> str:
    return _cor(t, "33")


def _vermelho(t: str) -> str:
    return _cor(t, "31")


def _cinza(t: str) -> str:
    return _cor(t, "90")


def _cor_prioridade(prioridade: Prioridade) -> str:
    return {
        Prioridade.ALTA: _vermelho,
        Prioridade.MEDIA: _amarelo,
        Prioridade.BAIXA: _cinza,
    }[prioridade]


def _linha(caractere: str = "─", largura: int = 78) -> str:
    return caractere * largura


def _titulo_secao(texto: str) -> str:
    return f"\n{_negrito(texto.upper())}\n{_linha('─')}"


class RelatorioConsole:
    """Monta e imprime o relatório textual completo no terminal."""

    def __init__(self, largura: int = 78):
        self.largura = largura

    def imprimir(
        self,
        analise: ResultadoAnalise,
        recomendacoes: List[Recomendacao],
        top_n: int = 15,
    ) -> None:
        linhas = self._montar(analise, recomendacoes, top_n)
        print("\n".join(linhas))

    def montar_texto(
        self,
        analise: ResultadoAnalise,
        recomendacoes: List[Recomendacao],
        top_n: int = 15,
    ) -> str:
        """Igual a `imprimir`, mas devolve a string em vez de imprimir —
        útil para salvar o relatório também em um arquivo .txt."""
        return "\n".join(self._montar(analise, recomendacoes, top_n))

    # ------------------------------------------------------------------

    def _montar(
        self,
        analise: ResultadoAnalise,
        recomendacoes: List[Recomendacao],
        top_n: int,
    ) -> List[str]:
        L: List[str] = []
        empresa = analise.balancete.empresa

        L.append(_linha("═"))
        L.append(_negrito("  ANALISADOR INTELIGENTE DE BALANCETES").center(self.largura))
        L.append(_linha("═"))
        L.append(f"Empresa : {empresa.nome}")
        if empresa.cnpj:
            L.append(f"CNPJ    : {empresa.cnpj}")
        L.append(f"Período : {empresa.periodo_formatado}")
        L.append(f"Arquivo : {analise.balancete.arquivo_origem}")

        L.extend(self._secao_indicadores(analise))
        L.extend(self._secao_fornecedores(analise, top_n))
        L.extend(self._secao_categorias(analise))
        L.extend(self._secao_recomendacoes(recomendacoes))

        L.append("")
        L.append(_linha("═"))
        return L

    def _secao_indicadores(self, analise: ResultadoAnalise) -> List[str]:
        i = analise.indicadores
        L = [_titulo_secao("Indicadores Financeiros")]

        linhas_dados = [
            ("Ativo Circulante", _fmt_moeda(i.ativo_circulante)),
            ("Passivo Circulante", _fmt_moeda(i.passivo_circulante)),
            ("Caixa Disponível", _fmt_moeda(i.caixa)),
            ("Estoque", _fmt_moeda(i.estoque)),
            ("Patrimônio Líquido", _fmt_moeda(i.patrimonio_liquido)),
            ("Receita Bruta do Período", _fmt_moeda(i.receita_bruta)),
            ("Capital de Giro", _fmt_moeda(i.capital_de_giro)),
        ]
        for rotulo, valor in linhas_dados:
            L.append(f"  {rotulo:<28} {valor:>20}")

        liquidez = i.liquidez_corrente
        if liquidez is not None:
            marcador = _verde("saudável") if liquidez >= 1.5 else (
                _amarelo("apertada") if liquidez >= 1 else _vermelho("crítica")
            )
            L.append(f"  {'Liquidez Corrente':<28} {liquidez:>19.2f}x  ({marcador})")

        margem = i.margem_liquida
        if margem is not None:
            L.append(f"  {'Margem Líquida':<28} {margem:>19.1f}%")

        return L

    def _secao_fornecedores(
        self, analise: ResultadoAnalise, top_n: int
    ) -> List[str]:
        L = [_titulo_secao(
            f"Ranking de Fornecedores "
            f"(por movimentação no período, top {top_n})"
        )]

        if not analise.fornecedores_ordenados:
            L.append("  Nenhum fornecedor com saldo identificado neste período.")
            return L

        L.append(
            f"  {'#':<3}{'Fornecedor':<40}{'Movimentação':>16}"
            f"{'%':>8}{'Acum%':>8}{'ABC':>5}"
        )
        L.append(f"  {_linha('-', 80)}")
        for f in analise.fornecedores_ordenados[:top_n]:
            classe = f.classe_abc.value if f.classe_abc else "-"
            cor_classe = {
                ClasseABC.A: _vermelho,
                ClasseABC.B: _amarelo,
                ClasseABC.C: _cinza,
            }.get(f.classe_abc, lambda t: t)
            L.append(
                f"  {f.ranking:<3}{f.nome_curto:<40}"
                f"{_fmt_moeda(f.movimentacao_periodo):>16}"
                f"{f.percentual_do_total:>7.1f}%"
                f"{f.percentual_acumulado:>7.1f}%"
                f"{cor_classe(classe):>5}"
            )

        L.append(f"  {_linha('-', 80)}")
        L.append(
            f"  {'TOTAL':<43}{_fmt_moeda(analise.total_movimentado_fornecedores):>16}"
        )
        L.append("")
        L.append(
            f"  Saldo em aberto total (a pagar na data-base): "
            f"{_fmt_moeda(analise.total_saldo_em_aberto)}"
        )
        L.append(
            f"  Índice de concentração (HHI): {analise.indice_hhi:,.0f} / 10.000"
        )
        return L

    def _secao_categorias(self, analise: ResultadoAnalise) -> List[str]:
        L = [_titulo_secao("Gastos por Categoria")]
        if not analise.resumo_por_categoria:
            L.append("  Sem dados suficientes.")
            return L

        maior = max((c.total for c in analise.resumo_por_categoria), default=1) or 1
        for c in analise.resumo_por_categoria:
            largura_barra = int((c.total / maior) * 30)
            barra = "█" * largura_barra
            L.append(
                f"  {c.categoria:<40}{_fmt_moeda(c.total):>14} "
                f"({c.quantidade_fornecedores}) {barra}"
            )
        return L

    def _secao_recomendacoes(
        self, recomendacoes: List[Recomendacao]
    ) -> List[str]:
        L = [_titulo_secao(f"Recomendações ({len(recomendacoes)})")]
        if not recomendacoes:
            L.append("  Nenhuma recomendação gerada.")
            return L

        for idx, r in enumerate(recomendacoes, start=1):
            cor = _cor_prioridade(r.prioridade)
            L.append(
                f"\n  {idx}. {cor('[' + r.prioridade.value.upper() + ']')} "
                f"{_negrito(r.titulo)}  {_cinza('(' + r.categoria + ')')}"
            )
            L.append(f"     {r.descricao}")
        return L
