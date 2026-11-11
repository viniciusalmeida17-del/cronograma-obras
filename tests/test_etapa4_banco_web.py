"""Etapa 4 — gravação no banco, banco de coeficientes, edições do usuário e rotas web."""
import io
import sqlite3

import pytest

from armazenamento import Banco
from conftest import copia_so_abas, copiar_biblioteca, preparar_obra
from mao_de_obra import obra as etapa4
from web.app import criar_app


@pytest.fixture()
def banco(tmp_path):
    return Banco(str(tmp_path / "obra.sqlite3"))


@pytest.fixture()
def obra(banco, arquivo_teste, biblioteca):
    obra_id = preparar_obra(banco, arquivo_teste, biblioteca)
    etapa4.analisar_obra(banco, obra_id, biblioteca)
    return obra_id


def _serv(estado, item):
    return next(s for s in estado["servicos"] if s["item"] == item)


def _ativ(estado, cod):
    return next(a for a in estado["atividades"] if a["codigo"] == cod)


def test_analise_grava_tudo(banco, obra, biblioteca):
    estado = etapa4.estado_mao_de_obra(banco, obra, biblioteca)
    s72 = _serv(estado, "7.2")
    assert s72["origem"] == "composicao"
    comp = {h["funcao"]: h["horas_un"] for h in s72["horas"] if h["origem"] == "composicao"}
    assert comp == {"Pedreiro": pytest.approx(0.99), "Servente": pytest.approx(0.495)}
    assert {e["funcao"]: e["pessoas"] for e in estado["equipe_fixa"]} == \
        {"Engenheiro": 0.2, "Encarregado": 1, "Técnico de segurança": 1, "Vigia": 1}
    assert {r["aba"] for r in estado["abas_composicoes"]} >= {"ELÉTRICA", "ALVENARIA", "FUNDAÇÃO", "CPU"}
    resumo = {r["atividade"]: r for r in banco.carregar_resumo_atividades(obra)}
    assert resumo["EST-03"]["duracao_dias"] == 21 and resumo["EST-03"]["duracao_unidade"] == "corridos"
    assert resumo["ALV-02"]["funcao_principal"] == "Pedreiro"
    con = sqlite3.connect(banco.caminho)
    assert con.execute("SELECT COUNT(*) FROM servico_mao_de_obra WHERE origem = 'estimado'").fetchone()[0] > 0
    assert con.execute("SELECT COUNT(*) FROM subcomposicoes_pendentes").fetchone()[0] > 0


def test_execucao_inicial_vem_da_biblioteca(banco, obra, biblioteca):
    ex = banco.carregar_execucao(obra)
    assert ex["MET-01"]["execucao"] == "terceirizada"
    assert ex["FUN-03"]["execucao"] == "propria"
    assert ex["ELE-04"]["execucao"] is None  # perguntar
    assert "IND-01" not in ex
    estado = etapa4.estado_mao_de_obra(banco, obra, biblioteca)
    assert any(p["atividade"] == "ELE-04" and p["tipo"] == "execucao" for p in estado["pendencias"])
    assert estado["pode_seguir"] is False


def test_resolver_todas_as_pendencias(banco, obra, biblioteca):
    estado = etapa4.estado_mao_de_obra(banco, obra, biblioteca)
    sem_exec = [p["atividade"] for p in estado["pendencias"] if p["tipo"] == "execucao"]
    etapa4.definir_execucao(banco, obra, sem_exec, "propria", biblioteca)
    estado = etapa4.estado_mao_de_obra(banco, obra, biblioteca)
    for p in estado["pendencias"]:
        assert p["tipo"] == "duracao"
        etapa4.definir_atividade(banco, obra, p["atividade"], duracao_manual=10, biblioteca=biblioteca)
    estado = etapa4.estado_mao_de_obra(banco, obra, biblioteca)
    assert estado["pendencias"] == [] and estado["pode_seguir"] is True
    assert _ativ(estado, "MET-01")["duracao"] == {"dias": 10, "unidade": "uteis", "tipo": "manual"}


