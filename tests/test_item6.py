"""Item 6 — regras do cronograma: biblioteca revista, prazos de espera (prática/norma), trocar função por
atividade, entradas na obra, custo de saída e volta, relatório de continuidade e sugestões."""
from datetime import date

import openpyxl
import pytest

from armazenamento import Banco
from atividades import carregar_biblioteca, obra as etapa3
from atividades.biblioteca import NORMA, PRATICA, ErroBiblioteca, interpretar_trocas
from atividades.grafo import achar_ciclo
from atividades.rede import _grafo, dependencias_de, montar_rede
from conftest import BIBLIOTECA, copiar_biblioteca, linha_da_atividade, preparar_obra
from cronograma import obra as etapa5
from cronograma.agenda import contratados_minimos, agendar_cedo
from cronograma.modelo import Elo
from cronograma.otimizador import menor_prazo
from mao_de_obra import obra as etapa4
from mao_de_obra.calculo import calcular_obra
from test_etapa5_obra import INICIO, resolver_pendencias
from test_etapa51_redes import equipe, inst, rede, resolver
from web.app import criar_app

FLEXIVEIS_ITEM6 = ("ELE-05", "ELE-06", "HID-05", "ESQ-02", "PIN-03", "EST-04", "QUA-04", "URB-02", "ACA-01")
COLUNAS_NOVAS = ("trocar_funcoes", "fonte", "depende_de_norma")
TROCADAS = ("Eletricista", "Ajudante de eletricista", "Bombeiro", "Ajudante de bombeiro", "Pintor")


# ------------------------------------------------------------------ biblioteca nova


def test_biblioteca_tem_as_tres_colunas_do_item6():
    """Item 6: 19 colunas, as três últimas novas (o item 7 acrescentou mais duas depois delas)."""
    ws = openpyxl.load_workbook(BIBLIOTECA, read_only=True)["Atividades"]
    cab = next(ws.iter_rows(min_row=1, max_row=1, values_only=True))
    assert len(cab) >= 19 and tuple(cab[16:19]) == COLUNAS_NOVAS


def test_colunas_lidas_pelo_nome(tmp_path, biblioteca):
    """Mesma biblioteca com as colunas em outra ordem: as atividades saem iguais."""
    def embaralhar(wb):
        ws = wb["Atividades"]
        linhas = [list(r) for r in ws.iter_rows(values_only=True)]
        ordem = list(reversed(range(len(linhas[0]))))
        ws.delete_rows(1, ws.max_row)
        for l in linhas:
            ws.append([l[i] for i in ordem])
    b = carregar_biblioteca(copiar_biblioteca(tmp_path / "embaralhada.xlsx", embaralhar))
    for cod, a in biblioteca.atividades.items():
        x = b.atividades[cod]
        assert (x.depende_de, x.depende_de_norma, x.trocar_funcoes, x.fonte, x.tipo, x.duracao_fixa_dias) == \
            (a.depende_de, a.depende_de_norma, a.trocar_funcoes, a.fonte, a.tipo, a.duracao_fixa_dias)


def test_biblioteca_antiga_sem_as_colunas_novas_carrega(tmp_path, biblioteca, servicos_ligados):
    def tirar(wb):
        wb["Atividades"].delete_cols(17, 3)
    b = carregar_biblioteca(copiar_biblioteca(tmp_path / "antiga.xlsx", tirar))
    assert all(not a.trocar_funcoes and a.fonte is None and a.depende_de_norma is None for a in b.atividades.values())
    # sem depende_de_norma, "norma" é igual a "prática"
    r1, r2 = montar_rede(b, servicos_ligados), montar_rede(b, servicos_ligados, prazos=NORMA)
    assert r1["dependencias"] == r2["dependencias"]


def test_rede_sem_ciclo_nas_duas_opcoes(biblioteca, servicos_ligados):
    for prazos in (PRATICA, NORMA):
        r = montar_rede(biblioteca, servicos_ligados, prazos=prazos)
        assert achar_ciclo(_grafo(r)) is None


