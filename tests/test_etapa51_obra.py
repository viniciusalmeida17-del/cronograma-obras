"""Etapa 5.1 — funções da empresa, juntar, referência, limite de estimativa, produção por dia, custos reais,
receita, SINAPI e leitor sem colunas sem BDI."""
import io
import math

import openpyxl
import pytest

from armazenamento import Banco
from conftest import ARQUIVO_TESTE, copiar_biblioteca, preparar_obra
from cronograma import obra as etapa5
from leitor_planilha import ler_planilha
from mao_de_obra import obra as etapa4
from mao_de_obra.calculo import aplicar_estimativas
from test_etapa5_obra import INICIO, resolver_pendencias
from web.app import criar_app


@pytest.fixture(scope="module")
def obra51(tmp_path_factory, arquivo_teste, biblioteca):
    banco = Banco(str(tmp_path_factory.mktemp("etapa51") / "obra.sqlite3"))
    obra = preparar_obra(banco, arquivo_teste, biblioteca)
    etapa4.analisar_obra(banco, obra, biblioteca)
    return banco, obra


def _ativ(estado, cod):
    return next(a for a in estado["atividades"] if a["codigo"] == cod)


def _serv(estado, item):
    return next(s for s in estado["servicos"] if s["item"] == item)


# ------------------------------------------------------------------ funções da empresa e juntar


@pytest.mark.parametrize("descricao, funcao", [
    ("AJUDANTE DE ARMADOR COM ENCARGOS COMPLEMENTARES", "Servente"),
    ("AUXILIAR DE ENCANADOR OU BOMBEIRO HIDRÁULICO COM ENCARGOS", "Servente"),
    ("AZULEJISTA OU LADRILHISTA COM ENCARGOS COMPLEMENTARES", "Pedreiro de acabamento"),
    ("ENCANADOR OU BOMBEIRO HIDRÁULICO COM ENCARGOS COMPLEMENTARES", "Bombeiro"),
    ("CALCETEIRO COM ENCARGOS COMPLEMENTARES", "Pedreiro"),
    ("TELHADISTA COM ENCARGOS COMPLEMENTARES", "Carpinteiro"),
    ("OPERADOR DE BETONEIRA ESTACIONÁRIA/MISTURADOR COM ENCARGOS", "Servente"),
    ("JARDINEIRO COM ENCARGOS COMPLEMENTARES", "Servente"),
])
def test_funcoes_da_empresa(tabela_funcoes, descricao, funcao):
    assert tabela_funcoes.identificar(descricao).funcao == funcao


def test_juntar_funcoes_padrao(tabela_funcoes):
    assert tabela_funcoes.juntar_padrao == {"Carpinteiro": "Pedreiro", "Armador": "Pedreiro"}


def test_juntar_na_fun03(obra51, biblioteca):
    banco, obra = obra51
    est = etapa4.estado_mao_de_obra(banco, obra, biblioteca)
    fun03 = _ativ(est, "FUN-03")
    assert "Carpinteiro" not in fun03["horas_brutas"] and "Armador" not in fun03["horas_brutas"]
    ligado = fun03["horas_brutas"]["Pedreiro"]
    # desligando o juntar nesta obra, as funções voltam a aparecer e o total de horas é o mesmo
    etapa4.salvar_parametros(banco, obra, {"juntar": {}})
    sem = _ativ(etapa4.estado_mao_de_obra(banco, obra, biblioteca), "FUN-03")["horas_brutas"]
    assert sem["Carpinteiro"] > 0 and sem["Armador"] > 0
    assert sem["Pedreiro"] + sem["Carpinteiro"] + sem["Armador"] == pytest.approx(ligado, abs=0.05)
    with pytest.raises(etapa4.ErroMaoDeObra):
        etapa4.salvar_parametros(banco, obra, {"juntar": {"Pintor": "Pedreiro"}})  # não está na aba Juntar funções
    etapa4.salvar_parametros(banco, obra, {"juntar": {"Carpinteiro": "Pedreiro", "Armador": "Pedreiro"}})


