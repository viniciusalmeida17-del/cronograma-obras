"""Etapa 5 — planilha de teste: cenários, comparação, períodos das indiretas, banco e tela."""
import io
import time
from datetime import date

import openpyxl
import pytest

from armazenamento import Banco
from conftest import copiar_biblioteca, preparar_obra
from cronograma import obra as etapa5
from cronograma.agenda import verificar
from mao_de_obra import obra as etapa4
from web.app import criar_app

INICIO = "2025-03-03"
TEMPO = 12  # segundos por cenário nos testes


def resolver_pendencias(banco, obra, biblioteca):
    """Responde as pendências da etapa 4 como um usuário faria e põe 4 caminhões na terraplenagem."""
    est = etapa4.estado_mao_de_obra(banco, obra, biblioteca)
    perguntar = [p["atividade"] for p in est["pendencias"] if p["tipo"] == "execucao"]
    if perguntar:
        etapa4.definir_execucao(banco, obra, perguntar, "propria", biblioteca)
    est = etapa4.estado_mao_de_obra(banco, obra, biblioteca)
    for p in est["pendencias"]:
        etapa4.definir_atividade(banco, obra, p["atividade"], duracao_manual=10, biblioteca=biblioteca)
    ter = next(a for a in est["atividades"] if a["codigo"] == "TER-01")
    caminhao = max(ter["horas_equipamento"], key=ter["horas_equipamento"].get)
    # com 1 caminhão a TER-01 leva 156 dias úteis e a obra não cabe em 12 meses
    etapa4.definir_atividade(banco, obra, "TER-01", maquinas={caminhao: 4}, biblioteca=biblioteca)


@pytest.fixture(scope="module")
def obra_pronta(tmp_path_factory, arquivo_teste, biblioteca):
    banco = Banco(str(tmp_path_factory.mktemp("etapa5") / "obra.sqlite3"))
    obra = preparar_obra(banco, arquivo_teste, biblioteca)
    etapa4.analisar_obra(banco, obra, biblioteca)
    resolver_pendencias(banco, obra, biblioteca)
    etapa5.salvar_parametros_cronograma(banco, obra, {"data_inicio": INICIO})
    return banco, obra


@pytest.fixture(scope="module")
def comparacao(obra_pronta, biblioteca):
    banco, obra = obra_pronta
    return etapa5.calcular_cenarios(banco, obra, [10, 12], biblioteca, TEMPO)


def _cenario(comparacao, prazo):
    return next(c for c in comparacao["cenarios"] if c["prazo_meses"] == prazo)


# ------------------------------------------------------------------ custos e parâmetros


def test_custo_por_hora_das_composicoes(obra_pronta):
    banco, obra = obra_pronta
    c = etapa5.custos_das_composicoes(banco, obra)
    assert c["Pedreiro"]["custo_hora"] == pytest.approx(24.43)
    # Servente: 17,77 (servente com encargos) misturado com ajudantes que a tabela de funções chama de Servente
    assert 17.77 <= c["Servente"]["custo_hora"] <= 19.67
    assert c["Pedreiro"]["base"] == "com encargos"


def test_parametros_padrao(obra_pronta, biblioteca):
    banco, obra = obra_pronta
    p = etapa5.parametros_cronograma(banco, obra, biblioteca)
    assert p["data_inicio"] == INICIO and p["limite_rigidas"] == 5 and p["tempo_limite"] == 60
    assert p["prazos"] == [9.0, 10.0, 11.0, 12.0]          # prazo − 3, − 2, − 1 e o próprio
    assert p["custos"]["Pedreiro"]["origem"] == "composicoes"
    assert "Pedreiro" in p["funcoes"] and p["pendencias_etapa4"] == []


def test_validacao_dos_parametros(obra_pronta):
    banco, obra = obra_pronta
    for ruim in ({"data_inicio": "03/03/2025"}, {"limite_rigidas": -1}, {"tempo_limite": 1},
                 {"custos_hora": {"Pedreiro": "abc"}}, {"custos_hora": {"Pedreiro": 0}}, {"prazos": [0]},
                 {"feriados_locais": [{"data": "31/02"}]}):
        with pytest.raises(etapa5.ErroCronograma):
            etapa5.salvar_parametros_cronograma(banco, obra, ruim)