def test_ciclo_so_na_norma_e_erro_da_biblioteca(tmp_path):
    def ciclo(wb):
        ws = wb["Atividades"]
        ws.cell(linha_da_atividade(ws, "PRE-01"), 19).value = "LIM-01"
    with pytest.raises(ErroBiblioteca, match="prazos de norma"):
        carregar_biblioteca(copiar_biblioteca(tmp_path / "ciclo.xlsx", ciclo))


def test_nove_atividades_viraram_flexiveis(biblioteca):
    assert all(biblioteca.atividades[c].tipo == "flexivel" for c in FLEXIVEIS_ITEM6)


def test_esperas_que_valem_nas_duas_opcoes(biblioteca):
    from atividades.biblioteca import Dependencia
    assert biblioteca.atividades["EST-03"].duracao_fixa_dias == 21
    assert biblioteca.atividades["FUN-05"].depende_de == [Dependencia("FUN-04", 3, "II", "d")]
    norma = [c for c, a in biblioteca.atividades.items() if a.depende_de_norma is not None]
    assert sorted(norma) == sorted(["REV-01", "REV-02", "REV-03", "PIS-02", "PIN-01", "PIN-04"])


# ------------------------------------------------------------------ prazos de espera na planilha de teste


@pytest.fixture
def obra_rede(tmp_path, arquivo_teste, biblioteca):
    banco = Banco(str(tmp_path / "rede.sqlite3"))
    return banco, preparar_obra(banco, arquivo_teste, biblioteca)


def _deps(banco, obra):
    return {(d["atividade"], d["depende_de"], d["espera_dias"], d["tipo"], d["unidade"])
            for d in banco.carregar_rede(obra)["dependencias"]}


def _depende(banco, obra, cod):
    return {d["depende_de"]: d for d in banco.carregar_rede(obra)["dependencias"] if d["atividade"] == cod}


def test_pratica_e_o_padrao(obra_rede):
    banco, obra = obra_rede
    est = etapa3.estado_rede(banco, obra)
    assert est["prazos_espera"] == PRATICA and est["atividades_norma"] == []
    assert "COB-02" not in _depende(banco, obra, "REV-02")
    assert banco.carregar_rede(obra)["atividades"]["EST-03"]["duracao_fixa_dias"] == 21


def test_norma_usa_depende_de_norma_e_volta_a_pratica(obra_rede, biblioteca):
    banco, obra = obra_rede
    antes = _deps(banco, obra)
    est = etapa3.definir_prazos_espera(banco, obra, NORMA, biblioteca)
    assert sorted(est["atividades_norma"]) == sorted(["REV-01", "REV-02", "REV-03", "PIS-02", "PIN-01", "PIN-04"])
    assert "COB-02" in _depende(banco, obra, "REV-02")
    assert _depende(banco, obra, "PIS-02")["PIS-01"]["espera_dias"] == 14
    assert _depende(banco, obra, "PIS-02")["PIS-01"]["unidade"] == "d"
    assert set(_depende(banco, obra, "REV-01")) == {"ELE-02", "HID-02", "ALV-02", "EST-02"}
    assert achar_ciclo(_grafo(banco.carregar_rede(obra))) is None
    assert banco.prazos_espera(obra) == NORMA
    etapa3.definir_prazos_espera(banco, obra, PRATICA, biblioteca)
    assert _deps(banco, obra) == antes


def test_edicao_manual_continua_valendo_ao_trocar_a_opcao(obra_rede, biblioteca):
    banco, obra = obra_rede
    etapa3.editar_atividade_obra(banco, obra, "REV-03", depende_de="REV-02:II+20du")
    for prazos in (NORMA, PRATICA, NORMA):
        est = etapa3.definir_prazos_espera(banco, obra, prazos, biblioteca)
        assert dependencias_de(banco.carregar_rede(obra), "REV-03", incluir_fim=False)[0].espera_dias == 20
        assert "REV-03" not in est["atividades_norma"]


