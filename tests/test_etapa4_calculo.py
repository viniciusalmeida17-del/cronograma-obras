"""Etapa 4 — fórmula de duração, estimativas e resumo da obra (funções puras)."""
import copy

import pytest

from atividades import ligar_servicos, montar_rede
from mao_de_obra.calculo import calcular_duracao, calcular_obra, semanas_do_prazo


def test_formula_exemplo_da_especificacao():
    """Atividade só com o item 7.2, rendimento 90%, 44 h em 5 dias (8,8 h/dia), equipe padrão 2."""
    ajust = {"Pedreiro": 387.72 / 0.9, "Servente": 193.86 / 0.9}
    assert ajust["Pedreiro"] == pytest.approx(430.80) and ajust["Servente"] == pytest.approx(215.40)
    r = calcular_duracao(ajust, {}, 2, 44 / 5)
    assert r["funcao_principal"] == "Pedreiro"
    assert r["equipe"] == {"Pedreiro": 2, "Servente": 1}
    assert r["dias_por_funcao"] == {"Pedreiro": pytest.approx(24.48), "Servente": pytest.approx(24.48)}
    assert r["dias"] == 25


def test_formula_rendimento_100():
    r = calcular_duracao({"Pedreiro": 387.72, "Servente": 193.86}, {}, 2, 8.8)
    assert r["dias"] == 23  # teto(387,72 ÷ 17,6)


def test_formula_equipe_e_equipamento():
    r = calcular_duracao({"Servente": 100, "Pedreiro": 30}, {"Retroescavadeira": 200}, 3, 8.8)
    assert r["equipe"] == {"Servente": 3, "Pedreiro": 1}  # teto(3 × 30/100) = 1
    assert r["limitante"] == "equipamento"
    assert r["dias"] == 23  # 200 ÷ 8,8 = 22,7
    assert calcular_duracao({}, {}, 2, 8.8) is None
    assert calcular_duracao({"Pedreiro": 17.6}, {}, 2, 8.8)["dias"] == 1  # exatamente 1, sem ruído


def test_semanas_do_prazo():
    assert semanas_do_prazo(12, "meses") == pytest.approx(51.96)
    assert semanas_do_prazo(70, "dias") == pytest.approx(10)
    assert semanas_do_prazo(None, "meses") is None


# ------------------------------------------------------------------ obra inteira (sem banco)


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


def _calc(obra_teste, execucao=None, parametros=None):
    servicos, analises, atividades, ex = obra_teste
    return calcular_obra(servicos, copy.deepcopy(analises), atividades, execucao or ex, parametros or {}, (12, "meses"))


def _ativ(res, cod):
    return next(a for a in res["atividades"] if a["codigo"] == cod)


def test_est03_duracao_fixa(obra_teste):
    a = _ativ(_calc(obra_teste), "EST-03")
    assert a["duracao"] == {"dias": 21, "unidade": "corridos", "tipo": "fixa"}


def test_terceirizada_sem_horas_e_pendencia_ate_duracao_manual(obra_teste):
    res = _calc(obra_teste)
    met = _ativ(res, "MET-01")
    assert met["execucao"] == "terceirizada" and met["horas_brutas"] == {} and met["duracao"] is None
    assert any(p["atividade"] == "MET-01" and p["tipo"] == "duracao" for p in res["pendencias"])
    ex = copy.deepcopy(obra_teste[3])
    ex["MET-01"]["duracao_manual"] = 40
    res2 = _calc(obra_teste, ex)
    assert _ativ(res2, "MET-01")["duracao"] == {"dias": 40, "unidade": "uteis", "tipo": "manual"}
    assert not any(p["atividade"] == "MET-01" for p in res2["pendencias"])


def test_execucao_sem_resposta_e_pendencia(obra_teste):
    ex = copy.deepcopy(obra_teste[3])
    ex["ELE-04"]["execucao"] = None
    res = _calc(obra_teste, ex)
    assert any(p["atividade"] == "ELE-04" and p["tipo"] == "execucao" for p in res["pendencias"])


