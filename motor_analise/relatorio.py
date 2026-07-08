"""Geração do relatório de análise financeira em texto, por tópicos.

Formata o `ResultadoAnalise` em um relatório legível (sem depender de
planilha/interface pronta) e permite salvá-lo como .txt e abrir
diretamente no Bloco de Notas — útil para o usuário final ver o
resultado da análise sem precisar da interface do Miguel.
"""

from __future__ import annotations

import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from .modelos import Alerta, ResultadoAnalise

PASTA_RELATORIOS_PADRAO = Path(__file__).resolve().parent.parent / "relatorios"

_ROTULO_SITUACAO = {
    "lucro": "LUCRO",
    "prejuizo": "PREJUÍZO",
    "equilibrio": "EQUILÍBRIO (receita = despesa)",
}

_ROTULO_SEVERIDADE = {
    "critica": "CRÍTICA",
    "alta": "ALTA",
    "media": "MÉDIA",
    "baixa": "BAIXA",
}


def _formatar_moeda(valor: float) -> str:
    texto = f"{valor:,.2f}"
    texto = texto.replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {texto}"


def _linha_titulo(texto: str) -> str:
    borda = "=" * len(texto)
    return f"{borda}\n{texto}\n{borda}"


def _secao_resultado_periodo(resultado: ResultadoAnalise) -> str:
    rc = resultado.resultado_contabil
    linhas = [
        "1. RESULTADO DO PERÍODO",
        f"   Situação: {_ROTULO_SITUACAO.get(rc['situacao'], rc['situacao'].upper())}",
        f"   Receita total: {_formatar_moeda(rc['receita_total'])}",
        f"   Despesa total: {_formatar_moeda(rc['despesa_total'])}",
        f"   Resultado do período: {_formatar_moeda(rc['resultado'])}",
    ]
    if rc["margem_percentual"] is not None:
        linhas.append(f"   Margem: {rc['margem_percentual']:.1f}%")
    return "\n".join(linhas)


def _secao_resumo_gastos(resultado: ResultadoAnalise) -> str:
    resumo = resultado.resumo
    linhas = [
        "2. RESUMO DE GASTOS",
        f"   Gasto total analisado: {_formatar_moeda(resumo['gasto_total'])}",
        f"   Lançamentos de despesa analisados: {resumo['quantidade_lancamentos']}",
    ]
    maior = resumo.get("maior_aumento")
    if maior:
        linhas.append(
            f"   Maior aumento de gasto: categoria '{maior['categoria']}' "
            f"({maior['variacao_percentual']:+.1f}%, de "
            f"{_formatar_moeda(maior['valor_referencia'])} para "
            f"{_formatar_moeda(maior['valor_atual'])})"
        )
    else:
        linhas.append("   Nenhum aumento de gasto identificado no período.")

    contagem = resumo["alertas_por_severidade"]
    linhas.append(
        f"   Alertas gerados: {resumo['numero_alertas']} "
        f"(crítica: {contagem['critica']}, alta: {contagem['alta']}, "
        f"média: {contagem['media']}, baixa: {contagem['baixa']})"
    )
    return "\n".join(linhas)


def _secao_onde_gasta_mais(resultado: ResultadoAnalise, top_n: int = 5) -> str:
    linhas = ["3. ONDE A EMPRESA GASTA MAIS"]

    ranking_categoria = resultado.rankings.get("por_categoria")
    if ranking_categoria is None or ranking_categoria.empty:
        linhas.append("   Sem lançamentos de despesa para ranquear neste período.")
        return "\n".join(linhas)

    linhas.append("   Por categoria:")
    for _, linha in ranking_categoria.head(top_n).iterrows():
        linhas.append(
            f"   {int(linha['posicao'])}. {linha['categoria']}: "
            f"{_formatar_moeda(linha['total'])} ({linha['percentual_do_total']:.1f}% do total)"
        )

    ranking_fornecedor = resultado.rankings.get("por_fornecedor")
    if ranking_fornecedor is not None and not ranking_fornecedor.empty:
        linhas.append("   Por fornecedor:")
        for _, linha in ranking_fornecedor.head(top_n).iterrows():
            linhas.append(
                f"   {int(linha['posicao'])}. {linha['fornecedor']}: "
                f"{_formatar_moeda(linha['total'])} ({linha['percentual_do_total']:.1f}% do total)"
            )

    return "\n".join(linhas)


