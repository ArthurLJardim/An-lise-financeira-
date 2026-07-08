"""
Utilitários compartilhados do módulo de upload.

Funções puras reutilizadas por parser, normalizer e accounting_parser:
padronização de datas/valores, detecção de tipo de documento, mapeamento
de colunas e configurações externas (JSON).
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

# Caminhos fixos para configurações extensíveis e diretório de saída
CONFIG_DIR = Path(__file__).resolve().parent / "config"
OUTPUTS_DIR = Path(__file__).resolve().parent.parent / "outputs"

# Formatos de data comuns em documentos financeiros brasileiros
DATE_PATTERNS = [
    (re.compile(r"^(\d{2})/(\d{2})/(\d{2})$"), "%d/%m/%y"),
    (re.compile(r"^(\d{2})/(\d{2})/(\d{4})$"), "%d/%m/%Y"),
    (re.compile(r"^(\d{2})-(\d{2})-(\d{4})$"), "%d-%m-%Y"),
    (re.compile(r"^(\d{4})-(\d{2})-(\d{2})$"), "%Y-%m-%d"),
    (re.compile(r"^(\d{2})\.(\d{2})\.(\d{4})$"), "%d.%m.%Y"),
]

# Aceita R$, parênteses e hífen final como indicadores de valor negativo
MONETARY_PATTERN = re.compile(
    r"^\s*(?:R\$\s*)?"
    r"(?:\()?-?"
    r"(\d{1,3}(?:\.\d{3})*(?:,\d{2})?|\d+(?:,\d{2})?|\d+(?:\.\d{2})?)"
    r"-?\)?\s*[DCdc]?\s*$",
    re.IGNORECASE,
)

# Caracteres de controle inválidos em células de planilha
INVALID_CHARS_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

# Palavras-chave para identificar automaticamente o tipo de documento contábil
DOCUMENT_TYPE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("BALANCETE", re.compile(r"\bBALANCETE\b", re.IGNORECASE)),
    ("BALANCO_PATRIMONIAL", re.compile(r"\bBALAN[ÇC]O\s+PATRIMONIAL\b", re.IGNORECASE)),
    ("DRE", re.compile(r"\bDEMONSTRA[ÇC][AÃ]O\s+DO\s+RESULTADO\b|\bDRE\b", re.IGNORECASE)),
    ("LIVRO_RAZAO", re.compile(r"\bLIVRO\s+RAZ[AÃ]O\b", re.IGNORECASE)),
    ("LIVRO_DIARIO", re.compile(r"\bLIVRO\s+DI[AÁ]RIO\b", re.IGNORECASE)),
]

# Regex para extrair campos do cabeçalho de relatórios contábeis
HEADER_PATTERNS: dict[str, re.Pattern[str]] = {
    "empresa": re.compile(
        r"(?:empresa|raz[aã]o\s+social)\s*[:\-]?\s*(.+?)(?:\n|cnpj|$)",
        re.IGNORECASE,
    ),
    "cnpj": re.compile(r"\b(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}|\d{14})\b"),
    "periodo": re.compile(
        r"(?:per[ií]odo|compet[eê]ncia|refer[eê]ncia)\s*[:\-]?\s*(.+?)(?:\n|$)",
        re.IGNORECASE,
    ),
    "data_emissao": re.compile(
        r"(?:data\s+(?:de\s+)?emiss[aã]o|emitido\s+em)\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})",
        re.IGNORECASE,
    ),
    "numero_livro": re.compile(r"(?:livro|n[ºo]\.?\s+livro)\s*[:\-]?\s*(\d+)", re.IGNORECASE),
    "folha": re.compile(r"(?:folha|fl\.?)\s*[:\-]?\s*(\d+)", re.IGNORECASE),
    "sistema_emissor": re.compile(
        r"(?:sistema|software|gerado\s+por)\s*[:\-]?\s*(.+?)(?:\n|$)",
        re.IGNORECASE,
    ),
}


def setup_logger(name: str = "upload_module") -> logging.Logger:
    """Configura logger padrão — registra todas as etapas do pipeline."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


def load_json_config(filename: str) -> dict[str, Any]:
    """
    Carrega configuração externa (categorias, aliases de colunas).

    Mantém regras de negócio fora do código-fonte para facilitar extensão.
    """
    path = CONFIG_DIR / filename
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def normalize_text(value: Any) -> str:
    """
    Padroniza texto para comparação e categorização.

    Remove acentos, normaliza espaços e converte para maiúsculas.
    """
    if pd.isna(value) or value is None:
        return ""
    text = str(value).strip()
    text = INVALID_CHARS_PATTERN.sub("", text)
    text = re.sub(r"\s+", " ", text)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.upper()