def test_equipe_padrao_recalcula_e_respeita_maximo(banco, obra, biblioteca):
    antes = _ativ(etapa4.estado_mao_de_obra(banco, obra, biblioteca), "ALV-02")["duracao"]["dias"]
    etapa4.definir_atividade(banco, obra, "ALV-02", equipe_padrao=4, biblioteca=biblioteca)
    depois = _ativ(etapa4.estado_mao_de_obra(banco, obra, biblioteca), "ALV-02")
    assert depois["equipe_padrao"] == 4 and depois["duracao"]["dias"] < antes
    with pytest.raises(etapa4.ErroMaoDeObra):
        etapa4.definir_atividade(banco, obra, "ALV-02", equipe_padrao=21, biblioteca=biblioteca)
    with pytest.raises(etapa4.ErroMaoDeObra):
        etapa4.definir_atividade(banco, obra, "IND-01", equipe_padrao=2, biblioteca=biblioteca)


def test_parametros(banco, obra, biblioteca):
    assert banco.carregar_parametros(obra)["horas_semana"] == 44
    etapa4.salvar_parametros(banco, obra, {"horas_semana": 40, "dias_semana": 5, "rendimento": 100, "mudancas_jornada": [
        {"a_partir_de": "2028-01-01", "horas_semana": 40}, {"a_partir_de": "2027-01-01", "horas_semana": 42}]})
    p = banco.carregar_parametros(obra)
    assert p["rendimento"] == 1.0 and p["horas_semana"] == 40
    assert [m["a_partir_de"] for m in p["mudancas_jornada"]] == ["2027-01-01", "2028-01-01"]
    assert etapa4.estado_mao_de_obra(banco, obra, biblioteca)["parametros"]["horas_por_dia"] == 8
    for ruim in ({"dias_semana": 7}, {"horas_semana": 0}, {"rendimento": 0.1},
                 {"mudancas_jornada": [{"a_partir_de": "01/01/2027", "horas_semana": 42}]}):
        with pytest.raises(etapa4.ErroMaoDeObra):
            etapa4.salvar_parametros(banco, obra, ruim)


def test_banco_de_coeficientes_reaproveitado_em_planilha_sem_composicoes(banco, obra, arquivo_teste, biblioteca, tmp_path):
    assert len(banco.listar_coeficientes()) > 300
    sem_comp = copia_so_abas(arquivo_teste, tmp_path / "sem_composicoes.xlsx", ("PLANILHA",))
    obra2 = preparar_obra(banco, sem_comp, biblioteca)
    estado = etapa4.analisar_obra(banco, obra2, biblioteca)
    assert estado["abas_composicoes"] == []
    s72 = _serv(estado, "7.2")
    assert s72["origem"] == "banco"
    assert {h["funcao"]: h["horas_un"] for h in s72["horas"]} == {"Pedreiro": pytest.approx(0.99), "Servente": pytest.approx(0.495)}
    # o que não está no banco é estimado pelo custo
    assert any(s["origem"] == "estimado" for s in estado["servicos"])


def test_banco_de_coeficientes_sobrevive_a_obra(banco, obra):
    n = len(banco.listar_coeficientes())
    banco.excluir_obra(obra)
    assert len(banco.listar_coeficientes()) == n


def test_horas_manuais_no_servico(banco, obra, biblioteca):
    estado = etapa4.estado_mao_de_obra(banco, obra, biblioteca)
    s = _serv(estado, "4.11")
    estado = etapa4.definir_horas_servico(banco, obra, s["id"], {"Servente": 1.5, "Pedreiro": "0,5"}, biblioteca)
    s = _serv(estado, "4.11")
    assert s["origem"] == "manual" and s["pendentes"] == []
    assert {h["funcao"]: (h["horas_un"], h["origem"]) for h in s["horas"]} == {"Servente": (1.5, "manual"), "Pedreiro": (0.5, "manual")}
    manuais = {(r["codigo"], r["funcao"]): r["horas_un"] for r in banco.listar_coeficientes(s["codigo"]) if r["origem"] == "manual"}
    assert manuais == {(s["codigo"].replace(" ", ""), "Servente"): 1.5, (s["codigo"].replace(" ", ""), "Pedreiro"): 0.5}
    # sobrevive a reler as composições
    s = _serv(etapa4.analisar_obra(banco, obra, biblioteca), "4.11")
    assert s["origem"] == "manual"
    # vazio = volta ao automático
    s = _serv(etapa4.definir_horas_servico(banco, obra, s["id"], {}, biblioteca), "4.11")
    assert s["origem"] == "estimado"