def test_sem_data_de_inicio_nao_calcula(tmp_path, arquivo_teste, biblioteca):
    banco = Banco(str(tmp_path / "x.sqlite3"))
    obra = preparar_obra(banco, arquivo_teste, biblioteca)
    etapa4.analisar_obra(banco, obra, biblioteca)
    with pytest.raises(etapa5.ErroCronograma, match="pendências da etapa 4"):
        etapa5.montar_instancia(banco, obra, 12, biblioteca)
    resolver_pendencias(banco, obra, biblioteca)
    with pytest.raises(etapa5.ErroCronograma, match="data de início"):
        etapa5.montar_instancia(banco, obra, 12, biblioteca)


def test_custo_salvo_vira_padrao_da_proxima_obra(tmp_path, arquivo_teste, biblioteca):
    banco = Banco(str(tmp_path / "x.sqlite3"))
    a = preparar_obra(banco, arquivo_teste, biblioteca)
    etapa4.analisar_obra(banco, a, biblioteca)
    etapa5.salvar_parametros_cronograma(banco, a, {"custos_hora": {"Pedreiro": "30,50"}})
    assert etapa5.parametros_cronograma(banco, a, biblioteca)["custos"]["Pedreiro"] == {
        "custo_hora": 30.5, "origem": "obra", "composicoes": 24.43}
    b = preparar_obra(banco, arquivo_teste, biblioteca)
    etapa4.analisar_obra(banco, b, biblioteca)
    pb = etapa5.parametros_cronograma(banco, b, biblioteca)["custos"]
    assert pb["Pedreiro"]["custo_hora"] == 30.5 and pb["Pedreiro"]["origem"] == "ultimo_usado"
    assert pb["Servente"]["origem"] == "composicoes"


def test_indiretos_que_variam_com_o_prazo(obra_pronta, biblioteca):
    banco, obra = obra_pronta
    inst, _ = etapa5.montar_instancia(banco, obra, 12, biblioteca)
    itens = {i.descricao.split()[0]: i for i in inst.indiretos}
    assert itens["1.5.1"].tipo == "obra" and itens["1.5.1"].custo_mes == pytest.approx(361091.88 / 12)
    assert itens["1.5.2"].tipo == "periodo" and itens["1.5.2"].custo_mes == pytest.approx(52428.78 / 3)
    assert (itens["1.5.2"].de, itens["1.5.2"].ate) == ("TER-01", "FUN-04")
    assert itens["1.1.1"].tipo == "fixo"                                       # taxa de mobilização (%)
    assert itens["1.4.1"].tipo == "fixo" and "não varia" in itens["1.4.1"].motivo  # andaime M2/MÊS
    assert itens["5.1.11"].tipo == "fixo"                                      # escoramento M2XMÊS


# ------------------------------------------------------------------ cenários


def test_tabela_tem_uma_linha_por_prazo(comparacao):
    assert [c["prazo_meses"] for c in comparacao["cenarios"]] == [10.0, 12.0]
    dez = _cenario(comparacao, 10.0)
    assert dez["situacao"] == "impossivel"
    assert dez["menor_prazo"]["dias_uteis"] > 0 and dez["menor_prazo"]["caminho_critico"][-1] == "LIM-01"
    assert "TER-01" in dez["menor_prazo"]["caminho_critico"]
    doze = _cenario(comparacao, 12.0)
    assert doze["situacao"] in ("otimo", "melhor_encontrado")
    assert doze["mais_barato"] and doze["diferenca"] == 0
    assert doze["custo_total"] == pytest.approx(doze["custo_mao_de_obra"] + doze["custo_indiretos"], abs=0.05)


def _reconstruir(banco, obra, biblioteca, cenario):
    """Lê o cenário gravado e remonta a solução para conferir as restrições por código."""
    inst, _ = etapa5.montar_instancia(banco, obra, cenario["prazo_meses"], biblioteca)
    cal = inst.calendario
    sol = {}
    for a in cenario["atividades"]:
        t = inst.tarefas[a["codigo"]]
        ini = cal.uteis.index(date.fromisoformat(a["inicio"]))
        modo = next(k for k, m in enumerate(t.modos) if m.equipe == a["equipe"] or (not a["equipe"] and not m.equipe)
                    or m.corridos)
        sol[a["codigo"]] = {"inicio": ini, "modo": modo, "duracao": inst.duracao(a["codigo"], modo, ini),
                            "fim": inst.termino(a["codigo"], modo, ini)}
        assert cal.data_do_offset(sol[a["codigo"]]["fim"]).isoformat() == a["termino"]
    contratados = {f["funcao"]: f["contratados"] for f in cenario["funcoes"]}
    return inst, sol, contratados


