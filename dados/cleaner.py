"""
Limpeza de DataFrames extraídos.

Segunda etapa de tratamento: remove ruído estrutural (linhas/colunas vazias,
duplicatas, caracteres inválidos) antes da padronização de tipos.
"""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

from dados.schemas import ProcessingErrorRecord, ProcessingWarning
from dados.utils import INVALID_CHARS_PATTERN, setup_logger

logger = setup_logger(__name__)

# Colunas geradas automaticamente por parsers que não agregam valor
USELESS_COLUMN_PATTERNS = [
    re.compile(r"^unnamed", re.IGNORECASE),
    re.compile(r"^col_\d+$", re.IGNORECASE),
    re.compile(r"^$"),
]


class DataCleaner:
    """
    Remove linhas/colunas inválidas e normaliza espaços.

    Nunca interrompe o pipeline por causa de uma linha problemática —
    apenas registra avisos sobre o que foi removido.
    """

    def __init__(self) -> None:
        self.warnings: list[dict[str, Any]] = []
        self.errors: list[dict[str, Any]] = []

    def clean(self, dataframe: pd.DataFrame) -> pd.DataFrame:
        """Aplica pipeline completo de limpeza em ordem fixa."""
        logger.info("Iniciando limpeza de dados (%d linhas)", len(dataframe))
        self.warnings = []
        self.errors = []

        df = dataframe.copy()
        df = self._remove_empty_rows(df)
        df = self._remove_empty_columns(df)
        df = self._remove_useless_columns(df)
        df = self._remove_duplicates(df)
        df = self._clean_cell_values(df)

        logger.info("Limpeza concluída (%d linhas restantes)", len(df))
        return df

    def _remove_empty_rows(self, df: pd.DataFrame) -> pd.DataFrame:
        before = len(df)
        cleaned = df.dropna(how="all")
        cleaned = cleaned[~cleaned.apply(self._is_empty_row, axis=1)]
        removed = before - len(cleaned)
        if removed:
            self.warnings.append(
                ProcessingWarning(mensagem=f"{removed} linhas vazias removidas.").model_dump()
            )
        return cleaned.reset_index(drop=True)

    def _remove_empty_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        before = len(df.columns)
        cleaned = df.dropna(axis=1, how="all")
        removed = before - len(cleaned.columns)
        if removed:
            self.warnings.append(
                ProcessingWarning(mensagem=f"{removed} colunas vazias removidas.").model_dump()
            )
        return cleaned

    def _remove_useless_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        cols_to_drop = [
            col
            for col in df.columns
            if any(pattern.search(str(col)) for pattern in USELESS_COLUMN_PATTERNS)
        ]
        if cols_to_drop:
            self.warnings.append(
                ProcessingWarning(
                    mensagem=f"Colunas sem utilidade removidas: {cols_to_drop}"
                ).model_dump()
            )
            return df.drop(columns=cols_to_drop)
        return df

    def _remove_duplicates(self, df: pd.DataFrame) -> pd.DataFrame:
        before = len(df)
        cleaned = df.drop_duplicates()
        removed = before - len(cleaned)
        self._duplicates_removed = removed
        if removed:
            self.warnings.append(
                ProcessingWarning(mensagem=f"{removed} duplicatas removidas.").model_dump()
            )
        return cleaned.reset_index(drop=True)

    def _clean_cell_values(self, df: pd.DataFrame) -> pd.DataFrame:
        """Remove quebras de linha, espaços extras e caracteres de controle."""
        cleaned = df.copy()
        for col in cleaned.columns:
            cleaned[col] = cleaned[col].apply(self._clean_single_value)
        return cleaned

    def _clean_single_value(self, value: Any) -> Any:
        if pd.isna(value) or value is None:
            return value
        if not isinstance(value, str):
            return value

        text = INVALID_CHARS_PATTERN.sub("", value)
        text = text.replace("\n", " ").replace("\r", " ")
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _is_empty_row(self, row: pd.Series) -> bool:
        return all(pd.isna(v) or str(v).strip() == "" for v in row)

    @property
    def duplicates_removed(self) -> int:
        return getattr(self, "_duplicates_removed", 0)

    def get_processing_errors(self) -> list[dict[str, Any]]:
        return self.errors

    def get_processing_warnings(self) -> list[dict[str, Any]]:
        return self.warnings

    def record_row_error(
        self,
        linha: int,
        coluna: str,
        erro: str,
        motivo: str,
    ) -> None:
        """Registra erro de linha sem interromper processamento."""
        self.errors.append(
            ProcessingErrorRecord(
                linha=linha,
                coluna=coluna,
                erro=erro,
                motivo=motivo,
            ).model_dump()
        )
