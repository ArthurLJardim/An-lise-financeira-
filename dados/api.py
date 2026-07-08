"""
Integração com FastAPI para o módulo de upload ETL.

Camada de apresentação (Clean Architecture): recebe requisições HTTP,
delega o processamento ao UploadService e retorna FinancialDataset
serializado — nunca expõe DataFrames diretamente.
"""

from __future__ import annotations

from typing import Any # significa que o valor recebido pode ser de qualquer tipo
from fastapi import FastAPI, File, HTTPException, UploadFile       #FastAPI = cria servidor; File = indica para o FastAPI que é um arquivo; HTTPException = devolver erros; UploadFile = representa o arquivo enviado pelo usuário
from pydantic import BaseModel #verifica se a estrutura está correta

from backend.upload.exceptions import FileValidationError, UploadModuleError #erros personalizados
from backend.upload.models import FinancialDataset #objeto final / tudo que o parser produzir vai terminar nessa classe
from backend.upload.upload_service import process_uploaded_file

app = FastAPI(
    title="Módulo ETL Financeiro",
    description="Entrada, validação, tratamento e padronização de dados financeiros.",     #Criando API
    version="1.0.0",
)


class UploadResponse(BaseModel):
    """Envelope de resposta — separa sucesso/erro dos dados processados."""

    success: bool
    data: dict[str, Any]                #dicionário


@app.post("/upload", response_model=UploadResponse)
async def upload_file(file: UploadFile = File(...)) -> UploadResponse:              #recebe arquivo ; file:UploadFile representa o "PDF" inteiro; File(...) informa a API
    """
    Endpoint de upload e processamento de arquivos financeiros.
    Aceita .xlsx, .csv ou .pdf e retorna FinancialDataset via to_dict().
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Nome do arquivo não informado.") #o arquivo realmente foi enviado?
    content = await file.read()  #lê o arquivo
    try:
        dataset = process_uploaded_file(content, file.filename)
        return UploadResponse(success=True, data=dataset.to_dict())
    except FileValidationError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc
    except UploadModuleError as exc:
        raise HTTPException(status_code=422, detail=exc.message) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Erro interno no processamento: {exc}",
        ) from exc


@app.get("/health")
async def health_check() -> dict[str, str]:                             #Verificar se a API está funcionando
    """Verificação de saúde — usado por load balancers e CI."""
    return {"status": "ok", "module": "etl-upload"}
