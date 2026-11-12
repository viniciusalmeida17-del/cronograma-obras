"""Etapa 4 — ajustes: biblioteca (TER-01, SIN-01, HID-03, TES-01), ARGAMASSA fora das palavras, máquinas por equipamento."""
import copy

import pytest

from armazenamento import Banco
from atividades import ligar_servicos, montar_rede
from conftest import copiar_biblioteca, preparar_obra
from mao_de_obra import obra as etapa4
from mao_de_obra.calculo import calcular_duracao, calcular_obra
from mao_de_obra.funcoes import carregar_palavras_subcomposicao, eh_subcomposicao
from web.app import criar_app


# ------------------------------------------------------------------ (1) biblioteca


def test_biblioteca_ajustada(biblioteca):
    a = biblioteca.atividades
    assert a["TER-01"].execucao_padrao == "terceirizada"
    assert a["SIN-01"].execucao_padrao == "terceirizada"
    assert a["HID-03"].duracao_fixa_dias == 2
    assert a["TES-01"].duracao_fixa_dias == 5


@pytest.fixture(scope="module")
def obra_teste(resultado, biblioteca, analisador):
    servicos = [dict(s, id=i) for i, s in enumerate(resultado["servicos"])]
    for s, l in zip(servicos, ligar_servicos(servicos, resultado["grupos"], biblioteca)):
        s.update(l)
    rede = montar_rede(biblioteca, servicos)
    analises = {s["id"]: analisador.analisar_servico(s) for s in servicos}
    execucao = {c: {"execucao": a["execucao_padrao"] if a["execucao_padrao"] != "perguntar" else "propria"}
                for c, a in rede["atividades"].items() if a["tipo"] != "indireta"}
    return servicos, analises, rede["atividades"], execucao


def _calc(obra_teste, execucao=None):
    servicos, analises, atividades, ex = obra_teste
    return calcular_obra(servicos, copy.deepcopy(analises), atividades, execucao or ex, {}, (12, "meses"))


def _ativ(res, cod):
    return next(a for a in res["atividades"] if a["codigo"] == cod)


def test_hid03_e_tes01_com_duracao_fixa(obra_teste):
    res = _calc(obra_teste)
    assert _ativ(res, "HID-03")["duracao"] == {"dias": 2, "unidade": "corridos", "tipo": "fixa"}
    assert _ativ(res, "TES-01")["duracao"] == {"dias": 5, "unidade": "corridos", "tipo": "fixa"}
    assert not any(p["atividade"] in ("HID-03", "TES-01") for p in res["pendencias"])


def test_ter01_e_sin01_terceirizadas_fora_do_resumo(obra_teste):
    res = _calc(obra_teste)
    assert _ativ(res, "TER-01")["execucao"] == "terceirizada"
    assert _ativ(res, "SIN-01")["execucao"] == "terceirizada"
    ex = copy.deepcopy(obra_teste[3])
    ex["TER-01"]["execucao"] = ex["SIN-01"]["execucao"] = "propria"
    propria = _calc(obra_teste, ex)
    servente = lambda r: next(f["horas_ajustadas"] for f in r["resumo_funcoes"] if f["funcao"] == "Servente")  # noqa: E731
    tiradas = sum(_ativ(res, c)["horas_ajustadas"].get("Servente", 0) for c in ("TER-01", "SIN-01"))
    assert servente(propria) - servente(res) == pytest.approx(tiradas, abs=0.05)


# ------------------------------------------------------------------ (2) ARGAMASSA


@pytest.mark.parametrize("descricao, esperado", [
    ("ARGAMASSA TRAÇO 1:2:8 (EM VOLUME DE CIMENTO, CAL E AREIA MÉDIA ÚMIDA), PREPARO MECÂNICO", False),
    ("ARGAMASSA COLANTE AC I", False),
    ("CONTRAPISO EM ARGAMASSA TRAÇO 1:4, PREPARO MECÂNICO", True),   # CONTRAPISO continua na lista
    ("CHAPISCO APLICADO EM ALVENARIA", True),
])
def test_argamassa_nao_e_mais_subcomposicao(descricao, esperado):
    palavras = carregar_palavras_subcomposicao()
    assert "ARGAMASSA" not in palavras
    assert eh_subcomposicao(descricao, palavras) is esperado


