"""
Módulo de entrada e tratamento de dados (Eduardo).

Duas frentes independentes, cada uma importável sem depender da outra:

- `dados.leitor_balancete` — lê balancete em PDF direto para o formato de
  lançamentos que o `motor_analise` consome (ver docs/CONTRATO_DADOS.md).
  Só depende de `pypdf`/`pandas`.
- `dados.upload_service` (+ accounting_parser/cleaner/normalizer/validator/
  parser/schemas/models) — pipeline ETL mais amplo (Excel/CSV/PDF,
  detecção de tipo de documento, categorização por JSON externo,
  `FinancialDataset` serializável) com API FastAPI em `dados.api`.
  Depende de `pydantic` (e opcionalmente `fastapi`, `pdfplumber`/`PyPDF2`).

Este pacote propositalmente não importa a pipeline ETL aqui no
`__init__.py`: isso permitiria fazer `from dados import FinancialDataset`
como atalho, mas faria QUALQUER `import dados` (inclusive só pra usar
`dados.leitor_balancete`) exigir `pydantic` instalado. Prefira importar
direto do submódulo que precisar, ex.:

    from dados.leitor_balancete import ler_balancete_pdf
    from dados.upload_service import process_uploaded_file
"""