def test_obra_com_funcoes_antigas_e_reprocessada(obra51, biblioteca):
    import sqlite3

    banco, obra = obra51
    sid = _serv(etapa4.estado_mao_de_obra(banco, obra, biblioteca), "9.1.1.1")["id"]
    con = sqlite3.connect(banco.caminho)
    with con:
        con.execute("INSERT OR REPLACE INTO servico_mao_de_obra VALUES (?, 'Auxiliar de eletricista', 0.029, 'composicao')", (sid,))
    con.close()
    est = etapa4.estado_mao_de_obra(banco, obra, biblioteca)  # a função antiga não existe mais: reprocessa
    assert {h["funcao"] for h in _serv(est, "9.1.1.1")["horas"]} == {"Eletricista", "Servente"}


# ------------------------------------------------------------------ referência e limite de estimativa


def test_referencia_chapisco_na_5_1_14(analise_por_item):
    a = analise_por_item["5.1.14"]
    ref = [e for e in a["expandidos"] if e.get("referencia") and str(e["codigo"]) == "87893"]
    assert ref and ref[0]["coeficiente"] == pytest.approx(5.26)
    assert ref[0]["horas_un"] == pytest.approx((0.1394 + 0.0465) * 5.26, abs=1e-4)
    horas_ref = {}
    for h in a["horas"]:
        if h["origem"] == "referencia":
            horas_ref[h["funcao"]] = horas_ref.get(h["funcao"], 0) + h["horas_un"]
    # chapisco: Pedreiro 0,1394 h/m² × 5,26 m²/m (a laje pré-moldada 101963 também vem da referência)
    assert horas_ref["Pedreiro"] == pytest.approx(0.1394 * 5.26, abs=1e-4)
    assert horas_ref["Servente"] >= 0.0465 * 5.26


def test_limite_da_estimativa_sintetico():
    servicos = [
        {"id": 1, "item": "1", "atividade_biblioteca": "X", "quantidade": 10, "total": 1000.0},
        {"id": 2, "item": "2", "atividade_biblioteca": "X", "quantidade": 10, "total": 100000.0},
    ]
    analises = {
        1: {"origem": "composicao", "horas": [{"funcao": "Pedreiro", "horas_un": 1.0, "origem": "composicao"}],
            "pendentes": [], "equipamentos": {}, "indireta": {}},
        2: {"origem": "estimado", "horas": [], "pendentes": [], "equipamentos": {}, "indireta": {},
            "estimar_servico_inteiro": True},
    }
    atividades = {"X": {"tipo": "rigida", "etapa": "E"}}
    avisos = aplicar_estimativas(servicos, analises, atividades, {"X": "propria"})
    est = analises[2]["estimativa"]
    # sem limite: 100.000 × (10 h ÷ R$ 1.000) = 1.000 h = 100 h/un; limite 3 × 1 h/un = 30 h
    assert est["limitada"] and est["horas_sem_limite"] == pytest.approx(1000) and est["horas"] == pytest.approx(30)
    assert sum(h["horas_un"] for h in analises[2]["horas"]) == pytest.approx(3.0)
    assert any(a.get("limitada") and "revisar" in a["mensagem"] for a in avisos)


def test_limite_da_estimativa_na_planilha(obra51, biblioteca):
    banco, obra = obra51
    est = etapa4.estado_mao_de_obra(banco, obra, biblioteca)
    limitadas = [s for s in est["servicos"] if (s.get("estimativa") or {}).get("limitada")]
    assert limitadas
    for s in limitadas:
        e = s["estimativa"]
        assert e["horas"] < e["horas_sem_limite"]
        assert e["horas"] == pytest.approx(e["limite_h_un"] * s["quantidade"], rel=0.01)


# ------------------------------------------------------------------ concretagem e produção por dia


def test_concretagem_na_obra(obra51, biblioteca):
    banco, obra = obra51
    fun04 = _ativ(etapa4.estado_mao_de_obra(banco, obra, biblioteca), "FUN-04")
    assert fun04["tipo_producao"] == "concretagem" and fun04["volume_m3"] > 0
    assert fun04["dias_concretagem"] == math.ceil(round(fun04["volume_m3"] / 24, 6))
    etapa4.salvar_parametros(banco, obra, {"volume_caminhao": 5, "caminhoes_dia": 1})
    fun04b = _ativ(etapa4.estado_mao_de_obra(banco, obra, biblioteca), "FUN-04")
    assert fun04b["dias_concretagem"] == math.ceil(round(fun04["volume_m3"] / 5, 6))
    assert fun04b["duracao"]["dias"] >= fun04b["dias_concretagem"]
    etapa4.salvar_parametros(banco, obra, {"volume_caminhao": 8, "caminhoes_dia": 3})


