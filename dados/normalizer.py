"""
Padronização e normalização de dados financeiros.

Terceira etapa de tratamento: converte tipos (datas, valores monetários),
unifica nomes de colunas e classifica descrições em categorias padronizadas.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from backend.upload.cleaner import DataCleaner
from backend.upload.schemas import ProcessingErrorRecord
from backend.upload.utils import (
    load_json_config,
    map_column_names,
    normalize_text,
    parse_date,
    parse_monetary,
    setup_logger,
)

logger = setup_logger(__name__)

# Colunas reconhecidas automaticamente pelo nome padronizado
DATE_COLUMNS = {"data", "data_emissao", "data_lancamento", "data_movimento", "periodo"}
MONETARY_COLUMNS = {
    "valor",
    "debito",
    "credito",
    "saldo",
    "saldo_anterior",
    "saldo_atual",
    "saldo_final",
}
TEXT_COLUMNS = {"descricao", "historico", "categoria", "empresa", "observacao"}


class DataNormalizer:
    """
    Padroniza tipos, formatos e categorias dos dados.

    Erros em células individuais são registrados, mas a linha permanece
    no dataset com o valor original ou None.
    """

    def __init__(self, categories_path: str = "categories.json") -> None:
        # Categorias e aliases vêm de JSON — extensíveis sem alterar código
        self.categories = load_json_config(categories_path)
        self.column_aliases = load_json_config("column_aliases.json")
        self.errors: list[dict[str, Any]] = []
        self.invalid_rows = 0

    def normalize(self, dataframe: pd.DataFrame) -> pd.DataFrame:
        """Aplica padronização completa ao DataFrame."""
        logger.info("Iniciando normalização de dados")
        self.errors = []
        self.invalid_rows = 0

        df = dataframe.copy()
        df = self._rename_columns(df)
        df = self._standardize_values(df)
        df = self._apply_category_normalization(df)

        logger.info("Normalização concluída")
        return df

    def _rename_columns(self, df: pd.DataFrame) -> pd.DataFrame:
      """Unifica nomes equivalentes (ex.: 'Histórico' → 'descricao')."""
      mapping = map_column_names(list(df.columns), self.column_aliases)
      renamed = {col: standard for col, standard in mapping.items()}
      df = df.rename(columns=renamed)

      if df.columns.duplicated().any():
          dupes = df.columns[df.columns.duplicated()].unique().tolist()
          logger.warning(
              "Colunas duplicadas após mapeamento de aliases: %s. "
              "Mantendo apenas a primeira ocorrência de cada.",
              dupes,
          )
          df = df.loc[:, ~df.columns.duplicated()]

      return df
      
    def _standardize_values(self, df: pd.DataFrame) -> pd.DataFrame:
        """Converte cada célula conforme o tipo inferido pela coluna."""
        result = df.copy()
        for col in result.columns:
            col_lower = str(col).lower()
            for idx, value in result[col].items():
                try:
                    if col_lower in DATE_COLUMNS or "data" in col_lower:
                        parsed = parse_date(value)
                        if value is not None and not pd.isna(value) and str(value).strip() and parsed is None:
                            self._record_error(idx, col, "DATA_INVALIDA", str(value))
                        result.at[idx, col] = parsed
                    elif col_lower in MONETARY_COLUMNS or self._looks_monetary(col_lower):
                        parsed = parse_monetary(value)
                        if self._is_non_empty(value) and parsed is None:
                            self._record_error(idx, col, "VALOR_INVALIDO", str(value))
                        result.at[idx, col] = parsed
                    elif col_lower in TEXT_COLUMNS or result[col].dtype == object:
                        result.at[idx, col] = normalize_text(value) if self._is_non_empty(value) else value
                except Exception as exc:
                    self._record_error(idx, col, "ERRO_PADRONIZACAO", str(exc))
        return result

    def _apply_category_normalization(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Mapeia descrições livres para categorias padronizadas.

        Ex.: 'Conta de Luz CPFL' → 'ENERGIA'
        """
        if "descricao" not in df.columns and "categoria" not in df.columns:
            return df

        result = df.copy()
        category_col = "categoria" if "categoria" in result.columns else None
        desc_col = "descricao" if "descricao" in result.columns else None

        normalized_categories: list[str | None] = []
        for idx, row in result.iterrows():
            text_source = ""
            if desc_col:
                text_source = str(row.get(desc_col, "") or "")
            elif category_col:
                text_source = str(row.get(category_col, "") or "")

            category = self._match_category(text_source)
            normalized_categories.append(category)

            if category_col:
                result.at[idx, category_col] = category
            else:
                result.at[idx, "categoria_normalizada"] = category

        self._identified_categories = sorted({c for c in normalized_categories if c})
        return result

    def _match_category(self, text: str) -> str | None:
        """Busca palavra-chave no dicionário externo de categorias."""
        if not text or not text.strip():
            return None

        normalized = normalize_text(text).lower()
        for category, keywords in self.categories.items():
            if category == "OUTROS":
                continue
            for keyword in keywords:
                if keyword.upper() in normalized or keyword.lower() in normalized.lower():
                    return category
        return "OUTROS"

    def _looks_monetary(self, column_name: str) -> bool:
        keywords = ("saldo", "debito", "credito", "valor", "vlr", "montante")
        return any(k in column_name for k in keywords)

    def _is_non_empty(self, value: Any) -> bool:
        return value is not None and not pd.isna(value) and str(value).strip() != ""

    def _record_error(self, linha: int, coluna: str, erro: str, motivo: str) -> None:
        self.invalid_rows += 1
        self.errors.append(
            ProcessingErrorRecord(
                linha=int(linha) + 1 if isinstance(linha, int) else linha,
                coluna=str(coluna),
                erro=erro,
                motivo=motivo,
            ).model_dump()
        )

    @property
    def identified_categories(self) -> list[str]:
        return getattr(self, "_identified_categories", [])

    def get_errors(self) -> list[dict[str, Any]]:
        return self.errors


class RowLevelProcessor:
    """
    Encapsula limpeza + normalização com acúmulo de erros.

    Útil quando se deseja processar um DataFrame isoladamente,
    fora do fluxo principal do UploadService.
    """

    def __init__(self) -> None:
        self.cleaner = DataCleaner()
        self.normalizer = DataNormalizer()

    def process(self, dataframe: pd.DataFrame) -> tuple[pd.DataFrame, list[dict], list[dict]]:
        """Executa limpeza e normalização acumulando erros."""
        cleaned = self.cleaner.clean(dataframe)
        normalized = self.normalizer.normalize(cleaned)

        all_errors = (
            self.cleaner.get_processing_errors()
            + self.normalizer.get_errors()
        )
        all_warnings = self.cleaner.get_processing_warnings()

        return normalized, all_errors, all_warnings
