"""Etapa 4 — funções, biblioteca nova, leitura das composições e horas por serviço."""
from collections import defaultdict

import pytest

from atividades import ErroBiblioteca, carregar_biblioteca
from conftest import BIBLIOTECA, copia_so_abas, copiar_biblioteca
from leitor_planilha.texto import normalizar
from mao_de_obra.analise import horas_por_funcao
from mao_de_obra.composicoes import _numero, ler_composicoes
from mao_de_obra.funcoes import eh_equipamento, eh_subcomposicao, nome_equipamento, unidade_de_mao_de_obra


def _h(analise):
    """Horas por função (h/un) somando as origens."""
    tot = defaultdict(float)
    for h in analise["horas"]:
        tot[h["funcao"]] += h["horas_un"]
    return dict(tot)


# ------------------------------------------------------------------ arquivos de configuração


def test_tabela_de_funcoes(tabela_funcoes):
    assert len(tabela_funcoes.regras) == 43
    assert tabela_funcoes.identificar("AJUDANTE DE ARMADOR COM ENCARGOS COMPLEMENTARES").funcao == "Servente"
    assert tabela_funcoes.identificar("AUXILIAR DE ELETRICISTA COM ENCARGOS").funcao == "Ajudante de eletricista"
    assert tabela_funcoes.identificar("ELETRICISTA COM ENCARGOS COMPLEMENTARES").funcao == "Eletricista"
    assert tabela_funcoes.identificar("LOCACAO VEICULO POPULAR (ENGENHEIRO E ENCARREGADO)") is None
    assert tabela_funcoes.identificar("TÉCNICO EM SEGURANÇA DO TRABALHO COM ENCARGOS").categoria == "indireta"


def test_biblioteca_com_colunas_novas(biblioteca):
    assert len(biblioteca.atividades) == 80
    est03 = biblioteca.atividades["EST-03"]
    assert est03.duracao_fixa_dias == 28
    assert biblioteca.atividades["MET-01"].execucao_padrao == "terceirizada"
    assert biblioteca.atividades["ELE-04"].execucao_padrao == "perguntar"
    fun03 = biblioteca.atividades["FUN-03"]
    assert (fun03.equipe_padrao, fun03.equipe_max) == (2, 20)  # colunas vazias = padrões


def test_biblioteca_sem_as_colunas_novas_usa_padroes(tmp_path):
    def tirar(wb):
        ws = wb["Atividades"]
        cab = [c.value for c in ws[1]]
        for nome in ("duracao_fixa_dias", "equipe_max", "equipe_padrao", "execucao_padrao"):
            if nome in cab:
                ws.delete_cols(cab.index(nome) + 1)
                cab = [c.value for c in ws[1]]

    b = carregar_biblioteca(copiar_biblioteca(tmp_path / "antiga.xlsx", tirar))
    a = b.atividades["FUN-03"]
    assert (a.execucao_padrao, a.equipe_padrao, a.equipe_max, a.duracao_fixa_dias) == ("propria", 2, 20, None)


def test_biblioteca_valida_colunas_novas(tmp_path):
    def estragar(wb):
        ws = wb["Atividades"]
        cab = [c.value for c in ws[1]]
        ws.cell(16, cab.index("execucao_padrao") + 1).value = "talvez"
        ws.cell(16, cab.index("equipe_padrao") + 1).value = 9
        ws.cell(16, cab.index("equipe_max") + 1).value = 6
        ws.cell(17, cab.index("duracao_fixa_dias") + 1).value = "três"

    with pytest.raises(ErroBiblioteca) as exc:
        carregar_biblioteca(copiar_biblioteca(tmp_path / "ruim.xlsx", estragar))
    msgs = " ".join(e["mensagem"] for e in exc.value.erros)
    assert "execucao_padrao 'talvez'" in msgs and "maior que equipe_max" in msgs and "duracao_fixa_dias" in msgs


# ------------------------------------------------------------------ leitura


@pytest.mark.parametrize("texto, valor", [
    ("1,2434000", 1.2434), ("4.789,18", 4789.18), ("1.6898", 1.6898), ("0.5", 0.5), (0.5, 0.5), (12, 12.0),
])
def test_numeros_em_formatos_misturados(texto, valor):
    assert _numero(texto) == pytest.approx(valor)