def test_7_2_sem_pendentes(analise_por_item):
    a = analise_por_item["7.2"]
    assert a["pendentes"] == []
    assert {"87292"} & {str(p["codigo"]) for p in analise_por_item["7.3"]["pendentes"]} == set()
    pend = {str(p["codigo"]) for p in analise_por_item["5.1.14"]["pendentes"]}
    assert "ED-48202" in pend  # 87893 e 101963 agora vêm de dados/produtividade_referencia.xlsx


def test_exemplo_da_especificacao_com_o_item_7_2_real(obra_teste):
    """Uma atividade só com o 7.2 (dados reais da composição): 25 dias úteis; 23 com rendimento 100%."""
    servicos, analises, atividades, ex = obra_teste
    s72 = next(s for s in servicos if s["item"] == "7.2")
    so = {"ALV-02": dict(atividades["ALV-02"])}
    res = calcular_obra([s72], {s72["id"]: copy.deepcopy(analises[s72["id"]])}, so, {"ALV-02": {"execucao": "propria"}}, {})
    a = res["atividades"][0]
    assert a["horas_brutas"] == {"Pedreiro": pytest.approx(387.72, abs=0.01), "Servente": pytest.approx(193.86, abs=0.01)}
    assert a["horas_ajustadas"] == {"Pedreiro": pytest.approx(430.80, abs=0.01), "Servente": pytest.approx(215.40, abs=0.01)}
    assert a["calculo"]["equipe"] == {"Pedreiro": 2, "Servente": 1}
    assert a["duracao"]["dias"] == 25
    res100 = calcular_obra([s72], {s72["id"]: copy.deepcopy(analises[s72["id"]])}, so,
                           {"ALV-02": {"execucao": "propria"}}, {"rendimento": 1.0})
    assert res100["atividades"][0]["duracao"]["dias"] == 23


# ------------------------------------------------------------------ (3) máquinas por equipamento


def test_formula_com_maquinas():
    um = calcular_duracao({"Servente": 88}, {"Caminhão": 264}, 2, 8.8)
    assert um["maquinas"] == {"Caminhão": 1} and um["dias"] == 30 and um["limitante"] == "equipamento"
    tres = calcular_duracao({"Servente": 88}, {"Caminhão": 264}, 2, 8.8, {"Caminhão": 3})
    assert tres["maquinas"] == {"Caminhão": 3}
    assert tres["dias_por_equipamento"] == {"Caminhão": 10.0}
    assert tres["dias"] == 10
    seis = calcular_duracao({"Servente": 88}, {"Caminhão": 264}, 2, 8.8, {"Caminhão": 6})
    assert seis["dias"] == 5 and seis["limitante"] == "mao_de_obra"  # agora quem limita são as pessoas
    assert calcular_duracao({}, {"Caminhão": 264}, 2, 8.8, {"Outro": 4})["maquinas"] == {"Caminhão": 1}


def test_maquinas_na_obra(obra_teste):
    # TER-01 como própria (terceirizada tem a duração da instalação, ajuste 7.1: as máquinas não mudam nada)
    ex0 = copy.deepcopy(obra_teste[3])
    ex0["TER-01"]["execucao"] = "propria"
    base = _ativ(_calc(obra_teste, ex0), "TER-01")
    assert base["calculo"]["limitante"] == "equipamento"
    caminhao = max(base["horas_equipamento"], key=base["horas_equipamento"].get)
    ex = copy.deepcopy(ex0)
    ex["TER-01"]["maquinas"] = {caminhao: 4}
    novo = _ativ(_calc(obra_teste, ex), "TER-01")
    assert novo["calculo"]["maquinas"][caminhao] == 4
    assert novo["calculo"]["dias_por_equipamento"][caminhao] == pytest.approx(
        base["calculo"]["dias_por_equipamento"][caminhao] / 4, abs=0.01)
    assert novo["duracao"]["dias"] < base["duracao"]["dias"]
    # terceirizada: duração da instalação pela produção da biblioteca, as máquinas não mudam
    terc = copy.deepcopy(obra_teste[3])
    terc["TER-01"]["maquinas"] = {caminhao: 4}
    assert _ativ(_calc(obra_teste, terc), "TER-01")["duracao"] == _ativ(_calc(obra_teste), "TER-01")["duracao"]


