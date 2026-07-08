"""
Parsers genéricos para Excel, CSV e PDF.

Responsável pela extração inicial: converte qualquer formato de entrada
em um DataFrame pandas, que será tratado pelas etapas seguintes do ETL.

Todos os parsers implementam a mesma interface (BaseParser) e retornam
exatamente o mesmo tipo de saída.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any

import pandas as pd

from backend.upload.exceptions import FileParsingError
from backend.upload.utils import setup_logger

logger = setup_logger(__name__)


class BaseParser(ABC):
    """Contrato único — garante que todo parser retorna DataFrame."""

    @abstractmethod
    def parse(self, content: bytes, filename: str) -> pd.DataFrame:
        """Extrai dados brutos e retorna DataFrame."""


class ExcelParser(BaseParser):
    """Lê planilhas .xlsx via openpyxl."""

    def parse(self, content: bytes, filename: str) -> pd.DataFrame:
        logger.info("Parsing Excel: %s", filename)
        try:
            df = pd.read_excel(BytesIO(content), engine="openpyxl")
            return self._ensure_dataframe(df, filename)
        except Exception as exc:
            raise FileParsingError(f"Erro ao ler Excel '{filename}': {exc}") from exc

    def _ensure_dataframe(self, df: pd.DataFrame, filename: str) -> pd.DataFrame:
        if df.empty:
            raise FileParsingError(f"Excel '{filename}' não contém dados.")
        df.columns = [str(col).strip() for col in df.columns]
        return df


class CSVParser(BaseParser):
    """
    Lê CSV com detecção automática de encoding e separador.

    Tenta combinações comuns em exportações brasileiras (utf-8/latin-1, ;/,).
    """

    def parse(self, content: bytes, filename: str) -> pd.DataFrame:
        logger.info("Parsing CSV: %s", filename)
        for encoding in ("utf-8", "latin-1", "cp1252"):
            for sep in (";", ",", "\t", "|"):
                try:
                    text = content.decode(encoding)
                    df = pd.read_csv(StringIO(text), sep=sep)
                    if len(df.columns) > 1:
                        df.columns = [str(col).strip() for col in df.columns]
                        return df
                except Exception:
                    continue
        raise FileParsingError(f"Não foi possível interpretar CSV '{filename}'.")


class PDFParser(BaseParser):
    """
    Parser genérico para PDFs simples.

    Ordem de extração tabular (conforme especificação):
    1. pdfplumber  2. Camelot  3. Tabula  4. fallback texto + regex
    """

    def parse(self, content: bytes, filename: str) -> pd.DataFrame:
        logger.info("Parsing PDF genérico: %s", filename)
        text = self._extract_text(content, filename)
        tables = self._extract_tables(content, filename)

        if tables:
            return pd.concat(tables, ignore_index=True)

        # Sem tabelas detectadas — reconstrói colunas a partir do texto
        return self._text_to_dataframe(text, filename)

    def _extract_text(self, content: bytes, filename: str) -> str:
        try:
            import pdfplumber

            pages_text: list[str] = []
            with pdfplumber.open(BytesIO(content)) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text() or ""
                    pages_text.append(page_text)
            return "\n".join(pages_text)
        except ImportError:
            logger.warning("pdfplumber não disponível, usando PyPDF2")
        except Exception as exc:
            logger.warning("pdfplumber falhou: %s", exc)

        try:
            from PyPDF2 import PdfReader

            reader = PdfReader(BytesIO(content))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as exc:
            raise FileParsingError(f"Erro ao extrair texto de PDF '{filename}': {exc}") from exc

    def _extract_tables(self, content: bytes, filename: str) -> list[pd.DataFrame]:
        tables: list[pd.DataFrame] = []

        try:
            import pdfplumber

            with pdfplumber.open(BytesIO(content)) as pdf:
                for page in pdf.pages:
                    page_tables = page.extract_tables() or []
                    for table in page_tables:
                        if table and len(table) > 1:
                            header = [str(h or f"col_{i}") for i, h in enumerate(table[0])]
                            rows = table[1:]
                            df = pd.DataFrame(rows, columns=header)
                            tables.append(df)
        except Exception as exc:
            logger.warning("Extração tabular pdfplumber falhou: %s", exc)

        if not tables:
            tables.extend(self._try_camelot(content))
        if not tables:
            tables.extend(self._try_tabula(content))

        return tables

    def _try_camelot(self, content: bytes) -> list[pd.DataFrame]:
        """Camelot funciona bem em PDFs com bordas de tabela visíveis."""
        try:
            import camelot

            temp_path = Path("/tmp") / "temp_pdf_parse.pdf"
            temp_path.write_bytes(content)
            result = camelot.read_pdf(str(temp_path), pages="all", flavor="lattice")
            temp_path.unlink(missing_ok=True)
            return [table.df for table in result]
        except Exception as exc:
            logger.debug("Camelot indisponível ou falhou: %s", exc)
            return []

    def _try_tabula(self, content: bytes) -> list[pd.DataFrame]:
        """Tabula como alternativa quando Camelot não extrai tabelas."""
        try:
            import tabula

            temp_path = Path("/tmp") / "temp_pdf_tabula.pdf"
            temp_path.write_bytes(content)
            dfs = tabula.read_pdf(str(temp_path), pages="all", multiple_tables=True)
            temp_path.unlink(missing_ok=True)
            return [df for df in dfs if df is not None and not df.empty]
        except Exception as exc:
            logger.debug("Tabula indisponível ou falhou: %s", exc)
            return []

    def _text_to_dataframe(self, text: str, filename: str) -> pd.DataFrame:
        """
        Último recurso: divide linhas de texto em colunas por espaçamento.

        Usado quando nenhuma ferramenta tabular consegue extrair estrutura.
        """
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            raise FileParsingError(f"PDF '{filename}' não contém texto extraível.")

        rows: list[dict[str, Any]] = []
        for line in lines:
            parts = re.split(r"\s{2,}|\t", line)
            if len(parts) == 1:
                parts = line.split()
            row = {f"col_{i}": part for i, part in enumerate(parts)}
            rows.append(row)

        return pd.DataFrame(rows)


def get_parser(file_type: str) -> BaseParser:
    """Factory — seleciona o parser correto sem expor a lógica ao chamador."""
    parsers = {
        "xlsx": ExcelParser(),
        "csv": CSVParser(),
        "pdf": PDFParser(),
    }
    parser = parsers.get(file_type.lower())
    if parser is None:
        raise FileParsingError(f"Parser não encontrado para tipo: {file_type}")
    return parser
