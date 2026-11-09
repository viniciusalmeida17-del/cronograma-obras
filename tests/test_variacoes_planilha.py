"""Cópias modificadas do arquivo de teste: o mapeamento tem de ser feito pelo nome, não pela posição."""
import pytest
from openpyxl.utils import get_column_letter

from conftest import gravar_copia
from leitor_planilha import ErroLeitura, ler_planilha

COLUNAS_ORIGINAIS = list(range(1, 11))  # B..K (0-based: 1..10)


def _permutar(linhas, nova_ordem):
    """nova_ordem: índices (0-based) das colunas originais na ordem em que devem aparecer, a partir de B."""
    resultado = []
    for linha in linhas:
        linha = list(linha) + [None] * (23 - len(linha))
        nova = [linha[0]] + [linha[i] for i in nova_ordem] + linha[11:]
        resultado.append(nova)
    return resultado


def _resumo(r):
    return (
        len(r["servicos"]),
        r["validacao"]["soma_servicos"],
        r["validacao"]["soma_servicos_bdi"],
        r["validacao"]["por_natureza"],
        r["obra"]["prazo_valor"],
        r["obra"]["bdi"],
    )


@pytest.fixture(scope="module")
def original(resultado):
    return resultado


def test_colunas_em_outra_ordem(tmp_path, valores_planilha, original):
    ordem = [10, 5, 1, 3, 9, 7, 2, 8, 6, 4]  # K, F, B, D, J, H, C, I, G, E
    caminho = gravar_copia(tmp_path / "trocada.xlsx", _permutar(valores_planilha, ordem))
    r = ler_planilha(caminho)

    assert r["linha_cabecalho"] == 10
    assert r["colunas_faltando"] == []
    # o campo "item" (coluna original B, índice 1) foi para a posição 3 (letra D)
    assert r["colunas"]["item"] == get_column_letter(1 + ordem.index(1) + 1)
    assert r["colunas"]["descricao"] == get_column_letter(1 + ordem.index(4) + 1)
    assert _resumo(r) == _resumo(original)
    assert r["validacao"]["ok"] is True

    por_item = {s["item"]: s for s in r["servicos"]}
    orig = {s["item"]: s for s in original["servicos"]}
    for item in ("1.1.1", "4.2", "4.10", "9.1.1.1", "22.8"):
        for campo in ("codigo", "descricao", "unidade", "quantidade", "total", "total_bdi", "natureza", "item_grupo"):
            assert por_item[item][campo] == orig[item][campo]


def test_aba_sem_nome_planilha_e_sugerida_pelo_cabecalho(tmp_path, valores_planilha, original):
    caminho = gravar_copia(
        tmp_path / "renomeada.xlsx", valores_planilha, nome_aba="ORÇAMENTO", abas_antes=("CRONOGRAMA", "CPU")
    )
    r = ler_planilha(caminho)
    assert r["aba"] == "ORÇAMENTO"
    assert r["motivo_aba"] == "cabecalho"
    assert any("sugerida" in a["mensagem"] for a in r["alertas"])
    assert _resumo(r) == _resumo(original)


def test_nome_da_aba_sem_acento_e_minusculas(tmp_path, valores_planilha):
    caminho = gravar_copia(tmp_path / "minusculas.xlsx", valores_planilha, nome_aba="Planilha", abas_antes=("CRONOGRAMA",))
    assert ler_planilha(caminho)["aba"] == "Planilha"


def test_usuario_escolhe_outra_aba(tmp_path, valores_planilha):
    caminho = gravar_copia(tmp_path / "abas.xlsx", valores_planilha, abas_antes=("CRONOGRAMA",))
    r = ler_planilha(caminho, aba="CRONOGRAMA")
    assert r["aba"] == "CRONOGRAMA"
    assert r["servicos"] == []
    with pytest.raises(ErroLeitura):
        ler_planilha(caminho, aba="NAO EXISTE")