def test_horas_de_subcomposicao_pendente(banco, obra, biblioteca):
    antes = _serv(etapa4.estado_mao_de_obra(banco, obra, biblioteca), "5.1.14")
    assert "ED-48202" in {p["codigo"] for p in antes["pendentes"]}
    estado = etapa4.definir_horas_subcomposicao(banco, obra, "ED-48202", {"Pedreiro": 0.8, "Servente": 0.4},
                                                "ALVENARIA ESTRUTURAL", biblioteca)
    depois = _serv(estado, "5.1.14")
    assert "ED-48202" not in {p["codigo"] for p in depois["pendentes"]}
    banco_h = {h["funcao"]: h["horas_un"] for h in depois["horas"] if h["origem"] == "banco"}
    coef = 6.52  # coeficiente do ED-48202 na composição do 5.1.14
    assert banco_h == {"Pedreiro": pytest.approx(0.8 * coef), "Servente": pytest.approx(0.4 * coef)}
    with pytest.raises(etapa4.ErroMaoDeObra):
        etapa4.definir_horas_subcomposicao(banco, obra, "ED-48202", {}, None, biblioteca)


def test_obra_sem_arquivo(banco, arquivo_teste, biblioteca):
    from atividades import obra as etapa3
    from leitor_planilha import ler_planilha

    obra_id = banco.salvar_importacao(ler_planilha(arquivo_teste))
    etapa3.ligar_obra(banco, obra_id, biblioteca)
    etapa3.montar_rede_obra(banco, obra_id, biblioteca)
    with pytest.raises(etapa4.ErroMaoDeObra) as exc:
        etapa4.analisar_obra(banco, obra_id, biblioteca)
    assert "arquivo da planilha" in str(exc.value)


def test_obra_sem_rede(banco, arquivo_teste, biblioteca):
    from leitor_planilha import ler_planilha

    obra_id = banco.salvar_importacao(ler_planilha(arquivo_teste))
    banco.guardar_arquivo(obra_id, arquivo_teste)
    with pytest.raises(etapa4.ErroMaoDeObra):
        etapa4.analisar_obra(banco, obra_id, biblioteca)


def test_migracao_de_banco_da_etapa_3(tmp_path):
    caminho = tmp_path / "etapa3.sqlite3"
    con = sqlite3.connect(caminho)
    con.executescript("""
        CREATE TABLE obras (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, prazo_valor REAL NOT NULL);
        CREATE TABLE servicos (id INTEGER PRIMARY KEY AUTOINCREMENT, obra_id INTEGER, item TEXT, natureza TEXT NOT NULL,
                               atividade_biblioteca TEXT, status_ligacao TEXT, regra_usada INTEGER);
        CREATE TABLE obra_atividades (obra_id INTEGER NOT NULL, codigo TEXT NOT NULL, tipo TEXT NOT NULL,
                                      PRIMARY KEY (obra_id, codigo));
    """)
    con.close()
    Banco(str(caminho))
    con = sqlite3.connect(caminho)
    cols = lambda t: {r[1] for r in con.execute(f"PRAGMA table_info({t})")}  # noqa: E731
    assert "origem_horas" in cols("servicos")
    assert {"arquivo_salvo", "composicoes_abas"} <= cols("obras")
    assert {"execucao_padrao", "equipe_padrao", "equipe_max", "duracao_fixa_dias"} <= cols("obra_atividades")
    tabelas = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"obra_parametros", "servico_mao_de_obra", "servico_equipamento", "subcomposicoes_pendentes",
            "atividade_execucao", "atividade_resumo", "banco_coeficientes"} <= tabelas


