# -*- coding: utf-8 -*-
"""
modelos.py
==========
Estruturas de dados centrais do Analisador Inteligente de Balancetes.

Todas as outras camadas do sistema (extrator, analisador, recomendador,
relatórios) conversam entre si através destas classes, o que mantém o
projeto desacoplado: trocar a forma de ler o PDF, por exemplo, não exige
mudar nenhuma linha da camada de análise.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import List, Optional


class Natureza(str, Enum):
    """Natureza contábil do saldo de uma conta."""
    DEVEDORA = "D"
    CREDORA = "C"

    @property
    def descricao(self) -> str:
        return "Devedora" if self is Natureza.DEVEDORA else "Credora"


class ClasseABC(str, Enum):
    """Classificação de curva ABC (Pareto) para concentração de gastos."""
    A = "A"  # maior impacto financeiro
    B = "B"
    C = "C"  # menor impacto financeiro

    @property
    def rotulo(self) -> str:
        return {
            ClasseABC.A: "A — Alto impacto",
            ClasseABC.B: "B — Impacto médio",
            ClasseABC.C: "C — Baixo impacto",
        }[self]


@dataclass
class ContaContabil:
    """Representa uma única linha (conta) extraída do balancete."""
    codigo: str
    descricao: str
    saldo_anterior: float
    debito: float
    credito: float
    saldo_atual: float
    natureza: Natureza

    @property
    def movimentacao(self) -> float:
        """Soma de débitos e créditos lançados no período: a melhor
        aproximação de 'quanto realmente transitou' por essa conta,
        diferente do saldo final (que pode estar líquido de pagamentos)."""
        return self.debito + self.credito

    @property
    def descricao_normalizada(self) -> str:
        return " ".join(self.descricao.upper().split())


@dataclass
class Fornecedor:
    """
    Um fornecedor identificado dentro do grupo 'Fornecedores' do passivo.

    O `saldo_em_aberto` é quanto ainda se deve a esse fornecedor na data do
    balancete (útil para caixa/liquidez). Já `movimentacao_periodo` é a soma
    de débitos + créditos lançados na conta durante o período — um proxy
    mais fiel de "quanto foi negociado com esse fornecedor no ano" do que o
    saldo final isoladamente, especialmente quando parte da dívida já foi
    paga durante o período.
    """
    codigo: str
    nome: str
    saldo_anterior: float
    debito: float
    credito: float
    saldo_em_aberto: float
    categoria: str = "Não classificado"

    # Preenchidos posteriormente pelo AnalisadorFinanceiro
    percentual_do_total: float = 0.0
    percentual_acumulado: float = 0.0
    classe_abc: Optional[ClasseABC] = None
    ranking: int = 0

    @property
    def movimentacao_periodo(self) -> float:
        return self.debito + self.credito

    @property
    def nome_curto(self) -> str:
        """Nome truncado, útil para gráficos e larguras de coluna fixas."""
        limpo = self.nome.strip()
        return limpo if len(limpo) <= 38 else limpo[:35].rstrip() + "..."


@dataclass
class Empresa:
    """Identificação da empresa e do período coberto pelo balancete."""
    nome: str = "Empresa não identificada"
    cnpj: str = ""
    periodo_inicio: Optional[date] = None
    periodo_fim: Optional[date] = None

    @property
    def periodo_formatado(self) -> str:
        if self.periodo_inicio and self.periodo_fim:
            return (f"{self.periodo_inicio.strftime('%d/%m/%Y')} a "
                    f"{self.periodo_fim.strftime('%d/%m/%Y')}")
        return "Período não identificado"


@dataclass
class Balancete:
    """
    Resultado completo da extração de um arquivo de balancete: a empresa,
    todas as contas contábeis (o 'plano de contas' inteiro do período) e,
    já separados para facilitar a análise, os fornecedores encontrados.
    """
    empresa: Empresa
    contas: List[ContaContabil] = field(default_factory=list)
    fornecedores: List[Fornecedor] = field(default_factory=list)
    arquivo_origem: str = ""

    def buscar_conta(self, *termos: str) -> Optional[ContaContabil]:
        """
        Retorna a primeira conta cuja descrição contenha TODOS os termos
        informados (busca case-insensitive, ignora acentuação diferente
        de maiúsculas/minúsculas). Útil para localizar contas-chave como
        'ATIVO CIRCULANTE' ou 'PATRIMÔNIO LÍQUIDO' sem depender do código,
        que varia de empresa para empresa.
        """
        termos_up = [t.upper() for t in termos]
        for conta in self.contas:
            desc = conta.descricao_normalizada
            if all(t in desc for t in termos_up):
                return conta
        return None

    def valor_conta(self, *termos: str) -> float:
        """Atalho: saldo atual (sempre positivo) da primeira conta encontrada,
        ou 0.0 se a conta não existir no balancete."""
        conta = self.buscar_conta(*termos)
        return conta.saldo_atual if conta else 0.0