def test_producao_por_dia_de_terceirizada(tmp_path, arquivo_teste, biblioteca):
    banco = Banco(str(tmp_path / "p.sqlite3"))
    obra = preparar_obra(banco, arquivo_teste, biblioteca)
    est = etapa4.analisar_obra(banco, obra, biblioteca)
    qtd, un = etapa4.quantidade_principal(banco.carregar_obra(obra)["servicos"], "QUA-03")
    assert un == "M2" and qtd > 0
    etapa4.definir_atividade(banco, obra, "QUA-03", producao_dia=150, biblioteca=biblioteca)
    est = etapa4.estado_mao_de_obra(banco, obra, biblioteca)
    q = _ativ(est, "QUA-03")
    assert q["duracao"] == {"dias": math.ceil(qtd / 150), "unidade": "uteis", "tipo": "manual"}
    assert est["producao"]["QUA-03"]["producao_dia"] == 150
    # vira o padrão da próxima obra
    outra = preparar_obra(banco, arquivo_teste, biblioteca)
    etapa4.analisar_obra(banco, outra, biblioteca)
    est2 = etapa4.estado_mao_de_obra(banco, outra, biblioteca)
    assert est2["producao"]["QUA-03"]["origem"] == "padrao"
    assert _ativ(est2, "QUA-03")["duracao"]["dias"] == math.ceil(qtd / 150)


# ------------------------------------------------------------------ custos reais e receita


def test_custos_reais_e_receita(tmp_path, arquivo_teste, biblioteca):
    banco = Banco(str(tmp_path / "c.sqlite3"))
    obra = preparar_obra(banco, arquivo_teste, biblioteca)
    etapa4.analisar_obra(banco, obra, biblioteca)
    resolver_pendencias(banco, obra, biblioteca)
    etapa5.salvar_parametros_cronograma(banco, obra, {"data_inicio": INICIO})
    p = etapa5.parametros_cronograma(banco, obra, biblioteca)
    assert any("referência da licitação" in a for a in p["avisos"]) and p["indiretos_referencia"]
    assert {t["codigo"] for t in p["terceirizados"]} >= {"TER-01", "MET-01"}
    crit = {c["item"]: c["criterio"] for c in p["criterios"]}
    assert crit["1.5.1"] == "proporcional" and crit["1.1.1"] == "fixo"   # taxa (%) = fixo
    etapa5.salvar_parametros_cronograma(banco, obra, {
        "salarios": {"Pedreiro": 3000}, "encargos": 80,
        "indiretos_reais": [{"descricao": "Engenheiro", "valor_mes": 15000}, {"descricao": "Topografia",
                            "valor_mes": 9000, "de": "TER-01", "ate": "FUN-04"}],
        "terceirizados": {"MET-01": 250000}, "criterios": {"1.5.1": "mensal"},
    })
    p = etapa5.parametros_cronograma(banco, obra, biblioteca)
    ped = p["custos"]["Pedreiro"]
    assert ped["origem"] == "salario" and ped["custo_hora"] == pytest.approx(3000 * 1.8 / (44 * 4.33), abs=0.01)
    assert not p["indiretos_referencia"]
    inst, ctx = etapa5.montar_instancia(banco, obra, 12, biblioteca)
    assert [(i.descricao, i.tipo) for i in inst.indiretos] == [("Engenheiro", "obra"), ("Topografia", "periodo")]
    receita = {r.descricao.split()[0]: r for r in inst.receitas}
    total_bdi = next(s["total_bdi"] for s in banco.carregar_obra(obra)["servicos"] if s["item"] == "1.5.1")
    assert receita["1.5.1"].custo_mes == pytest.approx(total_bdi / 12, abs=0.01)
    assert ctx["custo_terceirizados"] > 250000
    # padrões lembrados para a próxima obra
    assert banco.padrao("salarios") == {"Pedreiro": 3000} and banco.padrao("encargos") == 80
    outra = preparar_obra(banco, arquivo_teste, biblioteca)
    etapa4.analisar_obra(banco, outra, biblioteca)
    p2 = etapa5.parametros_cronograma(banco, outra, biblioteca)
    assert p2["custos"]["Pedreiro"]["origem"] == "salario_padrao"
    assert [i["descricao"] for i in p2["indiretos_reais"]] == ["Engenheiro", "Topografia"]