# ------------------------------------------------------------------ web


@pytest.fixture()
def cliente(tmp_path):
    caminho = copiar_biblioteca(tmp_path / "bib.xlsx")
    app = criar_app(str(tmp_path / "web.sqlite3"), str(tmp_path / "uploads"), str(caminho))
    app.testing = True
    return app.test_client()


def _obra_web(cliente, arquivo_teste):
    with open(arquivo_teste, "rb") as f:
        dados = cliente.post("/api/leitura", data={"arquivo": (io.BytesIO(f.read()), arquivo_teste.name)},
                             content_type="multipart/form-data").get_json()
    obra = cliente.post("/api/importacoes", json={"token": dados["token"]}).get_json()["id"]
    assert cliente.get(f"/api/obras/{obra}/ligacao").status_code == 200
    assert cliente.post(f"/api/obras/{obra}/rede").status_code == 200
    return obra


def test_pagina(cliente):
    assert cliente.get("/mao-de-obra").status_code == 200
    assert cliente.get("/static/mao_de_obra.js").status_code == 200


def test_fluxo_web_etapa4(cliente, arquivo_teste):
    obra = _obra_web(cliente, arquivo_teste)
    r = cliente.get(f"/api/obras/{obra}/mao-de-obra")
    assert r.status_code == 200, r.get_json()
    estado = r.get_json()
    assert len(estado["atividades"]) == 74
    assert any(p["atividade"] == "MET-01" for p in estado["pendencias"])

    r = cliente.post(f"/api/obras/{obra}/execucao", json={"atividades": ["ELE-01", "ELE-02"], "execucao": "terceirizada"})
    assert r.status_code == 200
    assert _ativ(r.get_json(), "ELE-01")["execucao"] == "terceirizada"
    assert cliente.post(f"/api/obras/{obra}/execucao", json={"atividades": ["ELE-01"], "execucao": "talvez"}).status_code == 400

    r = cliente.post(f"/api/obras/{obra}/atividade/MET-01", json={"duracao_manual": 45})
    assert _ativ(r.get_json(), "MET-01")["duracao"]["dias"] == 45
    assert cliente.post(f"/api/obras/{obra}/atividade/MET-01", json={"duracao_manual": "abc"}).status_code == 400

    r = cliente.post(f"/api/obras/{obra}/parametros", json={"horas_semana": 42, "dias_semana": 5, "rendimento": 0.9})
    assert r.get_json()["parametros"]["horas_por_dia"] == pytest.approx(8.4)

    sid = _serv(estado, "4.11")["id"]
    r = cliente.post(f"/api/obras/{obra}/servico/{sid}/horas", json={"horas": {"Servente": 2}})
    assert _serv(r.get_json(), "4.11")["origem"] == "manual"
    r = cliente.post(f"/api/obras/{obra}/subcomposicao", json={"codigo": "87893", "horas": {"Pedreiro": 0.2}})
    assert r.status_code == 200
    assert cliente.post(f"/api/obras/{obra}/mao-de-obra/analisar").status_code == 200


def test_web_obra_sem_arquivo_pede_reenvio(cliente, arquivo_teste, tmp_path):
    obra = _obra_web(cliente, arquivo_teste)
    import sqlite3 as sq
    con = sq.connect(tmp_path / "web.sqlite3")
    con.execute("UPDATE obras SET arquivo_salvo = NULL")
    con.commit()
    con.close()
    r = cliente.get(f"/api/obras/{obra}/mao-de-obra")
    assert r.status_code == 409 and r.get_json()["precisa_arquivo"] is True
    with open(arquivo_teste, "rb") as f:
        r = cliente.post(f"/api/obras/{obra}/arquivo", data={"arquivo": (io.BytesIO(f.read()), "planilha.xlsx")},
                         content_type="multipart/form-data")
    assert r.status_code == 200 and len(r.get_json()["servicos"]) == 374
