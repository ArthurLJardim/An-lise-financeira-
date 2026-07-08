"""
Módulo de upload, validação e ETL de dados financeiros.

Responsabilidade exclusiva: receber arquivos, tratá-los e entregar
dados limpos via FinancialDataset. Não realiza análise financeira
nem utiliza Inteligência Artificial.

Ponto de integração para o módulo de IA:
    dataset = process_uploaded_file(bytes, "arquivo.csv")
    payload = dataset.to_dict()
"""

from backend.upload.models import FinancialDataset
from backend.upload.upload_service import UploadService, process_uploaded_file

__all__ = ["FinancialDataset", "UploadService", "process_uploaded_file"]
