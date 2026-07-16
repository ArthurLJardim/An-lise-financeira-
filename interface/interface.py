"""
INTERFACE - Miguel Cruzeiro Pinheiro

Contei com auxilio da IA para gerar o parte do código da interface
"""

import tempfile
from pathlib import Path
from typing import Optional

import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(
    page_title="Bot de Análise Financeira e Compras",
    page_icon="💰",
    layout="wide",
)

# Erro se o app for rodado fora da raiz do repositório

try:
    from motor_analise import AnaliseFinanceira
    from motor_analise.modelos import CATEGORIAS_PADRAO, TIPOS_LANCAMENTO
except ImportError:
    st.error(
        "Não foi possível importar `motor_analise`. Rode este app a partir da "
        "raiz do repositório do grupo (onde ficam as pastas `motor_analise/` "
        "e `dados/`), ex.: `streamlit run aplicativointerface.py`."
    )
    st.stop()

try:
    from dados.leitor_balancete import (
        LeitorBalanceteError,
        extrair_metadados_balancete,
        ler_balancete_pdf,
    )
except ImportError:
    st.error(
        "Não foi possível importar `dados.leitor_balancete`. Confirme se o "
        "arquivo do Eduardo está em `dados/leitor_balancete.py` na raiz do repo."
    )
    st.stop()

try:
    from fornecedores.recomendacoes import gerar_recomendacoes
except ImportError:
    st.error(
        "Não foi possível importar `fornecedores.recomendacoes`. Confirme se o "
        "arquivo está em `fornecedores/recomendacoes.py` na raiz do repo."
    )
    st.stop()



# Tratamento de dados 

COLUNAS_OBRIGATORIAS = {"data", "categoria", "fornecedor", "valor"}


def tratar_dados(arquivo_enviado) -> tuple[pd.DataFrame, Optional[dict]]:
    """Converte o arquivo enviado no DataFrame de lançamentos do contrato
    (CONTRATO_DADOS.md, seção 3): colunas `data`, `categoria`, `fornecedor`,
    `valor` (+ `tipo`, `produto`, `descricao` opcionais).

    Devolve `(dados, metadados)` — `metadados` (empresa/CNPJ/período do
    cabeçalho) só vem preenchido quando o arquivo é um balancete em PDF;
    para Excel/CSV já tratados não há cabeçalho contábil pra extrair.
    """
    nome = arquivo_enviado.name.lower()
    metadados = None

    if nome.endswith(".pdf"):
        # Balancete real de contabilidade -> usa o leitor do Eduardo.
        # `ler_balancete_pdf` espera um caminho em disco; o upload do
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(arquivo_enviado.getvalue())
            caminho_tmp = Path(tmp.name)
        try:
            dados = ler_balancete_pdf(caminho_tmp)
            metadados = extrair_metadados_balancete(caminho_tmp)
        except LeitorBalanceteError as erro:
            raise ValueError(str(erro)) from erro
        finally:
            caminho_tmp.unlink(missing_ok=True)

    elif nome.endswith((".xlsx", ".xls")):

        dados = pd.read_excel(arquivo_enviado)

    elif nome.endswith(".csv"):
        dados = pd.read_csv(arquivo_enviado)

    else:
        raise ValueError(f"Formato de arquivo não suportado: {arquivo_enviado.name}")

    return _validar_e_completar(dados), metadados


def _validar_e_completar(dados: pd.DataFrame) -> pd.DataFrame:
    faltando = COLUNAS_OBRIGATORIAS - set(dados.columns)
    if faltando:
        raise ValueError(
            "O arquivo não está no formato de lançamentos esperado pelo motor "
            f"(faltam as colunas: {', '.join(sorted(faltando))}). "
            "Veja docs/CONTRATO_DADOS.md, seção 3."
        )

    dados = dados.copy()
    dados["data"] = pd.to_datetime(dados["data"])
    dados["mes_ano"] = dados["data"].dt.strftime("%Y-%m")  # usado só para os filtros da interface

    if "tipo" not in dados.columns:
        dados["tipo"] = "despesa"  # contrato: ausente = despesa

    return dados


def alertas_para_dataframe(alertas: list) -> pd.DataFrame:
    """`resultado.alertas` é uma lista de `motor_analise.Alerta`, não um
    DataFrame — convertemos aqui só para exibir na tabela do Streamlit."""
    if not alertas:
        return pd.DataFrame(columns=["categoria", "severidade", "mensagem"])
    linhas = [
        {
            "categoria": getattr(alerta, "categoria", ""),
            "severidade": alerta.severidade,
            "mensagem": alerta.mensagem,
        }
        for alerta in alertas
    ]
    return pd.DataFrame(linhas)


# Barra lateral


if "dados" not in st.session_state:
    st.session_state.dados = None

