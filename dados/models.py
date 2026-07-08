"""
Modelo principal de saída do pipeline ETL.

A classe FinancialDataset é o ponto de entrega do módulo: encapsula os dados
tratados e oferece métodos de serialização para consumo pela API ou pelo
módulo de Inteligência Artificial (via to_dict / to_json).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from backend.upload.schemas import (
    DatasetMetadata,
    DatasetStatistics,
    FinancialDatasetSchema,
    ProcessingErrorRecord,
    ProcessingWarning,
)
from backend.upload.utils import OUTPUTS_DIR, ensure_output_dirs


class FinancialDataset:
    """
    Objeto estruturado resultante do pipeline ETL.

    Responsabilidades:
    - Manter DataFrame interno + metadados + estatísticas + erros/avisos
    - Expor dados sempre no mesmo formato, independente da origem do arquivo
    - Nunca expor DataFrame cru para camadas externas (API/IA)
    """

    def __init__(
        self,
        dataframe: pd.DataFrame,
        metadata: dict[str, Any],
        statistics: dict[str, Any] | None = None,
        warnings: list[dict[str, Any]] | None = None,
        errors: list[dict[str, Any]] | None = None,
    ) -> None:
        # Cópia defensiva para evitar mutação acidental após a entrega
        self.dataframe = dataframe.copy()
        self.metadata = metadata
        self.statistics = statistics or {}
        self.warnings = warnings or []
        self.errors = errors or []

    def to_dataframe(self) -> pd.DataFrame:
        """Retorna cópia do DataFrame — uso interno ou análises ad hoc."""
        return self.dataframe.copy()

    def to_dict(self) -> dict[str, Any]:
        """
        Serializa para dicionário validado pelo Pydantic.

        Este é o método principal de integração com o módulo de IA.
        """
        records = self._records_from_dataframe()
        schema = FinancialDatasetSchema(
            metadata=DatasetMetadata(**self._prepare_metadata()),
            statistics=DatasetStatistics(**self._prepare_statistics()),
            warnings=[ProcessingWarning(**w) for w in self.warnings],
            errors=[ProcessingErrorRecord(**e) for e in self.errors],
            records=records,
        )
        return schema.model_dump(mode="json")

    def to_json(self, indent: int = 2) -> str:
        """Serializa para JSON — mesmo conteúdo de to_dict(), em string."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent, default=str)

    def to_parquet(self, filepath: str | Path | None = None) -> Path:
        """Persiste apenas o DataFrame em Parquet (armazenamento eficiente)."""
        ensure_output_dirs()
        if filepath is None:
            filename = self.metadata.get("nome_arquivo", "dataset")
            stem = Path(str(filename)).stem
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = OUTPUTS_DIR / "parquet" / f"{stem}_{timestamp}.parquet"
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.dataframe.to_parquet(path, index=False)
        return path

    def save_json(self, filepath: str | Path | None = None) -> Path:
        """Persiste dataset completo (metadados + registros + erros) em JSON."""
        ensure_output_dirs()
        if filepath is None:
            filename = self.metadata.get("nome_arquivo", "dataset")
            stem = Path(str(filename)).stem
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = OUTPUTS_DIR / "json" / f"{stem}_{timestamp}.json"
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")
        return path

    def _records_from_dataframe(self) -> list[dict[str, Any]]:
        """Converte DataFrame em lista de dicts, substituindo NaN por None."""
        if self.dataframe.empty:
            return []
        df = self.dataframe.where(pd.notna(self.dataframe), None)
        return df.to_dict(orient="records")

    def _prepare_metadata(self) -> dict[str, Any]:
        """Normaliza enums e datetimes para serialização JSON."""
        prepared = dict(self.metadata)
        if isinstance(prepared.get("data_upload"), datetime):
            prepared["data_upload"] = prepared["data_upload"].isoformat()
        if "tipo_arquivo" in prepared and hasattr(prepared["tipo_arquivo"], "value"):
            prepared["tipo_arquivo"] = prepared["tipo_arquivo"].value
        if "document_type" in prepared and hasattr(prepared["document_type"], "value"):
            prepared["document_type"] = prepared["document_type"].value
        return prepared

    def _prepare_statistics(self) -> dict[str, Any]:
        stats = dict(self.statistics)
        stats.setdefault("categorias_identificadas", [])
        return stats