def test_cabecalho_em_outra_linha_com_variacoes_de_texto(tmp_path, valores_planilha, original):
    linhas = [list(l) for l in valores_planilha]
    cab = linhas[9]
    cab[1:11] = ["Item", "Fonte", "Cód.", "Discriminação", "Unidade", "Qtd", "Valor Unitário",
                 "Valor unitário\n(com BDI)", "Valor Total", "Valor total (com bdi)"]
    linhas = [[None] * 5, [None] * 5, *linhas]  # cabeçalho desce para a linha 12
    r = ler_planilha(gravar_copia(tmp_path / "variacoes.xlsx", linhas))
    assert r["linha_cabecalho"] == 12
    assert r["colunas_faltando"] == []
    assert _resumo(r) == _resumo(original)
    assert r["servicos"][0]["linha_excel"] == original["servicos"][0]["linha_excel"] + 2


def test_coluna_obrigatoria_faltando_e_mapeamento_manual(tmp_path, valores_planilha, original):
    linhas = [list(l) for l in valores_planilha]
    linhas[9][5] = "MEDIDA"  # cabeçalho de unidade (coluna F) com nome não reconhecido
    caminho = gravar_copia(tmp_path / "sem_unidade.xlsx", linhas)

    r = ler_planilha(caminho)
    assert r["colunas_faltando"] == ["unidade"]
    assert r["servicos"] == []
    assert r["linha_cabecalho"] is None
    assert any(a["nivel"] == "erro" and "Unidade" in a["mensagem"] for a in r["alertas"])
    assert {"letra": "F", "texto": "MEDIDA"} in r["cabecalhos"]  # opções para o usuário apontar

    r2 = ler_planilha(caminho, mapeamento={"unidade": "F"}, linha_cabecalho=10)
    assert r2["colunas_faltando"] == []
    assert _resumo(r2) == _resumo(original)


def test_sem_dados_gerais_campos_vazios(tmp_path, valores_planilha):
    linhas = [[None] * 23 for _ in range(9)] + [list(l) for l in valores_planilha[9:]]
    r = ler_planilha(gravar_copia(tmp_path / "sem_dados.xlsx", linhas))
    obra = r["obra"]
    assert obra["nome"] is None and obra["prazo_valor"] is None and obra["bdi"] is None
    assert any(a["nivel"] == "erro" and "Prazo" in a["mensagem"] for a in r["alertas"])
    assert len(r["servicos"]) == 374


def test_total_divergente_gera_alerta(tmp_path, valores_planilha):
    linhas = [list(l) for l in valores_planilha]
    linhas[16][9] = linhas[16][9] + 100  # linha 17 (1.2.1): total +100
    r = ler_planilha(gravar_copia(tmp_path / "divergente.xlsx", linhas))
    v = r["validacao"]
    assert v["ok"] is False
    assert v["total_confere"] is False
    assert v["diferenca_total"] == pytest.approx(100)
    assert v["servicos_divergentes"] == 1
    linhas_alerta = {a["linha"] for a in r["alertas"] if a["nivel"] in ("erro", "aviso")}
    assert 17 in linhas_alerta  # q × preço ≠ total
    assert 13 in linhas_alerta  # grupo 1 não fecha
    assert "NÃO confere" in r["resumo"]


def test_item_numerico_com_formato(tmp_path, valores_planilha):
    """Item gravado como número (4.1 com formato 0.00) é lido como '4.10'."""
    import openpyxl

    caminho = gravar_copia(tmp_path / "item_numero.xlsx", valores_planilha)
    wb = openpyxl.load_workbook(caminho)
    ws = wb["PLANILHA"]
    assert ws["B76"].value == "4.10"
    ws["B76"].value = 4.1
    ws["B76"].number_format = "0.00"
    wb.save(caminho)
    r = ler_planilha(caminho)
    itens = [s["item"] for s in r["servicos"]]
    assert "4.10" in itens and itens.count("4.1") == 1
    assert any(a["linha"] == 76 and "como número" in a["mensagem"] for a in r["alertas"])


def test_arquivo_invalido(tmp_path):
    caminho = tmp_path / "nao_e_excel.xlsx"
    caminho.write_text("isto não é uma planilha")
    with pytest.raises(ErroLeitura):
        ler_planilha(caminho)
