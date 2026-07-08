import re

import pytest

import dados.leitor_balancete as leitor_balancete
from dados.leitor_balancete import LeitorBalanceteError, processar_texto_balancete


def _num(valor: float) -> str:
    """Formata um valor como número brasileiro (1.234,56), igual ao balancete."""
    texto = f"{valor:,.2f}"
    return texto.replace(",", "_").replace(".", ",").replace("_", ".")


def _linha(codigo: str, descricao: str, atual: float, natureza: str, credito: float, debito: float, anterior: float = 0.0) -> str:
    """Monta uma linha de conta no formato bruto extraído do PDF pelo pypdf
    (ordem das colunas invertida em relação à tabela visual: saldo atual,
    crédito, débito, saldo anterior, código, descrição)."""
    return f"{_num(atual)}{natureza}{_num(credito)}{_num(debito)}{_num(anterior)}{codigo} {descricao}"


# Balancete sintético (dados fictícios) com a mesma estrutura de um balancete
# real: ATIVO (caixa + estoque), PASSIVO (fornecedores + capital) e RESULTADO
# (receita de serviços) — usado pra validar reconstrução de hierarquia e
# classificação sem depender de nenhum PDF real nem de dados de terceiros.
_TEXTO_BALANCETE = "\n".join(
    [
        "Periodo: 01/01/2025 - 31/12/2025",
        _linha("1", "ATIVO", 58000.00, "D", 0.00, 58000.00, 0.00),
        _linha("2", "CAIXA GERAL", 50000.00, "D", 0.00, 50000.00, 0.00),
        _linha("3", "ESTOQUE DE MERCADORIAS", 8000.00, "D", 0.00, 8000.00, 0.00),
        _linha("10", "PASSIVO", 9500.00, "C", 9500.00, 0.00, 0.00),
        _linha("11", "FORNECEDORES", 6000.00, "C", 6000.00, 0.00, 0.00),
        _linha("12", "FORNECEDOR TESTE UM LTDA", 4000.00, "C", 4000.00, 0.00, 0.00),
        _linha("13", "FORNECEDOR TESTE DOIS EIRELI", 2000.00, "C", 2000.00, 0.00, 0.00),
        _linha("14", "CAPITAL SOCIAL", 3500.00, "C", 3500.00, 0.00, 0.00),
        _linha("20", "RESULTADO DO PERIODO", 15000.00, "C", 15000.00, 0.00, 0.00),
        _linha("21", "RECEITA DE PRESTACAO DE SERVICOS", 15000.00, "C", 15000.00, 0.00, 0.00),
    ]
)


