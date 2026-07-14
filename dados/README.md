# Módulo de entrada e tratamento de dados — Eduardo Pereira Silva

Responsável: **Eduardo Pereira Silva** (RA 202601009).

Esta pasta deve conter o código que recebe o arquivo enviado pelo usuário
(Excel, CSV ou PDF), padroniza contas, valores, datas, fornecedores e
produtos, e produz o DataFrame de lançamentos que o motor de análise
financeira consome.

O contrato exato de colunas esperadas pelo motor está documentado em
[`docs/CONTRATO_DADOS.md`](../docs/CONTRATO_DADOS.md) — use
`motor_analise.padronizar_categoria()` para normalizar a coluna
`categoria` no mesmo padrão usado pelo motor.

Exemplo de lançamentos já no formato esperado:
[`examples/dados_exemplo.csv`](../examples/dados_exemplo.csv).

## Leitura de balancete em PDF (`leitor_balancete.py`)

Já existe uma primeira versão funcionando: `ler_balancete_pdf(caminho)` lê um
balancete contábil em PDF e devolve o DataFrame de lançamentos direto,
reconstruindo a hierarquia de contas (sintéticas vs. analíticas) por
reconciliação de valores (uma identidade contábil universal, não depende do
sistema que gerou o balancete) e classificando cada conta analítica em
receita/despesa e categoria por palavras-chave. Veja o docstring do módulo e
a seção 2 de [`docs/CONTRATO_DADOS.md`](../docs/CONTRATO_DADOS.md) para os
detalhes do algoritmo. Testes em
[`tests/test_leitor_balancete.py`](../tests/test_leitor_balancete.py).

**Importante:** isso ainda não é um parser universal — a ordem em que o PDF
grava as colunas no texto varia de sistema contábil pra sistema contábil, e
só existem **dois layouts cadastrados** até agora (`_LAYOUTS_CONHECIDOS` em
`leitor_balancete.py`): o "reverso", validado contra um balancete real, e o
"natural" (ordem visual da tabela), testado só contra PDF sintético gerado
localmente — nenhum dos dois passou por um segundo balancete real ainda.
Um balancete de outro contador/sistema pode ter layout diferente dos dois e
falhar com `LeitorBalanceteError` — nesse caso, o ajuste é cadastrar um novo
layout a partir de um exemplo real (passo a passo no docstring do módulo),
não assumir que os layouts testados até agora são a regra geral.

Também vale a checagem de identidade contábil (`_validar_identidade_contabil`):
se a soma das contas devedoras não bater com a soma das credoras depois da
reconstrução de hierarquia, o parser falha alto em vez de arriscar um
número errado — cobre o caso em que um balancete lista as contas fora da
pré-ordem que o algoritmo de hierarquia espera.

Próximos passos naturais pra esse módulo: coletar balancetes reais de mais
contadores/sistemas pra cadastrar novos layouts, e ampliar/curar o
vocabulário de categorias com mais planos de conta reais.

### OCR (balancete escaneado/foto, sem camada de texto)

Se o PDF não tiver texto extraível (documento escaneado ou foto — comum
quando alguém tira foto do balancete impresso e converte pra PDF), o leitor
tenta OCR automaticamente antes de desistir: renderiza cada página como
imagem (`pypdfium2`) e roda o Tesseract (`pytesseract`) em cima. Precisa do
motor Tesseract instalado no sistema (não é só um pacote Python — no
Windows, `winget install --id UB-Mannheim.TesseractOCR`; no Linux,
`apt install tesseract-ocr`). Sem o Tesseract instalado, ou sem
`pytesseract`/`pypdfium2`, o parser levanta `LeitorBalanceteError` com
instrução de como instalar, em vez de travar com um erro confuso.

Por padrão o OCR roda em português (`por`) se o pacote de idioma estiver
instalado (`tessdata/por.traineddata` — baixe em
https://github.com/tesseract-ocr/tessdata), e cai pra inglês (`eng`, que
já vem em qualquer instalação do Tesseract) se não estiver. **Recomendado
instalar o pacote de português** — testei os dois: com português, o OCR
reconheceu um balancete sintético de teste perfeitamente; só com inglês,
o reconhecimento de alguns valores decimais saiu com espaço a mais
(`"58000, 00"` em vez de `"58000,00"`), quebrando a reconciliação de
algumas contas — nesse caso a checagem de identidade contábil pega o
problema e falha com erro claro, em vez de gerar números errados (não
tenta "adivinhar"/corrigir o número malformado).

## Pipeline ETL (Excel/CSV/PDF) — `upload_service.py` e módulos de apoio

Também existe um pipeline mais amplo (validação → parsing → limpeza →
normalização → categorização por JSON externo em `dados/config/`), com
`FinancialDataset` serializável e API FastAPI opcional (`dados/api.py`):

```python
from dados.upload_service import process_uploaded_file

dataset = process_uploaded_file(conteudo_em_bytes, "arquivo.xlsx")
dataset.to_dict()  # ou dataset.to_dataframe()
```

Estava com dois bugs que impediam qualquer coisa de rodar (corrigidos): os
imports internos apontavam para `backend.upload.*` em vez de `dados.*`, e
`categories.json`/`column_aliases.json` foram movidos para `dados/config/`
pra bater com o caminho que o código espera. Testado contra CSV (funciona
bem, categoriza automaticamente) e contra PDF (identifica corretamente
empresa/CNPJ/período/tipo de documento, mas a separação de
saldo anterior/débito/crédito/saldo atual em colunas própria ainda tem
arestas para PDFs — segue como próximo passo).

Este pipeline e o `leitor_balancete.py` continuam sendo dois caminhos
independentes e complementares para "entrada de dados": use
`ler_balancete_pdf` quando o objetivo é já chegar direto no formato de
lançamentos do motor a partir de um balancete em PDF; use
`process_uploaded_file` para Excel/CSV genéricos, ou quando precisar dos
metadados/estatísticas extras (empresa, CNPJ, gastos por fornecedor etc.)
que só o pipeline ETL calcula.
