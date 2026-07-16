# -*- coding: utf-8 -*-
"""
recomendador.py
================
Motor de recomendações baseado em regras. Cada regra observa o resultado
da análise (`ResultadoAnalise`, ver `analisador.py`) e, quando a condição
é satisfeita, produz uma `Recomendacao` com prioridade e categoria.

Propositalmente NÃO é machine learning: é um conjunto de heurísticas
financeiras conhecidas (curva ABC, índice de concentração HHI, liquidez
corrente, capital de giro etc.), documentadas e fáceis de auditar — o que
importa muito mais para o dono de uma empresa do que uma "caixa preta".

Para adicionar uma nova regra, basta escrever um método `_regra_*` que
devolve uma lista de `Recomendacao` (vazia se a regra não se aplicar) e
registrá-lo em `_todas_as_regras`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

from analisador import ResultadoAnalise, VariacaoFornecedor
from utils import formatar_moeda


class Prioridade(str, Enum):
    ALTA = "Alta"
    MEDIA = "Média"
    BAIXA = "Baixa"

    @property
    def peso_ordenacao(self) -> int:
        return {"Alta": 0, "Média": 1, "Baixa": 2}[self.value]


@dataclass
class Recomendacao:
    titulo: str
    descricao: str
    prioridade: Prioridade
    categoria: str  # ex.: "Negociação", "Fluxo de Caixa", "Risco", "Diversificação"


class MotorDeRecomendacoes:
    """Aplica todas as regras cadastradas e devolve a lista priorizada."""

    def gerar(
        self,
        analise: ResultadoAnalise,
        variacoes: Optional[List[VariacaoFornecedor]] = None,
    ) -> List[Recomendacao]:
        recomendacoes: List[Recomendacao] = []
        for regra in self._todas_as_regras():
            recomendacoes.extend(regra(analise))

        if variacoes:
            recomendacoes.extend(self._regra_variacoes_periodo(variacoes))

        recomendacoes.sort(key=lambda r: r.prioridade.peso_ordenacao)
        return recomendacoes

    def _todas_as_regras(self):
        return [
            self._regra_dependencia_fornecedor_unico,
            self._regra_concentracao_top3,
            self._regra_indice_hhi,
            self._regra_base_pouco_diversificada,
            self._regra_categoria_dominante,
            self._regra_consolidacao_por_categoria,
            self._regra_liquidez_corrente,
            self._regra_caixa_ocioso,
            self._regra_capital_de_giro_negativo,
            self._regra_margem_liquida,
            self._regra_sem_fornecedores,
            self._regra_boas_praticas_gerais,
        ]

    # ------------------------------------------------------------------
    # Regras sobre concentração de fornecedores
    # ------------------------------------------------------------------

    @staticmethod
    def _regra_dependencia_fornecedor_unico(
        analise: ResultadoAnalise,
    ) -> List[Recomendacao]:
        if not analise.fornecedores_ordenados:
            return []
        principal = analise.fornecedores_ordenados[0]
        if principal.percentual_do_total < 40:
            return []
        return [
            Recomendacao(
                titulo=f"Dependência crítica de {principal.nome_curto}",
                descricao=(
                    f"Este fornecedor concentra {principal.percentual_do_total:.1f}% "
                    "de toda a movimentação com fornecedores no período. Qualquer "
                    "problema de preço, prazo ou disponibilidade nessa relação afeta "
                    "diretamente a operação. Vale negociar um contrato formal com "
                    "condições de preço e prazo mais claras, e mapear ao menos um "
                    "fornecedor alternativo para essa categoria como plano de "
                    "contingência."
                ),
                prioridade=Prioridade.ALTA,
                categoria="Risco de Concentração",
            )
        ]

    @staticmethod
    def _regra_concentracao_top3(analise: ResultadoAnalise) -> List[Recomendacao]:
        if len(analise.fornecedores_ordenados) < 3:
            return []
        if analise.top_3_percentual < 70:
            return []
        nomes = ", ".join(
            f.nome_curto for f in analise.fornecedores_ordenados[:3]
        )
        return [
            Recomendacao(
                titulo="Alta concentração nos 3 maiores fornecedores",
                descricao=(
                    f"{nomes} respondem juntos por {analise.top_3_percentual:.1f}% "
                    "do total movimentado com fornecedores. É uma concentração "
                    "saudável de acompanhar de perto: negociações de melhores "
                    "preços ou prazos com esse grupo têm o maior impacto "
                    "financeiro possível por unidade de esforço."
                ),
                prioridade=Prioridade.MEDIA,
                categoria="Negociação",
            )
        ]

    @staticmethod
    def _regra_indice_hhi(analise: ResultadoAnalise) -> List[Recomendacao]:
        # Limiares inspirados nos usados por órgãos de defesa da
        # concorrência para mercados (>2500 = altamente concentrado),
        # aqui reaproveitados para medir a concentração da própria base
        # de fornecedores da empresa.
        if analise.indice_hhi <= 2500 or len(analise.fornecedores_ordenados) < 2:
            return []
        return [
            Recomendacao(
                titulo="Índice de concentração de fornecedores elevado (HHI)",
                descricao=(
                    f"O índice Herfindahl-Hirschman da base de fornecedores está em "
                    f"{analise.indice_hhi:,.0f} pontos (de um máximo de 10.000). "
                    "Valores acima de 2.500 indicam uma base pouco diversificada — "
                    "o mesmo indicador que reguladores usam para apontar mercados "
                    "concentrados. Aumentar o número de fornecedores homologados "
                    "por categoria reduz o risco de interrupção de suprimento."
                ),
                prioridade=Prioridade.MEDIA,
                categoria="Risco de Concentração",
            )
        ]

    @staticmethod
    def _regra_base_pouco_diversificada(
        analise: ResultadoAnalise,
    ) -> List[Recomendacao]:
        qtd = len(analise.fornecedores_ordenados)
        if qtd == 0 or qtd >= 4:
            return []
        return [
            Recomendacao(
                titulo="Base de fornecedores muito pequena",
                descricao=(
                    f"Foram identificados apenas {qtd} fornecedor(es) em aberto "
                    "neste balancete. Uma base tão enxuta é normal em empresas "
                    "pequenas, mas aumenta o risco operacional: qualquer atraso ou "
                    "problema com um deles pode travar a operação. Vale mapear ao "
                    "menos um fornecedor alternativo por categoria essencial."
                ),
                prioridade=Prioridade.BAIXA,
                categoria="Diversificação",
            )
        ]

    # ------------------------------------------------------------------
    # Regras sobre categorias de gasto
    # ------------------------------------------------------------------

    @staticmethod
    def _regra_categoria_dominante(analise: ResultadoAnalise) -> List[Recomendacao]:
        if not analise.resumo_por_categoria:
            return []
        principal = analise.resumo_por_categoria[0]
        if principal.percentual_do_total < 50 or principal.categoria.startswith("Outros"):
            return []
        return [
            Recomendacao(
                titulo=f"Categoria '{principal.categoria}' domina os gastos",
                descricao=(
                    f"{principal.percentual_do_total:.1f}% do valor movimentado com "
                    f"fornecedores está concentrado em '{principal.categoria}' "
                    f"({principal.quantidade_fornecedores} fornecedor(es)). Vale "
                    "avaliar contratos anuais ou de volume nessa categoria "
                    "especificamente, onde o ganho percentual de uma negociação "
                    "tem o maior efeito no caixa."
                ),
                prioridade=Prioridade.MEDIA,
                categoria="Negociação",
            )
        ]

    @staticmethod
    def _regra_consolidacao_por_categoria(
        analise: ResultadoAnalise,
    ) -> List[Recomendacao]:
        recomendacoes = []
        for resumo in analise.resumo_por_categoria:
            if resumo.quantidade_fornecedores < 2:
                continue
            if resumo.categoria.startswith("Outros"):
                continue
            nomes = ", ".join(f.nome_curto for f in resumo.fornecedores)
            recomendacoes.append(
                Recomendacao(
                    titulo=f"Possível consolidação em '{resumo.categoria}'",
                    descricao=(
                        f"Há {resumo.quantidade_fornecedores} fornecedores nessa "
                        f"mesma categoria ({nomes}), somando {formatar_moeda(resumo.total)}. "
                        "Vale avaliar se faz sentido concentrar o volume em um "
                        "único parceiro para negociar desconto por escala, ou se a "
                        "pulverização atual é intencional (redundância proposital "
                        "por segurança de fornecimento)."
                    ),
                    prioridade=Prioridade.BAIXA,
                    categoria="Consolidação",
                )
            )
        return recomendacoes

    # ------------------------------------------------------------------
    # Regras sobre saúde financeira geral
    # ------------------------------------------------------------------

    @staticmethod
    def _regra_liquidez_corrente(analise: ResultadoAnalise) -> List[Recomendacao]:
        liquidez = analise.indicadores.liquidez_corrente
        if liquidez is None:
            return []
        if liquidez >= 1:
            return []
        return [
            Recomendacao(
                titulo="Liquidez corrente abaixo de 1,0 — atenção ao caixa",
                descricao=(
                    f"O índice de liquidez corrente está em {liquidez:.2f}, ou seja, "
                    "o ativo circulante não cobre integralmente as obrigações de "
                    "curto prazo (incluindo fornecedores). Priorize renegociar "
                    "prazos com fornecedores e acelerar o recebimento de clientes "
                    "antes de assumir novos compromissos."
                ),
                prioridade=Prioridade.ALTA,
                categoria="Fluxo de Caixa",
            )
        ]

    @staticmethod
    def _regra_caixa_ocioso(analise: ResultadoAnalise) -> List[Recomendacao]:
        ind = analise.indicadores
        if ind.caixa <= 0 or ind.passivo_circulante <= 0:
            return []
        razao = ind.caixa / ind.passivo_circulante
        if razao < 10:
            return []
        return [
            Recomendacao(
                titulo="Caixa parado muito acima das obrigações de curto prazo",
                descricao=(
                    f"O caixa disponível ({formatar_moeda(ind.caixa)}) é {razao:.0f}x maior "
                    f"que o total a pagar a fornecedores e demais obrigações de "
                    f"curto prazo ({formatar_moeda(ind.passivo_circulante)}). Depois de "
                    "reservar um colchão de segurança, o excedente parado no caixa "
                    "poderia render em uma aplicação de baixo risco (CDB, Tesouro "
                    "Selic) ou ser reinvestido no negócio."
                ),
                prioridade=Prioridade.BAIXA,
                categoria="Fluxo de Caixa",
            )
        ]

    @staticmethod
    def _regra_capital_de_giro_negativo(
        analise: ResultadoAnalise,
    ) -> List[Recomendacao]:
        if analise.indicadores.capital_de_giro >= 0:
            return []
        return [
            Recomendacao(
                titulo="Capital de giro negativo",
                descricao=(
                    f"O capital de giro está negativo em "
                    f"{formatar_moeda(abs(analise.indicadores.capital_de_giro))} "
                    "(ativo circulante menor que o passivo circulante). Esse é um "
                    "sinal de alerta financeiro que costuma preceder dificuldades "
                    "para pagar fornecedores em dia — vale revisar o ciclo "
                    "financeiro (prazo de recebimento vs. prazo de pagamento) com "
                    "prioridade."
                ),
                prioridade=Prioridade.ALTA,
                categoria="Fluxo de Caixa",
            )
        ]

    @staticmethod
    def _regra_margem_liquida(analise: ResultadoAnalise) -> List[Recomendacao]:
        margem = analise.indicadores.margem_liquida
        if margem is None:
            return []
        if margem >= 90:
            return [
                Recomendacao(
                    titulo="Margem líquida aparente muito alta — validar despesas",
                    descricao=(
                        f"O resultado do período equivale a {margem:.1f}% da receita "
                        "bruta. Isso costuma indicar que este balancete não tem uma "
                        "conta de Despesas detalhada (comum em empresas que lançam "
                        "custos de forma simplificada) — ou seja, a margem real "
                        "provavelmente é menor. Vale conferir com o contador se há "
                        "despesas operacionais não classificadas separadamente."
                    ),
                    prioridade=Prioridade.BAIXA,
                    categoria="Alerta de Dados",
                )
            ]
        if margem < 5:
            return [
                Recomendacao(
                    titulo="Margem líquida baixa",
                    descricao=(
                        f"O resultado do período representa apenas {margem:.1f}% da "
                        "receita bruta. Vale revisar tanto o custo dos fornecedores "
                        "quanto a política de preços praticada."
                    ),
                    prioridade=Prioridade.MEDIA,
                    categoria="Rentabilidade",
                )
            ]
        return []

    @staticmethod
    def _regra_sem_fornecedores(analise: ResultadoAnalise) -> List[Recomendacao]:
        if analise.fornecedores_ordenados:
            return []
        return [
            Recomendacao(
                titulo="Nenhum fornecedor em aberto neste período",
                descricao=(
                    "Não foi identificada nenhuma conta de fornecedores com saldo "
                    "no balancete analisado. Isso pode significar que a empresa "
                    "pagou tudo à vista no período (sem saldo em aberto no "
                    "encerramento), ou que o plano de contas usa um nome diferente "
                    "de 'Fornecedores' para essas obrigações."
                ),
                prioridade=Prioridade.BAIXA,
                categoria="Alerta de Dados",
            )
        ]

    @staticmethod
    def _regra_boas_praticas_gerais(analise: ResultadoAnalise) -> List[Recomendacao]:
        if not analise.fornecedores_ordenados:
            return []
        return [
            Recomendacao(
                titulo="Boas práticas recorrentes de gestão de fornecedores",
                descricao=(
                    "Independente da situação atual, três hábitos costumam trazer "
                    "retorno consistente: (1) renegociar prazos e condições "
                    "anualmente, mesmo com fornecedores satisfatórios; (2) sempre "
                    "cotar com pelo menos 2 fornecedores antes de compras "
                    "relevantes; (3) revisar trimestralmente esta mesma análise "
                    "para acompanhar tendências de concentração e custo ao longo "
                    "do tempo."
                ),
                prioridade=Prioridade.BAIXA,
                categoria="Boas Práticas",
            )
        ]

    # ------------------------------------------------------------------
    # Regra sobre variação entre períodos (múltiplos balancetes)
    # ------------------------------------------------------------------

    @staticmethod
    def _regra_variacoes_periodo(
        variacoes: List[VariacaoFornecedor],
    ) -> List[Recomendacao]:
        recomendacoes = []

        for v in variacoes:
            if v.eh_fornecedor_novo:
                recomendacoes.append(
                    Recomendacao(
                        titulo=f"Novo fornecedor: {v.nome}",
                        descricao=(
                            f"Passou a movimentar {formatar_moeda(v.valor_periodo_atual)} "
                            "neste período, sem histórico no período anterior. "
                            "Vale confirmar se há contrato/condições formalizadas."
                        ),
                        prioridade=Prioridade.BAIXA,
                        categoria="Variação de Período",
                    )
                )
                continue

            pct = v.variacao_percentual
            if pct is None:
                continue
            if pct >= 40:
                recomendacoes.append(
                    Recomendacao(
                        titulo=f"Alta de {pct:.0f}% em {v.nome}",
                        descricao=(
                            f"A movimentação com este fornecedor saltou de "
                            f"{formatar_moeda(v.valor_periodo_anterior)} para "
                            f"{formatar_moeda(v.valor_periodo_atual)}. Vale entender se foi "
                            "aumento de preço, de volume comprado, ou reclassificação "
                            "contábil — e se o aumento é sustentável."
                        ),
                        prioridade=Prioridade.MEDIA,
                        categoria="Variação de Período",
                    )
                )
            elif pct <= -40:
                recomendacoes.append(
                    Recomendacao(
                        titulo=f"Queda de {abs(pct):.0f}% em {v.nome}",
                        descricao=(
                            f"A movimentação caiu de {formatar_moeda(v.valor_periodo_anterior)} "
                            f"para {formatar_moeda(v.valor_periodo_atual)}. Se não foi uma "
                            "decisão deliberada, vale confirmar se o fornecimento "
                            "continua ativo e nas condições esperadas."
                        ),
                        prioridade=Prioridade.BAIXA,
                        categoria="Variação de Período",
                    )
                )

        return recomendacoes
