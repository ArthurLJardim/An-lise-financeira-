# Analisador Inteligente de Balancetes

Projeto em Python que lê um balancete contábil em PDF, identifica os
fornecedores e sua movimentação financeira, e gera uma análise completa
com indicadores, ranking, categorização automática de gastos e
recomendações práticas — em relatório de terminal, Excel (.xlsx) e
gráficos (.png).

Feito para ler os balancetes gerados por sistemas contábeis brasileiros
(o exemplo de referência foi emitido pelo Domínio Sistemas), mas o motor
de análise e recomendação funciona com qualquer balancete no formato
padrão "Código / Descrição / Saldo Anterior / Débito / Crédito / Saldo
Atual".

---

## 1. Instalação

Requer Python 3.9+.

```bash
pip install -r requirements.txt
```

Isso instala:
- **pdfplumber** — leitura do PDF
- **openpyxl** — geração do relatório Excel
- **matplotlib** — geração dos gráficos .png (opcional: se não estiver
  instalado, o programa continua funcionando, só sem essa saída)

## 2. Uso

### Um único balancete

```bash
python main.py caminho/do/balancete.pdf
```

Isso vai:
1. Imprimir um relatório completo no terminal (indicadores, ranking de
   fornecedores, gastos por categoria, recomendações).
2. Salvar em `relatorios/`:
   - `analise_<empresa>.xlsx` — relatório completo em Excel
   - `graficos/ranking_fornecedores.png` e `graficos/categorias.png`
   - `relatorio_<empresa>.txt` — o mesmo conteúdo do terminal, em arquivo

### Comparando dois ou mais períodos

```bash
python main.py balancete_2024.pdf balancete_2025.pdf
```

Quando mais de um arquivo é informado, o programa identifica o período de
cada um (pela data no cabeçalho do balancete), ordena do mais antigo para
o mais recente e adiciona ao relatório uma seção de comparação: quais
fornecedores cresceram, caíram, surgiram ou desapareceram entre o período
mais antigo e o mais recente do lote. As recomendações passam a incluir
alertas sobre essas variações.

### Opções

```
python main.py --help

  BALANCETE.pdf        Um ou mais arquivos PDF (informe 2+ para comparar períodos)
  --saida PASTA         Pasta de saída dos relatórios (padrão: ./relatorios)
  --top N                Quantos fornecedores mostrar no ranking do console (padrão: 15)
  --sem-excel              Não gera o arquivo .xlsx
  --sem-graficos            Não gera os arquivos .png
  --sem-console              Não imprime no terminal (útil para rodar em lote/CI)
```

---

## 3. Estrutura do projeto

```
analisador_balancete/
├── main.py               # CLI — ponto de entrada
├── extrator.py            # Lê o PDF e devolve dados estruturados
├── modelos.py               # Dataclasses: Empresa, ContaContabil, Fornecedor, Balancete
├── categorizador.py           # Classifica fornecedores por categoria de gasto
├── analisador.py                # Indicadores, ranking, curva ABC, índice HHI, comparação de períodos
├── recomendador.py                # Motor de recomendações baseado em regras
├── relatorio_console.py             # Saída formatada para terminal
├── relatorio_excel.py                 # Geração do .xlsx (openpyxl)
├── graficos.py                          # Geração dos .png (matplotlib)
├── utils.py                               # Formatação de moeda/percentual no padrão BR
└── requirements.txt
```

Cada camada só conhece a interface da anterior (o extrator não sabe nada
sobre Excel, o motor de recomendações não sabe nada sobre PDF), então dá
para trocar qualquer peça — por exemplo, ler de uma planilha em vez de
PDF, ou adicionar uma saída em HTML — sem reescrever o resto.

---

## 4. Como a extração do PDF funciona (e por que ela precisou ser "esperta")

Balancetes gerados por alguns sistemas contábeis (o de referência deste
projeto é do Domínio Sistemas) têm uma característica traiçoeira: por
baixo de boa parte das linhas da tabela, o gerador do relatório desenha
uma segunda camada de texto idêntica ao conteúdo da própria linha,
deslocada verticalmente por menos de 1 ponto — invisível a olho nu, mas
suficiente para confundir qualquer extração de texto ingênua. O resultado
de um `pdf.extract_text()` comum nesse tipo de arquivo é lixo do tipo:

```
ATIVO2 CIRACTUIVLOA CNITRECULANTE   0,00   163.853,58   0,00   163.853,58D
```

...em vez de `2  ATIVO CIRCULANTE  0,00  163.853,58  0,00  163.853,58D`.

