# Módulo de interface, relatórios e apresentação — Miguel Cruzeiro Pinheiro

Responsável: **Miguel Cruzeiro Pinheiro** (RA 202600428).

Esta pasta deve conter a interface (upload de arquivo, filtros de mês/
categoria/fornecedor, cards de resumo, gráfico de maiores gastos, tabela
de alertas, tabela de fornecedores) e a geração de relatório final em PDF
ou Excel, conforme o esboço do documento de proposta do projeto.

Toda a interface deve ser alimentada por `resultado.to_dict()`, retornado
pelo motor de análise financeira — não recalcule nada que o motor já
fornece. Estrutura do dicionário e exemplo de uso completo em
[`docs/CONTRATO_DADOS.md`](../docs/CONTRATO_DADOS.md) e
[`examples/exemplo_uso.py`](../examples/exemplo_uso.py).

Os cards de resumo do esboço mapeiam assim:

| Card               | Fonte                                                   |
|---------------------|----------------------------------------------------------|
| Gasto total          | `resultado.resumo["gasto_total"]`                        |
| Maior aumento         | `resultado.resumo["maior_aumento"]`                       |
| Economia estimada    | `fornecedores.recomendacoes.gerar_recomendacoes(...)`  |

## Estado atual

[`interface.py`](interface.py) já implementa isso em Streamlit — upload
(PDF/Excel/CSV), filtros de mês/categoria/fornecedor, cards de resumo,
gráfico de gastos por categoria (Plotly), tabela de alertas e tabela de
recomendações, ligado a `motor_analise`, `dados.leitor_balancete` e
`fornecedores.recomendacoes`.

```bash
streamlit run interface/interface.py
```

Testado manualmente ponta a ponta (upload de lançamentos + orçamento →
alertas → recomendações → gráfico), sem erros no console. Falta ligar os
botões de exportação (Excel/PDF) — hoje desabilitados — a
`motor_analise.relatorio.gerar_relatorio`.
