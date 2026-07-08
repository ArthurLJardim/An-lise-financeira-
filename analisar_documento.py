"""CLI: analisa um balancete/DRE e gera o relatório em tópicos no Bloco de Notas.

Uso:
    python analisar_documento.py caminho/balancete.pdf
    python analisar_documento.py caminho/balancete.pdf --historico caminho/balancete_mes_anterior.pdf
    python analisar_documento.py caminho/lancamentos.csv --orcamento caminho/orcamento.csv
    python analisar_documento.py caminho/lancamentos.xlsx --historico caminho/mes_anterior.xlsx --periodo "2026-06"

`lancamentos` pode ser:
- um balancete em **PDF**, lido diretamente via `dados.leitor_balancete`
  (é o caso de uso principal: a empresa exporta o balancete do sistema
  contábil e aponta o script pra ele); ou
- um arquivo já tratado no formato interno do contrato (`.xlsx`/`.csv`,
  colunas em docs/CONTRATO_DADOS.md: data, categoria, fornecedor, valor e,
  opcionalmente, tipo, produto, descricao, forma_pagamento) — útil quando o
  balancete já foi convertido por outro meio, ou para dados sintéticos de
  teste.

`--orcamento` e `--historico` também aceitam PDF de balancete (`--historico`
tipicamente será o balancete do período anterior).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from dados.leitor_balancete import LeitorBalanceteError, ler_balancete_pdf
from motor_analise import AnaliseFinanceira
from motor_analise.relatorio import gerar_relatorio


def _ler_tabela(caminho: Path) -> pd.DataFrame:
    sufixo = caminho.suffix.lower()
    if sufixo == ".pdf":
        return ler_balancete_pdf(caminho)
    if sufixo in (".xlsx", ".xls"):
        return pd.read_excel(caminho)
    if sufixo in (".csv", ".tsv"):
        separador = "\t" if sufixo == ".tsv" else ","
        return pd.read_csv(caminho, sep=separador)
    raise ValueError(f"Formato de arquivo não suportado: {sufixo} (use .pdf, .xlsx, .csv ou .tsv)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("lancamentos", type=Path, help="Balancete em PDF, ou lançamentos já tratados (.xlsx/.csv)")
    parser.add_argument("--orcamento", type=Path, default=None, help="Arquivo com limites por categoria")
    parser.add_argument(
        "--historico", type=Path, default=None, help="Balancete (PDF) ou lançamentos do período anterior"
    )
    parser.add_argument("--periodo", type=str, default=None, help="Rótulo do período (ex.: 2026-06)")
    parser.add_argument("--saida", type=Path, default=None, help="Caminho do .txt de saída (padrão: pasta relatorios/)")
    parser.add_argument(
        "--nao-abrir", action="store_true", help="Não abrir o relatório no Bloco de Notas automaticamente"
    )
    args = parser.parse_args(argv)

    if not args.lancamentos.exists():
        print(f"Arquivo não encontrado: {args.lancamentos}", file=sys.stderr)
        return 1

    try:
        lancamentos = _ler_tabela(args.lancamentos)
        orcamento = _ler_tabela(args.orcamento) if args.orcamento else None
        historico = _ler_tabela(args.historico) if args.historico else None
    except LeitorBalanceteError as erro:
        print(f"Não foi possível ler o balancete: {erro}", file=sys.stderr)
        return 1
    periodo = args.periodo or args.lancamentos.stem

    engine = AnaliseFinanceira()
    resultado = engine.analisar(lancamentos, orcamento=orcamento, historico=historico, periodo=periodo)

    destino = gerar_relatorio(resultado, caminho=args.saida, abrir_bloco_de_notas=not args.nao_abrir)
    print(f"Relatório salvo em: {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
