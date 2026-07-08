# Bot de Análise Financeira e Compras

Bot para leitura de balancetes, análise de gastos, identificação de
desperdícios e apoio a decisões de economia. Recebe um balancete, DRE ou
planilha financeira, organiza os dados por categoria (mercadorias,
energia, aluguel, folha, transporte, serviços), compara com histórico ou
orçamento e aponta onde a empresa gasta mais do que o esperado, sugerindo
renegociação com fornecedores e fornecedores alternativos.

## Grupo — Análise Financeira

| Integrante                  | RA         | Módulo                                            |
|------------------------------|------------|-----------------------------------------------------|
| Eduardo Pereira Silva         | 202601009  | [`dados/`](dados/) — entrada e tratamento dos dados |
| **Arthur Lopes Jardim**       | 202600412  | [`motor_analise/`](motor_analise/) — motor de análise financeira |
| João Thiago Peixoto Luzine    | 202601034  | [`fornecedores/`](fornecedores/) — análise de fornecedores e recomendações de economia |
| Miguel Cruzeiro Pinheiro      | 202600428  | [`interface/`](interface/) — interface, relatórios e apresentação |

## Como funciona

1. **Upload** — usuário envia arquivo Excel, CSV ou PDF com dados financeiros.
2. **Tratamento** — sistema padroniza contas, valores, datas, fornecedores e produtos.
3. **Análise** — motor calcula variações, rankings de gastos e alertas por severidade.
4. **Recomendação** — bot sugere economia, renegociação e fornecedores alternativos.
5. **Resultado** — interface exibe tabelas, gráficos, alertas e relatório final.

## Motor de análise financeira (`motor_analise/`)

Já implementado nesta pasta. Recebe os lançamentos tratados (etapa 2) e
devolve resumo, rankings de gastos, variações contra orçamento/histórico
e alertas classificados por severidade (baixa/média/alta/crítica) —
insumo para as etapas 4 e 5.

```python
from motor_analise import AnaliseFinanceira

engine = AnaliseFinanceira()
resultado = engine.analisar(lancamentos_df, orcamento=orcamento_df, historico=historico_df, periodo="2026-06")

resultado.resumo       # cards de resumo
resultado.rankings     # maiores gastos por categoria/fornecedor/produto
resultado.variacoes    # variação por categoria vs orçamento/histórico
resultado.alertas      # alertas ordenados por severidade
resultado.to_dict()    # formato JSON para interface e recomendações
```

O contrato de dados completo (colunas de entrada, formato de saída) está
em [`docs/CONTRATO_DADOS.md`](docs/CONTRATO_DADOS.md) — é o que os demais
módulos devem seguir para integrar sem alterações no motor.

## Rodando localmente

```bash
pip install -r requirements.txt

# exemplo end-to-end com dados sintéticos
python examples/exemplo_uso.py

# testes do motor de análise financeira
pytest
```

## Estrutura do repositório

```
docs/               contrato de dados entre os módulos
motor_analise/       motor de análise financeira (Arthur)
dados/                entrada e tratamento dos dados (Eduardo)
fornecedores/          análise de fornecedores e recomendações (João Thiago)
interface/             interface, relatórios e apresentação (Miguel)
examples/             dados sintéticos e script de uso end-to-end
tests/                 testes automatizados
```
