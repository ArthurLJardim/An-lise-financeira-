"""
Validação de arquivos enviados pelo usuário.

Primeira etapa do pipeline: garante que o arquivo existe, tem extensão
suportada, tamanho aceitável e não está corrompido antes de qualquer parsing.
"""

from __future__ import annotations

import zipfile
from io import BytesIO
from pathlib import Path
from typing import BinaryIO

from dados.exceptions import FileValidationError, UnsupportedFileTypeError
from dados.schemas import FileType
from dados.utils import setup_logger

logger = setup_logger(__name__)

SUPPORTED_EXTENSIONS = {".xlsx", ".csv", ".pdf"}
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB


class FileValidator:
    """
    Valida extensão, tamanho, existência e integridade de arquivos.

    Falha cedo (fail-fast) para evitar processamento desnecessário
    de arquivos inválidos ou corrompidos.
    """

    def __init__(self, max_size_bytes: int = MAX_FILE_SIZE_BYTES) -> None:
        self.max_size_bytes = max_size_bytes

    def validate(
        self,
        file_content: bytes | BinaryIO,
        filename: str,
    ) -> FileType:
        """
        Executa todas as validações e retorna o tipo do arquivo.

        Raises:
            FileValidationError: Quando qualquer validação falha.
            UnsupportedFileTypeError: Quando extensão não é suportada.
        """
        logger.info("Iniciando validação do arquivo: %s", filename)

        if not filename or not filename.strip():
            raise FileValidationError("Nome do arquivo não informado.")

        path = Path(filename)
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            raise UnsupportedFileTypeError(
                f"Extensão '{path.suffix}' não suportada. "
                f"Use: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
            )

        content = self._read_content(file_content)
        if not content:
            raise FileValidationError("Arquivo vazio ou inexistente.")

        self._validate_size(content, filename)
        file_type = self._resolve_file_type(path.suffix.lower())
        self._validate_integrity(content, file_type, filename)
        self._validate_readability(content, file_type, filename)

        logger.info("Validação concluída com sucesso: %s", filename)
        return file_type

    def _read_content(self, file_content: bytes | BinaryIO) -> bytes:
        if isinstance(file_content, bytes):
            return file_content
        return file_content.read()

    def _validate_size(self, content: bytes, filename: str) -> None:
        size = len(content)
        if size > self.max_size_bytes:
            raise FileValidationError(
                f"Arquivo '{filename}' excede o tamanho máximo permitido "
                f"({self.max_size_bytes // (1024 * 1024)} MB).",
                details={"size_bytes": size},
            )

    def _resolve_file_type(self, extension: str) -> FileType:
        mapping = {
            ".xlsx": FileType.XLSX,
            ".csv": FileType.CSV,
            ".pdf": FileType.PDF,
        }
        return mapping[extension]

    def _validate_integrity(
        self,
        content: bytes,
        file_type: FileType,
        filename: str,
    ) -> None:
        # .xlsx é um ZIP internamente — testzip detecta corrupção estrutural
        if file_type == FileType.XLSX:
            try:
                with zipfile.ZipFile(BytesIO(content)) as archive:
                    if archive.testzip() is not None:
                        raise FileValidationError(
                            f"Arquivo Excel '{filename}' está corrompido."
                        )
            except zipfile.BadZipFile as exc:
                raise FileValidationError(
                    f"Arquivo Excel '{filename}' está corrompido ou inválido."
                ) from exc

        elif file_type == FileType.PDF:
            if not content.startswith(b"%PDF"):
                raise FileValidationError(
                    f"Arquivo PDF '{filename}' não possui cabeçalho válido."
                )

    def _validate_readability(
        self,
        content: bytes,
        file_type: FileType,
        filename: str,
    ) -> None:
        """Tenta abrir o arquivo com a biblioteca nativa do formato."""
        try:
            if file_type == FileType.CSV:
                text = content.decode("utf-8")
                if not text.strip():
                    raise FileValidationError(f"CSV '{filename}' não contém dados legíveis.")
            elif file_type == FileType.XLSX:
                import openpyxl

                openpyxl.load_workbook(BytesIO(content), read_only=True)
            elif file_type == FileType.PDF:
                from PyPDF2 import PdfReader

                reader = PdfReader(BytesIO(content))
                if len(reader.pages) == 0:
                    raise FileValidationError(f"PDF '{filename}' não possui páginas legíveis.")
        except FileValidationError:
            raise
        except UnicodeDecodeError:
            # CSVs brasileiros frequentemente usam latin-1/cp1252
            try:
                content.decode("latin-1")
            except UnicodeDecodeError as exc:
                raise FileValidationError(
                    f"Arquivo '{filename}' possui codificação não legível."
                ) from exc
        except Exception as exc:
            raise FileValidationError(
                f"Arquivo '{filename}' não pôde ser lido: {exc}"
            ) from exc
