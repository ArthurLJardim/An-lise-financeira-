"""Motor de análise financeira — parte de Arthur Lopes Jardim no projeto Análise Financeira.

Uso básico:

    from motor_analise import AnaliseFinanceira

    engine = AnaliseFinanceira()
    resultado = engine.analisar(lancamentos_df, orcamento_df, historico_df, periodo="2026-06")
    resultado.to_dict()  # pronto para a interface / exportação

Veja docs/CONTRATO_DADOS.md para o formato esperado de entrada e saída.
"""

from .engine import AnaliseFinanceira, ConfiguracaoAnalise
from .modelos import Alerta, ContratoDadosError, ResultadoAnalise, padronizar_categoria
from .relatorio import abrir_no_bloco_de_notas, gerar_relatorio, montar_relatorio_texto, salvar_relatorio_txt

__all__ = [
    "AnaliseFinanceira",
    "ConfiguracaoAnalise",
    "Alerta",
    "ResultadoAnalise",
    "ContratoDadosError",
    "padronizar_categoria",
    "montar_relatorio_texto",
    "salvar_relatorio_txt",
    "abrir_no_bloco_de_notas",
    "gerar_relatorio",
]