def test_opcao_vale_ao_montar_a_rede_de_novo(obra_rede, biblioteca):
    banco, obra = obra_rede
    etapa3.definir_prazos_espera(banco, obra, NORMA, biblioteca)
    etapa3.montar_rede_obra(banco, obra, biblioteca)
    assert "COB-02" in _depende(banco, obra, "REV-02")


def test_rota_prazos_de_espera(obra_rede, tmp_path):
    banco, obra = obra_rede
    c = criar_app(banco.caminho, str(tmp_path / "up")).test_client()
    r = c.post(f"/api/obras/{obra}/prazos-espera", json={"prazos": "norma"})
    assert r.status_code == 200 and r.get_json()["prazos_espera"] == "norma"
    seq = {a["codigo"]: a for a in r.get_json()["sequencia"]}
    assert seq["REV-02"]["usa_norma"] and seq["REV-02"]["fonte"].startswith("[Prática]")
    assert seq["ELE-05"]["criterio_tipo"] and seq["PRE-01"]["trocar_funcoes"].startswith("Eletricista > Pedreiro")
    assert c.post(f"/api/obras/{obra}/prazos-espera", json={"prazos": "xx"}).status_code == 400


# ------------------------------------------------------------------ trocar funções


def test_leitura_das_trocas():
    funcoes = ["Pintor", "Servente", "Eletricista", "Pedreiro"]
    assert interpretar_trocas(" pintor >servente ;Eletricista > Pedreiro", funcoes) == \
        ([("Pintor", "Servente"), ("Eletricista", "Pedreiro")], [])
    _, erros = interpretar_trocas("Pintr > Servente", funcoes)
    assert erros and "Pintr" in erros[0]


def test_funcao_inexistente_na_biblioteca_da_erro_com_atividade_e_texto(tmp_path):
    def errar(wb):
        ws = wb["Atividades"]
        ws.cell(linha_da_atividade(ws, "PRE-02"), 17).value = "Pintor > Encanador chefe"
    with pytest.raises(ErroBiblioteca) as exc:
        carregar_biblioteca(copiar_biblioteca(tmp_path / "trocas.xlsx", errar))
    texto = str(exc.value)
    assert "PRE-02" in texto and "Pintor > Encanador chefe" in texto and "Encanador chefe" in texto


def _calc(trocas, juntar=None, execucao="propria"):
    servicos = [{"id": 1, "atividade_biblioteca": "X", "quantidade": 1.0, "total": 100.0, "unidade": "M2", "item": "1"}]
    analises = {1: {"origem": "composicao", "pendentes": [], "equipamentos": {}, "indireta": {},
                    "horas": [{"funcao": "Pintor", "horas_un": 10.0, "origem": "composicao"},
                              {"funcao": "Pedreiro", "horas_un": 5.0, "origem": "composicao"}]}}
    atividades = {"X": {"codigo": "X", "tipo": "rigida", "trocar_funcoes": trocas, "equipe_padrao": 2}}
    r = calcular_obra(servicos, analises, atividades, {"X": {"execucao": execucao}}, {"juntar": juntar or {}})
    return r["atividades"][0]


def test_troca_antes_de_juntar():
    """Pintor > Carpinteiro com "juntar Carpinteiro → Pedreiro": as horas vão para o Pedreiro."""
    a = _calc("Pintor > Carpinteiro", {"Carpinteiro": "Pedreiro"})
    assert a["horas_brutas"] == {"Pedreiro": 15.0}
    assert a["trocas_aplicadas"] == [{"origem": "Pintor", "destino": "Carpinteiro", "horas": 10.0}]


