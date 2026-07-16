# Bot de Análise Financeira e Compras

Bot para leitura de balancetes, análise de gastos, identificação de
desperdícios e apoio a decisões de economia. Recebe um balancete, DRE ou
planilha financeira, organiza os dados por categoria (mercadorias,
energia, aluguel, folha, transporte, serviços), compara com histórico ou
orçamento e aponta onde a empresa gasta mais do que o esperado, sugerindo
renegociação com fornecedores e fornecedores alternativos.

## Como testar (professor)

Forma mais simples, sem digitar comando nenhum:

1. Instale as dependências uma vez, dando duplo-clique em
   [`instalar_dependencias.bat`](instalar_dependencias.bat) (precisa de
   [Python](https://www.python.org/downloads/) instalado, com a opção "Add
   Python to PATH" marcada na instalação).
2. Coloque um balancete em **PDF** dentro da pasta [`entrada/`](entrada/).
3. Dê duplo-clique em [`rodar_bot.bat`](rodar_bot.bat).

O bot lê o balancete, analisa e abre um relatório em texto (lucro/prejuízo,
onde a empresa mais gasta, alertas, sugestões de economia) direto no Bloco
de Notas — nenhuma planilha precisa ser preparada antes.

Quem preferir rodar por terminal (ex.: no VS Code, `` Ctrl+` ``) pode usar
`python rodar_bot.py`, ou `python analisar_documento.py caminho/balancete.pdf`
para mais opções (orçamento, histórico, rótulo de período — ver seção
"Relatório em tópicos" abaixo). Também dá pra rodar a interface visual com
`streamlit run interface/interface.py` (abre no navegador, local).

## Grupo — Análise Financeira

| Integrante                  | RA         | Módulo                                            |
|------------------------------|------------|-----------------------------------------------------|
| Eduardo Pereira Silva         | 202601009  | [`dados/`](dados/) — entrada e tratamento dos dados |
| **Arthur Lopes Jardim**       | 202600412  | [`motor_analise/`](motor_analise/) — motor de análise financeira |
| João Thiago Peixoto Luzine    | 202601034  | [`fornecedores/`](fornecedores/) — análise de fornecedores e recomendações de economia |
| Miguel Cruzeiro Pinheiro      | 202600428  | [`interface/`](interface/) — interface, relatórios e apresentação |

## Como funciona

1. **Upload** — usuário envia o balancete (ou DRE) exportado do sistema contábil, em PDF ou Excel.
2. **Tratamento** — sistema lê o balancete e padroniza contas, valores, datas e fornecedores em lançamentos de receita/despesa por categoria.
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
python analisar_documento.py caminho/balancete.pdf --orcamento caminho/orcamento.csv --periodo "2026-06"
```

O comando já lê o balancete em **PDF** direto ([`dados/leitor_balancete.py`](dados/leitor_balancete.py))
e converte pra lançamentos automaticamente — não é preciso preparar planilha
nenhuma. Também aceita um arquivo já tratado (`.xlsx`/`.csv`) no formato
interno descrito em [`docs/CONTRATO_DADOS.md`](docs/CONTRATO_DADOS.md), útil
para dados sintéticos de teste.

## Recomendações de fornecedores (`fornecedores/`)

[`fornecedores/recomendacoes.py`](fornecedores/recomendacoes.py) consome os
`alertas` do motor e sugere ação por categoria (cotar fornecedor alternativo,
renegociar aluguel, auditar consumo de energia etc.), com prioridade pela
severidade e uma estimativa de economia (quanto a categoria gastou acima da
referência). Também existe
[`fornecedores/analisador_balancete_standalone.py`](fornecedores/analisador_balancete_standalone.py),
um script independente (não integrado ao motor) útil para analisar um CSV/Excel avulso fora do fluxo do bot.

## Interface (`interface/`)

App em Streamlit ([`interface/interface.py`](interface/interface.py)): upload
do balancete (PDF/Excel/CSV), filtros por mês/categoria/fornecedor, cards de
resumo, gráfico de gastos por categoria, tabela de alertas e tabela de
recomendações — já ligado ao motor, ao leitor de balancete e ao módulo de
recomendações.

```bash
streamlit run interface/interface.py
```

## Rodando localmente

```bash
pip install -r requirements.txt

# exemplo end-to-end com dados sintéticos (gera .txt em relatorios/)
python examples/exemplo_uso.py

# analisar um arquivo próprio e abrir o relatório no Bloco de Notas
python analisar_documento.py examples/dados_exemplo.csv --orcamento examples/orcamento_exemplo.csv

# interface web (upload, filtros, gráficos, alertas, recomendações)
streamlit run interface/interface.py

# testes automatizados (motor, leitor de balancete, recomendações)
pytest
```

## Estrutura do repositório

```
docs/                contrato de dados entre os módulos
motor_analise/        motor de análise financeira (Arthur)
dados/                 entrada e tratamento dos dados (Eduardo) — lê balancete em PDF/Excel/CSV
fornecedores/           recomendações de economia e fornecedores (João Thiago)
interface/              interface Streamlit (Miguel)
examples/              dados sintéticos e script de uso end-to-end
tests/                  testes automatizados
analisar_documento.py  CLI: analisa um arquivo e gera o relatório .txt
relatorios/            saída dos relatórios gerados (não versionado)
```