def test_cenario_de_12_meses_respeita_todas_as_restricoes(obra_pronta, biblioteca, comparacao):
    banco, obra = obra_pronta
    doze = _cenario(comparacao, 12.0)
    c = etapa5.detalhe_cenario(banco, obra, doze["id"])
    assert c["termino"] <= c["data_limite"] == "2026-03-02"
    assert len(c["atividades"]) == 74
    inst, sol, contratados = _reconstruir(banco, obra, biblioteca, c)
    assert verificar(inst, sol, contratados) == []
    # sobe e desce, conferido aqui também
    for f in c["funcoes"]:
        serie = f["contratados"]
        pico = serie.index(max(serie))
        assert all(a <= b for a, b in zip(serie[:pico], serie[1:pico + 1])), f["funcao"]
        assert all(a >= b for a, b in zip(serie[pico:], serie[pico + 1:])), f["funcao"]
    # terceirizadas sem equipe própria
    for a in c["atividades"]:
        if a["execucao"] == "terceirizada":
            assert a["equipe"] == {}
    assert c["pico"] == max(c["total_semana"])
    assert 0 < c["ociosidade"] < 100
    assert c["caminho_critico"][0] == "PRE-01" and c["caminho_critico"][-1] == "LIM-01"


def test_periodos_das_indiretas(obra_pronta, comparacao):
    banco, obra = obra_pronta
    c = etapa5.detalhe_cenario(banco, obra, _cenario(comparacao, 12.0)["id"])
    ativ = {a["codigo"]: a for a in c["atividades"]}
    per = {p["codigo"]: p for p in c["periodos_indiretas"]}
    assert per["IND-03"]["inicio"] == ativ["TER-01"]["inicio"] and per["IND-03"]["termino"] == ativ["FUN-04"]["termino"]
    assert per["IND-01"]["inicio"] == INICIO and per["IND-01"]["termino"] == c["termino"]
    assert per["IND-05"]["inicio"] == ativ["REV-01"]["inicio"]
    topo = next(i for i in c["indiretos"] if i["descricao"].startswith("1.5.2"))
    assert topo["inicio"] == ativ["TER-01"]["inicio"]
    assert topo["custo"] == pytest.approx(52428.78 / 3 * topo["meses"], rel=0.01)
    assert {e["funcao"] for e in c["equipe_indireta"]} >= {"Engenheiro", "Encarregado"}


def test_escolher_cenario_e_exportar(obra_pronta, comparacao):
    banco, obra = obra_pronta
    dez, doze = _cenario(comparacao, 10.0), _cenario(comparacao, 12.0)
    with pytest.raises(etapa5.ErroCronograma):
        etapa5.escolher_cenario(banco, obra, dez["id"])
    etapa5.escolher_cenario(banco, obra, doze["id"])
    assert etapa5.detalhe_cenario(banco, obra)["id"] == doze["id"]
    assert [c["escolhido"] for c in etapa5.comparacao(banco, obra)["cenarios"]] == [False, True]
    wb = openpyxl.load_workbook(io.BytesIO(etapa5.exportar_equipe_excel(banco, obra)))
    assert wb.sheetnames == ["Contratados", "Horas ocupadas", "Atividades"]
    ws = wb["Contratados"]
    assert ws.cell(3, 1).value == "Função" and ws.cell(4, 1).value
    assert ws.max_column == 4 + len(etapa5.detalhe_cenario(banco, obra)["semanas"])


def test_equipe_travada_na_obra(obra_pronta, biblioteca):
    banco, obra = obra_pronta
    etapa5.travar_equipe(banco, obra, "FUN-03", 3, biblioteca)
    inst, _ = etapa5.montar_instancia(banco, obra, 12, biblioteca)
    assert len(inst.tarefas["FUN-03"].modos) == 1 and inst.tarefas["FUN-03"].modos[0].equipe["Carpinteiro"] == 3
    with pytest.raises(etapa5.ErroCronograma):
        etapa5.travar_equipe(banco, obra, "TER-01", 2, biblioteca)   # terceirizada
    with pytest.raises(etapa5.ErroCronograma):
        etapa5.travar_equipe(banco, obra, "FUN-03", 9, biblioteca)   # acima da equipe máxima
    etapa5.travar_equipe(banco, obra, "FUN-03", None, biblioteca)
    assert banco.equipes_travadas(obra) == {}