def test_principal_trocada_passa_para_o_destino():
    a = _calc("Pintor > Servente")
    assert a["horas_brutas"] == {"Servente": 10.0, "Pedreiro": 5.0}
    assert a["funcao_principal"] == "Servente" and a["calculo"]["equipe"]["Servente"] == 2


def test_troca_ignorada_em_terceirizada():
    a = _calc("Pintor > Servente", execucao="terceirizada")
    assert a["horas_brutas"] == {"Pintor": 10.0, "Pedreiro": 5.0} and a["trocas_aplicadas"] == []


@pytest.fixture(scope="module")
def obra_analisada(tmp_path_factory, arquivo_teste, biblioteca):
    banco = Banco(str(tmp_path_factory.mktemp("item6") / "obra.sqlite3"))
    obra = preparar_obra(banco, arquivo_teste, biblioteca)
    etapa4.analisar_obra(banco, obra, biblioteca)
    resolver_pendencias(banco, obra, biblioteca)
    etapa5.salvar_parametros_cronograma(banco, obra, {"data_inicio": INICIO, "tempo_limite": 10})
    return banco, obra


def _ativ(est, cod):
    return next(a for a in est["atividades"] if a["codigo"] == cod)


def test_pre01_e_pre02_sem_eletricista_bombeiro_e_pintor(obra_analisada, biblioteca):
    banco, obra = obra_analisada
    est = etapa4.estado_mao_de_obra(banco, obra, biblioteca)
    totais = {}
    for cod in ("PRE-01", "PRE-02"):
        a = _ativ(est, cod)
        assert a["execucao"] == "propria"
        assert not set(a["horas_brutas"]) & set(TROCADAS), (cod, a["horas_brutas"])
        assert a["trocas_aplicadas"]
        totais[cod] = sum(a["horas_brutas"].values())
    # sem as trocas (só nesta obra): as mesmas horas, nas funções da composição
    for cod in ("PRE-01", "PRE-02"):
        est = etapa4.definir_trocas(banco, obra, cod, "", biblioteca=biblioteca)
        a = _ativ(est, cod)
        assert set(a["horas_brutas"]) & set(TROCADAS)
        assert sum(a["horas_brutas"].values()) == pytest.approx(totais[cod], abs=0.05)
    for cod in ("PRE-01", "PRE-02"):   # volta ao que veio da biblioteca
        lib = banco.carregar_rede(obra)["atividades"][cod]["trocar_funcoes_biblioteca"]
        etapa4.definir_trocas(banco, obra, cod, lib, biblioteca=biblioteca)


def test_editar_trocas_na_obra_e_na_biblioteca(obra_analisada, biblioteca, tmp_path):
    banco, obra = obra_analisada
    with pytest.raises(etapa4.ErroMaoDeObra, match="não existe"):
        etapa4.definir_trocas(banco, obra, "PRE-03", "Servente > Inexistente", biblioteca=biblioteca)
    caminho = copiar_biblioteca(tmp_path / "bib.xlsx")
    c = criar_app(banco.caminho, str(tmp_path / "up"), str(caminho)).test_client()
    r = c.post(f"/api/obras/{obra}/atividade/PRE-03/trocas", json={"trocar_funcoes": "servente > pedreiro",
                                                                  "salvar_biblioteca": True})
    assert r.status_code == 200, r.get_json()
    a = _ativ(r.get_json(), "PRE-03")
    assert a["trocar_funcoes"] == "Servente > Pedreiro" and "Servente" not in a["horas_brutas"]
    assert r.get_json()["backup_biblioteca"]
    assert carregar_biblioteca(caminho).atividades["PRE-03"].trocar_funcoes == [("Servente", "Pedreiro")]
    etapa4.definir_trocas(banco, obra, "PRE-03", "", biblioteca=biblioteca)


# ------------------------------------------------------------------ entradas na obra


