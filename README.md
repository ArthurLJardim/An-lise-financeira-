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

Já implementado nesta pasta. Recebe os lançamentos tratados (etapa 2, com
receitas e despesas de um balancete/DRE) e devolve:

- se a empresa está tendo **lucro ou prejuízo** no período, e a margem;
- **onde** ela está gastando mais do que o esperado (rankings de gastos por
  categoria/fornecedor/produto e variações contra orçamento e/ou histórico);
- **alertas** classificados por severidade (baixa/média/alta/crítica);
- sugestões preliminares de **onde economizar**, a partir dos alertas.

```python
from motor_analise import AnaliseFinanceira

engine = AnaliseFinanceira()
resultado = engine.analisar(lancamentos_df, orcamento=orcamento_df, historico=historico_df, periodo="2026-06")

resultado.resultado_contabil  # lucro/prejuízo, receita total, despesa total, margem
resultado.resumo              # cards de resumo de gastos
resultado.rankings            # maiores gastos por categoria/fornecedor/produto
resultado.variacoes           # variação por categoria vs orçamento/histórico
resultado.alertas             # alertas ordenados por severidade
resultado.to_dict()           # formato JSON para interface e recomendações
```

O contrato de dados completo (colunas de entrada, formato de saída) está
em [`docs/CONTRATO_DADOS.md`](docs/CONTRATO_DADOS.md) — é o que os demais
módulos devem seguir para integrar sem alterações no motor.

### Relatório em tópicos (.txt / Bloco de Notas)

Além da saída estruturada, o motor gera um relatório em texto, por
tópicos (resultado do período, resumo de gastos, onde a empresa gasta
mais, alertas e onde economizar), e pode abri-lo direto no Bloco de Notas:

```bash
python analisar_documento.py caminho/lancamentos.xlsx --orcamento caminho/orcamento.csv --periodo "2026-06"
```

O arquivo `lancamentos` (`.xlsx` ou `.csv`) precisa já estar no formato do
contrato de dados. Enquanto o módulo de tratamento de dados do Eduardo não
está pronto, essa é a forma de testar a análise ponta a ponta.

## Rodando localmente

```bash
pip install -r requirements.txt

# exemplo end-to-end com dados sintéticos (gera .txt em relatorios/)
python examples/exemplo_uso.py

# analisar um arquivo próprio e abrir o relatório no Bloco de Notas
python analisar_documento.py examples/dados_exemplo.csv --orcamento examples/orcamento_exemplo.csv

# testes do motor de análise financeira
pytest
```

## Estrutura do repositório

```
docs/                contrato de dados entre os módulos
motor_analise/        motor de análise financeira (Arthur)
dados/                 entrada e tratamento dos dados (Eduardo)
fornecedores/           análise de fornecedores e recomendações (João Thiago)
interface/              interface, relatórios e apresentação (Miguel)
examples/              dados sintéticos e script de uso end-to-end
tests/                  testes automatizados
analisar_documento.py  CLI: analisa um arquivo e gera o relatório .txt
relatorios/            saída dos relatórios gerados (não versionado)
```
