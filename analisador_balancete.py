#!/usr/bin/env python3
"""
Analisador de Balancete Empresarial
------------------------------------
Le um balancete (CSV ou Excel), calcula variacoes entre periodos,
gera ranking de gastos, alertas por severidade e recomendacoes de
economia / renegociacao / fornecedores alternativos.

USO:
    python analisador_balancete.py caminho/para/balancete.csv
    python analisador_balancete.py caminho/para/balancete.xlsx --saida relatorio.txt

FORMATO ESPERADO DO ARQUIVO DE ENTRADA (nomes de coluna flexiveis):
    conta / categoria / descricao          -> nome da conta ou centro de custo
    atual / valor_atual / mes_atual        -> valor do periodo atual
    anterior / valor_anterior / mes_anterior -> valor do periodo anterior

Se as colunas nao forem encontradas automaticamente, o script pede
para o usuario informar os nomes/indices corretos (ou use --conta,
--atual, --anterior para especificar direto).

Requisitos: pip install pandas openpyxl
"""

import argparse
import sys
import os
from datetime import datetime

try:
    import pandas as pd
except ImportError:
    print("Este script requer a biblioteca pandas.")
    print("Instale com: pip install pandas openpyxl")
    sys.exit(1)


# ----------------------------- Configuracoes -----------------------------

# Limiares de severidade para variacao percentual (em modulo)
SEVERIDADE_ALTA = 30.0    # variacao >= 30% -> ALTA
SEVERIDADE_MEDIA = 15.0   # variacao >= 15% -> MEDIA (abaixo disso -> BAIXA)

# Palavras-chave usadas para direcionar o tipo de recomendacao
PALAVRAS_FORNECEDOR = ["fornecedor", "material", "insumo", "compra", "mercadoria", "materia"]
PALAVRAS_SERVICO = ["servico", "serviço", "manutencao", "manutenção", "consultoria", "terceir"]
PALAVRAS_ENERGIA = ["energia", "luz", "eletric"]
PALAVRAS_ALUGUEL = ["aluguel", "locacao", "locação", "imovel", "imóvel"]
PALAVRAS_FOLHA = ["folha", "salario", "salário", "pessoal", "encargo", "beneficio", "benefício"]
PALAVRAS_MARKETING = ["marketing", "publicidade", "propaganda", "midia", "mídia"]


# ----------------------------- Funcoes auxiliares -----------------------------

def detectar_colunas(df):
    """Tenta identificar automaticamente as colunas relevantes do balancete."""
    colunas = {c.lower().strip(): c for c in df.columns}

    def achar(opcoes):
        for op in opcoes:
            for chave, original in colunas.items():
                if op in chave:
                    return original
        return None

    col_conta = achar(["conta", "categoria", "descricao", "descrição", "centro de custo", "centro_custo"])
    col_atual = achar(["atual", "periodo_atual", "mes_atual", "valor_atual", "corrente"])
    col_anterior = achar(["anterior", "periodo_anterior", "mes_anterior", "valor_anterior", "passado"])

    return col_conta, col_atual, col_anterior


def pedir_colunas_manual(df):
    print("\nNao consegui identificar automaticamente todas as colunas necessarias.")
    print("Colunas disponiveis no arquivo:")
    for i, c in enumerate(df.columns):
        print(f"  [{i}] {c}")

    def escolher(msg):
        while True:
            try:
                idx = int(input(msg))
                return df.columns[idx]
            except (ValueError, IndexError):
                print("Opcao invalida, tente novamente.")

    col_conta = escolher("Digite o numero da coluna de CONTA/CATEGORIA: ")
    col_atual = escolher("Digite o numero da coluna do VALOR ATUAL: ")
    col_anterior = escolher("Digite o numero da coluna do VALOR ANTERIOR: ")
    return col_conta, col_atual, col_anterior


