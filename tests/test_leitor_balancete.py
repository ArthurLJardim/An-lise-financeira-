import re
import shutil

import pytest

import dados.leitor_balancete as leitor_balancete
from dados.leitor_balancete import LeitorBalanceteError, processar_texto_balancete

_TESSERACT_DISPONIVEL = bool(
    shutil.which("tesseract") or any(
        __import__("pathlib").Path(c).exists() for c in leitor_balancete._CAMINHOS_TESSERACT_WINDOWS
    )
)


def _num(valor: float) -> str:
    """Formata um valor como número brasileiro (1.234,56), igual ao balancete."""
    texto = f"{valor:,.2f}"
    return texto.replace(",", "_").replace(".", ",").replace("_", ".")


def _linha(codigo: str, descricao: str, atual: float, natureza: str, credito: float, debito: float, anterior: float = 0.0) -> str:
    """Monta uma linha de conta no formato "reverso" (layout A — o único
    validado contra um balancete real): saldo atual, crédito, débito, saldo
    anterior, código, descrição — nessa ordem, sem espaço entre os campos."""
    return f"{_num(atual)}{natureza}{_num(credito)}{_num(debito)}{_num(anterior)}{codigo} {descricao}"


def _linha_classificada(
    codigo: str,
    classificacao: str,
    descricao: str,
    atual: float,
    natureza: str,
    anterior: float = 0.0,
    natureza_anterior: str | None = None,
    debito: float = 0.0,
    credito: float = 0.0,
) -> str:
    """Monta uma linha de conta no formato "classificado" (layout C):
    código, classificação (código hierárquico com pontos), saldo
    atual+natureza, saldo anterior (às vezes com natureza própria — quando
    None, sem sufixo), débito, crédito, descrição — descrição colada direto
    no crédito, sem espaço. Validado contra dois balancetes reais."""
    sufixo_anterior = natureza_anterior or ""
    return (
        f"{codigo} {classificacao} {_num(atual)}{natureza}{_num(anterior)}{sufixo_anterior} "
        f"{_num(debito)} {_num(credito)}{descricao}"
    )


def _linha_natural(codigo: str, descricao: str, atual: float, natureza: str, credito: float, debito: float, anterior: float = 0.0) -> str:
    """Monta uma linha de conta no formato "natural" (layout B): código,
    descrição, saldo anterior, débito, crédito, saldo atual — a própria
    ordem visual da tabela, com espaço entre os campos."""
    return (
        f"{codigo} {descricao}  {_num(anterior)}  {_num(debito)}  "
        f"{_num(credito)}  {_num(atual)}{natureza}"
    )


