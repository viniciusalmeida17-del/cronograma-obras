"""Etapa 3 — banco (memória, rede da obra) e rotas da interface web."""
import io
import sqlite3

import pytest

from armazenamento import Banco
from atividades import carregar_biblioteca, obra as etapa3
from conftest import copiar_biblioteca
from leitor_planilha import ler_planilha
from web.app import criar_app


@pytest.fixture()
def banco(tmp_path):
    return Banco(str(tmp_path / "obra.sqlite3"))


def _importar(banco, arquivo_teste):
    return banco.salvar_importacao(ler_planilha(arquivo_teste))


def _por_item(estado):
    return {s["item"]: s for s in estado["servicos"]}


def test_ligar_obra_grava_no_banco(banco, arquivo_teste, biblioteca):
    obra_id = _importar(banco, arquivo_teste)
    estado = etapa3.ligar_obra(banco, obra_id, biblioteca)
    assert estado["resumo"]["texto"] == "374 serviços — 374 ligados automaticamente, 0 pendentes"
    s = _por_item(banco.carregar_obra(obra_id))
    assert s["4.10"]["atividade_biblioteca"] == "FUN-03"
    assert s["4.10"]["status_ligacao"] == "automatico"
    assert s["4.10"]["regra_usada"] == 17
    totais = {a["codigo"]: a for a in estado["atividades"]}
    assert totais["FUN-03"]["n_itens"] == 9
    assert round(sum(a["total_bdi"] for a in estado["atividades"]), 2) == 5669771.17


def test_memoria_ao_reimportar(banco, arquivo_teste, biblioteca):
    obra1 = _importar(banco, arquivo_teste)
    etapa3.ligar_obra(banco, obra1, biblioteca)
    s410 = _por_item(banco.carregar_obra(obra1))["4.10"]

    estado = etapa3.confirmar_ligacao(banco, obra1, [s410["id"]], "FUN-04", biblioteca)
    p = _por_item(estado)
    assert (p["4.10"]["atividade_biblioteca"], p["4.10"]["status_ligacao"]) == ("FUN-04", "confirmado")
    assert p["4.10"]["regra_usada"] is None
    assert estado["resumo"]["por_status"]["confirmado"] == 1

    # reimporta a mesma planilha → nova obra
    obra2 = _importar(banco, arquivo_teste)
    estado2 = etapa3.ligar_obra(banco, obra2, biblioteca)
    p2 = _por_item(estado2)
    assert (p2["4.10"]["atividade_biblioteca"], p2["4.10"]["status_ligacao"]) == ("FUN-04", "memoria")
    # mesmo código (SINAPI 96616), outro grupo: não é afetado pela memória
    assert (p2["6.4"]["atividade_biblioteca"], p2["6.4"]["status_ligacao"]) == ("CON-01", "automatico")
    assert (p2["15.2.3"]["atividade_biblioteca"], p2["15.2.3"]["status_ligacao"]) == ("QUA-01", "automatico")
    assert estado2["resumo"]["por_status"]["memoria"] == 1


def test_memoria_atualiza_com_nova_escolha(banco, arquivo_teste, biblioteca):
    obra = _importar(banco, arquivo_teste)
    etapa3.ligar_obra(banco, obra, biblioteca)
    sid = _por_item(banco.carregar_obra(obra))["4.10"]["id"]
    etapa3.confirmar_ligacao(banco, obra, [sid], "FUN-04", biblioteca)
    etapa3.confirmar_ligacao(banco, obra, [sid], "FUN-03", biblioteca)
    assert list(banco.carregar_memoria().values()) == ["FUN-03"]


def test_refazer_mantem_confirmados(banco, arquivo_teste, biblioteca):
    obra = _importar(banco, arquivo_teste)
    etapa3.ligar_obra(banco, obra, biblioteca)
    sid = _por_item(banco.carregar_obra(obra))["13.14"]["id"]
    etapa3.confirmar_ligacao(banco, obra, [sid], "SER-01", biblioteca)
    estado = etapa3.ligar_obra(banco, obra, biblioteca, refazer=True)
    assert _por_item(estado)["13.14"]["atividade_biblioteca"] == "SER-01"
    assert _por_item(estado)["13.14"]["status_ligacao"] == "confirmado"


def test_confirmar_atividade_inexistente(banco, arquivo_teste, biblioteca):
    obra = _importar(banco, arquivo_teste)
    etapa3.ligar_obra(banco, obra, biblioteca)
    sid = _por_item(banco.carregar_obra(obra))["4.10"]["id"]
    with pytest.raises(etapa3.ErroObra):
        etapa3.confirmar_ligacao(banco, obra, [sid], "XYZ-01", biblioteca)


