"""
Orquestração do pipeline ETL de upload.

Ponto central do módulo: coordena validação → parsing → limpeza →
normalização e monta o FinancialDataset final.

Este módulo NÃO realiza análise financeira — apenas prepara dados
limpos para consumo pela API ou pelo módulo de IA.
"""

from __future__ import annotations

import time             #quanto tempo demorou o processamento
from datetime import datetime, timezone         #quando foi feito o upload
from io import BytesIO      #faz os bytes funcionarem como um arquivo
from pathlib import Path
from typing import Any, BinaryIO

import pandas as pd #dataframe

from backend.upload.accounting_parser import AccountingStatementParser, ParseContext #AccountingStatementParser = reconhecer documentos contábeis
from backend.upload.cleaner import DataCleaner #limpar
from backend.upload.exceptions import UploadModuleError
from backend.upload.models import FinancialDataset
from backend.upload.normalizer import DataNormalizer #padronizar os dados
from backend.upload.parser import get_parser #escolher o parser relacionado a extensão do documento
from backend.upload.schemas import DocumentType, FileType
from backend.upload.utils import (
    dataframe_preview_text,
    detect_document_type,                               #identificar o tipo do documento
    extract_header_metadata,
    parse_monetary,
    setup_logger,
)
from backend.upload.validator import FileValidator

logger = setup_logger(__name__)

# Tipos que acionam o parser contábil especializado em vez do genérico
ACCOUNTING_DOCUMENT_TYPES = {
    "BALANCETE",                        #set
    "BALANCO_PATRIMONIAL",
    "DRE",
    "LIVRO_RAZAO",
    "LIVRO_DIARIO",
}

SUPPLIER_KEYWORDS = (
    "FORNECEDOR",
    "FORNECEDORES",
    "COMPRA",
    "AQUISICAO",
    "AQUISIÇÃO",
)

SUPPLIER_COLUMN_CANDIDATES = (
    "fornecedor",
    "fornecedores",
    "nome_fornecedor",
    "razao_social",
    "razão_social",
)