def carregar_balancete(caminho):
    ext = os.path.splitext(caminho)[1].lower()
    if ext in [".xlsx", ".xls"]:
        df = pd.read_excel(caminho)
    elif ext == ".csv":
        try:
            df = pd.read_csv(caminho, sep=None, engine="python")
        except Exception:
            df = pd.read_csv(caminho)
    else:
        raise ValueError("Formato de arquivo nao suportado. Use .csv, .xlsx ou .xls")
    return df


def classificar_severidade(variacao_pct):
    v = abs(variacao_pct)
    if v >= SEVERIDADE_ALTA:
        return "ALTA"
    elif v >= SEVERIDADE_MEDIA:
        return "MEDIA"
    else:
        return "BAIXA"


def sugerir_recomendacao(nome_conta, variacao_pct, severidade):
    nome = str(nome_conta).lower()
    recomendacoes = []

    if variacao_pct <= 0:
        return ["Gasto em queda ou estavel - nenhuma acao urgente necessaria."]

    if any(p in nome for p in PALAVRAS_FORNECEDOR):
        recomendacoes.append("Cotar precos com pelo menos 2-3 fornecedores alternativos.")
        recomendacoes.append("Negociar prazos de pagamento e descontos por volume com o fornecedor atual.")
    if any(p in nome for p in PALAVRAS_SERVICO):
        recomendacoes.append("Revisar contrato de prestacao de servico e buscar propostas concorrentes.")
    if any(p in nome for p in PALAVRAS_ENERGIA):
        recomendacoes.append("Avaliar migracao para mercado livre de energia ou fontes alternativas.")
        recomendacoes.append("Auditar consumo e identificar equipamentos ineficientes.")
    if any(p in nome for p in PALAVRAS_ALUGUEL):
        recomendacoes.append("Renegociar valor de locacao ou avaliar espacos alternativos.")
    if any(p in nome for p in PALAVRAS_FOLHA):
        recomendacoes.append("Revisar estrutura de cargos, horas extras e beneficios.")
    if any(p in nome for p in PALAVRAS_MARKETING):
        recomendacoes.append("Reavaliar ROI das campanhas e redirecionar verba para canais mais eficientes.")

    if not recomendacoes:
        recomendacoes.append("Investigar causa do aumento e buscar alternativas de reducao de custo.")

    if severidade == "ALTA":
        recomendacoes.insert(0, "PRIORIDADE ALTA: acao imediata recomendada.")
    elif severidade == "MEDIA":
        recomendacoes.insert(0, "Prioridade media: monitorar de perto no proximo periodo.")

    return recomendacoes


# ----------------------------- Motor de analise -----------------------------

def analisar(df, col_conta, col_atual, col_anterior):
    dados = df[[col_conta, col_atual, col_anterior]].copy()
    dados.columns = ["conta", "valor_atual", "valor_anterior"]

    for c in ["valor_atual", "valor_anterior"]:
        dados[c] = (
            dados[c]
            .astype(str)
            .str.replace("R$", "", regex=False)
            .str.replace(".", "", regex=False)
            .str.replace(",", ".", regex=False)
            .str.strip()
        )
        dados[c] = pd.to_numeric(dados[c], errors="coerce")

    dados = dados.dropna(subset=["valor_atual", "valor_anterior"])

    dados["variacao_absoluta"] = dados["valor_atual"] - dados["valor_anterior"]
    dados["variacao_pct"] = dados.apply(
        lambda r: (r["variacao_absoluta"] / r["valor_anterior"] * 100) if r["valor_anterior"] != 0 else 0,
        axis=1,
    )
    dados["severidade"] = dados["variacao_pct"].apply(classificar_severidade)
    dados["recomendacoes"] = dados.apply(
        lambda r: sugerir_recomendacao(r["conta"], r["variacao_pct"], r["severidade"]), axis=1
    )

    dados = dados.sort_values("valor_atual", ascending=False).reset_index(drop=True)
    return dados


# ----------------------------- Geracao de relatorio -----------------------------

