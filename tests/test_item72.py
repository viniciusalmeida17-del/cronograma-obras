"""Ajuste 7.2 — horas das subcomposições pela referência (código e descrição), estimativa por custo à vista e
concreto de caminhão a partir de 5 m³, sem limite de caminhões por dia."""
import math
import shutil

import openpyxl
import pytest

from armazenamento import Banco
from conftest import preparar_obra
from cronograma import obra as etapa5
from mao_de_obra import obra as etapa4
from mao_de_obra.analise import CONCRETO_CAMINHAO_M3, Analisador
from mao_de_obra.calculo import PARAMETROS_PADRAO
from mao_de_obra.composicoes import Composicao, LinhaComposicao
from mao_de_obra.funcoes import (
    CAMINHO_REFERENCIAS,
    ErroFuncoes,
    carregar_funcoes,
    carregar_referencias,
    carregar_referencias_descricao,
    regra_por_descricao,
)
from test_etapa5_obra import INICIO, resolver_pendencias

VALIDAS = ("otimo", "melhor_encontrado")


@pytest.fixture(scope="module")
def tabela():
    return carregar_funcoes()


@pytest.fixture(scope="module")
def regras(tabela):
    return carregar_referencias_descricao(tabela)


def _linha(codigo, descricao, unidade, coef, total=0.0):
    return LinhaComposicao(codigo=codigo, descricao=descricao, unidade=unidade, coeficiente=coef, preco=None,
                           total=total, linha_excel=1)


def _analisar(tabela, linhas, referencias=None, regras=None, servico=None, **kw):
    comp = Composicao(item="1.1", descricao="X", aba="A", linha_excel=1, formato="A", codigo="X1", linhas=linhas)
    palavras = ["LANÇAMENTO", "ALVENARIA", "LAJE", "TRATAMENTO", "CONCRETO", "EXECUÇÃO"]
    from leitor_planilha.texto import normalizar
    an = Analisador({"1.1": comp}, tabela, [normalizar(p) for p in palavras], {}, referencias=referencias or {},
                    referencias_descricao=regras, **kw)
    return an.analisar_servico({"item": "1.1", "descricao": "SERVIÇO", "unidade": "M2", "quantidade": 1,
                                **(servico or {})})


def _horas(a):
    return {(h["funcao"], h["origem"]): round(h["horas_un"], 4) for h in a["horas"]}


# ------------------------------------------------------------------ arquivo e regras


def test_arquivo_tem_aba_por_descricao_com_17_regras(regras):
    wb = openpyxl.load_workbook(CAMINHO_REFERENCIAS, read_only=True)
    assert "Por descricao" in wb.sheetnames
    assert [r.ordem for r in regras] == list(range(1, 18))
    refs = carregar_referencias(carregar_funcoes())
    for cod in ("98577", "98575", "97090", "97097", "97096", "90280", "87630", "103317", "103321"):
        assert refs.get(cod), cod
    # ajudante de armador → Servente; operador de betoneira → Servente (pela funcoes.xlsx)
    assert refs["97090"] == {"Armador": 0.031, "Servente": 0.011}
    assert refs["90280"] == {"Servente": pytest.approx(1.6076 + 2.5492)}


def test_lancamento_em_radier_usa_a_regra_do_97096(regras):
    r = regra_por_descricao(regras, "TRANSPORTE, LANÇAMENTO E ADENSAMENTO DE\nCONCRETO EM RADIER, PISO OU ELEMENTO", "m3")
    assert r.ordem == 6 and r.equivale_a == "SINAPI 97096" and r.horas == {"Pedreiro": 0.411, "Servente": 0.411}