class TestProcessarTextoBalancete:
    def test_gera_um_lancamento_por_conta_analitica(self):
        df = processar_texto_balancete(_TEXTO_BALANCETE)
        # CAIXA GERAL, ESTOQUE e CAPITAL SOCIAL são contas patrimoniais puras
        # (sem sinal de receita/despesa) e não devem virar lançamento.
        assert set(df["fornecedor"]) == {
            "FORNECEDOR TESTE UM LTDA",
            "FORNECEDOR TESTE DOIS EIRELI",
            "RECEITA DE PRESTACAO DE SERVICOS",
        }

    def test_nao_conta_contas_sinteticas_duas_vezes(self):
        df = processar_texto_balancete(_TEXTO_BALANCETE)
        despesas = df[df["tipo"] == "despesa"]["valor"].sum()
        receitas = df[df["tipo"] == "receita"]["valor"].sum()
        # PASSIVO (9500) = FORNECEDORES (6000, despesa) + CAPITAL (3500, excluido)
        assert despesas == pytest.approx(6000.00)
        assert receitas == pytest.approx(15000.00)

    def test_fornecedor_vira_despesa_categoria_mercadorias(self):
        df = processar_texto_balancete(_TEXTO_BALANCETE)
        linha = df[df["fornecedor"] == "FORNECEDOR TESTE UM LTDA"].iloc[0]
        assert linha["tipo"] == "despesa"
        assert linha["categoria"] == "mercadorias"
        assert linha["valor"] == pytest.approx(4000.00)

    def test_receita_de_servicos_vira_receita_categoria_servicos(self):
        df = processar_texto_balancete(_TEXTO_BALANCETE)
        linha = df[df["fornecedor"] == "RECEITA DE PRESTACAO DE SERVICOS"].iloc[0]
        assert linha["tipo"] == "receita"
        assert linha["categoria"] == "servicos"
        assert linha["valor"] == pytest.approx(15000.00)

    def test_nao_confunde_revenda_com_receita_de_venda(self):
        # "REVENDA" contém a substring "venda", mas é conta de estoque (ativo),
        # não de receita — não pode virar lançamento de receita.
        texto = "\n".join(
            [
                "Periodo: 01/01/2025 - 31/12/2025",
                _linha("1", "ATIVO", 3000.00, "D", 0.00, 3000.00, 0.00),
                _linha("2", "MERCADORIAS PARA REVENDA", 3000.00, "D", 0.00, 3000.00, 0.00),
                *_TEXTO_BALANCETE.splitlines()[8:],  # anexa o bloco de RESULTADO/RECEITA pra nao dar dataframe vazio
            ]
        )
        df = processar_texto_balancete(texto)
        assert "MERCADORIAS PARA REVENDA" not in set(df["fornecedor"])

    def test_usa_data_final_do_periodo_em_todos_os_lancamentos(self):
        df = processar_texto_balancete(_TEXTO_BALANCETE)
        assert set(df["data"]) == {"2025-12-31"}

    def test_sem_periodo_no_texto_usa_data_atual_sem_quebrar(self):
        texto = _TEXTO_BALANCETE.replace("Periodo: 01/01/2025 - 31/12/2025\n", "")
        df = processar_texto_balancete(texto)
        assert not df.empty

    def test_texto_sem_contas_reconheciveis_levanta_erro(self):
        with pytest.raises(LeitorBalanceteError):
            processar_texto_balancete("isso nao e um balancete, so texto qualquer")

    def test_conta_que_nao_reconcilia_levanta_erro(self):
        linha_quebrada = _linha("1", "ATIVO QUEBRADO", 1000.00, "D", 0.00, 999.00, 0.00)
        with pytest.raises(LeitorBalanceteError):
            processar_texto_balancete(linha_quebrada)

    def test_balancete_sem_nenhuma_conta_de_resultado_levanta_erro(self):
        texto = "\n".join(
            [
                _linha("1", "ATIVO", 1000.00, "D", 0.00, 1000.00, 0.00),
                _linha("2", "CAIXA GERAL", 1000.00, "D", 0.00, 1000.00, 0.00),
            ]
        )
        with pytest.raises(LeitorBalanceteError):
            processar_texto_balancete(texto)

    def test_dataframe_tem_colunas_do_contrato_de_lancamentos(self):
        df = processar_texto_balancete(_TEXTO_BALANCETE)
        assert list(df.columns) == ["data", "tipo", "categoria", "fornecedor", "valor", "descricao"]


class TestSelecaoDeLayout:
    """O parser não pode depender de um único layout de PDF (sistemas contábeis
    diferentes gravam as colunas em ordens diferentes no texto) — ele tenta os
    layouts cadastrados e usa a reconciliação de valores pra escolher qual bate.
    """

    def test_ignora_layout_que_nao_reconcilia_e_usa_o_que_reconcilia(self, monkeypatch):
        padrao_certo = leitor_balancete._LAYOUTS_CONHECIDOS[0]
        # Mesmo formato de linha, mas trocando os grupos "debito" e "credito" de
        # posicao: nunca vai reconciliar pra uma conta com movimentacao real,
        # simulando um layout de outro sistema contabil que nao e' o certo.
        padrao_errado = re.compile(
            rf"(?P<atual>{leitor_balancete._NUM})(?P<natureza>[DC])"
            rf"(?P<debito>{leitor_balancete._NUM})(?P<credito>{leitor_balancete._NUM})"
            rf"(?P<anterior>{leitor_balancete._NUM})(?P<codigo>\d+)\s+(?P<descricao>.+)$"
        )
        monkeypatch.setattr(
            leitor_balancete, "_LAYOUTS_CONHECIDOS", [padrao_errado, padrao_certo]
        )

        df = processar_texto_balancete(_TEXTO_BALANCETE)

        assert set(df["fornecedor"]) == {
            "FORNECEDOR TESTE UM LTDA",
            "FORNECEDOR TESTE DOIS EIRELI",
            "RECEITA DE PRESTACAO DE SERVICOS",
        }

    def test_nenhum_layout_cadastrado_bate_levanta_erro(self, monkeypatch):
        padrao_impossivel = re.compile(r"nao vai casar com nada aqui")
        monkeypatch.setattr(leitor_balancete, "_LAYOUTS_CONHECIDOS", [padrao_impossivel])

        with pytest.raises(LeitorBalanceteError):
            processar_texto_balancete(_TEXTO_BALANCETE)
