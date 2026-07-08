"""Leitura de balancetes contábeis em PDF e conversão para lançamentos.

Primeira versão do módulo de tratamento de dados (Eduardo, `dados/`):
recebe o balancete exportado do sistema contábil (PDF) e produz o
DataFrame de lançamentos que o `motor_analise` consome (contrato em
docs/CONTRATO_DADOS.md).

Um balancete lista todas as contas do plano de contas, cada uma com seu
saldo, mas mistura **contas sintéticas** (totalizadoras, ex.: "PASSIVO
CIRCULANTE") com **contas analíticas** (as que representam um lançamento
de fato, ex.: um fornecedor específico ou "SERVIÇOS PRESTADOS"). O PDF não
traz a profundidade/indentação de cada conta de forma confiável, então a
hierarquia é reconstruída por **reconciliação de valores**: uma conta é
sintética quando o valor de uma sequência contígua de contas seguintes
(mesma natureza D/C) soma exatamente o valor dela; senão, é uma conta
analítica (folha) e vira um lançamento. Essa reconciliação (saldo anterior
+ débito − crédito = saldo atual) é o que garante que o bot funcione com
balancetes de contadores/sistemas diferentes: qualquer plano de contas
respeita essa identidade contábil, então ela não depende de nenhum
código, layout ou numeração específica de um sistema em particular.

O ponto realmente específico de um sistema contábil é **em que ordem o
PDF grava as colunas no texto** (a ordem em que o `pypdf` extrai o texto
nem sempre é a ordem visual da tabela — ver `_LAYOUTS_CONHECIDOS`). Cada
sistema/contador pode gerar isso de um jeito diferente; o parser tenta os
layouts conhecidos e usa a reconciliação de valores pra confirmar qual
bateu, mas só suporta de fato os layouts cadastrados em `_LAYOUTS_CONHECIDOS`
— hoje, só o layout validado contra o balancete de exemplo testado. Um
balancete de outro contador/sistema pode ter um layout diferente e falhar
com `LeitorBalanceteError`; nesse caso, o ajuste é registrar um novo
layout aqui a partir de um exemplo real, não redesenhar o bot em torno de
um exemplo só.

Limitação conhecida: um balancete é uma foto de saldos acumulados do
período, sem data por lançamento — todas as linhas geradas usam a data de
fim do período como `data`. A classificação de receita/despesa e a
categoria são inferidas por palavras-chave na conta e nos seus
ancestrais; balancetes com um plano de contas muito diferente do usual
podem precisar de ajuste nessas palavras-chave.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import pypdf

EPS = 0.01

_NUM = r"\d{1,3}(?:\.\d{3})*,\d{2}"

# Layouts conhecidos de linha de conta, tentados nesta ordem. Cada um assume
# uma ordem diferente para os 4 valores monetários (saldo atual, crédito,
# débito, saldo anterior) e para o bloco código+descrição — a ordem em que o
# PDF grava o texto varia de sistema contábil pra sistema contábil, mesmo
# quando a tabela visual é idêntica. Só existe um layout aqui hoje (o único
# validado até agora, contra um balancete real); pra dar suporte a um novo
# sistema, adicione um novo padrão nesta lista a partir de um exemplo real —
# não é preciso mudar mais nada, `_parse_linhas_texto` escolhe automaticamente
# qual layout bate por reconciliação de valores (ver `_reconcilia`).
_LAYOUTS_CONHECIDOS: list[re.Pattern[str]] = [
    # "reverso": saldo atual, crédito, débito, saldo anterior, código, descrição.
    re.compile(
        rf"(?P<atual>{_NUM})(?P<natureza>[DC])(?P<credito>{_NUM})(?P<debito>{_NUM})"
        rf"(?P<anterior>{_NUM})(?P<codigo>\d+)\s+(?P<descricao>.+)$"
    ),
]

_PADRAO_PERIODO = re.compile(r"(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})")

_PALAVRAS_CATEGORIA = (
    (("energia", "eletrica", "luz"), "energia"),
    (("aluguel", "condominio", "locacao"), "aluguel"),
    (
        (
            "salario",
            "ordenado",
            "folha",
            "inss",
            "fgts",
            "vale transporte",
            "vale-transporte",
            "vale alimentacao",
            "pessoal",
            "encargo",
        ),
        "folha",
    ),
    (("transporte", "frete", "combustivel", "logistica"), "transporte"),
    (("servico", "contabil", "manutencao", "internet", "telefonia", "assessoria"), "servicos"),
    (("mercadoria", "compra", "revenda", "fornecedor", "insumo", "produto"), "mercadorias"),
)


class LeitorBalanceteError(ValueError):
    """Levantado quando o PDF não pôde ser interpretado como um balancete contábil."""


@dataclass(frozen=True)
class ContaBalancete:
    """Uma linha (conta) do balancete, já com os valores convertidos para float."""

    codigo: str
    descricao: str
    saldo_anterior: float
    debito: float
    credito: float
    saldo_atual: float
    natureza: str  # "D" (devedor) ou "C" (credor)


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto.strip().lower())
    return "".join(c for c in texto if not unicodedata.combining(c))


def _para_float(valor_br: str) -> float:
    return float(valor_br.replace(".", "").replace(",", "."))


def _reconcilia(conta: ContaBalancete) -> bool:
    """Confere se saldo_anterior + débito - crédito bate com o saldo_atual.

    É uma identidade contábil universal (vale pra qualquer plano de contas,
    de qualquer sistema) — por isso serve tanto pra validar uma conta quanto
    pra descobrir, entre vários layouts candidatos, qual ordem de colunas
    este PDF em particular usa (ver `_parse_linhas_texto`).
    """
    esperado = conta.saldo_anterior + conta.debito - conta.credito
    if conta.natureza == "D":
        return esperado >= -EPS and abs(esperado - conta.saldo_atual) < EPS
    return esperado <= EPS and abs(-esperado - conta.saldo_atual) < EPS


def _extrair_contas_com_layout(texto: str, padrao: re.Pattern[str]) -> list[ContaBalancete]:
    contas: list[ContaBalancete] = []
    for linha in texto.splitlines():
        m = padrao.search(linha)
        if not m:
            continue
        contas.append(
            ContaBalancete(
                codigo=m.group("codigo"),
                descricao=m.group("descricao").strip(),
                saldo_anterior=_para_float(m.group("anterior")),
                debito=_para_float(m.group("debito")),
                credito=_para_float(m.group("credito")),
                saldo_atual=_para_float(m.group("atual")),
                natureza=m.group("natureza"),
            )
        )
    return contas


def _parse_linhas_texto(texto: str) -> list[ContaBalancete]:
    """Extrai as contas de um balancete a partir do texto bruto do PDF.

    Tenta cada layout conhecido (`_LAYOUTS_CONHECIDOS`) e usa a reconciliação
    de valores pra escolher: o layout certo é aquele em que TODAS as contas
    reconciliam (saldo anterior + débito - crédito = saldo atual). Se nenhum
    layout reconciliar 100%, devolve o resultado do melhor candidato parcial
    (o que reconciliou mais contas) — `_validar_contas`, chamada depois,
    é quem efetivamente rejeita esse caso com uma mensagem clara.
    """
    melhor: list[ContaBalancete] = []
    melhor_reconciliadas = -1
    for padrao in _LAYOUTS_CONHECIDOS:
        contas = _extrair_contas_com_layout(texto, padrao)
        if not contas:
            continue
        reconciliadas = sum(1 for c in contas if _reconcilia(c))
        if reconciliadas == len(contas):
            return contas
        if reconciliadas > melhor_reconciliadas:
            melhor, melhor_reconciliadas = contas, reconciliadas
    return melhor


def _validar_contas(contas: list[ContaBalancete]) -> None:
    """Confere cada conta contra `_reconcilia`.

    Se `_parse_linhas_texto` não achou nenhum layout que bata 100%, é aqui
    que isso vira um erro claro em vez de números errados passarem adiante.
    """
    for conta in contas:
        if not _reconcilia(conta):
            raise LeitorBalanceteError(
                f"Conta '{conta.codigo} {conta.descricao}' não reconcilia "
                "(saldo anterior + débito - crédito não bate com o saldo atual). "
                "O layout deste balancete não é nenhum dos suportados hoje "
                "(_LAYOUTS_CONHECIDOS em dados/leitor_balancete.py) — provavelmente "
                "vem de um sistema contábil diferente do testado."
            )


def _consumir_grupo(
    contas: list[ContaBalancete],
    indice: int,
    alvo: float,
    natureza: str,
    ancestrais: list[str],
) -> tuple[Optional[list[tuple[ContaBalancete, list[str]]]], int]:
    """Tenta explicar `alvo` com uma sequência contígua de contas a partir de `indice`.

    Retorna a lista de contas-folha (com seus ancestrais) e o próximo índice
    não consumido, se a soma bater exatamente com `alvo`; ou (None, indice)
    se não for possível — sinal de que a conta candidata não é uma agregadora.
    """
    total = 0.0
    i = indice
    n = len(contas)
    folhas: list[tuple[ContaBalancete, list[str]]] = []
    while total < alvo - EPS:
        if i >= n:
            return None, indice
        conta = contas[i]
        if conta.natureza != natureza or total + conta.saldo_atual > alvo + EPS:
            return None, indice
        sub_folhas, proximo = _consumir_grupo(
            contas, i + 1, conta.saldo_atual, natureza, ancestrais + [conta.descricao]
        )
        if sub_folhas is not None:
            folhas.extend(sub_folhas)
            i = proximo
        else:
            folhas.append((conta, ancestrais))
            i += 1
        total += conta.saldo_atual
    if abs(total - alvo) < EPS:
        return folhas, i
    return None, indice


def _identificar_folhas(contas: list[ContaBalancete]) -> list[tuple[ContaBalancete, list[str]]]:
    """Percorre todas as contas (podem existir várias árvores-raiz independentes,
    ex.: ATIVO e PASSIVO) e devolve só as contas analíticas (folhas), cada uma
    com a cadeia de descrições dos seus ancestrais (raiz primeiro)."""
    folhas: list[tuple[ContaBalancete, list[str]]] = []
    i = 0
    n = len(contas)
    while i < n:
        conta = contas[i]
        sub_folhas, proximo = _consumir_grupo(
            contas, i + 1, conta.saldo_atual, conta.natureza, [conta.descricao]
        )
        if sub_folhas is not None:
            folhas.extend(sub_folhas)
            i = proximo
        else:
            folhas.append((conta, []))
            i += 1
    return folhas


def _inferir_categoria(*textos: str) -> str:
    junto = " ".join(_normalizar(t) for t in textos)
    for palavras, categoria in _PALAVRAS_CATEGORIA:
        if any(p in junto for p in palavras):
            return categoria
    return "outros"


_PADRAO_PALAVRA_RECEITA = re.compile(r"\b(receita|resultado bruto|venda)")


def _classificar(conta: ContaBalancete, ancestrais: list[str]) -> Optional[tuple[str, str]]:
    """Decide se uma conta-folha é receita, despesa, ou nenhuma das duas
    (contas puramente patrimoniais, como saldo de caixa ou capital, não
    entram como lançamento). Devolve (tipo, categoria) ou None.
    """
    caminho = " ".join(_normalizar(a) for a in ancestrais)
    descricao_norm = _normalizar(conta.descricao)

    # \b evita falso positivo de "venda" dentro de "revenda" (conta de estoque, não receita).
    if _PADRAO_PALAVRA_RECEITA.search(caminho) or _PADRAO_PALAVRA_RECEITA.search(descricao_norm):
        return "receita", _inferir_categoria(conta.descricao, *ancestrais)

    if any(p in caminho for p in ("despesa", "custo")):
        return "despesa", _inferir_categoria(conta.descricao, *ancestrais)

    if any("fornecedor" in _normalizar(a) for a in ancestrais):
        return "despesa", _inferir_categoria(conta.descricao, *ancestrais)

    return None


def _extrair_data_periodo_de_texto(texto: str) -> str:
    """Extrai a data final do período do balancete (formato YYYY-MM-DD).

    Usada como `data` de todos os lançamentos gerados, já que o balancete
    não traz data por conta — só o período coberto.
    """
    m = _PADRAO_PERIODO.search(texto)
    if not m:
        return datetime.now().strftime("%Y-%m-%d")
    _, fim = m.groups()
    dia, mes, ano = fim.split("/")
    return f"{ano}-{mes}-{dia}"


def _montar_dataframe(
    folhas: list[tuple[ContaBalancete, list[str]]], data_lancamento: str
) -> pd.DataFrame:
    linhas = []
    for conta, ancestrais in folhas:
        classificacao = _classificar(conta, ancestrais)
        if classificacao is None:
            continue
        tipo, categoria = classificacao
        linhas.append(
            {
                "data": data_lancamento,
                "tipo": tipo,
                "categoria": categoria,
                "fornecedor": conta.descricao,
                "valor": conta.saldo_atual,
                "descricao": " > ".join([*ancestrais, conta.descricao]),
            }
        )
    if not linhas:
        raise LeitorBalanceteError(
            "Nenhuma conta de receita/despesa foi identificada no balancete. "
            "Verifique se o arquivo é mesmo um balancete/DRE contábil."
        )
    return pd.DataFrame(linhas, columns=["data", "tipo", "categoria", "fornecedor", "valor", "descricao"])


def processar_texto_balancete(texto: str) -> pd.DataFrame:
    """Núcleo puro (sem I/O) do parser: texto extraído do PDF -> lançamentos."""
    contas = _parse_linhas_texto(texto)
    if not contas:
        raise LeitorBalanceteError(
            "Não foi possível reconhecer nenhuma conta no texto do balancete. "
            "O layout deste PDF pode ser diferente do esperado."
        )
    _validar_contas(contas)
    folhas = _identificar_folhas(contas)
    data_lancamento = _extrair_data_periodo_de_texto(texto)
    return _montar_dataframe(folhas, data_lancamento)


def ler_balancete_pdf(caminho: Path | str) -> pd.DataFrame:
    """Lê um balancete em PDF e devolve o DataFrame de lançamentos do motor.

    Levanta `LeitorBalanceteError` com uma mensagem acionável quando o PDF
    não tem o layout esperado (não é possível reconhecer contas, ou os
    valores não reconciliam).
    """
    caminho = Path(caminho)
    leitor = pypdf.PdfReader(str(caminho))
    texto = "\n".join(pagina.extract_text() or "" for pagina in leitor.pages)
    return processar_texto_balancete(texto)