def test_bloco_de_9_cm_usa_a_regra_de_9_e_nao_a_de_19(regras):
    r = regra_por_descricao(regras, "ALVENARIA DE VEDAÇÃO COM BLOCO DE CONCRETO, ESP. 9CM, PARA REVESTIMENTO", "M2")
    assert r.equivale_a == "SINAPI 103317" and r.horas["Pedreiro"] == 0.73
    r19 = regra_por_descricao(regras, "ALVENARIA ESTRUTURAL COM BLOCO DE CONCRETO, ESP. 19CM, (FBK 4,5MPA)", "M2")
    assert r19.equivale_a == "SINAPI 103321" and r19.horas["Pedreiro"] == 1.13
    # termos em qualquer parte da descrição, sem diferenciar acentos e maiúsculas
    r_bloco = regra_por_descricao(regras, "alvenaria de vedacao de blocos vazados de concreto 19x19x39 cm", "m2")
    assert r_bloco.ordem == 10


def test_unidade_diferente_nao_casa(regras):
    assert regra_por_descricao(regras, "TRANSPORTE, LANÇAMENTO E ADENSAMENTO DE CONCRETO EM RADIER", "M2") is None
    assert regra_por_descricao(regras, "ALVENARIA DE VEDAÇÃO COM BLOCO DE CONCRETO, ESP. 9CM", "M3") is None


def test_laje_trelicada_e_so_material_fica_com_0_h_e_fora_da_estimativa(tabela, regras):
    a = _analisar(tabela, [
        _linha("88309", "PEDREIRO COM ENCARGOS COMPLEMENTARES", "H", 1.0),
        _linha(None, "LAJE TRELIÇADA TR12, ENCHIMENTO EM EPS, SOBRECARGA 250KGF/M2", "M2", 1.0, total=80.0),
    ], regras=regras)
    assert _horas(a) == {("Pedreiro", "composicao"): 1.0}
    assert a["pendentes"] == [] and a["origem"] == "composicao"
    assert a["por_descricao"][0]["regra"]["ordem"] == 17 and a["por_descricao"][0]["regra"]["material"]


def test_subcomposicao_pela_descricao_soma_horas_com_o_coeficiente(tabela, regras):
    a = _analisar(tabela, [
        _linha("88309", "PEDREIRO COM ENCARGOS COMPLEMENTARES", "H", 0.5),
        _linha("ED-48324", "TRANSPORTE, LANÇAMENTO E ADENSAMENTO DE CONCRETO EM RADIER, PISO", "M3", 0.1, total=50.0),
    ], regras=regras)
    assert _horas(a) == {("Pedreiro", "composicao"): 0.5, ("Pedreiro", "referencia_descricao"): 0.0411,
                         ("Servente", "referencia_descricao"): 0.0411}
    assert a["pendentes"] == [] and a["por_descricao"][0]["codigo"] == "ED-48324"


def test_codigo_da_aba_referencias_vem_antes_da_descricao(tabela, regras):
    linha = _linha("98577", "TRATAMENTO DE JUNTA SERRADA, COM TARUGO DE POLIETILENO", "M", 1.0, total=30.0)
    a = _analisar(tabela, [linha], referencias={"98577": {"Pedreiro": 9.0}}, regras=regras)
    assert _horas(a) == {("Pedreiro", "referencia"): 9.0} and a["por_descricao"] == []
    # sem o código na referência, a mesma linha usa a regra 1 (pela descrição)
    b = _analisar(tabela, [linha], referencias={}, regras=regras)
    assert _horas(b) == {("Pedreiro", "referencia_descricao"): 1.1655, ("Servente", "referencia_descricao"): 0.2359}


def test_sem_regra_continua_pendente_para_a_estimativa(tabela, regras):
    a = _analisar(tabela, [
        _linha("88309", "PEDREIRO COM ENCARGOS COMPLEMENTARES", "H", 1.0),
        _linha("ED-48227", "ALVENARIA DE VEDAÇÃO COM TIJOLO MACIÇO REQUEIMADO, ESP. 10CM", "M2", 1.0, total=40.0),
    ], regras=regras)
    assert [p["codigo"] for p in a["pendentes"]] == ["ED-48227"] and a["por_descricao"] == []