def gerar_relatorio(dados, arquivo_origem, caminho_saida):
    linhas = []
    linhas.append("=" * 70)
    linhas.append("RELATORIO DE ANALISE DE BALANCETE")
    linhas.append(f"Arquivo analisado: {arquivo_origem}")
    linhas.append(f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    linhas.append("=" * 70)

    total_atual = dados["valor_atual"].sum()
    total_anterior = dados["valor_anterior"].sum()
    var_total_pct = ((total_atual - total_anterior) / total_anterior * 100) if total_anterior else 0

    linhas.append("\nRESUMO GERAL")
    linhas.append(f"  Total periodo atual:    R$ {total_atual:,.2f}")
    linhas.append(f"  Total periodo anterior: R$ {total_anterior:,.2f}")
    linhas.append(f"  Variacao total:         {var_total_pct:+.2f}%")

    linhas.append("\n" + "-" * 70)
    linhas.append("RANKING DE GASTOS (do maior para o menor, periodo atual)")
    linhas.append("-" * 70)
    for i, row in dados.iterrows():
        linhas.append(
            f"{i+1:>2}. {row['conta']:<35} R$ {row['valor_atual']:>12,.2f}  "
            f"({row['variacao_pct']:+.1f}%)  [{row['severidade']}]"
        )

    linhas.append("\n" + "-" * 70)
    linhas.append("ALERTAS POR SEVERIDADE")
    linhas.append("-" * 70)
    for sev in ["ALTA", "MEDIA", "BAIXA"]:
        subset = dados[dados["severidade"] == sev]
        if subset.empty:
            continue
        linhas.append(f"\n>> Severidade {sev} ({len(subset)} conta(s))")
        for _, row in subset.iterrows():
            linhas.append(
                f"   - {row['conta']}: R$ {row['valor_atual']:,.2f} "
                f"({row['variacao_pct']:+.1f}% vs periodo anterior)"
            )

    linhas.append("\n" + "-" * 70)
    linhas.append("RECOMENDACOES DETALHADAS (contas com aumento de gasto)")
    linhas.append("-" * 70)
    for _, row in dados.iterrows():
        if row["variacao_pct"] <= 0:
            continue
        linhas.append(f"\n* {row['conta']} (variacao {row['variacao_pct']:+.1f}%, severidade {row['severidade']})")
        for rec in row["recomendacoes"]:
            linhas.append(f"    - {rec}")

    texto = "\n".join(linhas)

    with open(caminho_saida, "w", encoding="utf-8") as f:
        f.write(texto)

    print(texto)
    print(f"\n\nRelatorio tambem salvo em: {caminho_saida}")


# ----------------------------- Main -----------------------------

def main():
    parser = argparse.ArgumentParser(description="Analisador de Balancete Empresarial")
    parser.add_argument("arquivo", help="Caminho para o arquivo do balancete (.csv, .xlsx ou .xls)")
    parser.add_argument(
        "--saida", default="relatorio_balancete.txt",
        help="Caminho do arquivo de relatorio de saida (padrao: relatorio_balancete.txt)"
    )
    parser.add_argument("--conta", help="Nome da coluna de conta/categoria (opcional)")
    parser.add_argument("--atual", help="Nome da coluna do valor atual (opcional)")
    parser.add_argument("--anterior", help="Nome da coluna do valor anterior (opcional)")
    args = parser.parse_args()

    if not os.path.exists(args.arquivo):
        print(f"Erro: arquivo '{args.arquivo}' nao encontrado.")
        sys.exit(1)

    df = carregar_balancete(args.arquivo)

    col_conta = args.conta
    col_atual = args.atual
    col_anterior = args.anterior

    if not (col_conta and col_atual and col_anterior):
        auto_conta, auto_atual, auto_anterior = detectar_colunas(df)
        col_conta = col_conta or auto_conta
        col_atual = col_atual or auto_atual
        col_anterior = col_anterior or auto_anterior

    if not (col_conta and col_atual and col_anterior):
        col_conta, col_atual, col_anterior = pedir_colunas_manual(df)

    dados = analisar(df, col_conta, col_atual, col_anterior)
    gerar_relatorio(dados, args.arquivo, args.saida)


if __name__ == "__main__":
    main()
