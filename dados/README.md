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
só existe **um layout cadastrado** até agora (`_LAYOUTS_CONHECIDOS` em
`leitor_balancete.py`), validado contra um único balancete real de teste.
Um balancete de outro contador/sistema pode ter layout diferente e falhar
com `LeitorBalanceteError` — nesse caso, o ajuste é cadastrar um novo layout
a partir de um exemplo real (a arquitetura já foi pensada pra isso), não
assumir que o layout testado até agora é a regra geral.

Próximos passos naturais pra esse módulo: coletar balancetes reais de mais
contadores/sistemas pra cadastrar novos layouts, leitura de balancete em
Excel, e ampliar/curar o vocabulário de categorias com mais planos de conta
reais.
