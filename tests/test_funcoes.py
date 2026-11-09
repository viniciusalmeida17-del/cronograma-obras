"""Testes unitários das funções de limpeza, cabeçalho, prazo e natureza."""
import pytest

from leitor_planilha.colunas import campo_do_cabecalho, eh_cabecalho
from leitor_planilha.dados_obra import interpretar_bdi, interpretar_prazo
from leitor_planilha.natureza import classificar_natureza
from leitor_planilha.texto import (
    arredondar_qtd,
    normalizar,
    para_numero,
    texto_item,
    unidade_canonica,
    unidade_limpa,
)
from leitor_planilha.validacao import formatar_reais


@pytest.mark.parametrize(
    "texto, campo",
    [
        ("ITEM", "item"),
        ("REF.", "base"), ("REFERÊNCIA", "base"), ("FONTE", "base"), ("BASE", "base"),
        ("CODIGO", "codigo"), ("CÓDIGO", "codigo"), ("CÓD.", "codigo"),
        ("SERVIÇO", "descricao"), ("DESCRIÇÃO", "descricao"), ("DISCRIMINAÇÃO", "descricao"),
        ("UND", "unidade"), ("UNID", "unidade"), ("UNIDADE", "unidade"),
        ("QUANT.", "quantidade"), ("QUANTIDADE", "quantidade"), ("QTD", "quantidade"),
        ("VALOR UNITÁRIO", "preco_unit"),
        ("VALOR UNITÁRIO \n(COM BDI)", "preco_unit_bdi"),
        ("CUSTO TOTAL", "total"), ("VALOR TOTAL", "total"),
        ("CUSTO TOTAL \n(COM BDI)", "total_bdi"),
        ("PLANILHA ORÇAMENTÁRIA", None), ("PRAZO EXECUÇÃO", None), (None, None),
    ],
)
def test_campo_do_cabecalho(texto, campo):
    assert campo_do_cabecalho(texto) == campo


def test_eh_cabecalho_exige_obrigatorios():
    assert eh_cabecalho([None, "ITEM", "SERVIÇO", "UND", "QUANT."])
    assert not eh_cabecalho([None, "ITEM", "SERVIÇO", "UND"])


def test_normalizar():
    assert normalizar("  Valor Unitário \n(com BDI) ") == "VALOR UNITARIO (COM BDI)"


@pytest.mark.parametrize(
    "valor, esperado",
    [("4.10", "4.10"), ("4.1", "4.1"), (" 1.2.1 ", "1.2.1"), ("9.", "9"), (1, "1"), (3.0, "3"), (None, None)],
)
def test_texto_item(valor, esperado):
    assert texto_item(valor) == esperado


def test_texto_item_numero_usa_formato():
    assert texto_item(4.1, "0.00") == "4.10"
    assert texto_item(4.1, "General") == "4.1"


@pytest.mark.parametrize(
    "valor, esperado",
    [(12, 12.0), ("1.234,56", 1234.56), ("25,22%", 0.2522), ("R$ 10,00", 10.0), ("abc", None), ("", None), (True, None)],
)
def test_para_numero(valor, esperado):
    assert para_numero(valor) == (pytest.approx(esperado) if esperado is not None else None)


def test_arredondamento_ruido_excel():
    assert arredondar_qtd(0.6599999999999999) == 0.66


def test_unidades():
    assert unidade_limpa("UN ") == "UN"
    assert unidade_limpa(" m2 ") == "M2"
    assert unidade_canonica("M2XMÊS") == unidade_canonica("M2/MÊS")
    assert unidade_canonica("M²") == "M2"


@pytest.mark.parametrize(
    "unidade, natureza",
    [
        ("M2", "producao"), ("M3", "producao"), ("M", "producao"), ("KG", "producao"),
        ("UN", "producao"), ("CJ", "producao"), ("T", "producao"),
        ("MÊS", "tempo"), ("MES", "tempo"), ("M2/MÊS", "tempo"), ("M2XMÊS", "tempo"),
        ("M3XKM", "transporte"), ("TXKM", "transporte"),
        ("%", "taxa"),
    ],
)
def test_classificar_natureza(unidade, natureza):
    assert classificar_natureza(unidade) == natureza


@pytest.mark.parametrize(
    "texto, valor, unidade",
    [("12 MESES", 12, "meses"), ("180 dias corridos", 180, "dias"), ("1 ANO", 1, "anos"), (12, 12, None), ("—", None, None)],
)
def test_interpretar_prazo(texto, valor, unidade):
    assert interpretar_prazo(texto) == (valor, unidade)


@pytest.mark.parametrize("valor", [0.2522, "25,22%", 25.22])
def test_interpretar_bdi(valor):
    assert interpretar_bdi(valor) == pytest.approx(0.2522)


def test_formatar_reais():
    assert formatar_reais(4527898.72) == "R$ 4.527.898,72"
    assert formatar_reais(-0.5) == "R$ -0,50"