def test_374_servicos_com_composicao_formato_a(composicoes_teste, resultado):
    itens = {s["item"] for s in resultado["servicos"]}
    a = {i for i, c in composicoes_teste.composicoes.items() if c.formato == "A"}
    assert itens <= a
    assert len(itens) == 374
    abas = {r["aba"]: r for r in composicoes_teste.resumo_abas()}
    for nome in ("ELÉTRICA", "ALVENARIA", "FUNDAÇÃO", "HIDROSSANITÁRIO", "ESTRUTURA"):
        assert abas[nome]["formato_a"] > 0
    assert abas["ELÉTRICA"]["formato_a"] == 78
    assert abas["CPU"]["formato_b"] == 65
    assert "PLANILHA" not in abas


def test_formato_b_so_quando_falta_o_a(tmp_path, arquivo_teste, tabela_funcoes):
    copia = copia_so_abas(arquivo_teste, tmp_path / "so_cpu.xlsx", ("PLANILHA", "CPU"))
    r = ler_composicoes(copia, "PLANILHA")
    assert len(r.composicoes) == 65
    assert all(c.formato == "B" for c in r.composicoes.values())
    c = r.composicoes["5.1.9"]
    assert c.codigo == "COMP-02"
    mao = {tabela_funcoes.identificar(l.descricao).funcao: l.coeficiente for l in c.linhas
           if tabela_funcoes.identificar(l.descricao)}
    assert mao == {"Carpinteiro": pytest.approx(0.55882), "Servente": pytest.approx(0.34237)}
    adm = r.composicoes["1.5.1"]
    assert {l.secao for l in adm.linhas} == {"mao_de_obra", "equipamento"}


# ------------------------------------------------------------------ mão de obra por serviço


def test_item_7_2(analise_por_item):
    a = analise_por_item["7.2"]
    assert a["origem"] == "composicao"
    h = {x["funcao"]: x["horas_un"] for x in a["horas"] if x["origem"] == "composicao"}
    assert h == {"Pedreiro": pytest.approx(0.99), "Servente": pytest.approx(0.495)}


def test_item_7_2_horas_brutas(analise_por_item, servicos_por_item):
    qtd = servicos_por_item["7.2"]["quantidade"]
    assert qtd == pytest.approx(391.64)
    h = _h({"horas": [x for x in analise_por_item["7.2"]["horas"] if x["origem"] == "composicao"]})
    assert h["Pedreiro"] * qtd == pytest.approx(387.72, abs=0.01)
    assert h["Servente"] * qtd == pytest.approx(193.86, abs=0.01)


def test_item_4_5_ajudante_vira_servente(analise_por_item):
    assert _h(analise_por_item["4.5"]) == {"Armador": pytest.approx(0.151), "Servente": pytest.approx(0.049)}


def test_item_9_1_1_1(analise_por_item):
    # auxiliar de eletricista é a função própria Ajudante de eletricista
    assert _h(analise_por_item["9.1.1.1"]) == {"Eletricista": pytest.approx(0.029), "Ajudante de eletricista": pytest.approx(0.029)}


def test_item_5_1_14_expande_subcomposicoes(analise_por_item):
    a = analise_por_item["5.1.14"]
    h = _h(a)
    comp = _h({"horas": [x for x in a["horas"] if x["origem"] == "composicao"]})
    assert comp["Pedreiro"] == pytest.approx(6.1654, abs=0.001)
    assert comp["Servente"] == pytest.approx(3.4437, abs=0.001)
    assert comp["Armador"] == pytest.approx(0.5027, abs=0.001)
    expandidos = {e["codigo"]: e["item"] for e in a["expandidos"] if not e.get("referencia")}
    assert expandidos == {"92761": "6.8", "92762": "5.1.4", "87529": "14.4", "COMP-07": "6.12"}
    pendentes = {str(p["codigo"]) for p in a["pendentes"]}
    assert "ED-48202" in pendentes and not {"87893", "101963"} & pendentes  # agora vêm da referência


