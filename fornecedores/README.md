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

## Estado atual

[`recomendacoes.py`](recomendacoes.py) já implementa isso e está ligado ao
`interface/interface.py` do Miguel:

```python
from fornecedores.recomendacoes import gerar_recomendacoes

recomendacoes = gerar_recomendacoes(resultado.alertas, lancamentos)
# DataFrame: fornecedor, categoria, severidade, acao_recomendada, economia_estimada
```

Por alerta (categoria com estouro), sugere uma ação por palavra-chave de
categoria (mercadorias → cotar fornecedores alternativos; energia → auditar
consumo/mercado livre; aluguel → renegociar locação; etc.), prioriza pela
severidade e estima a economia como o quanto a categoria gastou acima da
referência (orçamento ou histórico). A lógica de ação-por-categoria foi
adaptada de [`analisador_balancete_standalone.py`](analisador_balancete_standalone.py)
— o script original de João Thiago, que também continua aqui como
ferramenta independente (lê seu próprio CSV/Excel e não depende do motor).

**Ainda não existe** uma base de fornecedores alternativos cadastrados — a
recomendação hoje é a ação a tomar (ex.: "cotar com 2-3 fornecedores"), não
o nome de um fornecedor concreto. Testes em
[`tests/test_recomendacoes.py`](../tests/test_recomendacoes.py).
