"""Modo mais simples de rodar o bot: sem digitar nada no terminal.

Coloque um ou mais balancetes (PDF) dentro da pasta `entrada/` e rode este
script (ou dê duplo-clique em `rodar_bot.bat`, no Windows). Ele analisa
cada PDF encontrado e abre um relatório em texto para cada um, no Bloco de
Notas — nenhum argumento de linha de comando necessário.

Para quem quer mais controle (orçamento, histórico, formato .csv/.xlsx já
tratado), use `analisar_documento.py` diretamente (ver seu docstring).
"""

from __future__ import annotations

from pathlib import Path

from dados.leitor_balancete import LeitorBalanceteError, ler_balancete_pdf
from motor_analise import AnaliseFinanceira
from motor_analise.relatorio import gerar_relatorio

PASTA_ENTRADA = Path(__file__).resolve().parent / "entrada"


def main() -> int:
    PASTA_ENTRADA.mkdir(exist_ok=True)
    pdfs = sorted(PASTA_ENTRADA.glob("*.pdf"))

    if not pdfs:
        print(f"Nenhum PDF encontrado em: {PASTA_ENTRADA}")
        print("Coloque o balancete (PDF) nessa pasta e rode de novo.")
        return 1

    engine = AnaliseFinanceira()
    algum_sucesso = False

    for pdf in pdfs:
        print(f"\nAnalisando '{pdf.name}'...")
        try:
            lancamentos = ler_balancete_pdf(pdf)
        except LeitorBalanceteError as erro:
            print(f"  Não foi possível ler este balancete: {erro}")
            continue

        resultado = engine.analisar(lancamentos, periodo=pdf.stem)
        destino = gerar_relatorio(resultado)
        print(f"  Relatório salvo e aberto: {destino}")
        algum_sucesso = True

    return 0 if algum_sucesso else 1


if __name__ == "__main__":
    raise SystemExit(main())