def test_servico_sem_composicao_usa_a_regra_pela_descricao(tabela, regras):
    an = Analisador({}, tabela, [], {}, referencias_descricao=regras)
    a = an.analisar_servico({"item": "9.9", "descricao": "CONTRAPISO EM ARGAMASSA TRAÇO 1:4, E=3CM", "unidade": "M2",
                             "quantidade": 10})
    assert a["origem"] == "referencia_descricao" and not a.get("estimar_servico_inteiro")
    assert {h["funcao"]: h["horas_un"] for h in a["horas"]} == {"Pedreiro": 0.245, "Servente": 0.123}


# ------------------------------------------------------------------ validação


def _referencia_com(tmp_path, linhas):
    destino = tmp_path / "ref.xlsx"
    shutil.copy(CAMINHO_REFERENCIAS, destino)
    wb = openpyxl.load_workbook(destino)
    ws = wb["Por descricao"]
    for l in linhas:
        ws.append(l)
    wb.save(destino)
    return destino, ws.max_row


def test_regra_com_mao_de_obra_desconhecida_da_erro_com_a_linha(tmp_path, tabela):
    arq, linha = _referencia_com(tmp_path, [(18, "TERMO NOVO", "M2", "ASTRONAUTA COM ENCARGOS", 1.0, None, None)])
    with pytest.raises(ErroFuncoes) as exc:
        carregar_referencias_descricao(tabela, arq)
    assert exc.value.erros[0]["linha"] == linha and "ASTRONAUTA" in exc.value.erros[0]["mensagem"]
    assert f"linha {linha}" in str(exc.value)


def test_regra_sem_unidade_ou_com_horas_negativas_da_erro(tmp_path, tabela):
    arq, linha = _referencia_com(tmp_path, [(18, "TERMO A", None, "PEDREIRO COM ENCARGOS", 1.0, None, None),
                                           (19, "TERMO B", "M", "PEDREIRO COM ENCARGOS", -1, None, None)])
    with pytest.raises(ErroFuncoes) as exc:
        carregar_referencias_descricao(tabela, arq)
    assert [(e["linha"], "unidade vazia" in e["mensagem"], "horas_por_unidade" in e["mensagem"]) for e in exc.value.erros] == [
        (linha - 1, True, False), (linha, False, True)]


def test_regra_acrescentada_pelo_usuario_vale(tmp_path, tabela):
    arq, _ = _referencia_com(tmp_path, [(18, "TIJOLO MACIÇO&ALVENARIA", "M2", "PEDREIRO COM ENCARGOS", 1.2, "SINAPI X", None),
                                        (18, "TIJOLO MACIÇO&ALVENARIA", "M2", "SERVENTE COM ENCARGOS", 0.6, None, None)])
    regras = carregar_referencias_descricao(tabela, arq)
    r = regra_por_descricao(regras, "ALVENARIA DE VEDAÇÃO COM TIJOLO MACIÇO REQUEIMADO", "m2")
    assert r.ordem == 18 and r.horas == {"Pedreiro": 1.2, "Servente": 0.6} and r.equivale_a == "SINAPI X"


# ------------------------------------------------------------------ concreto de caminhão (padrões novos)


def _concreto(tabela, quantidade, **kw):
    return _analisar(tabela, [
        _linha("88309", "PEDREIRO COM ENCARGOS COMPLEMENTARES", "H", 1.0),
        _linha("94964", "CONCRETO FCK = 20MPA, TRAÇO 1:2,7:3, PREPARO MECÂNICO COM BETONEIRA 400 L", "M3", 1.0),
    ], referencias={"94964": {"Servente": 4.0}},
        servico={"descricao": "PISO DE CONCRETO MOLDADO IN LOCO, FEITO EM OBRA", "unidade": "M3", "quantidade": quantidade},
        **kw)


def test_padroes_do_concreto(tmp_path):
    assert CONCRETO_CAMINHAO_M3 == 5 and PARAMETROS_PADRAO["concreto_caminhao_m3"] == 5
    assert PARAMETROS_PADRAO["caminhoes_dia"] is None and PARAMETROS_PADRAO["volume_caminhao"] == 8
    p = Banco(str(tmp_path / "p.sqlite3")).carregar_parametros(1)
    assert (p["concreto_caminhao_m3"], p["caminhoes_dia"], p["volume_caminhao"]) == (5, None, 8)


