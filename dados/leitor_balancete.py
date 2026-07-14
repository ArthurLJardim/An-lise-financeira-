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
— hoje, três: o "reverso" e o "classificado" (validados contra três
balancetes reais, de dois contadores/sistemas diferentes — o "classificado"
tem uma coluna de classificação hierárquica que permite reconstruir a
hierarquia sem depender de reconciliação de valores, ver
`_identificar_folhas_por_classificacao`), e o "natural" (a ordem visual da
própria tabela, sem inversão — testado só contra PDF sintético, ainda não
contra um balancete real desse tipo). Um balancete de outro contador/sistema
pode ter um layout diferente dos três e falhar com `LeitorBalanceteError`.

Como adicionar suporte a um novo layout, a partir de um balancete real que
falhou:
1. Rode `pypdf.PdfReader(caminho).pages[0].extract_text()` e veja a ordem
   real em que os campos aparecem no texto (não confie na ordem visual do
   PDF — pypdf às vezes extrai em outra ordem, como aconteceu no primeiro
   layout).
2. Escreva um novo `re.compile(...)` com grupos nomeados `atual`,
   `natureza`, `credito`, `debito`, `anterior`, `codigo`, `descricao` que
   capture essa ordem, e acrescente à lista `_LAYOUTS_CONHECIDOS`.
3. Não precisa mexer em mais nada — `_parse_linhas_texto` testa todos os
   layouts cadastrados e escolhe automaticamente o que reconcilia 100%
   (`_reconcilia`), e `_validar_identidade_contabil` pega qualquer
   reconstrução de hierarquia que não tenha fechado certo.
4. Adicione um teste em `tests/test_leitor_balancete.py` com esse layout
   (dados fictícios, não o balancete real) — ver `TestLayoutNatural` como
   modelo.

Limitação conhecida: um balancete é uma foto de saldos acumulados do
período, sem data por lançamento — todas as linhas geradas usam a data de
fim do período como `data`. A classificação de receita/despesa e a
categoria são inferidas por palavras-chave na conta e nos seus
ancestrais; balancetes com um plano de contas muito diferente do usual
podem precisar de ajuste nessas palavras-chave (`_PALAVRAS_CATEGORIA`).
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

from dados.utils import detect_document_type, extract_header_metadata

EPS = 0.01
EPS_IDENTIDADE_CONTABIL = 1.0

# Número no formato brasileiro. Tolerante ao separador de milhar (aceita
# "58000,00" e "58.000,00") — nem todo sistema agrupa milhares, e exigir
# isso rejeitaria balancetes válidos de sistemas que não agrupam.
_NUM = r"\d[\d.]*,\d{2}"

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
    # Único layout validado contra um balancete real até agora.
    re.compile(
        rf"(?P<atual>{_NUM})(?P<natureza>[DC])(?P<credito>{_NUM})(?P<debito>{_NUM})"
        rf"(?P<anterior>{_NUM})(?P<codigo>\d+)\s+(?P<descricao>.+)$"
    ),
    # "natural": código, descrição, saldo anterior, débito, crédito, saldo
    # atual — a ordem visual da própria tabela, sem inversão. É o jeito mais
    # intuitivo de gravar o texto, mas ainda não validado contra um PDF real
    # (só contra um PDF sintético gerado localmente); mantido aqui como
    # segunda tentativa, escolhida automaticamente só se reconciliar 100%.
    re.compile(
        rf"(?P<codigo>\d+)\s+(?P<descricao>\D+?)\s+(?P<anterior>{_NUM})\s+"
        rf"(?P<debito>{_NUM})\s+(?P<credito>{_NUM})\s+(?P<atual>{_NUM})(?P<natureza>[DC])\s*$"
    ),
    # "classificado": código, classificação (código hierárquico com pontos,
    # ex.: "1.1.3.08.00001"), saldo atual+natureza, saldo anterior (às vezes
    # também com natureza — ex.: "36.777.176,96D34.914.972,47D"), débito,
    # crédito, descrição. Validado contra dois balancetes reais (empresas e
    # sistema diferentes do primeiro layout). Quando a classificação está
    # presente, `_identificar_folhas` usa ela pra achar as contas-folha (mais
    # robusto que reconciliação de valores — não depende da ordem das contas
    # no PDF) em vez do algoritmo de reconciliação.
    re.compile(
        rf"(?P<codigo>\d+)\s+(?P<classificacao>[\d.]+)\s+(?P<atual>{_NUM})(?P<natureza>[DC])"
        rf"(?P<anterior>{_NUM})(?P<natureza_anterior>[DC])?\s+(?P<debito>{_NUM})\s+(?P<credito>{_NUM})(?P<descricao>.+)$"
    ),
]

