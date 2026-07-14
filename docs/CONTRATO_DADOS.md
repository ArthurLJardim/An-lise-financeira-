# Contrato de dados — Motor de Análise Financeira

Este documento define a interface entre o **motor de análise financeira** (Arthur)
e os demais módulos do projeto. Enquanto os módulos de Eduardo, João Thiago e
Miguel não existem, o motor foi construído contra este contrato — qualquer
implementação futura que o respeite deve integrar sem alterações no `motor_analise`.

## 1. Entrada real — o que a empresa envia

A empresa **não** prepara uma planilha de lançamentos já categorizados. O que ela
envia é o **balancete** (ou DRE) exportado direto do sistema contábil — em PDF ou
Excel.

Importante: um balancete é gerado por um sistema contábil (ou escritório de
contabilidade) diferente para cada empresa — o layout exato do PDF (colunas,
ordem, fonte, se tem ou não um "código" de conta) varia de sistema para
sistema e **não é padronizado**. O bot precisa funcionar independente de
qual sistema gerou o balancete, então o contrato de entrada é definido pelo
que é **universal em qualquer balancete** (essa identidade vale pra
qualquer plano de contas, de qualquer contador), não pelo formato de um
exemplo específico:

| Conceito                          | Universal? | Descrição                                                          |
|------------------------------------|:----------:|---------------------------------------------------------------------|
| Descrição da conta                 | sim        | Nome da conta (ex.: "FORNECEDORES", "ENERGIA ELÉTRICA", "SERVIÇOS PRESTADOS") |
| Saldo, com natureza devedora/credora | sim      | O valor da conta no período, e se é `D` (devedor) ou `C` (credor)   |
| Saldo anterior / débito / crédito  | geralmente, mas não essencial | Detalha a movimentação; o bot usa isso só como conferência (saldo anterior + débito − crédito = saldo atual), não como dado necessário |
| Código da conta                    | **não**    | Numeração interna definida pelo contador/sistema que gerou o balancete — não é um padrão universal, só ajuda a delimitar onde termina a descrição no texto do PDF |

Um balancete mistura **contas sintéticas** (totalizadoras, ex.: `PASSIVO CIRCULANTE`)
e **contas analíticas** (as que recebem lançamento de fato, ex.: um fornecedor
específico ou "SERVIÇOS PRESTADOS"). Só as contas analíticas do período representam
receita/despesa reais; as sintéticas são apenas a soma das contas abaixo delas e
não devem ser contadas — contar as duas geraria valores duplicados. Essa distinção
sintética/analítica também é universal (vale pra qualquer plano de contas), então é
nela que o parser se apoia — ver seção 2.

## 2. Tratamento — do balancete para lançamentos internos (Eduardo, `dados/`)

É responsabilidade do módulo de tratamento de dados (Eduardo):

1. Ler o balancete (PDF ou Excel) enviado pela empresa.
2. Identificar as contas analíticas do período (ignorando as sintéticas/totalizadoras).
3. Classificar cada conta em receita ou despesa e em uma categoria padronizada
   (`mercadorias`, `energia`, `aluguel`, `folha`, `transporte`, `servicos`, `impostos`, `outros`),
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
valor dela; senão, é uma conta analítica (folha) e vira um lançamento. Essa parte
é independente do sistema contábil que gerou o PDF (é uma identidade contábil,
seção 1). A classificação em receita/despesa/categoria usa palavras-chave na
conta e nos seus ancestrais (ex.: uma conta sob "FORNECEDORES" vira despesa;
sob "RECEITA..." vira receita).

