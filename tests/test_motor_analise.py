import pandas as pd
import pytest

from motor_analise import AnaliseFinanceira, ConfiguracaoAnalise, ContratoDadosError
from motor_analise.modelos import padronizar_categoria, validar_lancamentos, validar_orcamento


def _lancamentos(linhas):
    return pd.DataFrame(linhas, columns=["data", "categoria", "fornecedor", "valor"])


@pytest.fixture
def lancamentos_atual():
    return _lancamentos(
        [
            ("2026-06-01", "Mercadorias", "Fornecedor A", 12000.0),
            ("2026-06-05", "mercadorias", "Fornecedor B", 3000.0),
            ("2026-06-02", "energia", "Cia Eletrica", 1000.0),
            ("2026-06-03", "aluguel", "Imobiliaria", 5000.0),
        ]
    )


@pytest.fixture
def orcamento():
    return pd.DataFrame(
        [
            ("mercadorias", 10000.0),
            ("energia", 1000.0),
            ("aluguel", 5000.0),
        ],
        columns=["categoria", "limite"],
    )


class TestPadronizarCategoria:
    def test_remove_acentos_e_normaliza_caixa(self):
        assert padronizar_categoria("  Serviços  ") == "servicos"

    def test_valor_nao_string_vira_outros(self):
        assert padronizar_categoria(None) == "outros"


class TestValidacaoContrato:
    def test_lancamentos_sem_colunas_obrigatorias_leva_a_erro_claro(self):
        df = pd.DataFrame({"categoria": ["mercadorias"]})
        with pytest.raises(ContratoDadosError, match="Colunas obrigatórias ausentes"):
            validar_lancamentos(df)

    def test_lancamentos_vazio_leva_a_erro(self):
        with pytest.raises(ContratoDadosError):
            validar_lancamentos(pd.DataFrame())

    def test_valor_negativo_leva_a_erro(self, lancamentos_atual):
        df = lancamentos_atual.copy()
        df.loc[0, "valor"] = -10.0
        with pytest.raises(ContratoDadosError, match="negativos"):
            validar_lancamentos(df)

    def test_data_invalida_leva_a_erro(self, lancamentos_atual):
        df = lancamentos_atual.copy()
        df.loc[0, "data"] = "nao e uma data"
        with pytest.raises(ContratoDadosError, match="data inválida"):
            validar_lancamentos(df)

    def test_categoria_normalizada_apos_validacao(self, lancamentos_atual):
        resultado = validar_lancamentos(lancamentos_atual)
        assert set(resultado["categoria"]) == {"mercadorias", "energia", "aluguel"}

    def test_orcamento_agrupa_categorias_duplicadas(self):
        df = pd.DataFrame(
            [("Mercadorias", 100.0), ("mercadorias", 50.0)],
            columns=["categoria", "limite"],
        )
        resultado = validar_orcamento(df)
        assert resultado.set_index("categoria")["limite"]["mercadorias"] == 150.0


class TestAnaliseFinanceira:
    def test_analise_sem_bases_de_comparacao_retorna_resumo_e_rankings(self, lancamentos_atual):
        engine = AnaliseFinanceira()
        resultado = engine.analisar(lancamentos_atual)

        assert resultado.resumo["gasto_total"] == pytest.approx(21000.0)
        assert resultado.variacoes.empty
        assert resultado.alertas == []
        assert "por_categoria" in resultado.rankings
        assert "por_fornecedor" in resultado.rankings

    def test_analise_com_orcamento_gera_alerta_de_estouro(self, lancamentos_atual, orcamento):
        engine = AnaliseFinanceira()
        resultado = engine.analisar(lancamentos_atual, orcamento=orcamento)

        categorias_com_alerta = {a.categoria for a in resultado.alertas}
        assert "mercadorias" in categorias_com_alerta
        alerta_mercadorias = next(a for a in resultado.alertas if a.categoria == "mercadorias")
        assert alerta_mercadorias.tipo == "estouro_orcamento"
        # 15000 gasto vs 10000 limite = +50% => severidade critica
        assert alerta_mercadorias.severidade == "critica"

    def test_categoria_dentro_do_orcamento_nao_gera_alerta(self, lancamentos_atual, orcamento):
        engine = AnaliseFinanceira()
        resultado = engine.analisar(lancamentos_atual, orcamento=orcamento)
        categorias_com_alerta = {a.categoria for a in resultado.alertas}
        assert "aluguel" not in categorias_com_alerta

    def test_alertas_ordenados_por_severidade_decrescente(self, lancamentos_atual, orcamento):
        engine = AnaliseFinanceira()
        resultado = engine.analisar(lancamentos_atual, orcamento=orcamento)
        severidades = [a.severidade for a in resultado.alertas]
        ordem = {"critica": 0, "alta": 1, "media": 2, "baixa": 3}
        assert severidades == sorted(severidades, key=lambda s: ordem[s])

    def test_resumo_identifica_maior_aumento(self, lancamentos_atual, orcamento):
        engine = AnaliseFinanceira()
        resultado = engine.analisar(lancamentos_atual, orcamento=orcamento)
        assert resultado.resumo["maior_aumento"]["categoria"] == "mercadorias"

    def test_to_dict_e_totalmente_serializavel(self, lancamentos_atual, orcamento):
        import json

        engine = AnaliseFinanceira()
        resultado = engine.analisar(lancamentos_atual, orcamento=orcamento)
        json.dumps(resultado.to_dict())  # não deve levantar exceção

    def test_configuracao_limiares_invalidos_leva_a_erro(self):
        with pytest.raises(ValueError):
            ConfiguracaoAnalise(limiares_severidade={"baixa": 50, "media": 10, "alta": 30, "critica": 60})

    def test_limiares_customizados_mudam_severidade(self, lancamentos_atual, orcamento):
        config = ConfiguracaoAnalise(
            limiares_severidade={"baixa": 5, "media": 10, "alta": 20, "critica": 200}
        )
        engine = AnaliseFinanceira(config)
        resultado = engine.analisar(lancamentos_atual, orcamento=orcamento)
        alerta_mercadorias = next(a for a in resultado.alertas if a.categoria == "mercadorias")
        # com limiar de critica em 200%, uma variacao de 50% cai em "alta"
        assert alerta_mercadorias.severidade == "alta"

    def test_analise_com_historico_gera_variacao_atipica(self):
        atual = _lancamentos(
            [
                ("2026-06-01", "transporte", "Posto A", 6000.0),
            ]
        )
        historico = _lancamentos(
            [
                ("2026-05-01", "transporte", "Posto A", 4000.0),
            ]
        )
        engine = AnaliseFinanceira()
        resultado = engine.analisar(atual, historico=historico)
        alerta = next(a for a in resultado.alertas if a.categoria == "transporte")
        assert alerta.tipo == "variacao_historica"
        assert alerta.variacao_percentual == pytest.approx(50.0)