def _cadeia(vales):
    """Eletricista 1 semana, Pedreiro N semanas (vale do eletricista), Eletricista 1 semana, … (tudo rígido)."""
    t = {"E0": equipe(5, (), Eletricista=1)}
    ant = "E0"
    for k, v in enumerate(vales):
        t[f"P{k}"] = equipe(5 * v, [Elo(ant)], Pedreiro=1)
        t[f"E{k + 1}"] = equipe(5, [Elo(f"P{k}")], Eletricista=1)
        ant = f"E{k + 1}"
    return rede(**t)


def _entradas(vales, n, **kw):
    i = inst(_cadeia(vales), limite_rigidas=0, entradas={"Eletricista": n},
             custo_hora={"Pedreiro": 24.43, "Eletricista": 30.0}, custo_troca_horas=8, **kw)
    return i, resolver(i)


def _fora(serie):
    return sum(1 for a, b in zip(serie, serie[1:]) if a > 0 and b == 0 and any(serie[serie.index(b, 1):]))


def test_uma_entrada_nao_sai_no_vale():
    i, r = _entradas([6], 1)
    assert r["contratados"]["Eletricista"] == [1] * 8
    assert contratados_minimos(i, agendar_cedo(i, "padrao"))["Eletricista"] == [1] * 8


def test_ate_2_entradas_sai_no_vale_e_volta():
    i, r = _entradas([6], 2)
    assert r["contratados"]["Eletricista"] == [1, 0, 0, 0, 0, 0, 0, 1]
    assert contratados_minimos(i, agendar_cedo(i, "padrao"))["Eletricista"] == [1, 0, 0, 0, 0, 0, 0, 1]


def test_vale_de_1_semana_com_minimo_2_nao_sai():
    _, r = _entradas([1], 2, min_semanas_reducao=2)
    assert r["contratados"]["Eletricista"] == [1, 1, 1]


def test_tres_vales_com_ate_2_entradas_sai_em_um_so():
    _, r = _entradas([6, 6, 6], 2)
    serie = r["contratados"]["Eletricista"]
    ativas = [w for w, v in enumerate(serie) if v]
    trechos = sum(1 for w in ativas if w == 0 or not serie[w - 1])
    assert trechos == 2 and serie.count(0) == 6


def test_conversao_da_opcao_antiga():
    funcoes = ["Servente", "Pedreiro", "Pintor"]
    assert etapa5.entradas_da_obra({"entradas": None, "transferiveis": ["Servente", "Pintor"]}, funcoes) == \
        {"Servente": 0, "Pedreiro": 1, "Pintor": 0}
    assert etapa5.entradas_da_obra({"entradas": None, "transferiveis": []}, funcoes) == \
        {"Servente": 1, "Pedreiro": 1, "Pintor": 1}
    # obra nova: Servente, Pedreiro, Bombeiro e Ajudante de bombeiro livres, as outras com uma entrada
    assert etapa5.entradas_da_obra({"entradas": None, "transferiveis": None},
                                   funcoes + ["Bombeiro", "Ajudante de bombeiro", "Eletricista"]) == \
        {"Servente": 0, "Pedreiro": 0, "Pintor": 1, "Bombeiro": 0, "Ajudante de bombeiro": 0, "Eletricista": 1}


def test_salvar_entradas_e_opcao_antiga(tmp_path):
    banco = Banco(str(tmp_path / "b.sqlite3"))
    obra = banco.salvar_importacao({"obra": {"nome": "x", "prazo_valor": 12, "prazo_unidade": "meses"}, "grupos": [],
                                    "servicos": []})
    etapa5.salvar_parametros_cronograma(banco, obra, {"transferiveis": ["Pintor"]})
    cal = banco.carregar_calendario(obra)
    assert etapa5.entradas_da_obra(cal, ["Servente", "Pintor"]) == {"Servente": 1, "Pintor": 0}
    etapa5.salvar_parametros_cronograma(banco, obra, {"entradas": {"Eletricista": 2, "Servente": "livre"}})
    cal = banco.carregar_calendario(obra)
    assert etapa5.entradas_da_obra(cal, ["Servente", "Pintor", "Eletricista"]) == \
        {"Servente": 0, "Pintor": 0, "Eletricista": 2}
    with pytest.raises(etapa5.ErroCronograma):
        etapa5.salvar_parametros_cronograma(banco, obra, {"entradas": {"Eletricista": -1}})