def test_feito_em_obra_com_4_m3_e_betoneira_e_com_5_m3_e_caminhao(tabela):
    a4 = _concreto(tabela, 4)
    assert _horas(a4)[("Servente", "referencia")] == 4.0 and not a4.get("concreto_caminhao")
    a5 = _concreto(tabela, 5)
    assert _horas(a5) == {("Pedreiro", "composicao"): 1.0}
    assert a5["concreto_caminhao"]["volume_m3"] == 5 and a5["concreto_caminhao"]["motivo"] == "5,0 m³ ≥ 5 m³"


# ------------------------------------------------------------------ planilha de teste


@pytest.fixture(scope="module")
def obra72(tmp_path_factory, arquivo_teste, biblioteca):
    banco = Banco(str(tmp_path_factory.mktemp("item72") / "obra.sqlite3"))
    obra = preparar_obra(banco, arquivo_teste, biblioteca)
    etapa4.analisar_obra(banco, obra, biblioteca)
    resolver_pendencias(banco, obra, biblioteca)
    etapa5.salvar_parametros_cronograma(banco, obra, {"data_inicio": INICIO})
    return banco, obra


@pytest.fixture(scope="module")
def est72(obra72, biblioteca):
    banco, obra = obra72
    return etapa4.estado_mao_de_obra(banco, obra, biblioteca)


def _servico(est, item):
    return next(s for s in est["servicos"] if s["item"] == item)


def _ativ(est, cod):
    return next(a for a in est["atividades"] if a["codigo"] == cod)


def _origens(s):
    return {h["origem"] for h in s["horas"]}


@pytest.mark.parametrize("item, por_descricao, por_codigo", [
    ("5.1.14", {"ED-48202"}, {"98575", "90280"}),                 # EST-04
    ("20.1.1", {"ED-48191"}, set()),                              # URB-01
    ("15.2.4", {"87745", "87755"}, {"87630"}),                    # PIS-01
    ("6.10", {"40.16.02"}, set()),                                # CON-01
])
def test_servicos_da_planilha_sem_horas_estimadas_por_custo(est72, item, por_descricao, por_codigo):
    s = _servico(est72, item)
    assert s["pendentes"] == [] and s["estimativa"] is None and "estimado" not in _origens(s), item
    assert {str(d["codigo"]) for d in s["por_descricao"]} == por_descricao
    if por_codigo:
        assert "referencia" in _origens(s)


def test_atividades_da_planilha_sem_estimativa(est72):
    for cod in ("QUA-02", "EST-04", "URB-01", "PIS-01", "CON-01"):
        a = _ativ(est72, cod)
        assert a["horas_estimadas"] == 0 and not a["aviso_estimado"], cod
    assert 2700 <= sum(_ativ(est72, "QUA-02")["horas_brutas"].values()) <= 3000
    # a laje treliçada da EST-01 é só material (regra 17): sai da estimativa
    assert _servico(est72, "5.1.10")["estimativa"] is None


def test_lista_para_conferir_tem_o_que_sobrou_ordenado_pelas_horas(est72):
    lista = est72["estimadas_conferir"]
    assert lista and [x["horas"] for x in lista] == sorted((x["horas"] for x in lista), reverse=True)
    hid = {(x["codigo"], x["item"]) for x in lista if x["atividade"] == "HID-01"}
    assert ("ED-48227", "10.1.5.3") in hid and ("ED-50760", "10.1.5.3") in hid   # tijolo maciço e reboco: sem regra
    assert lista[0]["codigo"] == "ED-48227" and lista[0]["custo"] > 0 and lista[0]["unidade"] == "m2"
    assert not {"98577", "97090", "ED-50619", "ED-48324", "ED-48202", "ED-48191"} & {x["codigo"] for x in lista}
    assert all(not x["servico_inteiro"] for x in lista if x["codigo"] == "ED-48227")


