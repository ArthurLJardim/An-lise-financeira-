# Contrato de dados — Motor de Análise Financeira

Este documento define a interface entre o **motor de análise financeira** (Arthur)
e os demais módulos do projeto. Enquanto os módulos de Eduardo, João Thiago e
Miguel não existem, o motor foi construído contra este contrato — qualquer
implementação futura que o respeite deve integrar sem alterações no `motor_analise`.

## 1. Entrada real — o que a empresa envia

A empresa **não** prepara uma planilha de lançamentos já categorizados. O que ela
envia é o **balancete** (ou DRE) exportado direto do sistema contábil — em PDF ou
Excel —, no formato tradicional de plano de contas:

| Coluna                | Descrição                                                          |
|------------------------|---------------------------------------------------------------------|
| `código`               | Código da conta contábil (ex.: `1`, `164`, `1008`)                  |
| `descrição da conta`   | Nome da conta (ex.: "FORNECEDORES", "ENERGIA ELÉTRICA", "SERVIÇOS PRESTADOS") |
| `saldo anterior`       | Saldo da conta no início do período                                 |
| `débito` / `crédito`   | Movimentação da conta dentro do período                             |
| `saldo atual`          | Saldo final, com natureza `D` (devedor) ou `C` (credor)             |

Um balancete mistura **contas sintéticas** (totalizadoras, ex.: `PASSIVO CIRCULANTE`)
e **contas analíticas** (as que recebem lançamento de fato, ex.: um fornecedor
específico ou "SERVIÇOS PRESTADOS"). Só as contas analíticas do período representam
receita/despesa reais; as sintéticas são apenas a soma das contas abaixo delas e
não devem ser contadas — contar as duas geraria valores duplicados.

## 2. Tratamento — do balancete para lançamentos internos (Eduardo, `dados/`)

É responsabilidade do módulo de tratamento de dados (Eduardo):

1. Ler o balancete (PDF ou Excel) enviado pela empresa.
2. Identificar as contas analíticas do período (ignorando as sintéticas/totalizadoras).
3. Classificar cada conta em receita ou despesa e em uma categoria padronizada
   (`mercadorias`, `energia`, `aluguel`, `folha`, `transporte`, `servicos`, `outros`),
   a partir da descrição da conta e/ou do nome do fornecedor.
4. Gerar o `pandas.DataFrame` de **lançamentos** descrito na seção 3 — esse sim é o
   contrato interno consumido pelo motor.

Existe uma primeira versão disso pronta e funcionando em
[`dados/leitor_balancete.py`](../dados/leitor_balancete.py) — `ler_balancete_pdf(caminho)`
lê um balancete em PDF e devolve direto o DataFrame de lançamentos, sem nenhuma
conversão manual. [`analisar_documento.py`](../analisar_documento.py) já usa isso
automaticamente quando o arquivo passado é um `.pdf`.

Como funciona, resumidamente: o balancete não traz a profundidade/indentação de
cada conta de forma confiável no PDF, então a hierarquia sintética/analítica é
reconstruída por **reconciliação de valores** — uma conta é sintética quando uma
sequência contígua de contas seguintes (mesma natureza D/C) soma exatamente o
valor dela; senão, é uma conta analítica (folha) e vira um lançamento. A
classificação em receita/despesa/categoria usa palavras-chave na conta e nos
seus ancestrais (ex.: uma conta sob "FORNECEDORES" vira despesa; sob
"RECEITA..." vira receita). Limitações conhecidas:

- O balancete não tem data por lançamento — todos os lançamentos gerados usam
  a data de fim do período (extraída do cabeçalho do PDF).
- Planos de contas muito diferentes do usual (nomes de conta fora do
  vocabulário de palavras-chave) podem cair em `categoria = "outros"` ou não
  ser reconhecidos como receita/despesa — ajustar as palavras-chave em
  `dados/leitor_balancete.py` conforme aparecerem casos novos.