def test_banco_antigo_ganha_tabelas_e_coluna(tmp_path):
    import sqlite3

    caminho = tmp_path / "antigo.sqlite3"
    con = sqlite3.connect(caminho)
    con.execute("CREATE TABLE atividade_execucao (obra_id INTEGER, atividade TEXT, execucao TEXT, rendimento REAL,"
                " equipe_padrao INTEGER, duracao_manual INTEGER)")
    con.close()
    Banco(str(caminho))
    con = sqlite3.connect(caminho)
    assert "equipe_travada" in {r[1] for r in con.execute("PRAGMA table_info(atividade_execucao)")}
    tabelas = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"obra_calendario", "cenarios", "cenario_atividades", "cenario_equipe_semana", "custos_hora_padrao"} <= tabelas


# ------------------------------------------------------------------ web


def test_fluxo_pela_web(tmp_path, arquivo_teste, biblioteca):
    caminho = copiar_biblioteca(tmp_path / "bib.xlsx")
    app = criar_app(str(tmp_path / "web.sqlite3"), str(tmp_path / "uploads"), str(caminho))
    cliente = app.test_client()
    with open(arquivo_teste, "rb") as f:
        dados = cliente.post("/api/leitura", data={"arquivo": (io.BytesIO(f.read()), arquivo_teste.name)},
                             content_type="multipart/form-data").get_json()
    obra = cliente.post("/api/importacoes", json={"token": dados["token"]}).get_json()["id"]
    cliente.get(f"/api/obras/{obra}/ligacao")
    cliente.post(f"/api/obras/{obra}/rede")
    cliente.get(f"/api/obras/{obra}/mao-de-obra")
    assert cliente.get(f"/cronograma?obra={obra}").status_code == 200
    # pendências da etapa 4 impedem o cálculo
    r = cliente.post(f"/api/obras/{obra}/cronograma/calcular", json={"prazos": [12]})
    assert r.status_code == 400 and "pendências" in r.get_json()["erro"]
    resolver_pendencias(Banco(str(tmp_path / "web.sqlite3")), obra, biblioteca)
    p = cliente.post(f"/api/obras/{obra}/cronograma/parametros",
                     json={"data_inicio": INICIO, "feriados_locais": [{"data": "2025-06-24", "nome": "São João"}]}).get_json()
    assert p["feriados_locais"] == [{"data": "2025-06-24", "nome": "São João"}]
    assert cliente.post(f"/api/obras/{obra}/cronograma/parametros", json={"data_inicio": "x"}).status_code == 400
    r = cliente.post(f"/api/obras/{obra}/cronograma/calcular", json={"prazos": ["11", "12"], "tempo_limite": 8})
    assert r.status_code == 200 and r.get_json()["rodando"]
    assert cliente.post(f"/api/obras/{obra}/cronograma/calcular", json={}).status_code == 409
    for _ in range(120):
        st = cliente.get(f"/api/obras/{obra}/cronograma/calculo").get_json()
        if not st["rodando"]:
            break
        assert 0 <= st["progresso"] <= 1
        time.sleep(0.5)
    assert not st["rodando"] and st["erro"] is None
    cmp = cliente.get(f"/api/obras/{obra}/cenarios").get_json()
    assert [c["prazo_meses"] for c in cmp["cenarios"]] == [11.0, 12.0]
    doze = next(c for c in cmp["cenarios"] if c["prazo_meses"] == 12)
    assert doze["situacao"] in ("otimo", "melhor_encontrado")
    assert cliente.post(f"/api/obras/{obra}/cenarios/{doze['id']}/escolher").status_code == 200
    det = cliente.get(f"/api/obras/{obra}/cenarios/escolhido").get_json()
    assert det["id"] == doze["id"] and det["atividades"] and det["funcoes"]
    # o feriado local não é dia de trabalho de nenhuma atividade com equipe
    for a in det["atividades"]:
        assert not (a["inicio"] == "2025-06-24")
    x = cliente.get(f"/api/obras/{obra}/cenarios/escolhido/excel")
    assert x.status_code == 200 and x.data[:2] == b"PK"
