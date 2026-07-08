# Módulo de análise de fornecedores e recomendações de economia — João Thiago Peixoto Luzine

Responsável: **João Thiago Peixoto Luzine** (RA 202601034).

Esta pasta deve conter o código que, a partir da saída do motor de
análise financeira (`ResultadoAnalise`/`resultado.to_dict()`), sugere
renegociação com fornecedores atuais, indica fornecedores alternativos
cadastrados e estima a economia possível (o card "economia estimada" da
interface).

Dados já disponíveis no resultado do motor que este módulo pode usar
diretamente, sem recalcular nada:

- `rankings["por_fornecedor"]` — gasto total e participação de cada
  fornecedor, para identificar concentração e prioridade de negociação.
- `variacoes` — categorias com maior estouro de orçamento/histórico, para
  priorizar onde a renegociação traz mais economia.
- `alertas` — já filtrados por severidade, útil para decidir quais casos
  merecem recomendação automática vs. apenas informativa.

Contrato completo em [`docs/CONTRATO_DADOS.md`](../docs/CONTRATO_DADOS.md).
