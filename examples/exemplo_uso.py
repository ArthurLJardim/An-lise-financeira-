"""Exemplo end-to-end do motor de análise financeira.

Simula a entrada que o módulo de tratamento de dados (Eduardo) deve
produzir, usando os CSVs sintéticos desta pasta, e mostra a saída que a
interface (Miguel) e o módulo de recomendações (João Thiago) devem
consumir via `resultado.to_dict()`.

Os dados sintéticos representam lançamentos já contabilizados, no nível
de detalhe de um balancete/DRE real (conta contábil, fornecedor com razão
social, encargos de folha separados etc.) — não uma lista de compras
avulsas/não contabilizadas. É esse o tipo de entrada que o motor espera
receber depois que um balancete é lido e tratado.

Rodar a partir da raiz do projeto:
    python examples/exemplo_uso.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PASTA_EXEMPLOS = Path(__file__).parent
sys.path.insert(0, str(PASTA_EXEMPLOS.parent))  # permite rodar via `python examples/exemplo_uso.py`

import pandas as pd

from motor_analise import AnaliseFinanceira
from motor_analise.relatorio import montar_relatorio_texto, salvar_relatorio_txt


def main() -> None:
    lancamentos = pd.read_csv(PASTA_EXEMPLOS / "dados_exemplo.csv")
    orcamento = pd.read_csv(PASTA_EXEMPLOS / "orcamento_exemplo.csv")
    historico = pd.read_csv(PASTA_EXEMPLOS / "historico_exemplo.csv")

    engine = AnaliseFinanceira()
    resultado = engine.analisar(
        lancamentos, orcamento=orcamento, historico=historico, periodo="2026-06"
    )

    print("=== RESULTADO CONTÁBIL (lucro/prejuízo) ===")
    print(json.dumps(resultado.resultado_contabil, indent=2, ensure_ascii=False))

    print("\n=== RESUMO ===")
    print(json.dumps(resultado.resumo, indent=2, ensure_ascii=False))

    print("\n=== RANKING POR CATEGORIA ===")
    print(resultado.rankings["por_categoria"].to_string(index=False))

    print("\n=== RANKING POR FORNECEDOR (top 5) ===")
    print(resultado.rankings["por_fornecedor"].head(5).to_string(index=False))

    print("\n=== ALERTAS ===")
    for alerta in resultado.alertas:
        print(f"[{alerta.severidade.upper():8s}] {alerta.mensagem}")

    print("\n=== JSON completo (formato para interface/recomendações) ===")
    print(json.dumps(resultado.to_dict(), indent=2, ensure_ascii=False)[:800], "...")

    print("\n=== RELATÓRIO EM TÓPICOS (prévia) ===")
    print(montar_relatorio_texto(resultado))

    caminho_relatorio = salvar_relatorio_txt(resultado, pasta_destino=PASTA_EXEMPLOS.parent / "relatorios")
    print(f"Relatório salvo em: {caminho_relatorio}")


if __name__ == "__main__":
    main()