def parse_date(value: Any) -> str | None:
    """Converte formatos brasileiros de data para o padrão ISO YYYY-MM-DD."""
    if pd.isna(value) or value is None or str(value).strip() == "":
        return None

    if isinstance(value, (datetime, pd.Timestamp)):
        return value.strftime("%Y-%m-%d")

    text = str(value).strip()
    for pattern, fmt in DATE_PATTERNS:
        if pattern.match(text):
            try:
                parsed = datetime.strptime(text, fmt)
                return parsed.strftime("%Y-%m-%d")
            except ValueError:
                continue
    return None


def parse_monetary(value: Any) -> float | None:
    """
    Converte valores monetários brasileiros para float.

    Suporta: R$ 2.350,50 | (250) | -250 | 250- | 92.553,10C | 250D
    O sufixo D/C (natureza) é apenas removido aqui — use extract_natureza()
    para capturar essa informação antes de chamar esta função.
    """
    if pd.isna(value) or value is None or str(value).strip() == "":
        return None

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    if not MONETARY_PATTERN.match(text):
        return None

    negative = text.startswith("(") or text.startswith("-") or text.endswith("-")
    cleaned = re.sub(r"[R$\s()]", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"[DCdc]$", "", cleaned)  # remove sufixo de natureza (D/C)
    cleaned = cleaned.rstrip("-")

    # Formato BR: 1.234,56 → ponto como separador de milhar, vírgula decimal
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    elif cleaned.count(".") > 1:
        parts = cleaned.split(".")
        cleaned = "".join(parts[:-1]) + "." + parts[-1]

    try:
        result = float(cleaned)
        return -abs(result) if negative else result
    except ValueError:
        return None


def extract_natureza(value: Any) -> str | None:
    """
    Detecta a natureza (D/C) a partir de um sufixo no valor monetário.

    Comum em balancetes brasileiros: '92.553,10C' significa saldo credor.
    Retorna None se não houver sufixo de natureza reconhecível.
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None

    text = str(value).strip().upper()
    match = re.search(r"\d\s*([DC])\s*$", text)
    return match.group(1) if match else None


def detect_document_type(text: str) -> str:
    """Identifica Balancete, DRE, Balanço etc. a partir do texto do documento."""
    for doc_type, pattern in DOCUMENT_TYPE_PATTERNS:
        if pattern.search(text):
            return doc_type
    return "DESCONHECIDO"


def extract_header_metadata(text: str) -> dict[str, str | None]:
    """Extrai empresa, CNPJ, período e demais dados do cabeçalho contábil."""
    metadata: dict[str, str | None] = {}
    for field, pattern in HEADER_PATTERNS.items():
        match = pattern.search(text)
        if match:
            metadata[field] = match.group(1).strip() if match.lastindex else match.group(0).strip()
        else:
            metadata[field] = None
    return metadata

def dataframe_preview_text(df: pd.DataFrame, max_rows: int = 15) -> str:
    """
    Converte um DataFrame em texto simples para detecção de tipo de
    documento e extração de cabeçalho (mesma lógica usada para PDFs).

    Usado quando o arquivo é Excel/CSV, que não passam por extração de texto.

    Analisa tanto o início quanto o fim do arquivo, já que informações de
    identificação (empresa, CNPJ, período) podem aparecer no topo ou no
    rodapé da planilha, dependendo do sistema que a exportou.

    Trata células vazias explicitamente (via pd.isna) em vez de depender
    do comportamento de DataFrame.astype(str), que mudou entre versões
    do pandas quanto à conversão de NaN.
    """
    if df.empty:
        return ""

    header_line = " ".join(str(col) for col in df.columns)

    if len(df) <= max_rows * 2:
        preview = df
    else:
        preview = pd.concat([df.head(max_rows), df.tail(max_rows)])

    rows_text = []
    for row in preview.itertuples(index=False, name=None):
        rows_text.append(" ".join("" if pd.isna(v) else str(v) for v in row))

    return header_line + "\n" + "\n".join(rows_text)


def map_column_names(columns: list[str], aliases: dict[str, list[str]]) -> dict[str, str]:
    """
    Unifica nomes de colunas equivalentes (ex.: 'Cod.' → 'codigo').

    Usa o dicionário externo column_aliases.json — nunca hardcoded.
    """
    mapping: dict[str, str] = {}
    normalized_aliases = {
        standard: [normalize_text(alias) for alias in alias_list]
        for standard, alias_list in aliases.items()
    }

    for col in columns:
        normalized_col = normalize_text(col)
        mapped = False
        for standard, alias_list in normalized_aliases.items():
            if normalized_col in alias_list or any(
                alias in normalized_col for alias in alias_list
            ):
                mapping[col] = standard
                mapped = True
                break
        if not mapped:
            mapping[col] = normalize_text(col).lower().replace(" ", "_")
    return mapping


def ensure_output_dirs() -> None:
    """Cria diretórios de saída (json/ e parquet/) se não existirem."""
    (OUTPUTS_DIR / "json").mkdir(parents=True, exist_ok=True)
    (OUTPUTS_DIR / "parquet").mkdir(parents=True, exist_ok=True)