def _secao_alertas(resultado: ResultadoAnalise) -> str:
    linhas = ["4. ALERTAS DE GASTOS"]
    if not resultado.alertas:
        linhas.append("   Nenhum alerta identificado neste período.")
        return "\n".join(linhas)

    for alerta in resultado.alertas:
        linhas.append(f"   [{_ROTULO_SEVERIDADE[alerta.severidade]}] {alerta.mensagem}")
    return "\n".join(linhas)


def _sugestoes_economia(alertas: list[Alerta]) -> list[str]:
    sugestoes = []
    categorias_ja_sugeridas = set()
    for alerta in alertas:
        if alerta.categoria in categorias_ja_sugeridas:
            continue
        if alerta.severidade not in ("alta", "critica"):
            continue
        categorias_ja_sugeridas.add(alerta.categoria)
        sugestoes.append(
            f"   - Rever contratos/fornecedores da categoria '{alerta.categoria}': "
            f"gasto {alerta.variacao_percentual:+.1f}% acima do esperado "
            f"({_formatar_moeda(alerta.valor_atual)} vs {_formatar_moeda(alerta.valor_referencia)})."
        )
    return sugestoes


def _secao_onde_economizar(resultado: ResultadoAnalise) -> str:
    linhas = ["5. ONDE A EMPRESA PODE ECONOMIZAR"]
    sugestoes = _sugestoes_economia(resultado.alertas)
    if sugestoes:
        linhas.extend(sugestoes)
    else:
        linhas.append(
            "   Nenhuma categoria com desvio grave o suficiente para ação imediata neste período."
        )
    linhas.append(
        "   (Recomendações preliminares baseadas nos alertas. Sugestões de fornecedores"
    )
    linhas.append(
        "   alternativos e estimativa de economia são geradas pelo módulo de fornecedores.)"
    )
    return "\n".join(linhas)


def montar_relatorio_texto(resultado: ResultadoAnalise) -> str:
    """Monta o relatório de análise financeira em texto, organizado por tópicos."""
    gerado_em = datetime.now().strftime("%d/%m/%Y %H:%M")
    cabecalho = _linha_titulo(f"RELATÓRIO DE ANÁLISE FINANCEIRA — {resultado.periodo}")

    secoes = [
        cabecalho,
        f"Gerado em {gerado_em}",
        "",
        _secao_resultado_periodo(resultado),
        "",
        _secao_resumo_gastos(resultado),
        "",
        _secao_onde_gasta_mais(resultado),
        "",
        _secao_alertas(resultado),
        "",
        _secao_onde_economizar(resultado),
        "",
    ]
    return "\n".join(secoes)


def _nome_arquivo_seguro(periodo: str) -> str:
    slug = re.sub(r"[^\w\-]+", "_", periodo.strip()) or "periodo"
    carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"analise_{slug}_{carimbo}.txt"


def salvar_relatorio_txt(
    resultado: ResultadoAnalise,
    caminho: Optional[Path | str] = None,
    pasta_destino: Optional[Path | str] = None,
) -> Path:
    """Salva o relatório em um arquivo .txt e devolve o caminho gerado.

    Se `caminho` não for informado, o arquivo é salvo em `pasta_destino`
    (padrão: pasta `relatorios/` na raiz do projeto) com um nome gerado a
    partir do período e do horário atual.
    """
    if caminho is not None:
        destino = Path(caminho)
    else:
        pasta = Path(pasta_destino) if pasta_destino is not None else PASTA_RELATORIOS_PADRAO
        pasta.mkdir(parents=True, exist_ok=True)
        destino = pasta / _nome_arquivo_seguro(resultado.periodo)

    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(montar_relatorio_texto(resultado), encoding="utf-8")
    return destino


def abrir_no_bloco_de_notas(caminho: Path | str) -> None:
    """Abre o arquivo de relatório no Bloco de Notas (Windows).

    Em sistemas que não são Windows, ou se o Bloco de Notas não estiver
    disponível, apenas não faz nada — o chamador ainda tem o caminho do
    arquivo para abrir manualmente.
    """
    if sys.platform != "win32":
        return
    try:
        subprocess.Popen(["notepad.exe", str(caminho)])
    except OSError:
        pass


def gerar_relatorio(
    resultado: ResultadoAnalise,
    caminho: Optional[Path | str] = None,
    abrir_bloco_de_notas: bool = True,
) -> Path:
    """Salva o relatório em .txt e (por padrão) já abre no Bloco de Notas.

    Função de conveniência que junta `salvar_relatorio_txt` +
    `abrir_no_bloco_de_notas` — é o que o script `analisar_documento.py` usa.
    """
    destino = salvar_relatorio_txt(resultado, caminho=caminho)
    if abrir_bloco_de_notas:
        abrir_no_bloco_de_notas(destino)
    return destino