def test_cenario_com_receita_mensal(tmp_path, arquivo_teste, biblioteca):
    banco = Banco(str(tmp_path / "r.sqlite3"))
    obra = preparar_obra(banco, arquivo_teste, biblioteca)
    etapa4.analisar_obra(banco, obra, biblioteca)
    resolver_pendencias(banco, obra, biblioteca)
    etapa5.salvar_parametros_cronograma(banco, obra, {"data_inicio": INICIO, "criterios": {"1.5.1": "mensal"}})
    res = etapa5.calcular_cenario(banco, obra, 12, biblioteca, 8)
    assert res["situacao"] in ("otimo", "melhor_encontrado") and res["violacoes"] == []
    assert res["receita_variavel"] > 0
    assert res["resultado"] == pytest.approx(res["receita_variavel"] - res["custo_total"], abs=0.05)
    cmp = etapa5.comparacao(banco, obra)
    assert cmp["cenarios"][0]["principal"] and cmp["cenarios"][0]["resultado"] == pytest.approx(res["resultado"], abs=0.05)


def test_data_de_inicio_sem_padrao(obra51, biblioteca):
    banco, obra = obra51
    assert etapa5.parametros_cronograma(banco, obra, biblioteca)["data_inicio"] is None


# ------------------------------------------------------------------ SINAPI


def _sinapi(caminho, cabecalho=("CODIGO DA COMPOSICAO", "TIPO ITEM", "CODIGO ITEM", "DESCRIÇÃO ITEM", "UNIDADE ITEM",
                                "COEFICIENTE")):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Analítico"
    ws.append(["SINAPI - CUSTO DE REFERÊNCIA DE COMPOSIÇÕES ANALÍTICO"])
    ws.append(["MG - 05/2026 - NÃO DESONERADO"])
    ws.append([])
    ws.append(list(cabecalho))
    linhas = [
        (98577, None, None, "TRATAMENTO DE JUNTA SERRADA", "M", None),
        (98577, "COMPOSICAO", 88309, "PEDREIRO COM ENCARGOS COMPLEMENTARES", "H", 0.2),
        (98577, "COMPOSICAO", 88316, "SERVENTE COM ENCARGOS COMPLEMENTARES", "H", 0.1),
        (98577, "INSUMO", 1234, "TARUGO DE POLIETILENO", "M", 1.05),
        (97090, "COMPOSICAO", 92000, "CORTE E DOBRA DE AÇO", "KG", 2.0),
        (97090, "COMPOSICAO", 88309, "PEDREIRO COM ENCARGOS COMPLEMENTARES", "H", 0.01),
        (92000, "COMPOSICAO", 88245, "ARMADOR COM ENCARGOS COMPLEMENTARES", "H", 0.05),
        (92000, "INSUMO", 555, "AÇO CA-50", "KG", 1.1),
        (92000, "COMPOSICAO", 88316, "OPERADOR DE MÁQUINAS", "H", 0.3),
    ]
    for l in linhas:
        ws.append(list(l))
    wb.save(caminho)
    return caminho


def test_importar_sinapi_e_reprocessar(tmp_path, arquivo_teste, biblioteca):
    banco = Banco(str(tmp_path / "s.sqlite3"))
    obra = preparar_obra(banco, arquivo_teste, biblioteca)
    est = etapa4.analisar_obra(banco, obra, biblioteca)
    assert "98577" in {str(p["codigo"]) for p in _serv(est, "15.2.2")["pendentes"]}
    res = etapa4.importar_sinapi(banco, str(_sinapi(tmp_path / "sinapi.xlsx")), biblioteca=biblioteca)
    assert not res["precisa_mapeamento"] and res["linha_cabecalho"] == 4
    assert res["composicoes_com_mao_de_obra"] == 3 and res["obras_reprocessadas"] == [obra]
    coef = {(r["codigo"], r["funcao"]): r["horas_un"] for r in banco.listar_coeficientes() if r["origem"] == "sinapi"}
    assert coef[("98577", "Pedreiro")] == pytest.approx(0.2) and coef[("98577", "Servente")] == pytest.approx(0.1)
    # auxiliar expandida: 2 × 0,05 h de armador; operador de máquina não entra
    assert coef[("97090", "Armador")] == pytest.approx(0.1) and coef[("97090", "Pedreiro")] == pytest.approx(0.01)
    est = etapa4.estado_mao_de_obra(banco, obra, biblioteca)
    s = _serv(est, "15.2.2")
    assert "98577" not in {str(p["codigo"]) for p in s["pendentes"]}
    assert any(h["origem"] == "banco" for h in s["horas"])