def test_item_1_5_1_equipe_indireta(analise_por_item):
    a = analise_por_item["1.5.1"]
    assert a["indireta"] == {"Engenheiro": pytest.approx(0.2), "Encarregado": 1, "Técnico de segurança": 1, "Vigia": 1}
    assert a["horas"] == []  # indireta não entra nas horas de produção


def test_linhas_com_encargos_tem_funcao(composicoes_teste, tabela_funcoes):
    sem = [l.descricao for c in composicoes_teste.composicoes.values() for l in c.linhas
           if "COM ENCARGOS" in normalizar(l.descricao) and tabela_funcoes.identificar(l.descricao) is None]
    assert sem == []


def test_equipamento_soma_chp_e_chi(composicoes_teste, analise_por_item):
    """No 2.2.1 a escavadeira aparece em duas linhas (CHP e CHI): vira um equipamento só, com a soma."""
    linhas = [l for l in composicoes_teste.composicoes["2.2.1"].linhas if "ESCAVADEIRA" in (l.descricao or "")]
    assert {str(l.unidade) for l in linhas} == {"CHP", "CHI"}
    equip = analise_por_item["2.2.1"]["equipamentos"]
    escavadeira = [n for n in equip if n.startswith("ESCAVADEIRA")]
    assert len(escavadeira) == 1 and "CH" not in escavadeira[0].split()[-1]
    assert equip[escavadeira[0]] == pytest.approx(sum(l.coeficiente for l in linhas))


def test_classificacao_de_linhas():
    assert eh_equipamento("RETROESCAVADEIRA - CHP DIURNO", "CHP")
    assert eh_equipamento("CHP/TRATOR DE ESTEIRAS", "H")
    assert not eh_equipamento("PEDREIRO COM ENCARGOS", "H")
    assert nome_equipamento("CAMINHÃO BASCULANTE 10 M3 - CHP DIURNO. AF_06/2014") == \
        nome_equipamento("CAMINHÃO BASCULANTE 10 M3 - CHI DIURNO. AF_06/2014") == "CAMINHÃO BASCULANTE 10 M3"
    assert nome_equipamento("CHP/TRATOR DE ESTEIRAS, 177HP") == "TRATOR DE ESTEIRAS, 177HP"
    for u in ("H", "HORA", "MÊS", None, "", "0.5", 1):
        assert unidade_de_mao_de_obra(u), u
    for u in ("M2", "UN", "KG", "CHP"):
        assert not unidade_de_mao_de_obra(u), u


@pytest.mark.parametrize("descricao, esperado", [
    ("CHAPISCO APLICADO EM ALVENARIA", True),
    ("ALVENARIA ESTRUTURAL COM BLOCO DE CONCRETO", True),
    ("LANÇAMENTO DE CONCRETO BOMBEADO EM FUNDAÇÕES", True),
    ("BLOCO CERAMICO VAZADO PARA ALVENARIA DE VEDACAO", False),       # finalidade do material
    ("TABUA NAO APARELHADA EM MACARANDUBA/MASSARANDUBA", False),       # palavra inteira
    ("MESA (APLICAÇÃO: ESCRITÓRIO|COR: CINZA)", False),                # atributo de material
    ("CIMENTO PORTLAND CP II-32", False),
])
def test_subcomposicao_pela_descricao(descricao, esperado):
    from mao_de_obra.funcoes import carregar_palavras_subcomposicao

    assert eh_subcomposicao(descricao, carregar_palavras_subcomposicao()) is esperado


def test_4_11_sem_mao_de_obra_direta_fica_para_estimar(analise_por_item):
    a = analise_por_item["4.11"]
    assert a["origem"] == "estimado" and a["horas"] == []
    assert [p["codigo"] for p in a["pendentes"]] == ["40.16.02"]


def test_origens_dos_374(analise_por_item):
    assert len(analise_por_item) == 374
    assert {a["origem"] for a in analise_por_item.values()} <= {"composicao", "estimado", "sem_mao_de_obra"}
    assert sum(1 for a in analise_por_item.values() if a["origem"] == "composicao") > 300
    assert horas_por_funcao({}) == {}
    assert BIBLIOTECA.exists()