def test_custo_de_saida_e_volta():
    assert etapa5.custo_troca_da_obra({}) == ("horas", 0.0, 8.0)
    assert etapa5.custo_troca_da_obra({"custo_troca": 150}) == ("reais", 150.0, 8.0)   # obra antiga com R$
    _, r = _entradas([6], 2)
    assert r["custo_saida_volta"] == pytest.approx(2 * 8 * 30.0)    # 1 pessoa sai e volta: 2 movimentos de 8 h
    assert r["custo_total"] == pytest.approx(r["custo_mao_de_obra"] + r["custo_indiretos"] + r["custo_saida_volta"])
    _, r = _entradas([6], 1)
    assert r["custo_saida_volta"] == 0


# ------------------------------------------------------------------ relatório e sugestões


def _rede_eletricista():
    """Uma atividade curta do Eletricista no começo (rígida, sem ligação com o resto) e outra depois de 6 semanas."""
    t = rede(ELE=equipe(3, (), Eletricista=1), P=equipe(30, (), Pedreiro=1), E2=equipe(5, [Elo("P")], Eletricista=1),
             LIM=equipe(1, [Elo("ELE"), Elo("E2")], Pedreiro=1))
    i = inst(t, limite_rigidas=0, custo_hora={"Pedreiro": 24.43, "Eletricista": 30.0, "Servente": 17.77},
             custo_troca_horas=8, final="LIM")
    return i, resolver(i)


def test_relatorio_quem_puxa_a_entrada():
    _, r = _rede_eletricista()
    linha = next(l for l in r["continuidade"] if l["funcao"] == "Eletricista")
    assert linha["puxa_entrada"]["codigo"] == "ELE" and linha["semana_entrada"] == 1
    assert linha["puxa_entrada"]["semanas_paradas_depois"] == 5 and linha["puxa_entrada"]["seguinte"] == "E2"
    assert linha["segura_saida"]["codigo"] == "E2" and linha["entradas"] == 1
    assert linha["semanas_sem_servico"] == 5 and linha["custo_horas_paradas"] > 0
    assert "por causa da ELE" in linha["texto"] and "5 semana(s) sem serviço até a E2" in linha["texto"]
    assert r["continuidade"][0]["funcao"] == "Eletricista"   # ordenado pelo custo das horas paradas


def test_sugestoes_com_ganho_calculado():
    i, r = _rede_eletricista()
    cand = etapa5.candidatas_melhoria(i, {}, r["continuidade"], ["Pedreiro", "Servente", "Eletricista"], {})
    tipos = {(c["tipo"], c.get("atividade")) for c in cand}
    assert {("flexivel", "ELE"), ("trocar", "ELE"), ("entradas", None)} <= tipos
    sugestoes, testadas = etapa5.testar_melhorias(i, cand, r["custo_total"], r["ociosidade"], 5)
    assert sugestoes and all(s["ganho"] > 0 for s in sugestoes)
    assert [s["ganho"] for s in sugestoes] == sorted((s["ganho"] for s in sugestoes), reverse=True)
    por = {(s["tipo"], s.get("atividade")): s for s in sugestoes}
    assert por[("flexivel", "ELE")]["ganho"] > 0 and por[("flexivel", "ELE")]["ganho_ociosidade"] > 0
    assert por[("trocar", "ELE")]["ganho"] > 0 and "Eletricista > Pedreiro" in por[("trocar", "ELE")]["texto"]
    assert len(testadas) == len(cand)