def test_sinapi_com_cabecalho_desconhecido_pede_mapeamento(tmp_path, biblioteca):
    banco = Banco(str(tmp_path / "m.sqlite3"))
    arq = str(_sinapi(tmp_path / "x.xlsx", ("CPU", "CLASSE", "ITEM", "TEXTO", "UM", "FATOR")))
    res = etapa4.importar_sinapi(banco, arq)
    assert res["precisa_mapeamento"] and set(res["faltando"]) >= {"codigo_composicao", "coeficiente"}
    mapa = {"codigo_composicao": 0, "tipo_item": 1, "codigo_item": 2, "descricao_item": 3, "unidade_item": 4,
            "coeficiente": 5}
    res = etapa4.importar_sinapi(banco, arq, mapa, linha_cabecalho=4)
    assert not res["precisa_mapeamento"] and res["composicoes_com_mao_de_obra"] == 3


def test_sinapi_pela_web(tmp_path):
    cliente = criar_app(str(tmp_path / "w.sqlite3"), str(tmp_path / "up"), str(copiar_biblioteca(tmp_path / "b.xlsx"))).test_client()
    assert cliente.get("/sinapi").status_code == 200
    with open(_sinapi(tmp_path / "s.xlsx", ("CPU", "CLASSE", "ITEM", "TEXTO", "UM", "FATOR")), "rb") as f:
        r = cliente.post("/api/sinapi", data={"arquivo": (io.BytesIO(f.read()), "sinapi.xlsx")},
                         content_type="multipart/form-data").get_json()
    assert r["precisa_mapeamento"] and r["cabecalho"][:2] == ["CPU", "CLASSE"]
    r2 = cliente.post("/api/sinapi", json={"token": r["token"], "linha_cabecalho": 4, "mapeamento": {
        "codigo_composicao": 0, "tipo_item": 1, "codigo_item": 2, "descricao_item": 3, "unidade_item": 4,
        "coeficiente": 5}}).get_json()
    assert r2["composicoes_com_mao_de_obra"] == 3


# ------------------------------------------------------------------ leitor sem colunas sem BDI


def test_planilha_sem_colunas_sem_bdi(tmp_path):
    wb = openpyxl.load_workbook(ARQUIVO_TESTE, data_only=True)
    ws = wb["PLANILHA"]
    for rng in list(ws.merged_cells.ranges):
        if rng.min_row >= 10:
            ws.unmerge_cells(str(rng))
    for r in range(10, ws.max_row + 1):   # tira VALOR UNITÁRIO e CUSTO TOTAL (sem BDI)
        ws.cell(r, 8).value = None
        ws.cell(r, 10).value = None
    caminho = tmp_path / "sem_bdi.xlsx"
    wb.save(caminho)
    r = ler_planilha(caminho)
    assert "preco_unit" not in r["colunas"] and "total" not in r["colunas"]
    assert [a for a in r["alertas"] if a["nivel"] == "erro"] == []
    assert len(r["servicos"]) == 374
    assert r["validacao"]["soma_servicos_bdi"] == pytest.approx(5669771.17, abs=0.01)
    assert r["validacao"]["ok"]
    avisos = [a["mensagem"] for a in r["alertas"] if "sem preços sem BDI" in a["mensagem"]]
    assert avisos == ["Planilha sem preços sem BDI; valores sem BDI calculados pelo BDI de 25,22%."]
    s = r["servicos"][5]
    assert s["valores_sem_bdi"] == "calculado"
    assert s["total"] == pytest.approx(s["total_bdi"] / 1.2522, abs=0.01)