- Layout de PDF muito diferente do testado (outro sistema contábil) pode falhar
  na extração; nesse caso o parser levanta `LeitorBalanceteError` com uma
  mensagem explicando o problema, em vez de gerar números errados.

## 3. Contrato interno — lançamentos (entrada do `motor_analise`)

O motor espera um `pandas.DataFrame` de **lançamentos financeiros**, já tratados
a partir do balancete, um por linha, com as colunas abaixo.

### Colunas obrigatórias

| Coluna       | Tipo               | Descrição                                                        |
|--------------|--------------------|--------------------------------------------------------------------|
| `data`       | `datetime` ou `str` (`YYYY-MM-DD`) | Data do lançamento (quando o balancete não traz data por conta, usar a data de fechamento do período) |
| `categoria`  | `str`              | Categoria padronizada (ver lista abaixo)                          |
| `fornecedor` | `str`              | Nome do fornecedor/beneficiário (a conta analítica do balancete)  |
| `valor`      | `float`            | Valor do gasto, sempre positivo                                   |

### Colunas opcionais

| Coluna           | Tipo    | Descrição                                          |
|------------------|---------|-------------------------------------------------------|
| `tipo`           | `str`   | `"receita"` ou `"despesa"`. Ausente = tratado como `"despesa"`. Necessário para o motor calcular lucro/prejuízo. |
| `produto`        | `str`   | Produto/item específico do lançamento, quando existir (balancete normalmente não tem esse nível de detalhe) |
| `descricao`      | `str`   | Nome da conta contábil de origem no balancete            |
| `forma_pagamento`| `str`   | Ex.: boleto, pix, cartão                             |

Para lançamentos de receita, a coluna `fornecedor` representa o
cliente/canal de venda (ex.: "Clientes - Prestação de Serviços"), não um
fornecedor de fato — o nome da coluna é reaproveitado para manter um único
formato de tabela.

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
  a um período anterior (tipicamente o balancete do mês/ano anterior, já tratado
  do mesmo jeito). Usado para comparar a variação atual contra o passado quando
  não há orçamento definido (ou em conjunto com ele).

Pelo menos uma das duas deve ser passada para o motor gerar variações e
alertas; sem nenhuma, o motor ainda retorna resumo e rankings, só não gera
`variacoes`/`alertas`.

## 4. Saída — consumida por Miguel (interface/relatórios) e João Thiago (recomendações)

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
de alta/crítica severidade) como parte do relatório em texto — ver seção 6.

## 5. Exemplo mínimo end-to-end

Veja [`examples/exemplo_uso.py`](../examples/exemplo_uso.py) e os dados
sintéticos em [`examples/dados_exemplo.csv`](../examples/dados_exemplo.csv),
[`examples/historico_exemplo.csv`](../examples/historico_exemplo.csv) e
[`examples/orcamento_exemplo.csv`](../examples/orcamento_exemplo.csv).

Atenção: esses CSVs já estão no formato **interno** da seção 3 (pós-tratamento),
não no formato de balancete da seção 1 — eles simulam a saída que o módulo do
Eduardo deve produzir a partir do balancete real da empresa.

## 6. Relatório em texto (`motor_analise.relatorio`)

Além da saída estruturada, o motor gera um relatório em texto por tópicos
(resultado do período, resumo de gastos, onde a empresa gasta mais,
alertas e onde economizar), pensado para o usuário final ler diretamente,
sem depender da interface do Miguel:

```python
from motor_analise.relatorio import gerar_relatorio

caminho = gerar_relatorio(resultado)  # salva .txt em relatorios/ e abre no Bloco de Notas
```

Uso via linha de comando, apontando direto para o balancete em PDF:

```bash
python analisar_documento.py caminho/balancete.pdf --orcamento caminho/orcamento.csv --periodo "2026-06"
```

Também funciona com um arquivo já tratado (`.xlsx`/`.csv`, seção 3), útil para
dados sintéticos de teste.