A parte que **de fato varia** de sistema contábil pra sistema contábil é em que
ordem o PDF grava as colunas dentro do texto (não necessariamente a ordem
visual da tabela — ver o docstring de `dados/leitor_balancete.py` pra
detalhes). Por isso o parser mantém um registro de layouts conhecidos
(`_LAYOUTS_CONHECIDOS`) e escolhe automaticamente qual bate usando a
reconciliação de valores como critério — **três layouts cadastrados até
agora**: o "reverso" e o "classificado" (ambos validados contra três
balancetes reais, de dois contadores/sistemas diferentes), e o "natural"
(a ordem visual da própria tabela, testado só contra PDF sintético — ainda
sem confirmação num balancete real). Isso não é um parser universal pronto;
é uma arquitetura pensada pra virar universal conforme mais exemplos reais
(de outros contadores/sistemas) forem aparecendo — quando um balancete vier
de um sistema diferente e nenhum layout bater, o parser falha alto
(`LeitorBalanceteError`) em vez de arriscar números errados, e o ajuste é
cadastrar um novo layout a partir desse exemplo real (passo a passo no
docstring do módulo), não redesenhar em cima dos poucos casos conhecidos.

O layout "classificado" traz uma coluna de classificação hierárquica
(código com pontos, ex.: `3.1.5.01.00002`) — quando presente, a hierarquia
sintética/analítica é reconstruída a partir desse código (uma conta é
folha quando nenhuma outra classificação começa com o prefixo dela + ".")
em vez de reconciliação de valores. É mais robusto (não depende da ordem
em que o balancete lista as contas), mas só se aplica quando o balancete
traz essa coluna — nos outros layouts, continua valendo a reconciliação
por valor.

Além da reconciliação por conta, há uma segunda camada de segurança:
`_validar_identidade_contabil` confere se o total das contas devedoras
bate com o total das credoras depois da reconstrução de hierarquia — uma
identidade contábil universal (débito total = crédito total, em qualquer
balancete válido) que pega o caso em que um balancete lista as contas fora
da pré-ordem que o algoritmo de hierarquia assume, e que de outra forma
passaria silenciosamente com números errados.

Outras limitações conhecidas:

- O balancete não tem data por lançamento — todos os lançamentos gerados usam
  a data de fim do período (extraída do cabeçalho do PDF).
- Planos de contas muito diferentes do usual (nomes de conta fora do
  vocabulário de palavras-chave) podem cair em `categoria = "outros"` ou não
  ser reconhecidos como receita/despesa — ajustar as palavras-chave em
  `dados/leitor_balancete.py` conforme aparecerem casos novos. O vocabulário
  já cobre um plano de contas brasileiro razoavelmente amplo (energia,
  aluguel, folha, transporte, serviços, impostos, mercadorias).
- PDF sem camada de texto (documento escaneado/foto) cai automaticamente em
  OCR (Tesseract via `pytesseract`/`pypdfium2`) — precisa do motor Tesseract
  instalado no sistema; sem ele, erro claro em vez de travar. Ver
  `dados/README.md`.
- Contas de rateio dentro de custo/despesa que têm duas pontas de naturezas
  opostas (ex.: `"(-) ESTOQUE INICIAL"`/`"(+) ESTOQUE FINAL"` dentro de
  CUSTOS DOS PRODUTOS VENDIDOS, onde CPV = estoque inicial + compras −
  estoque final) não têm como ser somadas corretamente sem suporte a valor
  com sinal no contrato de lançamentos (seção 3 exige `valor` sempre
  positivo). O parser exclui as duas pontas de estoque inicial/final em vez
  de somar só uma como se fosse o custo inteiro do período (o que já
  causou, num balancete real, uma despesa de estoque contado sozinho — R$
  91,68 milhões — virar um "prejuízo" fictício de R$ 92 milhões numa
  empresa que teve lucro de verdade). Outras contas de rateio/crédito
  recuperável mais específicas do plano de contas (ex.: IPI/ICMS
  recuperável sobre compras) ainda podem gerar uma pequena distorção
  residual — o parser não tenta identificar e nettar todo padrão de rateio
  possível, só o de estoque inicial/final por ser um item padrão de DRE.

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

`mercadorias`, `energia`, `aluguel`, `folha`, `transporte`, `servicos`, `impostos`, `outros`

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