def test_servicos_semelhantes():
    servicos = [
        {"id": 1, "base": "SINAPI", "codigo": "96616", "item_grupo": "4"},
        {"id": 2, "base": "SINAPI", "codigo": "96616", "item_grupo": "4"},
        {"id": 3, "base": "SINAPI", "codigo": "96616", "item_grupo": "6"},   # outro grupo
        {"id": 4, "base": "SETOP", "codigo": "96616", "item_grupo": "4"},    # outra base
        {"id": 5, "base": "SINAPI", "codigo": "96617", "item_grupo": "4"},   # outro código
    ]
    assert [s["id"] for s in etapa3.servicos_semelhantes(servicos, servicos[0])] == [2]


def test_rede_gravada_e_independente_da_biblioteca(banco, arquivo_teste, tmp_path):
    caminho = copiar_biblioteca(tmp_path / "bib.xlsx")
    bib = carregar_biblioteca(caminho)
    obra = _importar(banco, arquivo_teste)
    etapa3.ligar_obra(banco, obra, bib)
    estado = etapa3.montar_rede_obra(banco, obra, bib)
    assert estado["resumo"]["atividades"] == 80
    assert estado["resumo"]["total_bdi"] == 5669771.17
    assert estado["sequencia"][-1]["codigo"] == "LIM-01"

    con = sqlite3.connect(tmp_path / "obra.sqlite3")
    assert con.execute("SELECT COUNT(*) FROM obra_atividades WHERE obra_id = ?", (obra,)).fetchone()[0] == 80
    assert con.execute("SELECT espera_dias FROM obra_dependencias WHERE obra_id = ? AND atividade = 'FUN-05' AND depende_de = 'FUN-04'", (obra,)).fetchone()[0] == 3

    # edição só na obra: biblioteca não muda
    estado = etapa3.editar_atividade_obra(banco, obra, "SER-03", tipo="rigida", depende_de="PEX-02",
                                          caminho_biblioteca=str(caminho))
    ser03 = next(a for a in estado["sequencia"] if a["codigo"] == "SER-03")
    assert ser03["tipo"] == "rigida" and ser03["depende_de_texto"] == "PEX-02"
    assert estado["backup_biblioteca"] is None
    assert carregar_biblioteca(caminho).atividades["SER-03"].tipo == "flexivel"

    # edição com "salvar também na biblioteca padrão"
    estado = etapa3.editar_atividade_obra(banco, obra, "SER-03", tipo="rigida", depende_de="PEX-02",
                                          salvar_na_biblioteca=True, caminho_biblioteca=str(caminho))
    assert estado["backup_biblioteca"]
    nova = carregar_biblioteca(caminho)
    assert nova.atividades["SER-03"].tipo == "rigida"
    assert [str(d) for d in nova.atividades["SER-03"].depende_de] == ["PEX-02"]

    # a rede gravada da obra não muda quando a biblioteca é editada depois
    antes = banco.carregar_rede(obra)
    from atividades.biblioteca import salvar_atividade_na_biblioteca
    salvar_atividade_na_biblioteca("FUN-05", "flexivel", None, caminho)
    assert banco.carregar_rede(obra) == antes


def test_editar_so_tipo_nao_grava_dependencias_herdadas(banco, arquivo_teste, tmp_path):
    caminho = copiar_biblioteca(tmp_path / "bib.xlsx")
    bib = carregar_biblioteca(caminho)
    obra = _importar(banco, arquivo_teste)
    etapa3.ligar_obra(banco, obra, bib)
    etapa3.montar_rede_obra(banco, obra, bib)
    etapa3.editar_atividade_obra(banco, obra, "LIM-01", tipo="flexivel", salvar_na_biblioteca=True,
                                 caminho_biblioteca=str(caminho))
    lim = carregar_biblioteca(caminho).atividades["LIM-01"]
    assert lim.tipo == "flexivel"
    assert [str(d) for d in lim.depende_de] == ["TES-01"]  # as ligações "fim" não vão para a biblioteca


def test_editar_com_ciclo_nao_grava(banco, arquivo_teste, biblioteca):
    obra = _importar(banco, arquivo_teste)
    etapa3.ligar_obra(banco, obra, biblioteca)
    etapa3.montar_rede_obra(banco, obra, biblioteca)
    antes = banco.carregar_rede(obra)
    with pytest.raises(etapa3.ErroObra) as exc:
        etapa3.editar_atividade_obra(banco, obra, "LOC-01", depende_de="FUN-02")
    assert "Ciclo" in str(exc.value)
    assert banco.carregar_rede(obra) == antes


