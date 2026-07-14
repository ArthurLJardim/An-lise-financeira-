import pandas as pd
import pytest

from motor_analise import Alerta
from fornecedores.recomendacoes import COLUNAS_RECOMENDACOES, gerar_recomendacoes


def _alerta(categoria="mercadorias", severidade="alta", valor_atual=10000.0, valor_referencia=8000.0):
    return Alerta(
        categoria=categoria,
        tipo="estouro_orcamento",
        severidade=severidade,
        valor_atual=valor_atual,
        valor_referencia=valor_referencia,
        variacao_percentual=((valor_atual - valor_referencia) / valor_referencia) * 100,
        mensagem=f"Categoria '{categoria}' estourou o orçamento.",
    )


class TestGerarRecomendacoes:
    def test_sem_alertas_devolve_dataframe_vazio_com_colunas_do_contrato(self):
        df = gerar_recomendacoes([])
        assert df.empty
        assert list(df.columns) == COLUNAS_RECOMENDACOES

    def test_uma_linha_por_alerta(self):
        alertas = [_alerta("mercadorias"), _alerta("energia", severidade="critica")]
        df = gerar_recomendacoes(alertas)
        assert len(df) == 2
        assert set(df["categoria"]) == {"mercadorias", "energia"}

    def test_economia_estimada_e_a_diferenca_acima_da_referencia(self):
        df = gerar_recomendacoes([_alerta(valor_atual=10000.0, valor_referencia=8000.0)])
        assert df.iloc[0]["economia_estimada"] == pytest.approx(2000.0)

    def test_categoria_desconhecida_cai_no_fallback_outros(self):
        df = gerar_recomendacoes([_alerta("categoria-nunca-vista")])
        assert "Investigar causa do aumento" in df.iloc[0]["acao_recomendada"]

    def test_severidade_alta_ou_critica_ganha_prefixo_de_prioridade(self):
        df = gerar_recomendacoes([_alerta(severidade="critica")])
        assert df.iloc[0]["acao_recomendada"].startswith("PRIORIDADE CRÍTICA")

    def test_severidade_baixa_nao_ganha_prefixo_de_prioridade(self):
        df = gerar_recomendacoes([_alerta(severidade="baixa")])
        assert not df.iloc[0]["acao_recomendada"].startswith("PRIORIDADE")

    def test_usa_fornecedor_de_maior_gasto_na_categoria_quando_lancamentos_informado(self):
        lancamentos = pd.DataFrame(
            [
                ("2026-06-01", "despesa", "mercadorias", "Fornecedor Pequeno", 1000.0),
                ("2026-06-02", "despesa", "mercadorias", "Fornecedor Grande", 9000.0),
                ("2026-06-03", "despesa", "energia", "Cia Eletrica", 500.0),
            ],
            columns=["data", "tipo", "categoria", "fornecedor", "valor"],
        )
        df = gerar_recomendacoes([_alerta("mercadorias")], lancamentos)
        assert df.iloc[0]["fornecedor"] == "Fornecedor Grande"

    def test_sem_lancamentos_usa_categoria_como_fornecedor(self):
        df = gerar_recomendacoes([_alerta("mercadorias")])
        assert df.iloc[0]["fornecedor"] == "mercadorias"

    def test_alerta_com_fornecedor_proprio_tem_prioridade_sobre_lancamentos(self):
        alerta = _alerta("mercadorias")
        alerta.fornecedor = "Fornecedor Explicito"
        df = gerar_recomendacoes([alerta])
        assert df.iloc[0]["fornecedor"] == "Fornecedor Explicito"
