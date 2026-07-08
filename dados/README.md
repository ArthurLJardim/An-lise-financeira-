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