# Balancete sintético (dados fictícios) com a mesma estrutura de um balancete
# real: ATIVO (caixa + estoque), PASSIVO (fornecedores + capital) e RESULTADO
# (receita de serviços) — usado pra validar reconstrução de hierarquia e
# classificação sem depender de nenhum PDF real nem de dados de terceiros.
# Precisa ser um balancete de verdade: débito total = crédito total
# (58.000 nos dois lados) — senão a checagem de identidade contábil rejeita.
_TEXTO_BALANCETE = "\n".join(
    [
        "Periodo: 01/01/2025 - 31/12/2025",
        _linha("1", "ATIVO", 58000.00, "D", 0.00, 58000.00, 0.00),
        _linha("2", "CAIXA GERAL", 50000.00, "D", 0.00, 50000.00, 0.00),
        _linha("3", "ESTOQUE DE MERCADORIAS", 8000.00, "D", 0.00, 8000.00, 0.00),
        _linha("10", "PASSIVO", 16000.00, "C", 16000.00, 0.00, 0.00),
        _linha("11", "FORNECEDORES", 6000.00, "C", 6000.00, 0.00, 0.00),
        _linha("12", "FORNECEDOR TESTE UM LTDA", 4000.00, "C", 4000.00, 0.00, 0.00),
        _linha("13", "FORNECEDOR TESTE DOIS EIRELI", 2000.00, "C", 2000.00, 0.00, 0.00),
        _linha("14", "CAPITAL SOCIAL", 10000.00, "C", 10000.00, 0.00, 0.00),
        _linha("20", "RESULTADO DO PERIODO", 42000.00, "C", 42000.00, 0.00, 0.00),
        _linha("21", "RECEITA DE PRESTACAO DE SERVICOS", 42000.00, "C", 42000.00, 0.00, 0.00),
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
        # PASSIVO (16000) = FORNECEDORES (6000, despesa) + CAPITAL (10000, excluido)
        assert despesas == pytest.approx(6000.00)
        assert receitas == pytest.approx(42000.00)

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
        assert linha["valor"] == pytest.approx(42000.00)

    def test_nao_confunde_revenda_com_receita_de_venda(self):
        # "REVENDA" contém a substring "venda", mas é conta de estoque (ativo),
        # não de receita — não pode virar lançamento de receita. Balancete
        # mínimo próprio, balanceado (3000 nos dois lados) com uma conta de
        # fornecedor real pra não dar dataframe vazio.
        texto = "\n".join(
            [
                "Periodo: 01/01/2025 - 31/12/2025",
                _linha("1", "ATIVO", 3000.00, "D", 0.00, 3000.00, 0.00),
                _linha("2", "MERCADORIAS PARA REVENDA", 3000.00, "D", 0.00, 3000.00, 0.00),
                _linha("10", "PASSIVO", 3000.00, "C", 3000.00, 0.00, 0.00),
                _linha("11", "FORNECEDORES", 3000.00, "C", 3000.00, 0.00, 0.00),
                _linha("12", "FORNECEDOR TESTE LTDA", 3000.00, "C", 3000.00, 0.00, 0.00),
            ]
        )
        df = processar_texto_balancete(texto)
        assert "MERCADORIAS PARA REVENDA" not in set(df["fornecedor"])
        assert set(df["fornecedor"]) == {"FORNECEDOR TESTE LTDA"}

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

    def test_ordem_fora_de_pre_ordem_levanta_erro_em_vez_de_numero_errado(self):
        # Mesmas contas do fixture principal, mas com PASSIVO e seus filhos
        # aparecendo ANTES de ESTOQUE (que deveria vir logo após ATIVO/CAIXA,
        # contíguo). Isso quebra a suposição de pré-ordem estrita do algoritmo
        # de reconstrução de hierarquia — sem a checagem de identidade
        # contábil (_validar_identidade_contabil), isso silenciosamente
        # trataria ATIVO e CAIXA GERAL como contas-folha (errado: ATIVO é
        # sintética) e devolveria números incorretos sem avisar.
        texto = "\n".join(
            [
                "Periodo: 01/01/2025 - 31/12/2025",
                _linha("1", "ATIVO", 58000.00, "D", 0.00, 58000.00, 0.00),
                _linha("2", "CAIXA GERAL", 50000.00, "D", 0.00, 50000.00, 0.00),
                _linha("10", "PASSIVO", 16000.00, "C", 16000.00, 0.00, 0.00),
                _linha("11", "FORNECEDORES", 6000.00, "C", 6000.00, 0.00, 0.00),
                _linha("12", "FORNECEDOR TESTE UM LTDA", 4000.00, "C", 4000.00, 0.00, 0.00),
                _linha("13", "FORNECEDOR TESTE DOIS EIRELI", 2000.00, "C", 2000.00, 0.00, 0.00),
                _linha("14", "CAPITAL SOCIAL", 10000.00, "C", 10000.00, 0.00, 0.00),
                _linha("3", "ESTOQUE DE MERCADORIAS", 8000.00, "D", 0.00, 8000.00, 0.00),
                _linha("20", "RESULTADO DO PERIODO", 42000.00, "C", 42000.00, 0.00, 0.00),
                _linha("21", "RECEITA DE PRESTACAO DE SERVICOS", 42000.00, "C", 42000.00, 0.00, 0.00),
            ]
        )
        with pytest.raises(LeitorBalanceteError, match="não fechou"):
            processar_texto_balancete(texto)


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


class TestVocabularioDeCategorias:
    """Cobertura do vocabulário de palavras-chave ampliado (item 3 do plano de
    universalidade) — cada caso é um nome de conta plausível num plano de
    contas brasileiro real que o dicionário antigo (mais enxuto) não cobria.
    """

    @pytest.mark.parametrize(
        "descricao,categoria_esperada",
        [
            ("CONTA DE LUZ CPFL", "energia"),
            ("ENEL DISTRIBUICAO SP", "energia"),
            ("ALUGUEL DA SEDE ADMINISTRATIVA", "aluguel"),
            ("TAXA DE CONDOMINIO", "aluguel"),
            ("13O SALARIO", "folha"),
            ("FERIAS E ABONO PECUNIARIO", "folha"),
            ("PRO LABORE DOS SOCIOS", "folha"),
            ("PEDAGIO E ESTACIONAMENTO", "transporte"),
            ("SEGURO VEICULAR FROTA", "transporte"),
            ("HONORARIOS ADVOCATICIOS", "servicos"),
            ("ASSINATURA DE SOFTWARE DE GESTAO", "servicos"),
            ("ICMS A RECOLHER", "impostos"),
            ("DARF SIMPLES NACIONAL", "impostos"),
            ("IRPJ E CSLL", "impostos"),
            ("MATERIA PRIMA PARA PRODUCAO", "mercadorias"),
            ("CUSTO DA MERCADORIA VENDIDA - CMV", "mercadorias"),
            ("CONTA SEM NENHUMA PALAVRA CONHECIDA", "outros"),
        ],
    )
    def test_categorias_do_vocabulario_ampliado(self, descricao, categoria_esperada):
        assert leitor_balancete._inferir_categoria(descricao) == categoria_esperada

    def test_impostos_e_categoria_reconhecida_end_to_end(self):
        # Natureza D no ramo de despesa/custo, igual num DRE real (contas de
        # imposto sob "IMPOSTOS, TAXAS E CONTRIBUIÇÕES" no resultado, não a
        # obrigação "a recolher" do passivo — essa é natureza C e não entra
        # como lançamento, ver TestConsistenciaDeNatureza).
        texto = "\n".join(
            [
                "Periodo: 01/01/2025 - 31/12/2025",
                # Valores diferentes de propósito (CAIXA != IPTU) — se
                # fossem iguais, o algoritmo de reconciliação (sem
                # classificação neste fixture) poderia coincidentemente
                # "encaixar" DESPESAS COM IMPOSTOS como filha de CAIXA, por
                # pura coincidência de valor, não por hierarquia real.
                _linha("1", "ATIVO", 5000.00, "D", 0.00, 5000.00, 0.00),
                _linha("2", "CAIXA GERAL", 5000.00, "D", 0.00, 5000.00, 0.00),
                _linha("10", "DESPESAS COM IMPOSTOS", 2000.00, "D", 0.00, 2000.00, 0.00),
                _linha("11", "IPTU", 2000.00, "D", 0.00, 2000.00, 0.00),
                # Balanceia o débito total (CAIXA 5000 + IPTU 2000 = 7000).
                _linha("20", "CAPITAL SOCIAL", 7000.00, "C", 7000.00, 0.00, 0.00),
            ]
        )
        df = processar_texto_balancete(texto)
        assert df.iloc[0]["categoria"] == "impostos"
        assert df.iloc[0]["tipo"] == "despesa"


class TestLayoutNatural:
    """O layout "natural" (código, descrição, valores na ordem visual da
    tabela) é o segundo padrão cadastrado em `_LAYOUTS_CONHECIDOS` — ainda
    não validado contra um balancete real (só contra PDF sintético gerado
    localmente), mas testado aqui com fixtures de texto pra garantir que a
    seleção automática por reconciliação continua funcionando quando o
    layout que bate não é o primeiro da lista.
    """

    def test_reconhece_balancete_em_ordem_natural(self):
        texto = "\n".join(
            [
                "Periodo: 01/01/2026 - 30/06/2026",
                _linha_natural("1", "ATIVO", 58000.00, "D", 0.00, 58000.00, 0.00),
                _linha_natural("2", "CAIXA GERAL", 50000.00, "D", 0.00, 50000.00, 0.00),
                _linha_natural("3", "ESTOQUE DE MERCADORIAS", 8000.00, "D", 0.00, 8000.00, 0.00),
                _linha_natural("10", "PASSIVO", 16000.00, "C", 16000.00, 0.00, 0.00),
                _linha_natural("11", "FORNECEDORES", 6000.00, "C", 6000.00, 0.00, 0.00),
                _linha_natural("12", "FORNECEDOR TESTE UM LTDA", 4000.00, "C", 4000.00, 0.00, 0.00),
                _linha_natural("13", "FORNECEDOR TESTE DOIS EIRELI", 2000.00, "C", 2000.00, 0.00, 0.00),
                _linha_natural("14", "CAPITAL SOCIAL", 10000.00, "C", 10000.00, 0.00, 0.00),
                _linha_natural("20", "RESULTADO DO PERIODO", 42000.00, "C", 42000.00, 0.00, 0.00),
                _linha_natural("21", "RECEITA DE PRESTACAO DE SERVICOS", 42000.00, "C", 42000.00, 0.00, 0.00),
            ]
        )
        df = processar_texto_balancete(texto)
        assert set(df["fornecedor"]) == {
            "FORNECEDOR TESTE UM LTDA",
            "FORNECEDOR TESTE DOIS EIRELI",
            "RECEITA DE PRESTACAO DE SERVICOS",
        }
        assert df[df["tipo"] == "despesa"]["valor"].sum() == pytest.approx(6000.00)
        assert df[df["tipo"] == "receita"]["valor"].sum() == pytest.approx(42000.00)

    def test_numero_sem_separador_de_milhar_tambem_reconcilia(self):
        # "58000,00" (sem ponto de milhar) precisa reconciliar igual a
        # "58.000,00" — nem todo sistema agrupa milhares no PDF.
        texto = "\n".join(
            [
                _linha_natural("1", "ATIVO", 1234567.00, "D", 0.00, 1234567.00, 0.00),
            ]
        )
        contas = leitor_balancete._parse_linhas_texto(texto)
        assert len(contas) == 1
        assert contas[0].saldo_atual == pytest.approx(1234567.00)


class TestOCR:
    """OCR (item 6 do plano de universalidade) é o fallback para PDF sem
    camada de texto (documento escaneado/foto). O gatilho ("texto insuficiente
    -> tenta OCR") é testado sem depender de Tesseract instalado; o OCR de
    verdade só roda se o Tesseract estiver disponível no sistema (pulado
    graciosamente em ambientes sem ele, ex.: CI).
    """

    def test_texto_vazio_e_insuficiente(self):
        assert leitor_balancete._texto_insuficiente("") is True
        assert leitor_balancete._texto_insuficiente("   \n\n  ") is True

    def test_texto_curto_e_insuficiente(self):
        assert leitor_balancete._texto_insuficiente("ok") is True

    def test_texto_normal_de_balancete_nao_e_insuficiente(self):
        assert leitor_balancete._texto_insuficiente(_TEXTO_BALANCETE) is False

    def test_pdf_sem_texto_aciona_ocr_automaticamente(self, monkeypatch, tmp_path):
        # Não depende de Tesseract de verdade: só confirma que
        # `_extrair_texto_pdf` cai no fallback de OCR quando o pypdf não
        # extrai texto suficiente, e usa o que o OCR devolver.
        import pypdf
        from PIL import Image

        caminho_pdf = tmp_path / "vazio.pdf"
        Image.new("RGB", (100, 100), "white").save(caminho_pdf, "PDF")
        assert pypdf.PdfReader(str(caminho_pdf)).pages[0].extract_text() == ""

        chamado = {}

        def _ocr_falso(caminho):
            chamado["caminho"] = caminho
            return "texto que veio do OCR"

        monkeypatch.setattr(leitor_balancete, "_extrair_texto_via_ocr", _ocr_falso)

        texto = leitor_balancete._extrair_texto_pdf(caminho_pdf)

        assert texto == "texto que veio do OCR"
        assert chamado["caminho"] == caminho_pdf

    def test_pdf_com_texto_normal_nao_aciona_ocr(self, monkeypatch, tmp_path):
        # Contraprova do teste acima: se o pypdf já extrai texto suficiente,
        # o OCR (bem mais lento) não deve ser chamado.
        def _ocr_que_nao_deveria_rodar(caminho):
            raise AssertionError("OCR não deveria ser chamado quando o PDF já tem texto")

        monkeypatch.setattr(leitor_balancete, "_extrair_texto_via_ocr", _ocr_que_nao_deveria_rodar)

        contas = leitor_balancete._parse_linhas_texto(_TEXTO_BALANCETE)
        assert len(contas) > 0  # confirma que o texto sintético em si é "suficiente"

    def test_erro_claro_quando_ocr_sem_bibliotecas_ou_tesseract(self, monkeypatch):
        # Simula ambiente sem pytesseract/pypdfium2 instalados.
        import builtins

        import_original = builtins.__import__

        def _import_bloqueando_ocr(nome, *args, **kwargs):
            if nome in ("pypdfium2", "pytesseract"):
                raise ImportError(f"{nome} não instalado (simulado)")
            return import_original(nome, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _import_bloqueando_ocr)

        with pytest.raises(LeitorBalanceteError, match="OCR"):
            leitor_balancete._extrair_texto_via_ocr("qualquer_caminho.pdf")

    @pytest.mark.skipif(not _TESSERACT_DISPONIVEL, reason="Tesseract OCR não instalado neste ambiente")
    def test_ocr_de_verdade_extrai_texto_de_pdf_escaneado(self, tmp_path):
        # Integração real: gera uma "página escaneada" (só imagem, via PIL,
        # sem nenhuma biblioteca de PDF extra) com uma frase conhecida, e
        # confirma que o Tesseract de verdade consegue reconhecer o texto.
        # Não valida acurácia perfeita (depende do idioma instalado — ver
        # dados/README.md) nem exige o pacote de português.
        from PIL import Image, ImageDraw, ImageFont

        imagem = Image.new("RGB", (1000, 150), "white")
        desenho = ImageDraw.Draw(imagem)
        try:
            fonte = ImageFont.truetype("arial.ttf", 28)
        except OSError:
            fonte = ImageFont.load_default()
        desenho.text((20, 50), "BALANCETE TESTE OCR", fill="black", font=fonte)

        caminho_pdf = tmp_path / "escaneado.pdf"
        imagem.save(caminho_pdf, "PDF")

        texto = leitor_balancete._extrair_texto_via_ocr(caminho_pdf)

        assert "BALANCETE" in texto.upper()


# Balancete sintético no layout "classificado" (dados fictícios), reproduzindo
# padrões achados em dois balancetes reais de teste (empresas e período
# diferentes do primeiro layout validado): coluna de classificação
# hierárquica, saldo anterior às vezes com natureza própria (inclusive
# mudando de credor pra devedor), conta redutora "(-)" sob ancestral
# "receita", e categoria "DESPESAS COM VENDAS" que contém a palavra "venda"
# mas é despesa. Cada linha reconcilia por si só (não depende da soma dos
# filhos — a hierarquia aqui vem da classificação, não de reconciliação).
_TEXTO_BALANCETE_CLASSIFICADO = "\n".join(
    [
        "Periodo: 01/01/2025 - 31/12/2025",
        _linha_classificada("1", "1", "ATIVO", 1000.00, "D", debito=1000.00),
        _linha_classificada("2", "1.1", "CAIXA", 1000.00, "D", debito=1000.00),
        _linha_classificada("10", "2", "PASSIVO", 400.00, "C", credito=400.00),
        _linha_classificada("11", "2.1", "FORNECEDORES", 400.00, "C", credito=400.00),
        _linha_classificada("12", "2.1.1", "FORNECEDOR TESTE LTDA", 400.00, "C", credito=400.00),
        _linha_classificada("20", "3", "RESULTADO", 900.00, "C", credito=900.00),
        _linha_classificada("21", "3.1", "RECEITA BRUTA", 750.00, "C", credito=750.00),
        _linha_classificada("22", "3.1.1", "VENDA DE PRODUTOS", 750.00, "C", credito=750.00),
        _linha_classificada("23", "3.2", "DESPESAS OPERACIONAIS", 300.00, "D", debito=300.00),
        _linha_classificada("24", "3.2.1", "DESPESAS COM VENDAS", 300.00, "D", debito=300.00),
        _linha_classificada("25", "3.2.1.1", "FRETES E CARRETOS", 300.00, "D", debito=300.00),
        _linha_classificada("26", "3.3", "DEDUCOES DA RECEITA BRUTA", 150.00, "D", debito=150.00),
        _linha_classificada("27", "3.3.1", "IMPOSTOS SOBRE VENDAS E SERVICOS", 150.00, "D", debito=150.00),
        _linha_classificada("28", "3.3.1.1", "(-) ICMS", 150.00, "D", debito=150.00),
        _linha_classificada(
            "9", "9", "SEM MOVIMENTO NO PERIODO", 500.00, "C", anterior=500.00, natureza_anterior="C"
        ),
        _linha_classificada(
            "10", "10", "MUDOU DE NATUREZA", 200.00, "D",
            anterior=300.00, natureza_anterior="C", debito=800.00, credito=300.00,
        ),
    ]
)


class TestLayoutClassificado:
    """Layout "classificado" (item extra do plano de universalidade, achado
    testando contra balancetes reais de duas empresas diferentes): tem
    coluna de classificação hierárquica (ex.: "1.1.3.08.00001") em vez de só
    código sequencial, e o saldo anterior às vezes vem com sua própria
    natureza (D/C), inclusive diferente da natureza do saldo atual.
    """

    def test_reconhece_balancete_e_usa_hierarquia_por_classificacao(self):
        df = processar_texto_balancete(_TEXTO_BALANCETE_CLASSIFICADO)
        # "SEM MOVIMENTO NO PERIODO" e "MUDOU DE NATUREZA" são contas-folha
        # de verdade (testadas à parte, abaixo, quanto à reconciliação), mas
        # não têm nenhuma palavra-chave de receita/despesa/fornecedor — a
        # classificação corretamente as exclui do lançamento, não é bug.
        # "FORNECEDOR TESTE LTDA" também some: como o balancete já tem
        # despesa de Resultado de verdade (FRETES E CARRETOS), o saldo a
        # pagar do fornecedor (só PASSIVO, sem seção de Resultado própria)
        # é descartado pra não contar as duas coisas juntas — ver
        # TestOrigemDaDespesa, abaixo.
        assert set(df["fornecedor"]) == {
            "VENDA DE PRODUTOS",
            "FRETES E CARRETOS",
            "(-) ICMS",
        }

    def test_conta_redutora_com_prefixo_nao_vira_receita(self):
        # "(-) ICMS" está sob "DEDUCOES DA RECEITA BRUTA" (contém "receita"),
        # mas é dedução — precisa virar despesa, não receita.
        df = processar_texto_balancete(_TEXTO_BALANCETE_CLASSIFICADO)
        linha = df[df["fornecedor"] == "(-) ICMS"].iloc[0]
        assert linha["tipo"] == "despesa"

    def test_despesas_com_vendas_nao_vira_receita_apesar_da_palavra_venda(self):
        # "FRETES E CARRETOS" está sob "DESPESAS COM VENDAS" (contém
        # "venda"), mas é despesa — o ancestral "despesas" precisa vencer.
        df = processar_texto_balancete(_TEXTO_BALANCETE_CLASSIFICADO)
        linha = df[df["fornecedor"] == "FRETES E CARRETOS"].iloc[0]
        assert linha["tipo"] == "despesa"

    def test_venda_de_produtos_continua_virando_receita(self):
        df = processar_texto_balancete(_TEXTO_BALANCETE_CLASSIFICADO)
        linha = df[df["fornecedor"] == "VENDA DE PRODUTOS"].iloc[0]
        assert linha["tipo"] == "receita"

    def test_saldo_anterior_credor_sem_movimento_reconcilia(self):
        # Sem o sinal correto do saldo anterior, essa conta (credora nos
        # dois períodos, sem nenhuma movimentação) não reconciliaria.
        contas = leitor_balancete._parse_linhas_texto(_TEXTO_BALANCETE_CLASSIFICADO)
        conta = next(c for c in contas if c.codigo == "9")
        assert leitor_balancete._reconcilia(conta)

    def test_saldo_anterior_que_muda_de_natureza_reconcilia(self):
        # Conta credora (C) no período anterior que virou devedora (D) no
        # atual — o sinal do saldo anterior tem que inverter no cálculo.
        contas = leitor_balancete._parse_linhas_texto(_TEXTO_BALANCETE_CLASSIFICADO)
        conta = next(c for c in contas if c.codigo == "10")
        assert leitor_balancete._reconcilia(conta)

    def test_totais_de_receita_e_despesa_dos_lancamentos_classificados(self):
        df = processar_texto_balancete(_TEXTO_BALANCETE_CLASSIFICADO)
        # FRETES E CARRETOS (300) + (-) ICMS (150) — sem FORNECEDOR TESTE
        # LTDA (400), descartado por já haver despesa de Resultado real.
        assert df[df["tipo"] == "despesa"]["valor"].sum() == pytest.approx(450.00)
        assert df[df["tipo"] == "receita"]["valor"].sum() == pytest.approx(750.00)


class TestOrigemDaDespesa:
    """Achado testando contra dois balancetes reais grandes: o saldo a pagar
    de fornecedores (PASSIVO CIRCULANTE) é só o que ainda está em aberto no
    fim do período — não o total gasto no período. Contar isso como despesa
    só faz sentido quando não há NENHUMA seção de Resultado/DRE no
    balancete (o único sinal de despesa disponível, como no primeiro
    balancete testado neste projeto). Quando existe uma seção de Resultado
    de verdade, o saldo a pagar é descartado, senão dobra a despesa
    (chegou a gerar "prejuízo" de centenas de milhões fictício antes dessa
    correção, numa empresa que na verdade teve lucro).
    """

    def test_fornecedor_pagavel_e_usado_quando_nao_ha_resultado_no_balancete(self):
        # Mesma estrutura do primeiro balancete real testado neste projeto:
        # só ATIVO/PASSIVO, sem nenhuma seção de Resultado — o saldo a pagar
        # de fornecedores é o único jeito de estimar despesa.
        texto = "\n".join(
            [
                "Periodo: 01/01/2025 - 31/12/2025",
                _linha("1", "ATIVO", 1000.00, "D", 0.00, 1000.00, 0.00),
                _linha("2", "MERCADORIAS PARA REVENDA", 1000.00, "D", 0.00, 1000.00, 0.00),
                _linha("10", "PASSIVO", 1000.00, "C", 1000.00, 0.00, 0.00),
                _linha("11", "FORNECEDORES", 1000.00, "C", 1000.00, 0.00, 0.00),
                _linha("12", "FORNECEDOR TESTE LTDA", 1000.00, "C", 1000.00, 0.00, 0.00),
            ]
        )
        df = processar_texto_balancete(texto)
        assert set(df["fornecedor"]) == {"FORNECEDOR TESTE LTDA"}
        assert df.iloc[0]["tipo"] == "despesa"

    def test_fornecedor_pagavel_e_descartado_quando_ha_despesa_de_resultado(self):
        df = processar_texto_balancete(_TEXTO_BALANCETE_CLASSIFICADO)
        assert "FORNECEDOR TESTE LTDA" not in set(df["fornecedor"])


class TestConsistenciaDeNatureza:
    """Achado testando contra balancetes reais: um DRE tem contas de ajuste
    de estoque (ex.: "(+) ESTOQUE FINAL") que ficam dentro de um ramo de
    custo/despesa mas têm natureza credora — são um abatimento do custo, não
    mais uma despesa somada. Como o contrato de lançamentos só aceita valor
    sempre positivo (sem como subtrair), a conta-folha cuja natureza não bate
    com o esperado do seu ramo (D para despesa, C para receita) é excluída
    em vez de somada com o sinal errado — o que já causou um "prejuízo" de
    centenas de milhões de reais fictício antes dessa correção.
    """

    def test_despesa_com_natureza_credora_e_excluida_nao_somada_errado(self):
        # "(+) ESTOQUE FINAL" com natureza C dentro de CUSTOS DOS PRODUTOS
        # VENDIDOS (ramo de despesa/custo) — reduz o custo, não é despesa.
        # Testa `_classificar` direto (não `processar_texto_balancete`,
        # que erraria com "nenhum lançamento" já que essa é a única folha).
        conta = leitor_balancete.ContaBalancete(
            codigo="11",
            descricao="(+) ESTOQUE FINAL",
            saldo_anterior=0.0,
            debito=0.0,
            credito=1000.0,
            saldo_atual=1000.0,
            natureza="C",
        )
        resultado = leitor_balancete._classificar(conta, ["CUSTOS DOS PRODUTOS VENDIDOS"])
        assert resultado is None

    def test_despesa_com_natureza_devedora_continua_normal(self):
        texto = "\n".join(
            [
                "Periodo: 01/01/2025 - 31/12/2025",
                _linha_classificada("1", "1", "ATIVO", 1000.00, "D", debito=1000.00),
                _linha_classificada("2", "1.1", "CUSTOS DOS PRODUTOS VENDIDOS", 1000.00, "D", debito=1000.00),
                _linha_classificada("3", "1.1.1", "MATERIA PRIMA", 1000.00, "D", debito=1000.00),
                _linha_classificada("10", "2", "CAPITAL SOCIAL", 1000.00, "C", credito=1000.00),
            ]
        )
        df = processar_texto_balancete(texto)
        linha = df[df["fornecedor"] == "MATERIA PRIMA"].iloc[0]
        assert linha["tipo"] == "despesa"
        assert linha["valor"] == pytest.approx(1000.00)

    def test_receita_com_natureza_devedora_e_excluida_nao_somada_errado(self):
        # Correção/estorno pontual de serviço já faturado — natureza D
        # dentro de um ramo de receita não deve virar receita positiva.
        conta = leitor_balancete.ContaBalancete(
            codigo="11",
            descricao="SERVICOS PRESTADOS",
            saldo_anterior=0.0,
            debito=1000.0,
            credito=0.0,
            saldo_atual=1000.0,
            natureza="D",
        )
        resultado = leitor_balancete._classificar(conta, ["RECEITA DE SERVICOS"])
        assert resultado is None


class TestRolloverDeEstoque:
    """Achado validando contra dois balancetes reais de uma empresa
    industrial: "(-) ESTOQUE INICIAL"/"(+) ESTOQUE FINAL" dentro de CUSTOS
    DOS PRODUTOS VENDIDOS não são despesas — são as duas pontas de uma
    fórmula de rateio (CPV = estoque inicial + compras − estoque final).
    "(+) ESTOQUE FINAL" (natureza C) já era excluído pela checagem de
    consistência de natureza ([[TestConsistenciaDeNatureza]]), mas
    "(-) ESTOQUE INICIAL" (natureza D, do lado "certo") passava batido e
    entrava como despesa pelo valor cheio — no balancete real, R$ 91,68
    milhões (o estoque TOTAL da empresa) contra um CPV líquido de apenas
    R$ 818 mil, inflando a despesa em quase 100 milhões de reais e virando
    um "prejuízo" fictício de R$ 92 milhões (a empresa teve lucro de
    verdade). Sem suporte a valor com sinal no contrato de lançamentos, a
    opção contável é excluir os dois lados da rolagem em vez de somar um
    deles como se fosse o custo inteiro do período.
    """

    def test_estoque_inicial_e_excluido_mesmo_com_natureza_devedora(self):
        conta = leitor_balancete.ContaBalancete(
            codigo="11",
            descricao="(-) ESTOQUE INICIAL",
            saldo_anterior=0.0,
            debito=91_683_954.01,
            credito=0.0,
            saldo_atual=91_683_954.01,
            natureza="D",
        )
        resultado = leitor_balancete._classificar(conta, ["CUSTOS DOS PRODUTOS VENDIDOS"])
        assert resultado is None

    def test_estoque_final_continua_excluido(self):
        conta = leitor_balancete.ContaBalancete(
            codigo="12",
            descricao="(+) ESTOQUE FINAL",
            saldo_anterior=0.0,
            debito=0.0,
            credito=92_502_112.54,
            saldo_atual=92_502_112.54,
            natureza="C",
        )
        resultado = leitor_balancete._classificar(conta, ["CUSTOS DOS PRODUTOS VENDIDOS"])
        assert resultado is None

    def test_estoque_inicial_final_nao_aparecem_no_dataframe_mas_materia_prima_sim(self):
        # Estrutura sintética espelhando o balancete real: CUSTOS DOS
        # PRODUTOS VENDIDOS com MATÉRIA-PRIMA (despesa de verdade) mais o
        # par de rolagem de estoque (que deve ser descartado, não somado).
        texto = "\n".join(
            [
                "Periodo: 01/01/2025 - 31/12/2025",
                _linha_classificada("1", "1", "ATIVO", 1000.00, "D", debito=1000.00),
                _linha_classificada("2", "1.1", "CUSTOS DOS PRODUTOS VENDIDOS", 1000.00, "D", debito=1000.00),
                _linha_classificada("3", "1.1.1", "MATERIA-PRIMA", 1000.00, "D", debito=1000.00),
                _linha_classificada("4", "1.1.2", "(-) ESTOQUE INICIAL", 3000.00, "D", debito=3000.00),
                _linha_classificada("5", "1.1.3", "(+) ESTOQUE FINAL", 3000.00, "C", credito=3000.00),
                _linha_classificada("10", "2", "CAPITAL SOCIAL", 1000.00, "C", credito=1000.00),
            ]
        )
        df = processar_texto_balancete(texto)
        fornecedores = set(df["fornecedor"])
        assert "MATERIA-PRIMA" in fornecedores
        assert "(-) ESTOQUE INICIAL" not in fornecedores
        assert "(+) ESTOQUE FINAL" not in fornecedores
        linha = df[df["fornecedor"] == "MATERIA-PRIMA"].iloc[0]
        assert linha["valor"] == pytest.approx(1000.00)
