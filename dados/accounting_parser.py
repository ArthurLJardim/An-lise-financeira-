"""
Parser especializado para documentos contábeis brasileiros.

Interpreta Balancete, Balanço Patrimonial, DRE, Livro Razão/Diário e
outros relatórios exportados por sistemas contábeis, produzindo sempre
o mesmo formato padronizado de colunas.

Utiliza Strategy Pattern para permitir adicionar novos layouts sem
modificar parsers existentes.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from io import BytesIO
from typing import Any

import pandas as pd

from dados.exceptions import FileParsingError
from dados.utils import (
    detect_document_type,
    extract_header_metadata,
    extract_natureza,
    load_json_config,
    map_column_names,
    normalize_text,
    parse_monetary,
    setup_logger,
)

logger = setup_logger(__name__)

# Formato de saída obrigatório — independente da origem do documento
STANDARD_COLUMNS = [
    "codigo",
    "descricao",
    "saldo_anterior",
    "debito",
    "credito",
    "saldo_atual",
    "natureza",
]

# Heurísticas para separar código e descrição quando vêm colados/duplicados
# Ex.: "CAIXA4 CAIXA" → codigo=4, descricao=CAIXA
CODE_DESC_PATTERNS = [
    re.compile(r"^(?P<descricao>[A-ZÀ-Ü\s\.&\-]+?)\s+(?P<codigo>\d+)\s+\1$"),
    re.compile(r"^(?P<descricao>[A-ZÀ-Ü]+)(?P<codigo>\d+)\s+(?P=descricao)$"),
    re.compile(r"^(?P<codigo>\d+)\s+(?P<descricao>.+)$"),
    re.compile(r"^(?P<descricao>.+?)\s+(?P<codigo>\d+)$"),
]

# Linha com valores monetários no final (típico de balancetes em texto)
MONETARY_AT_END = re.compile(
    r"^(?P<prefix>.+?)\s+"
    r"(?P<saldo_anterior>(?:\(?\-?\d[\d\.,]*\)?)?)\s*"
    r"(?P<debito>(?:\(?\-?\d[\d\.,]*\)?)?)\s*"
    r"(?P<credito>(?:\(?\-?\d[\d\.,]*\)?)?)\s*"
    r"(?P<saldo_atual>\(?\-?\d[\d\.,]*\)?)\s*$"
)


@dataclass
class ParseContext:
    """
    Contexto compartilhado entre estratégias de parsing.

    Carrega texto bruto, tipo detectado e metadados do cabeçalho
    para enriquecer o FinancialDataset.metadata.
    """

    raw_text: str = ""
    document_type: str = "DESCONHECIDO"
    header_metadata: dict[str, str | None] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


class DocumentLayoutStrategy(ABC):
    """
    Interface do Strategy Pattern para layouts contábeis.

    Novos layouts (ex.: exportação de ERP específico) implementam
    esta classe e são registrados via register_strategy().
    """

    @abstractmethod
    def can_handle(self, context: ParseContext) -> bool:
        """Verifica se a estratégia é aplicável ao documento."""

    @abstractmethod
    def parse_dataframe(self, raw_df: pd.DataFrame, context: ParseContext) -> pd.DataFrame:
        """Converte DataFrame bruto para o formato STANDARD_COLUMNS."""


class GenericAccountingStrategy(DocumentLayoutStrategy):
    """
    Estratégia genérica — fallback para qualquer layout contábil.

    Tenta mapear colunas por alias; se falhar, reconstrói linhas via regex.
    """

    def can_handle(self, context: ParseContext) -> bool:
        return True  # Sempre aplicável como último recurso

    def parse_dataframe(self, raw_df: pd.DataFrame, context: ParseContext) -> pd.DataFrame:
        aliases = load_json_config("column_aliases.json")
        mapping = map_column_names(list(raw_df.columns), aliases)
        df = raw_df.rename(columns={k: v for k, v in mapping.items()})

        records: list[dict[str, Any]] = []
        for _, row in df.iterrows():
            record = self._row_to_standard(row.to_dict())
            if record.get("descricao") or record.get("codigo"):
                records.append(record)

        # Extração tabular falhou — reconstrói a partir do texto bruto
        if not records:
            records = self._parse_from_text_lines(context.raw_text)

        return self._to_standard_dataframe(records)

    def _row_to_standard(self, row: dict[str, Any]) -> dict[str, Any]:
      """Normaliza uma linha do DataFrame bruto para o schema padrão."""
      record = {col: None for col in STANDARD_COLUMNS}

      for key, value in row.items():
          key_lower = str(key).lower()
          if key_lower in STANDARD_COLUMNS:
              record[key_lower] = value

      # Corrige casos onde código e descrição vieram colados
      if record["descricao"] and not record["codigo"]:
          fixed = self._fix_code_description(str(record["descricao"]))
          record.update(fixed)

      # Captura natureza pelo sufixo D/C (ex.: '92.553,10C') antes de limpar o valor
      if record["natureza"] is None:
          for money_col in ("saldo_atual", "saldo_anterior", "credito", "debito"):
              detected = extract_natureza(record[money_col])
              if detected:
                  record["natureza"] = detected
                  break

      for money_col in ("saldo_anterior", "debito", "credito", "saldo_atual"):
        if record[money_col] is not None:
            record[money_col] = parse_monetary(record[money_col])

      # Infere natureza contábil (D/C) a partir do sinal do saldo, se não veio no sufixo
      if record["saldo_atual"] is not None and record["natureza"] is None:
        record["natureza"] = "D" if record["saldo_atual"] >= 0 else "C"

      if record["descricao"]:
          record["descricao"] = normalize_text(record["descricao"])

      return record

    def _parse_from_text_lines(self, text: str) -> list[dict[str, Any]]:
        """Fallback: interpreta cada linha de texto com heurísticas regex."""
        records: list[dict[str, Any]] = []
        for line in text.splitlines():
            line = line.strip()
            if not line or len(line) < 3:
                continue
            record = self._parse_line_heuristic(line)
            if record:
                records.append(record)
        return records

    def _parse_line_heuristic(self, line: str) -> dict[str, Any] | None:
        for pattern in CODE_DESC_PATTERNS:
            match = pattern.match(line)
            if match:
                groups = match.groupdict()
                return {
                    "codigo": groups.get("codigo"),
                    "descricao": normalize_text(groups.get("descricao", "")),
                    "saldo_anterior": None,
                    "debito": None,
                    "credito": None,
                    "saldo_atual": None,
                    "natureza": None,
                }

        money_match = MONETARY_AT_END.match(line)
        if money_match:
            groups = money_match.groupdict()
            prefix = groups["prefix"]
            code_desc = self._fix_code_description(prefix)
            return {
                "codigo": code_desc.get("codigo"),
                "descricao": code_desc.get("descricao"),
                "saldo_anterior": parse_monetary(groups.get("saldo_anterior")),
                "debito": parse_monetary(groups.get("debito")),
                "credito": parse_monetary(groups.get("credito")),
                "saldo_atual": parse_monetary(groups.get("saldo_atual")),
                "natureza": None,
            }

        return None

    def _fix_code_description(self, text: str) -> dict[str, str | None]:
        """
        Separa código e descrição em textos mal formatados.

        Cobre exportações com OCR ruim ou colunas desalinhadas.
        """
        text = text.strip()
        for pattern in CODE_DESC_PATTERNS:
            match = pattern.match(text)
            if match:
                groups = match.groupdict()
                return {
                    "codigo": groups.get("codigo"),
                    "descricao": normalize_text(groups.get("descricao", "")),
                }

        parts = text.rsplit(" ", 1)
        if len(parts) == 2 and parts[1].isdigit():
            return {"codigo": parts[1], "descricao": normalize_text(parts[0])}

        leading = re.match(r"^(\d+)\s+(.+)$", text)
        if leading:
            return {"codigo": leading.group(1), "descricao": normalize_text(leading.group(2))}

        trailing = re.match(r"^(.+?)\s+(\d+)$", text)
        if trailing:
            return {"codigo": trailing.group(2), "descricao": normalize_text(trailing.group(1))}

        return {"codigo": None, "descricao": normalize_text(text)}

    def _to_standard_dataframe(self, records: list[dict[str, Any]]) -> pd.DataFrame:
        if not records:
            return pd.DataFrame(columns=STANDARD_COLUMNS)
        df = pd.DataFrame(records)
        for col in STANDARD_COLUMNS:
            if col not in df.columns:
                df[col] = None
        return df[STANDARD_COLUMNS]


class BalanceteStrategy(GenericAccountingStrategy):
    """Estratégia específica para Balancete de Verificação."""

    def can_handle(self, context: ParseContext) -> bool:
        return context.document_type == "BALANCETE"


class BalancoPatrimonialStrategy(GenericAccountingStrategy):
    """Estratégia específica para Balanço Patrimonial."""

    def can_handle(self, context: ParseContext) -> bool:
        return context.document_type == "BALANCO_PATRIMONIAL"


class DREStrategy(GenericAccountingStrategy):
    """Estratégia específica para Demonstração do Resultado (DRE)."""

    def can_handle(self, context: ParseContext) -> bool:
        return context.document_type == "DRE"


class AccountingStatementParser:
    """
    Parser especializado para documentos contábeis brasileiros.

    Fluxo:
    1. Extrai texto e detecta tipo de documento
    2. Extrai metadados do cabeçalho (empresa, CNPJ, período)
    3. Tenta extração tabular via PDFParser
    4. Seleciona estratégia de layout e padroniza colunas
    """

    def __init__(self) -> None:
        # Ordem importa: estratégias específicas antes da genérica
        self.strategies: list[DocumentLayoutStrategy] = [
            BalanceteStrategy(),
            BalancoPatrimonialStrategy(),
            DREStrategy(),
            GenericAccountingStrategy(),
        ]

    def parse(self, content: bytes, filename: str) -> tuple[pd.DataFrame, ParseContext]:
        """Extrai e padroniza documento contábil."""
        logger.info("Parsing documento contábil: %s", filename)

        raw_text = self._extract_text(content)
        context = ParseContext(
            raw_text=raw_text,
            document_type=detect_document_type(raw_text),
            header_metadata=extract_header_metadata(raw_text),
        )

        raw_df = self._extract_raw_dataframe(content, raw_text, filename)
        strategy = self._select_strategy(context)
        logger.info(
            "Documento identificado: %s | Estratégia: %s",
            context.document_type,
            strategy.__class__.__name__,
        )

        standardized = strategy.parse_dataframe(raw_df, context)
        if standardized.empty:
            raise FileParsingError(
                f"Não foi possível extrair dados contábeis de '{filename}'."
            )

        return standardized, context

    def standardize_dataframe(self,raw_df: pd.DataFrame,context: ParseContext,) -> pd.DataFrame:
      """Aplica a estratégia de layout adequada a um DataFrame já extraído(usado para Excel/CSV, que não passam pela extração de texto/PDF)."""
      strategy = self._select_strategy(context)
      logger.info(
          "Documento identificado (fonte tabular): %s | Estratégia: %s",
          context.document_type,
          strategy.__class__.__name__,
      )
      standardized = strategy.parse_dataframe(raw_df, context)
      if standardized.empty:
          # Estratégia não conseguiu padronizar — mantém dados originais
          # em vez de descartar o arquivo inteiro.
          logger.warning(
              "Padronização contábil vazia para DataFrame tabular; "
              "mantendo dados originais sem padronização."
          )
          return raw_df
      return standardized

    def _select_strategy(self, context: ParseContext) -> DocumentLayoutStrategy:
        for strategy in self.strategies:
            if strategy.can_handle(context):
                return strategy
        return self.strategies[-1]

    def _extract_text(self, content: bytes) -> str:
        try:
            import pdfplumber

            pages: list[str] = []
            with pdfplumber.open(BytesIO(content)) as pdf:
                for page in pdf.pages:
                    pages.append(page.extract_text() or "")
            return "\n".join(pages)
        except Exception:
            pass

        from PyPDF2 import PdfReader

        reader = PdfReader(BytesIO(content))
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    def _extract_raw_dataframe(
        self,
        content: bytes,
        raw_text: str,
        filename: str,
    ) -> pd.DataFrame:
        from dados.parser import PDFParser

        pdf_parser = PDFParser()
        try:
            return pdf_parser.parse(content, filename)
        except FileParsingError:
            # Sem tabelas — usa linhas de texto como entrada para heurísticas
            lines = [line for line in raw_text.splitlines() if line.strip()]
            return pd.DataFrame({"raw_line": lines})

    def register_strategy(self, strategy: DocumentLayoutStrategy) -> None:
        """Registra nova estratégia de layout antes do fallback genérico."""
        self.strategies.insert(-1, strategy)