with st.sidebar:
    st.title("💰 Bot Financeiro")
    st.caption("Análise de gastos e recomendação de fornecedores")

    st.subheader("1. Upload do arquivo")
    arquivo_enviado = st.file_uploader(
        "Envie um balancete (PDF) ou lançamentos já tratados (Excel/CSV)",
        type=["xlsx", "xls", "csv", "pdf"],
    )

    if arquivo_enviado is not None:
        # Sem essa checagem, `tratar_dados` reprocessaria o arquivo do zero a
        # cada interação (inclusive editar a tabela de revisão abaixo),
        # sobrescrevendo qualquer correção que o usuário tenha feito.
        identificador = f"{arquivo_enviado.name}:{arquivo_enviado.size}"
        if st.session_state.get("arquivo_processado") != identificador:
            try:
                st.session_state.dados, st.session_state.metadados = tratar_dados(arquivo_enviado)
                st.session_state.arquivo_processado = identificador
            except ValueError as erro:
                st.error(f"Erro ao processar o arquivo: {erro}")
                st.session_state.dados = None
                st.session_state.arquivo_processado = None

        if st.session_state.dados is not None:
            st.success(f"Arquivo '{arquivo_enviado.name}' carregado com sucesso!")
            metadados = st.session_state.get("metadados")
            if metadados and (metadados.get("empresa") or metadados.get("cnpj")):
                partes = [
                    f"**{metadados[campo]}**" if campo == "empresa" else metadados[campo]
                    for campo in ("empresa", "cnpj", "periodo")
                    if metadados.get(campo)
                ]
                st.caption(" · ".join(partes))

    st.divider()

    if st.session_state.dados is not None:
        st.subheader("2. Filtros")
        dados_completos = st.session_state.dados

        meses_disponiveis = sorted(dados_completos["mes_ano"].unique())
        meses_selecionados = st.multiselect("Mês", meses_disponiveis, default=meses_disponiveis)

        categorias_disponiveis = sorted(dados_completos["categoria"].unique())
        categorias_selecionadas = st.multiselect(
            "Categoria", categorias_disponiveis, default=categorias_disponiveis
        )

        fornecedores_disponiveis = sorted(dados_completos["fornecedor"].unique())
        fornecedores_selecionados = st.multiselect(
            "Fornecedor", fornecedores_disponiveis, default=fornecedores_disponiveis
        )

        st.divider()
        st.subheader("3. Comparação (opcional)")
        st.caption(
            "O motor só gera variações e alertas se você enviar orçamento "
            "e/ou histórico do período anterior (CONTRATO_DADOS.md §3)."
        )
        arquivo_orcamento = st.file_uploader(
            "Orçamento/limites por categoria (CSV: categoria, limite)", type=["csv"], key="orcamento"
        )
        arquivo_historico = st.file_uploader(
            "Histórico do período anterior (mesmo formato de lançamentos)", type=["csv"], key="historico"
        )

# Interface principal


st.title("💰 Bot de Análise Financeira e Compras")

if st.session_state.dados is None:
    st.markdown(
        """
Envie o **balancete contábil** da sua empresa (o PDF exportado direto do
sistema contábil) e o bot faz a análise sozinho — não precisa preparar
planilha nem categorizar nada na mão.

**O que o bot faz:**
- Lê o balancete e identifica automaticamente receitas e despesas por categoria
  (mercadorias, energia, folha, transporte, serviços, impostos, entre outras).
- Calcula se o período teve **lucro ou prejuízo** e a margem.
- Mostra **onde a empresa mais gasta**, por categoria e por fornecedor.
- Compara com um orçamento e/ou o balancete de um período anterior (opcional)
  e gera **alertas** quando algum gasto sai do esperado.
- Sugere fornecedores alternativos e onde há espaço pra economizar.

Antes de rodar a análise, você revisa numa tabela editável como cada
lançamento foi classificado — a classificação é automática por palavra-chave
e pode errar em planos de conta fora do usual, então dá pra corrigir ali
mesmo antes de continuar.
"""
    )
    st.info(
        "👈 Envie um balancete (PDF) ou uma planilha de lançamentos já tratados "
        "na barra lateral para começar a análise."
    )
    st.stop()

dados_filtrados = st.session_state.dados[
    (st.session_state.dados["mes_ano"].isin(meses_selecionados))
    & (st.session_state.dados["categoria"].isin(categorias_selecionadas))
    & (st.session_state.dados["fornecedor"].isin(fornecedores_selecionados))
]

if dados_filtrados.empty:
    st.warning("Nenhum dado encontrado para os filtros selecionados.")
    st.stop()


# Revisão antes de analisar