@pytest.fixture()
def banco_obra(tmp_path, arquivo_teste, biblioteca):
    banco = Banco(str(tmp_path / "obra.sqlite3"))
    obra_id = preparar_obra(banco, arquivo_teste, biblioteca)
    etapa4.analisar_obra(banco, obra_id, biblioteca)
    return banco, obra_id


def test_maquinas_gravadas_e_validadas(banco_obra, biblioteca):
    banco, obra = banco_obra
    etapa4.definir_execucao(banco, obra, ["TER-01"], "propria", biblioteca)   # máquinas valem na própria
    estado = etapa4.estado_mao_de_obra(banco, obra, biblioteca)
    ter = _ativ(estado, "TER-01")
    caminhao = max(ter["horas_equipamento"], key=ter["horas_equipamento"].get)
    etapa4.definir_atividade(banco, obra, "TER-01", maquinas={caminhao: 3}, biblioteca=biblioteca)
    assert banco.carregar_execucao(obra)["TER-01"]["maquinas"] == {caminhao: 3}
    novo = _ativ(etapa4.estado_mao_de_obra(banco, obra, biblioteca), "TER-01")
    assert novo["calculo"]["maquinas"][caminhao] == 3 and novo["duracao"]["dias"] < ter["duracao"]["dias"]
    resumo = {r["atividade"]: r for r in banco.carregar_resumo_atividades(obra)}
    assert resumo["TER-01"]["maquinas"][caminhao] == 3
    # voltar para 1 apaga a linha (1 é o padrão)
    etapa4.definir_atividade(banco, obra, "TER-01", maquinas={caminhao: 1}, biblioteca=biblioteca)
    assert "maquinas" not in banco.carregar_execucao(obra)["TER-01"]
    for ruim in (0, 2.5, "abc", 21):
        with pytest.raises(etapa4.ErroMaoDeObra):
            etapa4.definir_atividade(banco, obra, "TER-01", maquinas={caminhao: ruim}, biblioteca=biblioteca)


def test_maquinas_pela_web(tmp_path, arquivo_teste):
    import io

    caminho = copiar_biblioteca(tmp_path / "bib.xlsx")
    cliente = criar_app(str(tmp_path / "web.sqlite3"), str(tmp_path / "uploads"), str(caminho)).test_client()
    with open(arquivo_teste, "rb") as f:
        dados = cliente.post("/api/leitura", data={"arquivo": (io.BytesIO(f.read()), arquivo_teste.name)},
                             content_type="multipart/form-data").get_json()
    obra = cliente.post("/api/importacoes", json={"token": dados["token"]}).get_json()["id"]
    cliente.get(f"/api/obras/{obra}/ligacao")
    cliente.post(f"/api/obras/{obra}/rede")
    estado = cliente.get(f"/api/obras/{obra}/mao-de-obra").get_json()
    ter = _ativ(estado, "TER-01")
    caminhao = max(ter["horas_equipamento"], key=ter["horas_equipamento"].get)
    r = cliente.post(f"/api/obras/{obra}/atividade/TER-01", json={"maquinas": {caminhao: 2}})
    assert r.status_code == 200
    assert _ativ(r.get_json(), "TER-01")["calculo"]["maquinas"][caminhao] == 2
    assert cliente.post(f"/api/obras/{obra}/atividade/TER-01", json={"maquinas": {caminhao: 0}}).status_code == 400


def test_migracao_atividade_resumo_sem_maquinas(tmp_path):
    import sqlite3

    caminho = tmp_path / "etapa4.sqlite3"
    con = sqlite3.connect(caminho)
    con.execute("CREATE TABLE atividade_resumo (obra_id INTEGER, atividade TEXT, equipe TEXT)")
    con.close()
    Banco(str(caminho))
    con = sqlite3.connect(caminho)
    assert "maquinas" in {r[1] for r in con.execute("PRAGMA table_info(atividade_resumo)")}
    assert "atividade_equipamento" in {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
