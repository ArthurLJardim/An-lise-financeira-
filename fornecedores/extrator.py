# -*- coding: utf-8 -*-
"""
categorizador.py
=================
Classifica fornecedores em categorias de gasto usando um dicionário de
palavras-chave. Balancetes não trazem uma "categoria de despesa" pronta
para cada fornecedor (isso normalmente vive num plano de contas gerencial
que este PDF não expõe) — então a melhor aproximação sem usar serviços
externos é reconhecer padrões no próprio nome/razão social.

O dicionário abaixo cobre categorias comuns para pequenas e médias
empresas brasileiras. Ele foi pensado para ser fácil de estender: para
ensinar uma nova categoria, basta adicionar uma entrada em
`REGRAS_CATEGORIA`.
"""

from __future__ import annotations

import re
from typing import Dict, List

# Ordem importa: a primeira categoria cujo padrão bater é a escolhida.
# Padrões são avaliados como substring (case-insensitive) do nome do
# fornecedor já normalizado (maiúsculas, sem acento duplicado, etc).
REGRAS_CATEGORIA: Dict[str, List[str]] = {
    "Tecnologia / TI": [
        "INFORMATICA", "TECNOLOGIA", "SOFTWARE", "SISTEMAS", "DIGITAL",
        "COMPUTACAO", "TELECOM", "INTERNET", "HOSTING", "CLOUD", "DADOS",
        "TECH", "ELETRONIC",
    ],
    "Contabilidade / Jurídico / Consultoria": [
        "CONTABIL", "CONTABILIDADE", "ADVOCACIA", "ADVOGADO", "JURIDIC",
        "CONSULTORIA", "AUDITORIA", "ASSESSORIA CONTABIL", "PERICIA",
    ],
    "Assinaturas / Publicações / Informação": [
        "EDICOES", "EDITORA", "PUBLICACOES", "REVISTA", "JORNAL",
        "ASSINATURA", "INFORMACOES CADASTRAIS", "BOLETIM",
    ],
    "Material de Escritório / Papelaria": [
        "PAPELARIA", "ESCRITORIO", "SUPRIMENTOS", "GRAFICA", "IMPRESSOS",
    ],
    "Logística / Transporte": [
        "TRANSPORTE", "LOGISTICA", "FRETE", "ENTREGA", "CARGO", "EXPRESS",
        "COURIER", "MOTOBOY",
    ],
    "Alimentação": [
        "ALIMENTOS", "ALIMENTICIA", "REFEICOES", "RESTAURANTE", "LANCHONETE",
        "PADARIA", "DISTRIBUIDORA DE ALIMENTOS",
    ],
    "Construção / Manutenção / Engenharia": [
        "CONSTRUCAO", "ENGENHARIA", "REFORMA", "MANUTENCAO", "ELETRICA",
        "HIDRAULICA", "PREDIAL", "ARQUITETURA",
    ],
    "Marketing / Publicidade": [
        "MARKETING", "PUBLICIDADE", "PROPAGANDA", "COMUNICACAO", "AGENCIA",
        "DESIGN",
    ],
    "Saúde / Segurança do Trabalho": [
        "SAUDE", "MEDICIN", "SEGURANCA DO TRABALHO", "CLINICA", "LABORATORIO",
        "ODONTO",
    ],
    "Energia / Utilidades": [
        "ENERGIA", "ELETRICIDADE", "SANEAMENTO", "AGUA E ESGOTO", "GAS",
    ],
    "Serviços Gerais / Terceirizados": [
        "SERVICOS GERAIS", "LIMPEZA", "VIGILANCIA", "SEGURANCA PATRIMONIAL",
        "TERCEIRIZ",
    ],
}

# Um fornecedor cujo nome começa com uma sequência de 6+ dígitos seguida de
# um nome de pessoa costuma ser um prestador autônomo / pessoa física (o
# número é um identificador interno do sistema contábil, próximo de onde
# normalmente ficaria o CPF). Vale a pena sinalizar isso separadamente,
# pois o tratamento fiscal e de negociação com pessoa física é diferente.
_RE_PESSOA_FISICA = re.compile(r"^\d{5,}\s+[A-ZÀ-Ü][A-ZÀ-Ü\s]+$")


def categorizar_fornecedor(nome: str) -> str:
    """Retorna a categoria de gasto mais provável para o nome informado."""
    nome_up = " ".join(nome.upper().split())

    if _RE_PESSOA_FISICA.match(nome_up):
        return "Prestador Pessoa Física / Autônomo"

    for categoria, palavras_chave in REGRAS_CATEGORIA.items():
        for palavra in palavras_chave:
            if palavra in nome_up:
                return categoria

    return "Outros / Não classificado"


def categorizar_lista(fornecedores) -> None:
    """Preenche `fornecedor.categoria` in-place para uma lista de
    objetos `Fornecedor` (ver modelos.py)."""
    for fornecedor in fornecedores:
        fornecedor.categoria = categorizar_fornecedor(fornecedor.nome)
