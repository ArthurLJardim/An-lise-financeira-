"""
Schemas Pydantic para validação de entrada e saída.

Define o contrato de dados entre as camadas do pipeline e garante que
a serialização para JSON/API seja consistente e tipada.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class FileType(str, Enum):
    """Formatos de arquivo aceitos no upload."""

    XLSX = "xlsx"
    CSV = "csv"
    PDF = "pdf"


class DocumentType(str, Enum):
    """Tipos de documentos contábeis brasileiros detectados automaticamente."""

    BALANCETE = "BALANCETE"
    BALANCO_PATRIMONIAL = "BALANCO_PATRIMONIAL"
    DRE = "DRE"
    LIVRO_RAZAO = "LIVRO_RAZAO"
    LIVRO_DIARIO = "LIVRO_DIARIO"
    GENERICO = "GENERICO"
    DESCONHECIDO = "DESCONHECIDO"


class ProcessingErrorRecord(BaseModel):
    """Erro em célula/linha específica — o pipeline continua após registrá-lo."""

    linha: int | None = None
    coluna: str | None = None
    erro: str
    motivo: str


class ProcessingWarning(BaseModel):
    """Aviso informativo (ex.: linhas removidas) que não impede o processamento."""

    linha: int | None = None
    coluna: str | None = None
    mensagem: str


class DatasetMetadata(BaseModel):
    """
    Metadados extraídos do arquivo e do cabeçalho contábil.

    Enriquece o dataset para que o módulo de IA saiba a origem dos dados
    sem precisar reanalisar o documento original.
    """

    empresa: str | None = None
    cnpj: str | None = None
    periodo: str | None = None
    data_emissao: str | None = None
    numero_livro: str | None = None
    folha: str | None = None
    sistema_emissor: str | None = None
    nome_arquivo: str
    data_upload: datetime
    tipo_arquivo: FileType
    document_type: DocumentType = DocumentType.DESCONHECIDO
    numero_registros: int = 0
    numero_colunas: int = 0
    tempo_processamento_segundos: float = 0.0


class DatasetStatistics(BaseModel):
    """Métricas de qualidade geradas durante o ETL."""

    linhas_validas: int = 0
    linhas_invalidas: int = 0
    duplicatas_removidas: int = 0
    valores_ausentes: int = 0
    categorias_identificadas: list[str] = Field(default_factory=list)
    total_gastos_fornecedores: float = 0.0
    gastos_por_fornecedor: list[dict[str, Any]] = Field(default_factory=list)


class FinancialDatasetSchema(BaseModel):
    """
    Formato final serializável consumido pela API e pelo módulo de IA.

    Agrupa metadados, estatísticas, erros/avisos e os registros limpos.
    """

    metadata: DatasetMetadata
    statistics: DatasetStatistics
    warnings: list[ProcessingWarning] = Field(default_factory=list)
    errors: list[ProcessingErrorRecord] = Field(default_factory=list)
    records: list[dict[str, Any]] = Field(default_factory=list)
