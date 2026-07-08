"""
Exceções customizadas do módulo de upload e ETL.

Centraliza os erros do pipeline em uma hierarquia tipada, permitindo que
a API e outros consumidores tratem cada falha de forma adequada (400 vs 422).
"""

# ---------------------------------------------------------------------------
# Hierarquia base — todas as exceções do módulo herdam desta classe
# ---------------------------------------------------------------------------


class UploadModuleError(Exception):
    """Exceção base do módulo de upload."""

    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class FileValidationError(UploadModuleError):
    """Arquivo rejeitado antes do parsing (extensão, tamanho, corrupção)."""


class FileParsingError(UploadModuleError):
    """Arquivo válido, mas conteúdo não pôde ser interpretado."""


class DataProcessingError(UploadModuleError):
    """Falha durante limpeza ou normalização dos dados."""


class UnsupportedFileTypeError(FileValidationError):
    """Extensão fora do conjunto permitido (.xlsx, .csv, .pdf)."""