def test_rede_recusa_pendencias(banco, arquivo_teste, tmp_path):
    def alterar(wb):
        wb["Regras"].append([90, 1, "FUN-04", "FUNDACAO", "LASTRO DE CONCRETO MAGRO", None])
        wb["Regras"].append([91, 1, "FUN-03", "FUNDACAO", "LASTRO DE CONCRETO MAGRO", None])

    bib = carregar_biblioteca(copiar_biblioteca(tmp_path / "bib.xlsx", alterar))
    obra = _importar(banco, arquivo_teste)
    estado = etapa3.ligar_obra(banco, obra, bib)
    pend = [s for s in estado["servicos"] if s["status_ligacao"] == "ambiguo"]
    assert len(pend) == 1 and pend[0]["candidatas"] == ["FUN-04", "FUN-03"]
    with pytest.raises(etapa3.ErroObra):
        etapa3.montar_rede_obra(banco, obra, bib)
    etapa3.confirmar_ligacao(banco, obra, [pend[0]["id"]], "FUN-03", bib)
    assert etapa3.montar_rede_obra(banco, obra, bib)["resumo"]["atividades"] == 80


def test_migracao_de_banco_da_etapa_2(tmp_path):
    caminho = tmp_path / "antigo.sqlite3"
    con = sqlite3.connect(caminho)
    con.executescript("""
        CREATE TABLE obras (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, prazo_valor REAL NOT NULL);
        CREATE TABLE servicos (id INTEGER PRIMARY KEY AUTOINCREMENT, obra_id INTEGER, item TEXT,
                               natureza TEXT NOT NULL, atividade_biblioteca TEXT, etapa_obra TEXT, local TEXT);
    """)
    con.close()
    Banco(str(caminho))
    con = sqlite3.connect(caminho)
    colunas = {r[1] for r in con.execute("PRAGMA table_info(servicos)")}
    assert {"status_ligacao", "regra_usada"} <= colunas
    tabelas = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"memoria_ligacoes", "obra_atividades", "obra_dependencias"} <= tabelas


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
    r = cliente.post("/api/importacoes", json={"token": dados["token"]})
    return r.get_json()["id"]


def test_paginas(cliente):
    for url in ("/ligacao", "/sequencia", "/static/ligacao.js", "/static/sequencia.js", "/static/comum.js"):
        assert cliente.get(url).status_code == 200, url


def test_fluxo_web_etapa3(cliente, arquivo_teste):
    assert len(cliente.get("/api/biblioteca").get_json()["atividades"]) == 80
    obra = _obra_web(cliente, arquivo_teste)

    r = cliente.get(f"/api/obras/{obra}/ligacao")
    assert r.status_code == 200
    estado = r.get_json()
    assert estado["resumo"]["pendentes"] == 0 and estado["resumo"]["total"] == 374

    # rede antes de montar: erro claro
    assert cliente.get(f"/api/obras/{obra}/rede").status_code == 400

    sid = next(s["id"] for s in estado["servicos"] if s["item"] == "4.10")
    r = cliente.post(f"/api/obras/{obra}/ligacao", json={"servicos": [sid], "atividade": "FUN-04"})
    assert r.status_code == 200
    assert next(s for s in r.get_json()["servicos"] if s["id"] == sid)["status_ligacao"] == "confirmado"
    assert cliente.post(f"/api/obras/{obra}/ligacao", json={"servicos": [sid], "atividade": "NAO-01"}).status_code == 400

    r = cliente.post(f"/api/obras/{obra}/rede")
    assert r.status_code == 200
    rede = r.get_json()
    assert rede["resumo"]["atividades"] == 80
    assert rede["sequencia"][-1]["codigo"] == "LIM-01"

    r = cliente.post(f"/api/obras/{obra}/rede/LOC-01", json={"depende_de": "FUN-02"})
    assert r.status_code == 400 and "Ciclo" in r.get_json()["erro"]
    r = cliente.post(f"/api/obras/{obra}/rede/SER-03", json={"tipo": "rigida", "depende_de": "PEX-02+2d"})
    assert r.status_code == 200
    ser03 = next(a for a in r.get_json()["sequencia"] if a["codigo"] == "SER-03")
    assert ser03["depende_de_texto"] == "PEX-02+2d"

    assert cliente.get("/api/importacoes").get_json()[0]["tem_rede"] == 1


def test_web_biblioteca_com_erro(tmp_path, arquivo_teste):
    def alterar(wb):
        ws = wb["Atividades"]
        ws["D8"].value = "PRE-03"  # PRE-01 → ciclo

    caminho = copiar_biblioteca(tmp_path / "bib.xlsx", alterar)
    app = criar_app(str(tmp_path / "web.sqlite3"), str(tmp_path / "uploads"), str(caminho))
    cliente = app.test_client()
    r = cliente.get("/api/biblioteca")
    assert r.status_code == 422
    erros = r.get_json()["erros_biblioteca"]
    assert any("Ciclo" in e["mensagem"] for e in erros)
