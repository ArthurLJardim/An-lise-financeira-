# -*- coding: utf-8 -*-
"""
extrator.py
===========
Camada responsável por transformar um PDF de balancete em objetos
`Balancete` estruturados (ver `modelos.py`).

O DESAFIO TÉCNICO
------------------
Balancetes emitidos por sistemas contábeis brasileiros populares (ex.:
Domínio Sistemas) costumam ter uma armadilha para quem tenta extrair o
texto de forma ingênua: o gerador de relatório desenha, por baixo de boa
parte das linhas, uma segunda camada de texto (um "rótulo fantasma", igual
ao conteúdo da própria linha) na mesma altura da linha real, deslocada só
uma fração de ponto na vertical. Ferramentas de extração de texto simples
(inclusive `pdfplumber.extract_text()` "cru" e `pdftotext`) enxergam as
duas camadas sobrepostas e embaralham os caracteres, produzindo lixo do
tipo "ATIVO2 CIRACTUIVLOA CNITRECULANTE" em vez de "2 ATIVO CIRCULANTE".

A SOLUÇÃO
---------
Em vez de tentar extrair texto e consertar com regex (abordagem frágil,
usada no protótipo original), este módulo trabalha diretamente com a
posição geométrica de cada caractere do PDF:

    1. Cada caractere carrega sua coordenada exata (x0, top).
    2. Agrupamos os caracteres por linha de base ('top'), com alta
       precisão (2 casas decimais) — cada camada de texto sobreposta cai
       em um grupo diferente, mesmo que a diferença seja de menos de 1pt.
    3. Uma linha de dados REAL sempre contém os 4 valores monetários da
       tabela (Saldo Anterior, Débito, Crédito, Saldo Atual), que ficam
       numa faixa de posição horizontal conhecida. O texto fantasma nunca
       carrega números — ele é só um rótulo decorativo. Isso nos dá um
       discriminador simples e muito confiável.
    4. Descartamos todo grupo que não alcança essa faixa e reconstruímos
       o texto apenas com os grupos "de dados", linha a linha, na ordem
       vertical original.

O resultado é uma extração perfeitamente limpa, sem depender de negrito,
sem heurística de "colar strings parecidas" e sem falsos positivos.

Se o PDF de entrada não tiver essa peculiaridade (ou seja, vier de outro
sistema contábil), o algoritmo simplesmente não encontra nada para
descartar e se comporta como uma extração de texto comum — por isso ele
serve como estratégia única e não precisa de um "modo B".
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pdfplumber

from modelos import Balancete, ContaContabil, Empresa, Fornecedor, Natureza

# --------------------------------------------------------------------------
# Padrões de reconhecimento
# --------------------------------------------------------------------------

# Um valor monetário no padrão brasileiro: 1.234.567,89 ou 0,00
_PADRAO_VALOR = r"\d{1,3}(?:\.\d{3})*,\d{2}"

# Uma linha de dados já "limpa": código, descrição, 4 valores e a natureza
# (D de Devedor ou C de Credor) colada no último valor.
_RE_LINHA_DADOS = re.compile(
    r"^(?P<codigo>\d+)\s+(?P<descricao>.+?)\s+"
    rf"(?P<saldo_anterior>{_PADRAO_VALOR})\s+"
    rf"(?P<debito>{_PADRAO_VALOR})\s+"
    rf"(?P<credito>{_PADRAO_VALOR})\s+"
    rf"(?P<saldo_atual>{_PADRAO_VALOR})(?P<natureza>[DC])\s*$"
)

_RE_EMPRESA = re.compile(r"Empresa:\s*(.+?)\s+(?:Folha:|C\.N\.P\.J\.|$)")
_RE_CNPJ = re.compile(r"C\.N\.P\.J\.:\s*([\d./-]+)")
_RE_PERIODO = re.compile(
    r"Per[íi]odo:\s*(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})"
)

# Margem de segurança usada quando não conseguimos localizar dinamicamente
# o início da coluna "Saldo Anterior" (ver `_limiar_coluna_valores`).
_LIMIAR_PADRAO_X = 280.0

# Palavras que indicam que a conta é um grupo/subtotal de alto nível e
# NÃO um fornecedor individual — usadas para saber onde a lista de
# fornecedores termina dentro do plano de contas.
PALAVRAS_FIM_DE_GRUPO = [
    "ATIVO", "PASSIVO", "PATRIMONIO", "PATRIMÔNIO", "RECEITA", "RECEITAS",
    "DESPESA", "DESPESAS", "CUSTO", "CUSTOS", "RESULTADO", "CIRCULANTE",
    "DISPONIVEL", "DISPONÍVEL", "ESTOQUE", "IMOBILIZADO", "INTANGIVEL",
    "INTANGÍVEL", "TRIBUTOS", "IMPOSTOS", "EMPRESTIMO", "EMPRÉSTIMO",
    "FINANCIAMENTO", "PROVISAO", "PROVISÃO", "LUCRO", "PREJUIZO",
    "PREJUÍZO", "CAPITAL SOCIAL", "RESERVA", "OBRIGACOES TRIBUTARIAS",
    "OBRIGAÇÕES TRIBUTÁRIAS", "SALARIOS", "SALÁRIOS", "ENCARGOS",
]


def _texto_para_float(texto: str) -> float:
    """Converte '1.234.567,89' (formato brasileiro) em 1234567.89 (float)."""
    return float(texto.replace(".", "").replace(",", "."))


def _texto_para_data(texto: str) -> Optional[date]:
    try:
        return datetime.strptime(texto, "%d/%m/%Y").date()
    except ValueError:
        return None


class ErroExtracao(Exception):
    """Erro de alto nível levantado quando o PDF não pôde ser interpretado."""


class ExtratorBalancete:
    """Lê um arquivo PDF de balancete e devolve um objeto `Balancete`."""

    def __init__(self, verboso: bool = False):
        self.verboso = verboso

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def extrair(self, caminho_pdf: str) -> Balancete:
        caminho = Path(caminho_pdf)
        if not caminho.exists():
            raise ErroExtracao(f"Arquivo não encontrado: {caminho_pdf}")

        linhas_texto: List[str] = []
        try:
            with pdfplumber.open(caminho) as pdf:
                if len(pdf.pages) == 0:
                    raise ErroExtracao("O PDF não contém páginas.")
                limiar = None
                topo_cabecalho = None
                for pagina in pdf.pages:
                    achado = self._localizar_cabecalho_tabela(pagina)
                    if achado:
                        limiar, topo_cabecalho = achado
                    linhas_texto.extend(
                        self._linhas_limpas(
                            pagina,
                            limiar if limiar is not None else _LIMIAR_PADRAO_X,
                            topo_cabecalho if topo_cabecalho is not None else 0.0,
                        )
                    )
        except ErroExtracao:
            raise
        except Exception as exc:  # pdfplumber/pypdf podem lançar vários tipos
            raise ErroExtracao(
                f"Não foi possível ler o PDF '{caminho_pdf}': {exc}"
            ) from exc

        texto_completo = "\n".join(linhas_texto)
        if not texto_completo.strip():
            raise ErroExtracao(
                "Nenhum texto pôde ser extraído do PDF. Se o arquivo for "
                "digitalizado (uma foto/scan da folha), este extrator não "
                "funciona — seria necessário OCR, o que está fora do "
                "escopo deste projeto."
            )

        empresa = self._extrair_empresa(texto_completo)
        contas = self._extrair_contas(linhas_texto)

        if not contas:
            raise ErroExtracao(
                "O texto foi extraído, mas nenhuma linha reconhecível de "
                "conta contábil foi encontrada. O layout deste balancete "
                "pode ser diferente do esperado pelo parser."
            )

        fornecedores = self._extrair_fornecedores(contas)

        return Balancete(
            empresa=empresa,
            contas=contas,
            fornecedores=fornecedores,
            arquivo_origem=str(caminho),
        )

    # ------------------------------------------------------------------
    # Desembaralhamento posicional (o núcleo técnico do módulo)
    # ------------------------------------------------------------------

    @staticmethod
    def _localizar_cabecalho_tabela(pagina) -> Optional[Tuple[float, float]]:
        """
        Localiza, a partir do texto "Saldo Anterior" no cabeçalho da
        tabela, dois números que tornam o algoritmo independente de
        margens fixas "chumbadas" no código:

            limiar_x        -> x0 a partir do qual uma linha é considerada
                                "linha de dados" (por conter valores).
            topo_cabecalho  -> posição vertical (top) da própria linha de
                                cabeçalho da tabela.

        O filtro de desembaralhamento (ver `_linhas_limpas`) só é aplicado
        ABAIXO dessa linha de cabeçalho; tudo o que vem antes (identificação
        da empresa, CNPJ, período) é sempre preservado sem alteração, pois
        essa área do relatório não sofre do problema de texto sobreposto.

        Retorna None se o cabeçalho não for encontrado nesta página (ex.:
        páginas de continuação sem cabeçalho repetido) — nesse caso quem
        chamou deve reaproveitar os valores da página anterior.
        """
        try:
            palavras = pagina.extract_words()
        except Exception:
            return None

        for i, palavra in enumerate(palavras[:-1]):
            if palavra["text"].strip("():") == "Saldo" and i + 1 < len(palavras):
                seguinte = palavras[i + 1]["text"]
                if seguinte.startswith("Anterior"):
                    limiar_x = max(0.0, palavra["x0"] - 25.0)
                    topo_cabecalho = palavra["top"] + 3.0  # já abaixo do próprio cabeçalho
                    return limiar_x, topo_cabecalho
        return None

    @staticmethod
    def _linhas_limpas(pagina, limiar_x: float, topo_cabecalho: float) -> List[str]:
        """
        Implementa o algoritmo descrito no cabeçalho do módulo: agrupa
        caracteres por linha de base exata e, apenas na região da tabela
        (abaixo de `topo_cabecalho`), mantém somente os grupos que avançam
        até a área das colunas de valores — descartando o texto fantasma.
        Tudo o que está acima do cabeçalho (bloco de identificação da
        empresa) é sempre preservado.
        """
        grupos: Dict[float, list] = defaultdict(list)
        for char in pagina.chars:
            grupos[round(char["top"], 1)].append(char)

        tops_validos = set()
        for top, chars in grupos.items():
            if any(c["x0"] > limiar_x for c in chars):
                tops_validos.add(top)

        def manter(obj) -> bool:
            if obj.get("object_type") != "char":
                return True
            if obj["top"] < topo_cabecalho:
                return True  # bloco de identificação: nunca filtra
            return round(obj["top"], 1) in tops_validos

        pagina_filtrada = pagina.filter(manter)
        texto = pagina_filtrada.extract_text() or ""
        return texto.split("\n")

    # ------------------------------------------------------------------
    # Interpretação do texto já limpo
    # ------------------------------------------------------------------

    @staticmethod
    def _extrair_empresa(texto: str) -> Empresa:
        empresa = Empresa()

        m = _RE_EMPRESA.search(texto)
        if m:
            empresa.nome = " ".join(m.group(1).split())

        m = _RE_CNPJ.search(texto)
        if m:
            empresa.cnpj = m.group(1)

        m = _RE_PERIODO.search(texto)
        if m:
            empresa.periodo_inicio = _texto_para_data(m.group(1))
            empresa.periodo_fim = _texto_para_data(m.group(2))

        return empresa

    @staticmethod
    def _extrair_contas(linhas: List[str]) -> List[ContaContabil]:
        contas: List[ContaContabil] = []
        for linha_bruta in linhas:
            linha = " ".join(linha_bruta.split())
            m = _RE_LINHA_DADOS.match(linha)
            if not m:
                continue
            d = m.groupdict()
            contas.append(
                ContaContabil(
                    codigo=d["codigo"],
                    descricao=d["descricao"].strip(" .") or d["descricao"],
                    saldo_anterior=_texto_para_float(d["saldo_anterior"]),
                    debito=_texto_para_float(d["debito"]),
                    credito=_texto_para_float(d["credito"]),
                    saldo_atual=_texto_para_float(d["saldo_atual"]),
                    natureza=Natureza(d["natureza"]),
                )
            )
        return contas

    @staticmethod
    def _extrair_fornecedores(contas: List[ContaContabil]) -> List[Fornecedor]:
        """
        Localiza o grupo "Fornecedores" dentro do plano de contas e coleta
        as contas analíticas (os fornecedores individuais) logo abaixo
        dele, até encontrar a próxima conta de nível de grupo.
        """
        indice_cabecalho = None
        for i, conta in enumerate(contas):
            if "FORNECEDOR" in conta.descricao_normalizada:
                indice_cabecalho = i  # guarda o ÚLTIMO cabeçalho encontrado

        if indice_cabecalho is None:
            return []

        fornecedores: List[Fornecedor] = []
        for conta in contas[indice_cabecalho + 1:]:
            desc_up = conta.descricao_normalizada
            eh_fim_de_grupo = any(p in desc_up for p in PALAVRAS_FIM_DE_GRUPO)
            if eh_fim_de_grupo:
                break
            if "FORNECEDOR" in desc_up:
                # eventual sub-cabeçalho repetido — ignora e continua
                continue

            fornecedores.append(
                Fornecedor(
                    codigo=conta.codigo,
                    nome=conta.descricao.strip(),
                    saldo_anterior=conta.saldo_anterior,
                    debito=conta.debito,
                    credito=conta.credito,
                    saldo_em_aberto=conta.saldo_atual,
                )
            )

        return fornecedores