class UploadService:
    """
    Serviço principal do pipeline ETL.

    Compõe as etapas em sequência e agrega metadados, estatísticas,
    erros e avisos no objeto FinancialDataset.
    """

    def __init__(self) -> None:
        self.validator = FileValidator()
        self.cleaner = DataCleaner()
        self.normalizer = DataNormalizer()
        self.accounting_parser = AccountingStatementParser()

    def process(
        self,
        file_content: bytes | BinaryIO,
        filename: str,
    ) -> FinancialDataset:
        """
        Executa pipeline completo: validação → leitura → tratamento → padronização.

        Returns:
            FinancialDataset pronto para consumo pela API ou módulo de IA.
        """
        start_time = time.perf_counter()
        content = self._to_bytes(file_content)
        errors: list[dict] = []
        warnings: list[dict] = []

        logger.info("=== Início do pipeline ETL: %s ===", filename)

        # --- Etapa 1: Validação do arquivo ---
        file_type = self.validator.validate(content, filename)
        logger.info("Validação concluída | tipo: %s", file_type.value)

        parse_context: ParseContext | None = None
        document_type = DocumentType.DESCONHECIDO
        header_metadata: dict = {}

        # --- Etapa 2: Parsing (extração para DataFrame) ---
        dataframe, parse_context = self._parse_content(content, filename, file_type)

        if parse_context:
            document_type = DocumentType(parse_context.document_type)
            header_metadata = parse_context.header_metadata

        logger.info("Parser concluído | registros brutos: %d", len(dataframe))

        # --- Etapa 3: Limpeza estrutural ---
        cleaned = self.cleaner.clean(dataframe)
        warnings.extend(self.cleaner.get_processing_warnings())

        # --- Etapa 4: Padronização de tipos e categorias ---
        normalized = self.normalizer.normalize(cleaned)
        errors.extend(self.normalizer.get_errors())

        elapsed = time.perf_counter() - start_time
        statistics = self._build_statistics(normalized, self.cleaner.duplicates_removed, errors)

        metadata = self._build_metadata(
            filename=filename,
            file_type=file_type,
            document_type=document_type,
            header_metadata=header_metadata,
            dataframe=normalized,
            elapsed=elapsed,
        )

        logger.info(
            "Pipeline concluído | registros: %d | erros: %d | tempo: %.2fs",
            len(normalized),
            len(errors),
            elapsed,
        )

        return FinancialDataset(
            dataframe=normalized,
            metadata=metadata,
            statistics=statistics,
            warnings=warnings,
            errors=errors,
        )

    def _parse_content(self,content: bytes,filename: str,file_type: FileType,) -> tuple[pd.DataFrame, ParseContext | None]:
        """Seleciona parser adequado ao tipo de arquivo.Detecta tipo de documento contábil e extrai metadados de cabeçalhoindependentemente do formato (PDF, Excel ou CSV)."""
        if file_type == FileType.PDF:
            preview_text = self._preview_pdf_text(content)
            doc_type = detect_document_type(preview_text)
            if doc_type in ACCOUNTING_DOCUMENT_TYPES or doc_type != "DESCONHECIDO":
                df, context = self.accounting_parser.parse(content, filename)
            return df, context

            parser = get_parser(file_type.value)
            return parser.parse(content, filename), None

        # Excel/CSV: extrai DataFrame primeiro, depois tenta identificar
        # se é um documento contábil a partir do próprio conteúdo tabular.
        parser = get_parser(file_type.value)
        raw_df = parser.parse(content, filename)

        preview_text = dataframe_preview_text(raw_df)
        doc_type = detect_document_type(preview_text)

        if doc_type != "DESCONHECIDO":
            header_metadata = extract_header_metadata(preview_text)
            context = ParseContext(
                raw_text=preview_text,
                document_type=doc_type,
                header_metadata=header_metadata,
            )
            standardized = self.accounting_parser.standardize_dataframe(raw_df, context)
            return standardized, context

        return raw_df, None

    def _preview_pdf_text(self, content: bytes) -> str:
        """Lê apenas a primeira página para decidir qual parser usar."""
        try:
            import pdfplumber

            with pdfplumber.open(BytesIO(content)) as pdf:
                if pdf.pages:
                    return pdf.pages[0].extract_text() or ""
        except Exception:
            pass
        try:
            from PyPDF2 import PdfReader

            reader = PdfReader(BytesIO(content))
            if reader.pages:
                return reader.pages[0].extract_text() or ""
        except Exception:
            pass
        return ""

    def _build_metadata(
        self,
        filename: str,
        file_type: FileType,
        document_type: DocumentType,
        header_metadata: dict,
        dataframe: pd.DataFrame,
        elapsed: float,
    ) -> dict:
        """Monta metadados automáticos exigidos pela especificação."""
        return {
            "empresa": header_metadata.get("empresa"),
            "cnpj": header_metadata.get("cnpj"),
            "periodo": header_metadata.get("periodo"),
            "data_emissao": header_metadata.get("data_emissao"),
            "numero_livro": header_metadata.get("numero_livro"),
            "folha": header_metadata.get("folha"),
            "sistema_emissor": header_metadata.get("sistema_emissor"),
            "nome_arquivo": Path(filename).name,
            "data_upload": datetime.now(timezone.utc),
            "tipo_arquivo": file_type,
            "document_type": document_type,
            "numero_registros": len(dataframe),
            "numero_colunas": len(dataframe.columns),
            "tempo_processamento_segundos": round(elapsed, 4),
        }

    def _build_statistics(
        self,
        dataframe: pd.DataFrame,
        duplicates_removed: int,
        errors: list[dict],
    ) -> dict:
        """Calcula métricas de qualidade do processamento."""
        missing_values = int(dataframe.isna().sum().sum()) if not dataframe.empty else 0
        invalid_rows = len({e.get("linha") for e in errors if e.get("linha")})
        supplier_stats = self._build_supplier_spend_statistics(dataframe)

        return {
            "linhas_validas": max(len(dataframe) - invalid_rows, 0),
            "linhas_invalidas": invalid_rows,
            "duplicatas_removidas": duplicates_removed,
            "valores_ausentes": missing_values,
            "categorias_identificadas": self.normalizer.identified_categories,
            "total_gastos_fornecedores": supplier_stats["total_gastos_fornecedores"],
            "gastos_por_fornecedor": supplier_stats["gastos_por_fornecedor"],
        }

    def _build_supplier_spend_statistics(self, dataframe: pd.DataFrame) -> dict[str, Any]:
        """
        Consolida gastos de fornecedores no geral e por fornecedor.

        Em balancetes, normalmente o fornecedor aparece na descrição da conta.
        Em arquivos financeiros mais diretos, pode existir uma coluna própria
        de fornecedor; os dois formatos são suportados aqui.
        """
        if dataframe.empty:
            return {
                "total_gastos_fornecedores": 0.0,
                "gastos_por_fornecedor": [],
            }

        supplier_col = self._find_first_column(dataframe, SUPPLIER_COLUMN_CANDIDATES)
        grouped: dict[str, dict[str, Any]] = {}

        for _, row in dataframe.iterrows():
            supplier_name = self._supplier_name_from_row(row, supplier_col)
            if not supplier_name:
                continue

            entry = grouped.setdefault(
                supplier_name,
                {
                    "fornecedor": supplier_name,
                    "valor_gasto": 0.0,
                    "debito": 0.0,
                    "credito": 0.0,
                    "saldo_atual": 0.0,
                    "quantidade_lancamentos": 0,
                },
            )
            entry["valor_gasto"] += self._supplier_spend_value(row)
            entry["debito"] += self._numeric_value(row.get("debito"))
            entry["credito"] += self._numeric_value(row.get("credito"))
            entry["saldo_atual"] += self._numeric_value(row.get("saldo_atual"))
            entry["quantidade_lancamentos"] += 1

        suppliers = [
            {
                key: round(value, 2) if isinstance(value, float) else value
                for key, value in entry.items()
            }
            for entry in grouped.values()
        ]
        suppliers.sort(key=lambda item: item["valor_gasto"], reverse=True)

        return {
            "total_gastos_fornecedores": round(
                sum(item["valor_gasto"] for item in suppliers),
                2,
            ),
            "gastos_por_fornecedor": suppliers,
        }

    def _supplier_name_from_row(
        self,
        row: pd.Series,
        supplier_col: str | None,
    ) -> str | None:
        if supplier_col:
            supplier = self._clean_supplier_name(row.get(supplier_col))
            if supplier:
                return supplier

        description = self._clean_supplier_name(row.get("descricao"))
        if not description:
            return None

        category = self._clean_supplier_name(row.get("categoria_normalizada") or row.get("categoria"))
        text_to_check = f"{description} {category or ''}"
        if any(keyword in text_to_check for keyword in SUPPLIER_KEYWORDS):
            return description

        return None

    def _supplier_spend_value(self, row: pd.Series) -> float:
        for column in ("valor", "debito", "saldo_atual"):
            value = self._numeric_value(row.get(column))
            if value:
                return abs(value)
        return 0.0

    def _find_first_column(
        self,
        dataframe: pd.DataFrame,
        candidates: tuple[str, ...],
    ) -> str | None:
        normalized_columns = {str(col).lower(): col for col in dataframe.columns}
        for candidate in candidates:
            if candidate in normalized_columns:
                return normalized_columns[candidate]
        return None

    def _clean_supplier_name(self, value: Any) -> str | None:
        if value is None or pd.isna(value):
            return None
        text = str(value).strip()
        return text if text else None

    def _numeric_value(self, value: Any) -> float:
        if value is None or pd.isna(value):
            return 0.0
        parsed = parse_monetary(value)
        if parsed is not None:
            return parsed
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _to_bytes(self, file_content: bytes | BinaryIO) -> bytes:
        if isinstance(file_content, bytes):
            return file_content
        return file_content.read()


def process_uploaded_file(
    file_content: bytes | BinaryIO,
    filename: str,
) -> FinancialDataset:
    """
    Ponto de entrada simplificado para integração com FastAPI.

    Encapsula a criação do UploadService — use esta função nos endpoints
    em vez de instanciar o serviço diretamente.

    Raises:
        UploadModuleError: Erros de validação ou parsing.
    """
    service = UploadService()
    return service.process(file_content, filename)