_PADRAO_PERIODO = re.compile(r"(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})")

# Vocabulário de palavras-chave por categoria. Checado nesta ordem (primeira
# que bater vence) — categorias com termos mais específicos vêm antes das
# mais genéricas ("mercadorias" por último, já que "compra"/"produto" são
# termos largos que apareceriam em descrições de outras categorias também.
# Cobertura ampla de plano de contas brasileiro, mas continua sendo um
# dicionário de palavras-chave: planos de conta muito fora do usual podem
# cair em "outros" — ver docs/CONTRATO_DADOS.md sobre esse limite.
_PALAVRAS_CATEGORIA = (
    (
        (
            "energia",
            "eletrica",
            "luz",
            "cpfl",
            "enel",
            "cemig",
            "light",
            "eletropaulo",
            "copel",
            "coelba",
            "celesc",
            "energisa",
            "equatorial",
            "neoenergia",
            "elektro",
            "distribuidora de energia",
        ),
        "energia",
    ),
    (("aluguel", "condominio", "locacao", "arrendamento", "imovel"), "aluguel"),
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
            "vale-alimentacao",
            "vale refeicao",
            "vale-refeicao",
            "pessoal",
            "encargo",
            "pro labore",
            "pro-labore",
            "decimo terceiro",
            "13o salario",
            "ferias",
            "rescisao",
            "beneficio",
            "plano de saude",
        ),
        "folha",
    ),
    (
        (
            "transporte",
            "frete",
            "combustivel",
            "logistica",
            "pedagio",
            "gasolina",
            "diesel",
            "etanol",
            "posto de combustivel",
            "seguro veicular",
            "manutencao de veiculo",
            "transportadora",
        ),
        "transporte",
    ),
    (
        (
            "servico",
            "contabil",
            "manutencao",
            "internet",
            "telefonia",
            "assessoria",
            "consultoria",
            "honorario",
            "advocacia",
            "juridico",
            "software",
            "licenca de uso",
            "assinatura",
            "tecnologia da informacao",
            "terceirizado",
            "mao de obra terceirizada",
        ),
        "servicos",
    ),
    (
        (
            "imposto",
            "tributo",
            "icms",
            "iss",
            "irpj",
            "csll",
            "pis",
            "cofins",
            "simples nacional",
            "darf",
            "taxa",
            "multa fiscal",
        ),
        "impostos",
    ),
    (
        (
            "mercadoria",
            "compra",
            "revenda",
            "fornecedor",
            "insumo",
            "produto",
            "materia prima",
            "materia-prima",
            "cmv",
            "custo da mercadoria",
        ),
        "mercadorias",
    ),
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
    natureza: str  # "D" (devedor) ou "C" (credor), do saldo atual
    # Código hierárquico com pontos (ex.: "1.1.3.08.00001"), quando o layout
    # tem essa coluna. None nos layouts sem ela — nesse caso a hierarquia é
    # reconstruída por reconciliação de valores (ver `_identificar_folhas`).
    classificacao: Optional[str] = None
    # Natureza do saldo anterior, quando o layout mostra essa marca também
    # (ex.: "18.120,00C" de saldo anterior, sem nenhuma movimentação no
    # período). None quando o layout não marca a natureza do saldo anterior
    # (nesse caso ele é tratado como já expresso na mesma convenção de sinal
    # da natureza do saldo atual — é o que os outros layouts sempre fizeram).
    natureza_anterior: Optional[str] = None


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

    Quando o layout marca a natureza do próprio saldo anterior (ex.: uma
    conta que era credora e virou devedora durante o período, ou uma sem
    nenhuma movimentação — só saldo anterior repetido, credor), o saldo
    anterior entra com sinal invertido se a natureza dele for credora —
    independente da natureza do saldo atual, que pode ser igual ou
    diferente. Sem essa marca (layouts que não mostram natureza no saldo
    anterior), assume-se que ele já está na mesma convenção de sinal do
    saldo atual — sempre foi assim que os outros layouts funcionaram.
    """
    anterior = -conta.saldo_anterior if conta.natureza_anterior == "C" else conta.saldo_anterior
    esperado = anterior + conta.debito - conta.credito
    if conta.natureza == "D":
        return esperado >= -EPS and abs(esperado - conta.saldo_atual) < EPS
    return esperado <= EPS and abs(-esperado - conta.saldo_atual) < EPS


def _extrair_contas_com_layout(texto: str, padrao: re.Pattern[str]) -> list[ContaBalancete]:
    contas: list[ContaBalancete] = []
    for linha in texto.splitlines():
        m = padrao.search(linha)
        if not m:
            continue
        grupos = m.groupdict()
        contas.append(
            ContaBalancete(
                codigo=grupos["codigo"],
                descricao=grupos["descricao"].strip(),
                saldo_anterior=_para_float(grupos["anterior"]),
                debito=_para_float(grupos["debito"]),
                credito=_para_float(grupos["credito"]),
                saldo_atual=_para_float(grupos["atual"]),
                natureza=grupos["natureza"],
                classificacao=grupos.get("classificacao"),
                natureza_anterior=grupos.get("natureza_anterior"),
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


def _identificar_folhas_por_reconciliacao(
    contas: list[ContaBalancete],
) -> list[tuple[ContaBalancete, list[str]]]:
    """Percorre todas as contas (podem existir várias árvores-raiz independentes,
    ex.: ATIVO e PASSIVO) e devolve só as contas analíticas (folhas), cada uma
    com a cadeia de descrições dos seus ancestrais (raiz primeiro).

    Assume que o balancete lista as contas em pré-ordem estrita (pai
    imediatamente seguido de todos os filhos, contíguos) — é o método usado
    quando o layout não tem coluna de classificação hierárquica (ver
    `_identificar_folhas_por_classificacao`, mais robusto, usado quando ela
    está disponível).
    """
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


def _identificar_folhas_por_classificacao(
    contas: list[ContaBalancete],
) -> list[tuple[ContaBalancete, list[str]]]:
    """Reconstrói a hierarquia usando a coluna de classificação (código
    hierárquico com pontos, ex.: "1.1.3.08.00001") em vez de reconciliação
    de valores — bem mais robusto, porque não depende da ordem em que as
    contas aparecem no PDF nem de nenhuma soma bater exatamente.

    Uma conta é folha (analítica) quando nenhuma outra conta da lista tem
    uma classificação que é "filha" dela (começa com "<classificacao>.").
    Os ancestrais de uma folha são as contas cuja classificação é um
    prefixo da dela (ex.: folha "1.1.1.01.00001" tem ancestrais nas
    classificações "1", "1.1", "1.1.1", "1.1.1.01", se existirem na lista).
    """
    por_classificacao = {c.classificacao: c for c in contas if c.classificacao}
    todas = sorted(por_classificacao.keys())

    folhas: list[tuple[ContaBalancete, list[str]]] = []
    for conta in contas:
        if conta.classificacao is None:
            continue
        prefixo = conta.classificacao + "."
        tem_filho = any(outra != conta.classificacao and outra.startswith(prefixo) for outra in todas)
        if tem_filho:
            continue

        partes = conta.classificacao.split(".")
        ancestrais = []
        for i in range(1, len(partes)):
            ancestral = por_classificacao.get(".".join(partes[:i]))
            if ancestral is not None:
                ancestrais.append(ancestral.descricao)
        folhas.append((conta, ancestrais))
    return folhas


def _identificar_folhas(contas: list[ContaBalancete]) -> list[tuple[ContaBalancete, list[str]]]:
    """Escolhe o método de reconstrução de hierarquia: por classificação
    (mais robusto) quando toda conta tem esse campo preenchido, senão por
    reconciliação de valores (layouts sem coluna de classificação)."""
    if contas and all(c.classificacao for c in contas):
        return _identificar_folhas_por_classificacao(contas)
    return _identificar_folhas_por_reconciliacao(contas)


def _validar_identidade_contabil(folhas: list[tuple[ContaBalancete, list[str]]]) -> None:
    """Confere se a soma das folhas devedoras bate com a soma das credoras.

    Em qualquer balancete válido, de qualquer plano de contas ou sistema,
    débito total = crédito total (é a própria definição de "balancete" —
    verificar esse equilíbrio). Como cada conta agregadora foi substituída
    pelas suas folhas (mesma soma, mesma natureza), essa igualdade também
    vale só entre as folhas identificadas — é uma conferência independente
    do layout e do algoritmo de reconciliação de hierarquia.

    Isso existe porque `_identificar_folhas` assume que o balancete lista
    as contas em pré-ordem estrita (pai imediatamente seguido de todos os
    filhos, contíguos). Se um sistema exportar em outra ordem, o algoritmo
    pode "fechar" grupos errados — sem dar erro nenhum na hora, só devolvendo
    um conjunto de folhas que não fecha a conta. Essa validação pega
    exatamente esse caso: se não bater, é sinal de que a suposição de
    ordem não valeu pra este PDF, e é melhor falhar alto do que devolver
    lançamentos com valor errado.
    """
    total_devedor = sum(conta.saldo_atual for conta, _ in folhas if conta.natureza == "D")
    total_credor = sum(conta.saldo_atual for conta, _ in folhas if conta.natureza == "C")
    if abs(total_devedor - total_credor) >= EPS_IDENTIDADE_CONTABIL:
        raise LeitorBalanceteError(
            "A reconstrução da hierarquia de contas não fechou: total devedor "
            f"(R$ {total_devedor:,.2f}) não bate com o total credor "
            f"(R$ {total_credor:,.2f}) entre as contas analíticas identificadas. "
            "Isso normalmente significa que este balancete lista as contas em "
            "uma ordem diferente da esperada (pai nem sempre seguido pelos "
            "filhos) — os números não são confiáveis; não prossiga sem revisar "
            "o layout deste PDF."
        )


def _inferir_categoria(*textos: str) -> str:
    junto = " ".join(_normalizar(t) for t in textos)
    for palavras, categoria in _PALAVRAS_CATEGORIA:
        if any(p in junto for p in palavras):
            return categoria
    return "outros"


# \b evita falso positivo de "venda" dentro de "revenda" (conta de estoque, não receita).
# "resultado bruto"/"resultado liquido" propositalmente NÃO entram aqui: são
# ancestrais tanto de contas de receita quanto de custo/despesa num DRE real
# (RESULTADO BRUTO tem RECEITA, CUSTOS e DESPESAS como ramos irmãos) — usá-los
# como gatilho de receita classificava custo/despesa como receita.
_PADRAO_PALAVRA_RECEITA = re.compile(r"\b(receita|venda|faturamento|servicos? prestados?)")
_PALAVRAS_DESPESA = ("despesa", "custo", "cpv", "cmv")

# "Estoque inicial"/"estoque final" dentro de CUSTOS DOS PRODUTOS VENDIDOS não
# são despesas isoladas: são as duas pontas de uma fórmula de rateio
# (CPV = estoque inicial + compras − estoque final), e só a combinação das
# duas (o saldo líquido da conta sintética "CUSTOS DOS PRODUTOS VENDIDOS")
# representa o custo do período de fato. Como o contrato de lançamentos só
# aceita valor positivo (sem como subtrair um do outro aqui), contar só o
# "estoque inicial" (que sozinho pode ser dezenas de milhões, o estoque
# TOTAL da empresa, não um gasto do mês) infla a despesa em ordens de
# grandeza — visto num balancete real (Termoquimica): R$ 91,68 milhões de
# "estoque inicial" sozinho, contra um CPV líquido real de R$ 818 mil.
# Sem suporte a valor com sinal na base do motor, a opção seria contável
# é excluir os dois lados em vez de somar um deles como se fosse o custo
# inteiro.
_PALAVRAS_ROLLOVER_ESTOQUE = ("estoque inicial", "estoque final")


def _classificar(conta: ContaBalancete, ancestrais: list[str]) -> Optional[tuple[str, str, str]]:
    """Decide se uma conta-folha é receita, despesa, ou nenhuma das duas
    (contas puramente patrimoniais, como saldo de caixa ou capital, não
    entram como lançamento). Devolve (tipo, categoria, origem) ou None.

    `origem` é "resultado" quando a conta vem de um ramo de receita/despesa/
    custo de verdade (uma seção de Resultado/DRE no balancete), ou
    "fornecedor_pagavel" quando vem só do saldo a pagar a um fornecedor
    (PASSIVO CIRCULANTE, sem nenhuma seção de Resultado no balancete pra se
    basear) — usado por `_montar_dataframe` pra não somar as duas coisas
    juntas quando há dado de Resultado de verdade (ver lá o porquê).
    """
    caminho = " ".join(_normalizar(a) for a in ancestrais)
    descricao_norm = _normalizar(conta.descricao)

    if any(p in descricao_norm for p in _PALAVRAS_ROLLOVER_ESTOQUE):
        return None

    # Despesa/custo é checado ANTES de receita de propósito: um DRE real tem
    # categorias como "DESPESAS COM VENDAS" ou "SERVIÇOS PRESTADOS POR
    # TERCEIROS" que contêm "venda"/"serviços prestados" mas são despesa, não
    # receita — o ancestral mais específico (despesa/custo) deve vencer.
    if any(p in caminho for p in _PALAVRAS_DESPESA):
        # Dentro de um ramo de despesa/custo, a convenção é natureza D
        # (devedora). Uma folha C aí dentro é um abatimento/estorno dentro
        # da própria conta de custo (ex.: "(+) ESTOQUE FINAL" em CUSTOS DOS
        # PRODUTOS VENDIDOS reduz o custo, não soma) — como o contrato de
        # lançamentos só aceita valor sempre positivo (sem como subtrair),
        # a opção segura é excluir em vez de somar como despesa errada.
        if conta.natureza != "D":
            return None
        return "despesa", _inferir_categoria(conta.descricao, *ancestrais), "resultado"

    if _PADRAO_PALAVRA_RECEITA.search(caminho) or _PADRAO_PALAVRA_RECEITA.search(descricao_norm):
        # Convenção contábil comum: conta cuja descrição começa com "(-)" é
        # uma conta redutora (dedução) — mesmo estando sob um ancestral
        # "receita" (ex.: "(-) ICMS" sob "(-) Deduções da Receita Bruta" é
        # imposto sobre venda, não receita). Só vale AQUI, quando a conta já
        # ia ser classificada como receita — "(-)" sozinho não é sinal de
        # despesa (contas de balanço como "(-) Depreciações Acumuladas" ou
        # "(-) Prejuízos Acumulados" também começam com "(-)" e não são
        # gasto do período; essas continuam caindo em `None` abaixo).
        if conta.descricao.strip().startswith("(-)"):
            if conta.natureza != "D":
                return None
            return "despesa", _inferir_categoria(conta.descricao, *ancestrais), "resultado"
        # Receita "de verdade" é natureza C; uma folha D aqui é uma
        # correção/estorno pontual (mesmo raciocínio do bloco de despesa
        # acima) — exclui em vez de somar como receita errada.
        if conta.natureza != "C":
            return None
        return "receita", _inferir_categoria(conta.descricao, *ancestrais), "resultado"

    if any("fornecedor" in _normalizar(a) for a in ancestrais):
        return "despesa", _inferir_categoria(conta.descricao, *ancestrais), "fornecedor_pagavel"

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
        tipo, categoria, origem = classificacao
        linhas.append(
            {
                "data": data_lancamento,
                "tipo": tipo,
                "categoria": categoria,
                "fornecedor": conta.descricao,
                "valor": conta.saldo_atual,
                "descricao": " > ".join([*ancestrais, conta.descricao]),
                "_origem": origem,
            }
        )

    # Quando o balancete tem uma seção de Resultado/DRE de verdade (pelo
    # menos uma despesa vinda de lá), o saldo de fornecedores a pagar
    # (PASSIVO CIRCULANTE) some dos lançamentos: é só o que ainda está em
    # aberto no fim do período, não o total gasto no período — contar os
    # dois juntos infla a despesa artificialmente (uma empresa com anos de
    # operação sempre tem fornecedores a pagar, isso não é "gasto extra").
    # Sem uma seção de Resultado (balancete só com saldos, como o primeiro
    # testado neste projeto), o saldo a pagar é o único sinal de despesa
    # disponível e continua sendo usado.
    tem_resultado_de_verdade = any(
        linha["_origem"] == "resultado" and linha["tipo"] == "despesa" for linha in linhas
    )
    if tem_resultado_de_verdade:
        linhas = [linha for linha in linhas if linha["_origem"] != "fornecedor_pagavel"]

    if not linhas:
        raise LeitorBalanceteError(
            "Nenhuma conta de receita/despesa foi identificada no balancete. "
            "Verifique se o arquivo é mesmo um balancete/DRE contábil."
        )
    df = pd.DataFrame(linhas, columns=["data", "tipo", "categoria", "fornecedor", "valor", "descricao", "_origem"])
    return df.drop(columns="_origem")


def processar_texto_balancete(texto: str) -> pd.DataFrame:
    """Núcleo puro (sem I/O) do parser: texto extraído do PDF -> lançamentos."""
    contas = _parse_linhas_texto(texto)
    if not contas:
        # detect_document_type (dados.utils, do pipeline do Eduardo) ajuda a
        # diferenciar "não é nem um documento contábil" de "é um documento
        # contábil, mas o layout de colunas não é nenhum dos cadastrados".
        tipo_detectado = detect_document_type(texto)
        if tipo_detectado == "DESCONHECIDO":
            raise LeitorBalanceteError(
                "Não foi possível reconhecer nenhuma conta no texto do balancete, "
                "e o documento não parece ser um Balancete/DRE/Balanço "
                "Patrimonial/Livro Razão (nenhum desses termos aparece no texto). "
                "Confira se o arquivo enviado é mesmo o documento contábil certo."
            )
        raise LeitorBalanceteError(
            f"O documento foi identificado como {tipo_detectado}, mas nenhuma "
            "conta pôde ser extraída com os layouts de coluna conhecidos "
            "(_LAYOUTS_CONHECIDOS). Provavelmente vem de um sistema contábil "
            "diferente do testado — é preciso cadastrar um novo layout a "
            "partir deste exemplo."
        )
    _validar_contas(contas)
    folhas = _identificar_folhas(contas)
    _validar_identidade_contabil(folhas)
    data_lancamento = _extrair_data_periodo_de_texto(texto)
    return _montar_dataframe(folhas, data_lancamento)


# Nº mínimo de caracteres não-espaço pra considerar que o PDF já tem texto
# extraível de verdade; abaixo disso, tenta OCR (documento escaneado/imagem).
_MINIMO_CARACTERES_TEXTO_PDF = 20


def _texto_insuficiente(texto: str) -> bool:
    return len(re.sub(r"\s", "", texto)) < _MINIMO_CARACTERES_TEXTO_PDF


# Locais comuns onde o instalador do Tesseract no Windows coloca o binário,
# quando ele não fica no PATH do processo Python (ex.: acabou de instalar
# na mesma sessão, ou instalado por um instalador que não atualiza o PATH
# de processos já abertos).
_CAMINHOS_TESSERACT_WINDOWS = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
)


def _configurar_caminho_tesseract(pytesseract_modulo) -> None:
    """Se `tesseract` não estiver no PATH, tenta os locais de instalação
    padrão do Windows antes de desistir (ver `_extrair_texto_via_ocr`)."""
    try:
        pytesseract_modulo.get_tesseract_version()
        return  # já está no PATH, nada a fazer
    except Exception:
        pass
    for caminho in _CAMINHOS_TESSERACT_WINDOWS:
        if Path(caminho).exists():
            pytesseract_modulo.pytesseract.tesseract_cmd = caminho
            return


def _idioma_ocr_disponivel(pytesseract_modulo) -> str:
    """Usa português se o pacote de idioma estiver instalado; senão inglês
    (sempre disponível em qualquer instalação do Tesseract) — degrada a
    qualidade do reconhecimento de acentos, mas não impede o OCR de rodar.
    """
    try:
        idiomas = pytesseract_modulo.get_languages(config="")
    except Exception:
        return "eng"
    return "por" if "por" in idiomas else "eng"


def _extrair_texto_via_ocr(caminho: Path | str) -> str:
    """Fallback via OCR pra PDF sem camada de texto (documento escaneado/foto).

    Renderiza cada página como imagem (pypdfium2 — não depende do poppler)
    e roda reconhecimento óptico de caracteres (pytesseract/Tesseract).
    Levanta `LeitorBalanceteError` com mensagem acionável se as bibliotecas
    Python ou o motor Tesseract não estiverem instalados, em vez de um
    traceback confuso.
    """
    try:
        import pypdfium2 as pdfium
        import pytesseract
    except ImportError as erro:
        raise LeitorBalanceteError(
            "Este PDF não tem texto extraível (parece ser um documento "
            "escaneado/imagem). Suporte a OCR requer as bibliotecas "
            "pypdfium2 e pytesseract (pip install pypdfium2 pytesseract)."
        ) from erro

    _configurar_caminho_tesseract(pytesseract)
    try:
        pytesseract.get_tesseract_version()
    except Exception as erro:
        raise LeitorBalanceteError(
            "Este PDF não tem texto extraível (parece ser um documento "
            "escaneado/imagem) e o motor de OCR Tesseract não foi encontrado "
            "no sistema. Instale o Tesseract OCR "
            "(https://github.com/tesseract-ocr/tesseract#installing-tesseract) "
            "e tente novamente."
        ) from erro

    idioma = _idioma_ocr_disponivel(pytesseract)
    documento = pdfium.PdfDocument(str(Path(caminho)))
    paginas_texto = []
    for pagina in documento:
        # scale=3 (~216dpi numa página A4) — resolução necessária pro OCR
        # reconhecer números pequenos de balancete com uma taxa de acerto
        # razoável; menos que isso costuma confundir dígitos parecidos.
        imagem = pagina.render(scale=3).to_pil()
        # --psm 6 ("bloco único de texto"): sem isso, o Tesseract tende a
        # detectar cada coluna da tabela como um bloco de texto separado e
        # devolve os números agrupados por coluna (todo "Saldo Anterior"
        # primeiro, depois todo "Débito"...) em vez de linha por linha —
        # o que quebra completamente o parser, que espera uma conta por linha.
        paginas_texto.append(
            pytesseract.image_to_string(imagem, lang=idioma, config="--psm 6")
        )
    return "\n".join(paginas_texto)


def _extrair_texto_pdf(caminho: Path | str) -> str:
    leitor = pypdf.PdfReader(str(Path(caminho)))
    texto = "\n".join(pagina.extract_text() or "" for pagina in leitor.pages)
    if _texto_insuficiente(texto):
        texto = _extrair_texto_via_ocr(caminho)
    return texto


def ler_balancete_pdf(caminho: Path | str) -> pd.DataFrame:
    """Lê um balancete em PDF e devolve o DataFrame de lançamentos do motor.

    Levanta `LeitorBalanceteError` com uma mensagem acionável quando o PDF
    não tem o layout esperado (não é possível reconhecer contas, os valores
    não reconciliam, ou a hierarquia de contas não fecha).
    """
    return processar_texto_balancete(_extrair_texto_pdf(caminho))


def extrair_metadados_balancete(caminho: Path | str) -> dict[str, Optional[str]]:
    """Extrai metadados do cabeçalho do balancete (empresa, CNPJ, período, ...).

    Reaproveita `dados.utils.extract_header_metadata` (pipeline do Eduardo) —
    não faz parsing de contas, só do cabeçalho, então funciona mesmo que o
    layout de colunas do corpo do balancete não seja um dos suportados.
    Pensado pra exibição na interface (ex.: confirmar "Empresa: X, CNPJ: Y"
    logo após o upload), não é usado pelo motor de análise.
    """
    return extract_header_metadata(_extrair_texto_pdf(caminho))