st.subheader("👀 Revisar lançamentos antes de analisar")
st.caption(
    "Categoria e tipo (receita/despesa) são classificados automaticamente por "
    "palavra-chave a partir do balancete e podem errar em planos de conta fora "
    "do usual — corrija aqui antes de rodar a análise. Data e fornecedor não "
    "são editáveis nesta tabela."
)
opcoes_categoria = sorted(set(CATEGORIAS_PADRAO) | set(dados_filtrados["categoria"].unique()))
colunas_exibidas = [c for c in dados_filtrados.columns if c != "mes_ano"]
dados_revisados = st.data_editor(
    dados_filtrados,
    column_order=colunas_exibidas,
    column_config={
        "categoria": st.column_config.SelectboxColumn("Categoria", options=opcoes_categoria, required=True),
        "tipo": st.column_config.SelectboxColumn("Tipo", options=list(TIPOS_LANCAMENTO), required=True),
        "valor": st.column_config.NumberColumn("Valor (R$)", min_value=0.0, format="R$ %.2f", required=True),
        "data": st.column_config.DateColumn("Data", disabled=True),
        "fornecedor": st.column_config.TextColumn("Fornecedor", disabled=True),
        "descricao": st.column_config.TextColumn("Descrição", disabled=True),
    },
    use_container_width=True,
    hide_index=True,
    num_rows="fixed",
    key="editor_lancamentos",
)
# Grava as correções de volta no dataset completo (por índice), pra persistir
# entre trocas de filtro e não perder a edição quando o app renderizar de novo.
st.session_state.dados.loc[dados_revisados.index, dados_revisados.columns] = dados_revisados

st.divider()

orcamento = pd.read_csv(arquivo_orcamento) if arquivo_orcamento is not None else None
historico = pd.read_csv(arquivo_historico) if arquivo_historico is not None else None

engine = AnaliseFinanceira()
resultado = engine.analisar(dados_revisados, orcamento=orcamento, historico=historico)

resumo = resultado.resumo
alertas = alertas_para_dataframe(resultado.alertas)
recomendacoes = gerar_recomendacoes(resultado.alertas, dados_revisados)


# Cards de resumo 

coluna1, coluna2, coluna3 = st.columns(3)

coluna1.metric("💵 Gasto Total", f"R$ {resumo['gasto_total']:,.2f}")

maior_aumento = resumo.get("maior_aumento")
if isinstance(maior_aumento, dict) and maior_aumento.get("categoria"):
    coluna2.metric(
        "📈 Maior Aumento",
        maior_aumento["categoria"],
        f"{maior_aumento.get('variacao_percentual', 0):+.1f}%",
    )
elif maior_aumento:
    coluna2.metric("📈 Maior Aumento", str(maior_aumento))
else:
    coluna2.metric("📈 Maior Aumento", "—")

economia_total = recomendacoes["economia_estimada"].sum() if not recomendacoes.empty else 0.0
coluna3.metric("♻️ Economia Estimada", f"R$ {economia_total:,.2f}")
if recomendacoes.empty:
    coluna3.caption("Nenhum alerta no período — sem estouro de orçamento/histórico para recomendar ação.")

st.divider()


# Gráfico de maiores despesas por categoria


st.subheader("Maiores Despesas por Categoria")

ranking_categoria = resultado.rankings["por_categoria"]
grafico = px.bar(
    ranking_categoria,
    x="categoria",
    y="total",
    text_auto=".2s",
    labels={"categoria": "Categoria", "total": "Valor (R$)"},
    color="total",
    color_continuous_scale="Blues",
)
grafico.update_layout(showlegend=False, coloraxis_showscale=False)
st.plotly_chart(grafico, use_container_width=True)

st.divider()


# Alertas financeiros

st.subheader("🚨 Alertas Financeiros")

if alertas.empty:
    if orcamento is None and historico is None:
        st.info(
            "Envie um orçamento ou histórico na barra lateral para o motor "
            "gerar alertas de estouro por categoria."
        )
    else:
        st.success("Nenhum alerta relevante identificado no período selecionado.")
else:
    st.dataframe(
        alertas.rename(columns={
            "categoria": "Categoria", "severidade": "Severidade", "mensagem": "Detalhe"
        }),
        use_container_width=True,
        hide_index=True,
    )

st.divider()


# Fornecedores e recomendações

st.subheader("🤝 Fornecedores e Recomendações de Economia")

if recomendacoes.empty:
    st.info(
        "Nenhuma recomendação a exibir: o motor só gera alertas quando há "
        "orçamento e/ou histórico para comparar (barra lateral, item 3) e "
        "algum estouro é identificado."
    )
else:
    st.dataframe(
        recomendacoes.rename(columns={
            "fornecedor": "Fornecedor",
            "categoria": "Categoria",
            "severidade": "Severidade",
            "acao_recomendada": "Ação Recomendada",
            "economia_estimada": "Economia Estimada (R$)",
        }).style.format({"Economia Estimada (R$)": "R$ {:,.2f}"}),
        use_container_width=True,
        hide_index=True,
    )

st.divider()


# Exportação

st.subheader("📄 Exportar Resultados")
st.caption(
    "O motor já tem `motor_analise.relatorio.gerar_relatorio(resultado)` "
    "para gerar um .txt (ver CONTRATO_DADOS.md §6). Os botões abaixo ainda "
    "precisam ser ligados a isso"
col_a, col_b = st.columns(2)
col_a.button("⬇️ Exportar análise (Excel)", disabled=True, use_container_width=True)
col_b.button("⬇️ Gerar relatório final (PDF/TXT)", disabled=True, use_container_width=True)