def test_4_11_recebe_horas_estimadas(obra_teste):
    servicos, analises, atividades, ex = obra_teste
    analises = copy.deepcopy(analises)
    calcular_obra(servicos, analises, atividades, ex, {}, (12, "meses"))
    s411 = next(s for s in servicos if s["item"] == "4.11")
    a = analises[s411["id"]]
    assert a["origem"] == "estimado"
    estimadas = [h for h in a["horas"] if h["origem"] == "estimado"]
    assert estimadas and sum(h["horas_un"] for h in estimadas) > 0
    assert a["estimativa"]["horas"] > 0
    assert a["pendentes"][0]["horas_estimadas"] > 0


def test_estimativa_nao_vale_para_indireta_nem_terceirizada_sem_horas(obra_teste):
    servicos, analises, atividades, ex = obra_teste
    analises = copy.deepcopy(analises)
    calcular_obra(servicos, analises, atividades, ex, {}, (12, "meses"))
    for s in servicos:
        if s["atividade_biblioteca"] in ("MET-01", "QUA-03", "IND-01", "IND-04"):
            assert not any(h["origem"] == "estimado" for h in analises[s["id"]]["horas"]), s["item"]


def test_terceirizar_tira_do_resumo_mas_nao_muda_duracao(obra_teste):
    base = _calc(obra_teste)
    ex = copy.deepcopy(obra_teste[3])
    ex["ELE-04"]["execucao"] = "terceirizada"  # ELE-04 é "perguntar" na biblioteca
    terc = _calc(obra_teste, ex)
    h_base = {f["funcao"]: f["horas_ajustadas"] for f in base["resumo_funcoes"]}
    h_terc = {f["funcao"]: f["horas_ajustadas"] for f in terc["resumo_funcoes"]}
    ele04 = _ativ(base, "ELE-04")["horas_ajustadas"]
    for funcao, h in ele04.items():
        assert h_terc.get(funcao, 0) == pytest.approx(h_base[funcao] - h, abs=0.05)
    assert _ativ(terc, "ELE-04")["duracao"] == _ativ(base, "ELE-04")["duracao"]


def test_rendimento_e_equipe_por_atividade(obra_teste):
    base = _ativ(_calc(obra_teste), "ALV-02")
    ex = copy.deepcopy(obra_teste[3])
    ex["ALV-02"].update(rendimento=1.0, equipe_padrao=4)
    novo = _ativ(_calc(obra_teste, ex), "ALV-02")
    assert novo["rendimento"] == 1.0 and novo["equipe_padrao"] == 4
    assert sum(novo["horas_ajustadas"].values()) == pytest.approx(sum(base["horas_brutas"].values()), abs=0.1)
    assert novo["duracao"]["dias"] < base["duracao"]["dias"]


def test_resumo_da_obra(obra_teste):
    res = _calc(obra_teste)
    assert res["parametros"]["horas_por_dia"] == pytest.approx(8.8)
    assert res["semanas_prazo"] == pytest.approx(51.96)
    serv = next(f for f in res["resumo_funcoes"] if f["funcao"] == "Servente")
    assert serv["media_pessoas"] == pytest.approx(serv["horas_ajustadas"] / (51.96 * 44), abs=0.01)
    assert sum(c["percentual"] for c in res["cobertura"].values()) == pytest.approx(100, abs=0.05)
    assert res["cobertura"]["composicao"]["percentual"] > 50
    assert all(a["tipo"] != "indireta" for a in res["atividades"])
    assert len(res["atividades"]) == 74


def test_seis_dias_por_semana(obra_teste):
    res = _calc(obra_teste, parametros={"horas_semana": 44, "dias_semana": 6})
    assert res["parametros"]["horas_por_dia"] == pytest.approx(44 / 6, abs=1e-4)
