"""Modelos de dados e contrato de colunas do motor de análise financeira.

Este módulo é a fronteira do motor com o resto do projeto: define quais
colunas são esperadas na entrada (ver docs/CONTRATO_DADOS.md) e as
estruturas de saída consumidas pela interface (Miguel) e pelo módulo de
recomendações (João Thiago).
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd

COLUNAS_OBRIGATORIAS_LANCAMENTOS = ("data", "categoria", "fornecedor", "valor")
COLUNAS_OBRIGATORIAS_ORCAMENTO = ("categoria", "limite")

CATEGORIAS_PADRAO = (
    "mercadorias",
    "energia",
    "aluguel",
    "folha",
    "transporte",
    "servicos",
    "outros",
)

SEVERIDADES = ("baixa", "media", "alta", "critica")
TIPOS_LANCAMENTO = ("receita", "despesa")


def padronizar_categoria(valor: str) -> str:
    """Normaliza uma string de categoria: minúsculo, sem acento, sem espaços nas pontas.

    Usado tanto internamente quanto pelo módulo de tratamento de dados (Eduardo)
    para garantir que categorias cheguem no formato que o motor espera.
    """
    if not isinstance(valor, str):
        return "outros"
    texto = unicodedata.normalize("NFKD", valor.strip().lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return texto or "outros"


class ContratoDadosError(ValueError):
    """Levantado quando a entrada não respeita o contrato de dados do motor."""


def validar_lancamentos(df: pd.DataFrame) -> pd.DataFrame:
    """Valida e normaliza um DataFrame de lançamentos financeiros.

    Retorna uma cópia normalizada (categoria padronizada, data convertida,
    valor numérico e positivo). Lança ContratoDadosError com uma mensagem
    acionável quando a entrada não respeita o contrato.
    """
    if df is None or df.empty:
        raise ContratoDadosError("DataFrame de lançamentos vazio ou não informado.")

    faltantes = [c for c in COLUNAS_OBRIGATORIAS_LANCAMENTOS if c not in df.columns]
    if faltantes:
        raise ContratoDadosError(
            f"Colunas obrigatórias ausentes nos lançamentos: {faltantes}. "
            f"Esperado no mínimo: {COLUNAS_OBRIGATORIAS_LANCAMENTOS}. "
            "Veja docs/CONTRATO_DADOS.md."
        )

    df = df.copy()
    df["categoria"] = df["categoria"].apply(padronizar_categoria)
    df["data"] = pd.to_datetime(df["data"], errors="coerce", format="mixed")
    if df["data"].isna().any():
        n = int(df["data"].isna().sum())
        raise ContratoDadosError(
            f"{n} linha(s) com data inválida/não reconhecida na coluna 'data'."
        )

    df["valor"] = pd.to_numeric(df["valor"], errors="coerce")
    if df["valor"].isna().any():
        n = int(df["valor"].isna().sum())
        raise ContratoDadosError(
            f"{n} linha(s) com valor inválido/não numérico na coluna 'valor'."
        )
    if (df["valor"] < 0).any():
        raise ContratoDadosError(
            "Coluna 'valor' contém valores negativos; o motor espera gastos "
            "sempre positivos (sinal já deve ter sido tratado na entrada)."
        )

    df["fornecedor"] = df["fornecedor"].fillna("nao informado").astype(str).str.strip()
    if "produto" in df.columns:
        df["produto"] = df["produto"].fillna("nao informado").astype(str).str.strip()

    if "tipo" in df.columns:
        df["tipo"] = df["tipo"].fillna("despesa").astype(str).str.strip().str.lower()
        invalidos = ~df["tipo"].isin(TIPOS_LANCAMENTO)
        if invalidos.any():
            valores = sorted(df.loc[invalidos, "tipo"].unique())
            raise ContratoDadosError(
                f"Coluna 'tipo' contém valor(es) inválido(s) {valores}; "
                f"esperado um de {TIPOS_LANCAMENTO}."
            )
    else:
        df["tipo"] = "despesa"

    return df


def validar_orcamento(df: pd.DataFrame) -> pd.DataFrame:
    """Valida e normaliza um DataFrame de orçamento/limites por categoria."""
    if df is None or df.empty:
        raise ContratoDadosError("DataFrame de orçamento vazio ou não informado.")

    faltantes = [c for c in COLUNAS_OBRIGATORIAS_ORCAMENTO if c not in df.columns]
    if faltantes:
        raise ContratoDadosError(
            f"Colunas obrigatórias ausentes no orçamento: {faltantes}. "
            f"Esperado: {COLUNAS_OBRIGATORIAS_ORCAMENTO}. Veja docs/CONTRATO_DADOS.md."
        )

    df = df.copy()
    df["categoria"] = df["categoria"].apply(padronizar_categoria)
    df["limite"] = pd.to_numeric(df["limite"], errors="coerce")
    if df["limite"].isna().any():
        raise ContratoDadosError("Coluna 'limite' do orçamento contém valores não numéricos.")

    return df.groupby("categoria", as_index=False)["limite"].sum()


@dataclass
class Alerta:
    """Um alerta financeiro gerado pelo motor para uma categoria (e opcionalmente fornecedor)."""

    categoria: str
    tipo: str  # "estouro_orcamento" | "variacao_historica"
    severidade: str  # ver SEVERIDADES
    valor_atual: float
    valor_referencia: float
    variacao_percentual: float
    mensagem: str
    fornecedor: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "categoria": self.categoria,
            "tipo": self.tipo,
            "severidade": self.severidade,
            "valor_atual": round(self.valor_atual, 2),
            "valor_referencia": round(self.valor_referencia, 2),
            "variacao_percentual": round(self.variacao_percentual, 2),
            "mensagem": self.mensagem,
            "fornecedor": self.fornecedor,
        }


@dataclass
class ResultadoAnalise:
    """Saída completa do motor de análise financeira para um período."""

    periodo: str
    resumo: dict[str, Any]
    resultado_contabil: dict[str, Any]
    variacoes: pd.DataFrame
    rankings: dict[str, pd.DataFrame]
    alertas: list[Alerta] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Converte o resultado para uma estrutura 100% serializável em JSON.

        É este o formato que a interface (Miguel) e o módulo de
        recomendações (João Thiago) devem consumir.
        """
        return {
            "periodo": self.periodo,
            "resumo": self.resumo,
            "resultado_contabil": self.resultado_contabil,
            "variacoes": self.variacoes.to_dict(orient="records"),
            "rankings": {
                nome: df.to_dict(orient="records") for nome, df in self.rankings.items()
            },
            "alertas": [a.to_dict() for a in self.alertas],
        }
