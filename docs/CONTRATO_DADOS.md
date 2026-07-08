# Contrato de dados — Motor de Análise Financeira

Este documento define a interface entre o **motor de análise financeira** (Arthur)
e os demais módulos do projeto. Enquanto os módulos de Eduardo, João Thiago e
Miguel não existem, o motor foi construído contra este contrato — qualquer
implementação futura que o respeite deve integrar sem alterações no `motor_analise`.

## 1. Entrada — vindo do módulo de tratamento de dados (Eduardo)

O motor espera um `pandas.DataFrame` de **lançamentos financeiros**, um por
linha, com as colunas abaixo.

### Colunas obrigatórias

| Coluna       | Tipo               | Descrição                                                        |
|--------------|--------------------|--------------------------------------------------------------------|
| `data`       | `datetime` ou `str` (`YYYY-MM-DD`) | Data do lançamento                                 |
| `categoria`  | `str`              | Categoria padronizada (ver lista abaixo)                          |
| `fornecedor` | `str`              | Nome do fornecedor/beneficiário                                   |
| `valor`      | `float`            | Valor do gasto, sempre positivo                                   |

### Colunas opcionais

| Coluna           | Tipo    | Descrição                                          |
|------------------|---------|-----------------------------------------------------|
| `tipo`           | `str`   | `"receita"` ou `"despesa"`. Ausente = tratado como `"despesa"` (compatível com o uso original de compras). Necessário para o motor calcular lucro/prejuízo. |
| `produto`        | `str`   | Produto/item específico do lançamento               |
| `descricao`      | `str`   | Texto livre / histórico do lançamento                |
| `forma_pagamento`| `str`   | Ex.: boleto, pix, cartão                             |

Para lançamentos de receita, a coluna `fornecedor` representa o
cliente/canal de venda (ex.: "Vendas Balcão"), não um fornecedor de fato —
o nome da coluna é reaproveitado para manter um único formato de tabela.

### Categorias padrão reconhecidas

`mercadorias`, `energia`, `aluguel`, `folha`, `transporte`, `servicos`, `outros`

Categorias fora dessa lista não quebram o motor (são tratadas como uma
categoria qualquer), mas o ideal é que o módulo de tratamento de dados
padronize para esses valores (minúsculo, sem acento) sempre que possível.
Use `motor_analise.modelos.padronizar_categoria()` para normalizar strings
antes de montar o DataFrame, se necessário.

### Bases de comparação (opcionais, uma ou ambas)

- **Orçamento/limites** — `pandas.DataFrame` com colunas `categoria`, `limite`.
  Define o teto de gasto esperado por categoria no período.
- **Histórico** — `pandas.DataFrame` no mesmo formato dos lançamentos, referente
  a um período anterior. Usado para comparar a variação atual contra o passado
  quando não há orçamento definido (ou em conjunto com ele).

Pelo menos uma das duas deve ser passada para o motor gerar variações e
alertas; sem nenhuma, o motor ainda retorna resumo e rankings, só não gera
`variacoes`/`alertas`.

## 2. Saída — consumida por Miguel (interface/relatórios) e João Thiago (recomendações)

O motor retorna um `motor_analise.ResultadoAnalise` com:

- `resultado_contabil: dict` — `receita_total`, `despesa_total`, `resultado`
  (receita − despesa), `situacao` (`"lucro"` | `"prejuizo"` | `"equilibrio"`)
  e `margem_percentual` (`None` se não houver receita). Calculado sobre
  **todos** os lançamentos (receita + despesa).
- `resumo: dict` — cards de resumo de gasto (gasto total, maior aumento, nº
  de alertas, período). Calculado apenas sobre despesas.
- `rankings: dict[str, pandas.DataFrame]` — chaves `"por_categoria"`,
  `"por_fornecedor"`, `"por_produto"` (se houver coluna `produto`).
  Calculado apenas sobre despesas.
- `variacoes: pandas.DataFrame` — uma linha por categoria de despesa
  comparada, com `valor_atual`, `valor_referencia`, `variacao_absoluta`,
  `variacao_percentual`, `base_comparacao` (`"orcamento"` ou `"historico"`).
- `alertas: list[motor_analise.Alerta]` — um alerta por estouro relevante,
  com `severidade` em `"baixa" | "media" | "alta" | "critica"`.

Todo `ResultadoAnalise` tem `.to_dict()`, que devolve uma estrutura 100%
JSON-serializável (DataFrames viram listas de dicts). É esse formato que
Miguel deve consumir na interface e que pode ser salvo/exportado.

`economia estimada` (um dos cards do esboço da interface) **não** é
calculada pelo motor — é resultado das recomendações de fornecedores do
João Thiago. O motor expõe os dados (rankings por fornecedor, variações)
que o módulo dele precisa para estimar essa economia. O motor gera, no
entanto, sugestões preliminares de onde economizar (baseadas nos alertas
de alta/crítica severidade) como parte do relatório em texto — ver seção 4.

## 3. Exemplo mínimo end-to-end

Veja [`examples/exemplo_uso.py`](../examples/exemplo_uso.py) e os dados
sintéticos em [`examples/dados_exemplo.csv`](../examples/dados_exemplo.csv),
[`examples/historico_exemplo.csv`](../examples/historico_exemplo.csv) e
[`examples/orcamento_exemplo.csv`](../examples/orcamento_exemplo.csv).

## 4. Relatório em texto (`motor_analise.relatorio`)

Além da saída estruturada, o motor gera um relatório em texto por tópicos
(resultado do período, resumo de gastos, onde a empresa gasta mais,
alertas e onde economizar), pensado para o usuário final ler diretamente,
sem depender da interface do Miguel:

```python
from motor_analise.relatorio import gerar_relatorio

caminho = gerar_relatorio(resultado)  # salva .txt em relatorios/ e abre no Bloco de Notas
```

Uso via linha de comando, apontando para um arquivo de lançamentos já
tratado (`.xlsx` ou `.csv`):

```bash
python analisar_documento.py caminho/lancamentos.xlsx --orcamento caminho/orcamento.csv --periodo "2026-06"
```