def test_resumo_das_horas_estimadas_e_aviso_acima_de_10_por_cento(est72):
    e = est72["estimadas"]
    proprias = [a for a in est72["atividades"] if a["execucao"] == "propria"]
    assert e["horas_proprias"] == pytest.approx(sum(sum(a["horas_brutas"].values()) for a in proprias), abs=0.5)
    assert 0 < e["horas"] < 500 and e["percentual"] == pytest.approx(100 * e["horas"] / e["horas_proprias"], abs=0.1)
    hid = _ativ(est72, "HID-01")
    assert hid["percentual_estimado"] > 10 and "HID-01" in e["atividades_acima"] and hid["aviso_estimado"]
    assert all((a["percentual_estimado"] > 10) == bool(a["aviso_estimado"]) for a in proprias)


def test_caminhoes_por_dia_vazio_e_digitado(tmp_path, arquivo_teste, biblioteca):
    banco = Banco(str(tmp_path / "c.sqlite3"))
    obra = preparar_obra(banco, arquivo_teste, biblioteca)
    est = etapa4.analisar_obra(banco, obra, biblioteca)
    fun = _ativ(est, "FUN-04")
    # vazio = sem limite: a duração da concretagem vem só da mão de obra
    assert est["parametros"]["caminhoes_dia"] is None and fun["dias_concretagem"] is None
    assert fun["calculo"]["limitante"] == "mao_de_obra"
    assert fun["duracao"]["dias"] == math.ceil(round(fun["calculo"]["dias_exatos"], 6))
    # 3 caminhões por dia digitados: volta o limite pelo volume (etapa 5.1)
    etapa4.salvar_parametros(banco, obra, {"caminhoes_dia": 3, "volume_caminhao": 8})
    fun3 = _ativ(etapa4.estado_mao_de_obra(banco, obra, biblioteca), "FUN-04")
    assert fun3["dias_concretagem"] == math.ceil(round(fun["volume_m3"] / 24, 6))
    etapa4.salvar_parametros(banco, obra, {"caminhoes_dia": 1, "volume_caminhao": 5})
    fun1 = _ativ(etapa4.estado_mao_de_obra(banco, obra, biblioteca), "FUN-04")
    assert fun1["calculo"]["limitante"] == "concretagem" and fun1["duracao"]["dias"] == math.ceil(fun["volume_m3"] / 5)
    # apagar o número volta a "sem limite"
    etapa4.salvar_parametros(banco, obra, {"caminhoes_dia": ""})
    assert banco.carregar_parametros(obra)["caminhoes_dia"] is None


def test_volume_por_caminhao_fora_de_5_a_10_e_aceito_com_aviso(tmp_path, arquivo_teste, biblioteca):
    banco = Banco(str(tmp_path / "v.sqlite3"))
    obra = preparar_obra(banco, arquivo_teste, biblioteca)
    assert etapa4.analisar_obra(banco, obra, biblioteca)["avisos_parametros"] == []
    etapa4.salvar_parametros(banco, obra, {"volume_caminhao": 12})
    est = etapa4.estado_mao_de_obra(banco, obra, biblioteca)
    assert est["parametros"]["volume_caminhao"] == 12 and "5 a 10 m³" in est["avisos_parametros"][0]
    etapa4.salvar_parametros(banco, obra, {"volume_caminhao": 10})
    assert etapa4.estado_mao_de_obra(banco, obra, biblioteca)["avisos_parametros"] == []


def test_regras_ficam_gravadas_e_aparecem_depois_de_reabrir(obra72, biblioteca):
    banco, obra = obra72
    analises = banco.carregar_analises(obra)
    s = _servico(etapa4.estado_mao_de_obra(banco, obra, biblioteca), "15.2.2")
    assert analises[s["id"]]["por_descricao"] == s["por_descricao"] and len(s["por_descricao"]) == 2
    assert {h["origem"] for h in s["horas"]} >= {"composicao", "referencia", "referencia_descricao"}


def test_planilha_de_teste_cabe_em_12_meses_com_os_padroes(obra72, biblioteca):
    banco, obra = obra72
    c = etapa5.calcular_cenario(banco, obra, 12, biblioteca, 12)
    assert c["situacao"] in VALIDAS