Em vez de tentar "consertar" esse texto com expressões regulares
heurísticas (abordagem frágil — foi o que um protótipo anterior tentou
fazer, com resultados inconsistentes), `extrator.py` resolve o problema na
raiz, trabalhando com a posição geométrica de cada caractere do PDF:

1. Cada caractere carrega sua coordenada exata (x, y).
2. Os caracteres são agrupados por linha de base (com alta precisão —
   grupos que diferem por menos de 1 ponto continuam separados).
3. Uma linha de dados **real** sempre estende até a área das colunas de
   valores monetários (a "camada fantasma" nunca contém números — ela é
   só um rótulo). Isso dá um critério simples e muito confiável para
   separar sinal de ruído.
4. Descartamos todo grupo que não alcança essa área e reconstruímos o
   texto só com os grupos válidos, linha a linha.

O resultado é uma extração perfeitamente limpa, validada linha por linha
contra o PDF de exemplo (23 contas contábeis e 4 fornecedores extraídos
com 100% de acerto, incluindo nomes longos que quebram em várias linhas
visuais e nomes com números embutidos).

Se o seu balancete vier de outro sistema (sem essa peculiaridade), o
algoritmo simplesmente não encontra nada para descartar — ele se comporta
como uma extração de texto comum, sem precisar de um "modo B" separado.

**Limitação conhecida:** PDFs digitalizados (uma foto/scan da folha, sem
camada de texto) não são suportados — seria necessário OCR, que está fora
do escopo deste projeto.

---

## 5. O que significa "gasto" neste relatório

Um balancete mostra o **saldo em aberto** de cada fornecedor (quanto
ainda se deve na data de fechamento) — não necessariamente o total
comprado dele durante o ano, porque parte da dívida pode já ter sido paga.

Por isso, o projeto calcula duas métricas separadas para cada fornecedor:

- **Saldo em aberto** (`saldo_atual`): quanto ainda está pendente de
  pagamento na data-base. Relevante para fluxo de caixa e liquidez.
- **Movimentação no período** (`débito + crédito` lançados na conta):
  uma aproximação melhor de "quanto foi negociado com esse fornecedor no
  ano", inclusive o que já foi pago. É essa métrica que o ranking, a
  curva ABC e a categorização usam como base — é a que responde melhor à
  pergunta "com quem eu mais gasto".

No balancete de exemplo fornecido, os dois valores coincidem (não há
pagamentos registrados no período), mas em balancetes com movimentação
de caixa ao longo do ano essa distinção passa a importar bastante.

---

## 6. Personalizando

### Categorias de fornecedores

Edite o dicionário `REGRAS_CATEGORIA` em `categorizador.py`. Cada entrada
é `"Nome da Categoria": ["PALAVRA1", "PALAVRA2", ...]` — a primeira
categoria cuja palavra-chave aparecer no nome do fornecedor é escolhida.

### Regras de recomendação

Cada regra em `recomendador.py` é um método `_regra_*` independente que
recebe o resultado da análise e devolve uma lista de `Recomendacao` (ou
uma lista vazia, se não se aplicar). Para adicionar uma regra nova, basta
escrever o método e registrá-lo em `_todas_as_regras`.

### Palavras que marcam o fim da lista de fornecedores

O extrator identifica onde a lista de fornecedores termina procurando a
próxima conta que pareça ser um "grupo" (ex.: `PATRIMÔNIO LÍQUIDO`,
`RECEITA BRUTA`). Essa lista de palavras-chave fica em
`PALAVRAS_FIM_DE_GRUPO`, em `extrator.py` — vale revisar se o seu plano de
contas usa nomes de grupo diferentes.

---

## 7. Limitações e honestidade sobre o escopo

- A categorização de fornecedores é por palavra-chave no nome, não por
  machine learning — funciona bem para nomes de empresa descritivos
  ("HIGH-TECH INFORMÁTICA"), mas pode cair em "Outros / Não classificado"
  para razões sociais genéricas.
- O balancete de exemplo não tem uma conta de Despesas detalhada (comum
  em empresas que lançam custos de forma simplificada) — quando isso
  acontece, o relatório sinaliza isso explicitamente na recomendação de
  "margem líquida aparente muito alta", em vez de simplesmente reportar
  um número enganoso sem contexto.
- O algoritmo de "fim de grupo" para identificar a lista de fornecedores
  é heurístico. Para a grande maioria dos planos de contas brasileiros
  ele funciona bem, mas balancetes muito fora do padrão podem precisar de
  ajuste na lista `PALAVRAS_FIM_DE_GRUPO`.