@pytest.fixture(scope="module")
def cenario12(obra_analisada, biblioteca):
    banco, obra = obra_analisada
    comp = etapa5.calcular_cenarios(banco, obra, [12], biblioteca, 10)
    c = comp["cenarios"][0]
    banco.escolher_cenario(obra, c["id"])
    return banco, obra, c


def test_planilha_de_teste_cabe_em_12_meses_com_os_padroes(cenario12):
    banco, obra, c = cenario12
    assert c["situacao"] in ("otimo", "melhor_encontrado")
    assert date.fromisoformat(c["termino"]) <= date.fromisoformat(c["data_limite"])
    det = etapa5.detalhe_cenario(banco, obra, c["id"])
    assert det["continuidade"] and det["custo_saida_volta"] is not None
    assert det["custo_total"] == pytest.approx(det["custo_mao_de_obra"] + det["custo_indiretos"]
                                               + det["custo_saida_volta"], abs=0.05)
    eletricista = next(l for l in det["continuidade"] if l["funcao"] == "Eletricista")
    assert eletricista["semana_entrada"] > 4    # não entra mais no 1º mês só por causa da PRE-01/PRE-02


def test_norma_pis02_comeca_14_dias_depois_do_contrapiso(obra_analisada, biblioteca):
    banco, obra = obra_analisada
    etapa3.definir_prazos_espera(banco, obra, NORMA, biblioteca)
    try:
        instancia, _ = etapa5.montar_instancia(banco, obra, 12, biblioteca)
        sol = menor_prazo(instancia)["solucao"]
        cal = instancia.calendario
        assert (cal.data(sol["PIS-02"]["inicio"]) - cal.data(sol["PIS-01"]["inicio"])).days >= 14
        assert "COB-02" in {e.anterior for e in instancia.tarefas["REV-02"].deps}
    finally:
        etapa3.definir_prazos_espera(banco, obra, PRATICA, biblioteca)


def _esperar(c, obra):
    import time
    for _ in range(600):
        st = c.get(f"/api/obras/{obra}/cronograma/calculo").get_json()
        if not st["rodando"]:
            return st
        time.sleep(0.2)
    pytest.fail("o cálculo não terminou")


def test_procurar_melhorias_e_aplicar_nesta_obra(cenario12, tmp_path):
    banco, obra, c = cenario12
    app = criar_app(banco.caminho, str(tmp_path / "up"))
    cli = app.test_client()
    r = cli.post(f"/api/obras/{obra}/cronograma/melhorias", json={"cenario": c["id"], "tempo": 2})
    assert r.status_code == 200 and r.get_json()["tipo"] == "melhorias"
    st = _esperar(cli, obra)
    assert st["erro"] is None, st
    det = cli.get(f"/api/obras/{obra}/cenarios/{c['id']}").get_json()
    m = det["melhorias"]
    assert m["testadas"] and all(s["ganho"] > 0 for s in m["sugestoes"])
    # aplicar: tornar flexível uma atividade rígida que puxa a entrada de alguma função, e recalcular
    linha = next(l for l in det["continuidade"] if l["puxa_entrada"] and
                 banco.carregar_rede(obra)["atividades"][l["puxa_entrada"]["codigo"]]["tipo"] == "rigida")
    cod = linha["puxa_entrada"]["codigo"]
    r = cli.post(f"/api/obras/{obra}/cronograma/melhorias/aplicar",
                 json={"acao": {"tipo": "flexivel", "atividade": cod}, "prazo_meses": c["prazo_meses"]})
    assert r.status_code == 200, r.get_json()
    assert _esperar(cli, obra)["erro"] is None
    assert banco.carregar_rede(obra)["atividades"][cod]["tipo"] == "flexivel"
    novo = next(x for x in banco.listar_cenarios(obra) if x["prazo_meses"] == c["prazo_meses"])
    assert novo["id"] != c["id"] and novo["situacao"] in ("otimo", "melhor_encontrado")
    etapa3.editar_atividade_obra(banco, obra, cod, tipo="rigida")
