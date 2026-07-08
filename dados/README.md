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
reconciliação de valores e classificando cada conta analítica em
receita/despesa e categoria por palavras-chave. Veja o docstring do módulo e
a seção 2 de [`docs/CONTRATO_DADOS.md`](../docs/CONTRATO_DADOS.md) para os
detalhes do algoritmo e as limitações conhecidas (sem data por lançamento,
vocabulário de categorias limitado, layout de outro sistema contábil pode
precisar de ajuste). Testes em
[`tests/test_leitor_balancete.py`](../tests/test_leitor_balancete.py).

Próximos passos naturais pra esse módulo: leitura de balancete em Excel,
ampliar/curar o vocabulário de categorias com mais planos de conta reais, e
tratar casos em que a reconciliação de valores falha (hoje levanta erro em
vez de arriscar números errados).
