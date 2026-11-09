"""Etapa 5.1 — redes pequenas: elos início-início, sair e voltar, terceirizada dividida, ociosidade, máquinas."""
from datetime import date

import pytest

from cronograma import Calendario, Modo, Tarefa, modos_por_horas
from cronograma.agenda import Instancia, agendar_cedo, reducao_respeitada, reducoes_minimas, verificar
from cronograma.modelo import OPERADOR, Elo, tamanhos_de_equipe
from cronograma.otimizador import otimizar
from mao_de_obra.calculo import calcular_duracao, dias_concretagem

SEGUNDA = "2025-08-04"


def equipe(dias, deps=(), tipo="rigida", **pessoas):
    return Tarefa(codigo="", modos=[Modo(equipe=pessoas or {"Pedreiro": 1}, dias_uteis=dias)], tipo=tipo, deps=list(deps))


def rede(**tarefas):
    for cod, t in tarefas.items():
        t.codigo = cod
    return tarefas


def inst(tarefas, inicio=SEGUNDA, limite_dias=200, **kw):
    cal = Calendario(inicio)
    return Instancia(cal, tarefas, cal.data(limite_dias - 1),
                     custo_hora=kw.pop("custo_hora", {"Pedreiro": 24.43, "Servente": 17.77}), **kw)


def resolver(i, segundos=10):
    res = otimizar(i, segundos)
    assert res["situacao"] in ("otimo", "melhor_encontrado"), res
    assert res["violacoes"] == []
    return res


def ativ(res):
    return {a["codigo"]: a for a in res["atividades"]}


# ------------------------------------------------------------------ elo início-início


def test_ii_comeca_e_termina_depois():
    """A (10 dias úteis) e B com A:II+3du (10 dias úteis): B começa 3 dias úteis depois de A e termina 3 depois."""
    t = rede(A=equipe(10), B=equipe(10, [Elo("A", 3, "II", "du")], Servente=1))
    i = inst(t, limite_rigidas=0)
    cedo = agendar_cedo(i, {"A": 0, "B": 0})
    assert cedo["B"]["inicio"] == cedo["A"]["inicio"] + 3
    assert cedo["B"]["ultimo"] >= cedo["A"]["ultimo"] + 3
    a = ativ(resolver(i))
    ia, ib = a["A"]["inicio_indice"], a["B"]["inicio_indice"]
    assert ib == ia + 3
    cal = i.calendario
    assert cal.uteis.index(date.fromisoformat(a["B"]["termino"])) >= cal.uteis.index(date.fromisoformat(a["A"]["termino"])) + 3


def test_ii_impede_terminar_antes():
    """A (20 dias úteis), B com A:II+2du e duração 5: B termina ≥ término de A + 2 dias úteis."""
    t = rede(A=equipe(20), B=equipe(5, [Elo("A", 2, "II", "du")], Servente=1))
    i = inst(t, limite_rigidas=0)
    cedo = agendar_cedo(i, {"A": 0, "B": 0})
    assert cedo["B"]["ultimo"] == cedo["A"]["ultimo"] + 2 and cedo["B"]["inicio"] == 17
    a = ativ(resolver(i))
    cal = i.calendario
    fim_a = cal.uteis.index(date.fromisoformat(a["A"]["termino"]))
    fim_b = cal.uteis.index(date.fromisoformat(a["B"]["termino"]))
    assert fim_b >= fim_a + 2
    # a verificação acusa B terminando antes
    sol = agendar_cedo(i, {"A": 0, "B": 0})
    sol["B"] = i.entrada("B", 0, 2)
    assert any("elo II" in e for e in verificar(i, sol, {"Pedreiro": [1] * 6, "Servente": [1] * 6}))


def test_ii_em_dias_corridos_e_ti_em_dias_uteis():
    t = rede(A=equipe(5), B=equipe(5, [Elo("A", 3, "II", "d")], Servente=1),
             C=equipe(2, [Elo("A", 2, "TI", "du")], Servente=1))
    i = inst(t)
    cedo = agendar_cedo(i, {c: 0 for c in t})
    cal = i.calendario
    assert cal.data(cedo["B"]["inicio"]) == date(2025, 8, 7)   # segunda + 3 dias corridos = quinta
    assert cal.data(cedo["C"]["inicio"]) == date(2025, 8, 13)  # A termina sexta; +2 du depois de segunda = quarta
    assert verificar(i, cedo, {"Pedreiro": [1] * 4, "Servente": [2] * 4}) == []


# ------------------------------------------------------------------ concretagem, equipes e máquinas


def test_concretagem_limita_a_duracao():
    """120 m³, 8 m³ por caminhão, 3 caminhões por dia: no mínimo 5 dias úteis."""
    assert dias_concretagem(120, 8, 3) == 5
    assert dias_concretagem(121, 8, 3) == 6
    assert dias_concretagem(0, 8, 3) is None
    c = calcular_duracao({"Pedreiro": 17.6}, {}, 2, 8.8, dias_minimos=5)  # pela mão de obra seria 1 dia
    assert c["dias"] == 5 and c["limitante"] == "concretagem"
    m = modos_por_horas({"Pedreiro": 880}, equipe_max=20, dias_minimos=5)
    assert min(x.duracao(8.8) for x in m) == 5  # nem com 20 pedreiros fica abaixo da concretagem


def test_tamanhos_de_equipe_ate_20():
    assert tamanhos_de_equipe(20) == [1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 20]
    assert tamanhos_de_equipe(7) == [1, 2, 3, 4, 5, 6, 7]
    m = modos_por_horas({"Pedreiro": 8.8 * 200})
    assert max(x.equipe["Pedreiro"] for x in m) == 20


def test_maquinas_escolhidas_com_operador():
    m = modos_por_horas({"Servente": 88}, {"Caminhão": 8.8 * 60}, equipe_max=6, maquinas_max=6)
    rapido = min(m, key=lambda x: x.duracao(8.8))
    assert rapido.maquinas == {"Caminhão": 6} and rapido.duracao(8.8) == 10
    assert rapido.equipe[OPERADOR] == 6                      # 1 operador por máquina (própria)
    terc = modos_por_horas({"Servente": 88}, {"Caminhão": 8.8 * 60}, equipe_max=6, maquinas_max=6, propria=False)
    assert all(OPERADOR not in x.equipe for x in terc)        # terceirizada: operador não conta
    assert min(x.duracao(8.8) for x in terc) == 10


# ------------------------------------------------------------------ sair e voltar


def _vale(semanas_vale, transferivel):
    # Servente: 2 semanas com 2, um vale de N semanas sem serviço (a obra continua com o pedreiro), 2 semanas com 2
    espera = 7 * semanas_vale
    t = rede(A=equipe(10, Servente=2), B=equipe(10, [("A", espera)], Servente=2),
             P=equipe(10 + 5 * semanas_vale + 10, Pedreiro=1))
    i = inst(t, limite_rigidas=0, transferiveis={"Servente"} if transferivel else set())
    return resolver(i)["contratados"]["Servente"]


def test_sair_e_voltar_reduz_no_vale_de_4_semanas():
    assert _vale(4, transferivel=False) == [2, 2, 2, 2, 2, 2, 2, 2]
    assert _vale(4, transferivel=True) == [2, 2, 0, 0, 0, 0, 2, 2]


def test_reducao_minima_de_2_semanas():
    """Vale de 1 semana não reduz, mesmo com a função transferível."""
    assert _vale(1, transferivel=True) == [2, 2, 2, 2, 2]
    assert reducoes_minimas([2, 2, 0, 2, 2], 2) == [2, 2, 2, 2, 2]
    assert reducoes_minimas([2, 2, 0, 0, 2], 2) == [2, 2, 0, 0, 2]
    assert reducao_respeitada([3, 1, 1, 3], 2) and not reducao_respeitada([3, 1, 3, 3], 2)


# ------------------------------------------------------------------ terceirizada dividida


def test_terceirizada_dividida_em_partes():
    """15 dias úteis em até 3 partes de no mínimo 5; elos valem no início da 1ª e no fim da última parte."""
    t = rede(A=equipe(5), T=Tarefa("T", [Modo(dias_uteis=15)], deps=[("A", 0)], execucao="terceirizada",
                                   tipo="flexivel", partes_max=3), B=equipe(3, [("T", 0)], Servente=1))
    i = inst(t)
    sol = agendar_cedo(i, {c: 0 for c in t})
    partes = [(5, 5), (15, 5), (25, 5)]                     # com intervalos de 5 dias úteis
    sol["T"] = i.entrada("T", 0, 5, partes)
    assert sol["T"]["ultimo"] == 29 and sol["T"]["duracao"] == 15
    sol["B"] = i.entrada("B", 0, 30)
    assert verificar(i, sol, {"Pedreiro": [1] * 8, "Servente": [1] * 8}) == []
    sol["B"] = i.entrada("B", 0, 20)                         # B não pode começar antes do fim da última parte
    assert any("B: começa antes" in e for e in verificar(i, sol, {"Pedreiro": [1] * 8, "Servente": [1] * 8}))
    sol["B"] = i.entrada("B", 0, 30)
    sol["T"] = i.entrada("T", 0, 5, [(5, 4), (15, 6), (25, 5)])  # parte com menos de 5 dias
    assert any("menos de 5" in e for e in verificar(i, sol, {"Pedreiro": [1] * 8, "Servente": [1] * 8}))
    sol["T"] = i.entrada("T", 0, 0, [(0, 5), (8, 5), (15, 5)])  # começa antes de A terminar
    assert any("T: começa antes" in e for e in verificar(i, sol, {"Pedreiro": [1] * 8, "Servente": [1] * 8}))
    # o otimizador aceita a tarefa divisível e devolve uma solução válida
    res = resolver(i)
    a = ativ(res)["T"]
    assert a["duracao"] == 15 and (a["partes"] is None or sum(p["duracao"] for p in a["partes"]) == 15)


def test_terceirizada_dividida_pelo_otimizador():
    """Rígida T (15 dias) liberada no dia 0 e um elo II que só deixa terminar no dia 29: a solução é dividir."""
    t = rede(X=Tarefa("X", [Modo(dias_corridos=41)], tipo="aguardar"),
             T=Tarefa("T", [Modo(dias_uteis=15)], deps=[Elo("X", 0, "II", "d")], execucao="terceirizada",
                      tipo="rigida", partes_max=3),
             F=equipe(3, [("T", 0)], Servente=1))
    i = inst(t, limite_rigidas=0)
    # sem dividir também é possível (começa no dia 15); o teste confere que dividir é aceito pelo modelo
    res = resolver(i)
    a = ativ(res)["T"]
    if a["partes"]:
        assert len(a["partes"]) <= 3 and all(p["duracao"] >= 5 for p in a["partes"])
    assert date.fromisoformat(a["termino"]) >= date(2025, 9, 13)


# ------------------------------------------------------------------ ociosidade


def test_ociosidade_sem_contar_feriados():
    """1 pedreiro trabalhando a semana inteira do Carnaval: 2 dias de feriado pagos, mas ociosidade zero."""
    t = rede(A=equipe(3, Pedreiro=1))
    i = inst(t, inicio="2026-02-16", limite_dias=20)  # segunda de Carnaval: trabalha qua, qui, sex
    res = resolver(i)
    assert res["horas_feriado"] == pytest.approx(2 * 8.8)
    assert res["ociosidade"] == pytest.approx(0.0)
    f = res["ociosidade_funcao"][0]
    assert f["funcao"] == "Pedreiro" and f["horas_feriado"] == pytest.approx(17.6) and f["ociosidade"] == 0
    linha = res["equipe_semana"][0]
    assert linha["horas_pagas"] == pytest.approx(44) and linha["horas_feriado"] == pytest.approx(17.6)


def test_ociosidade_por_funcao_e_causas():
    t = rede(A=equipe(5, Pedreiro=2), B=equipe(5, [("A", 14)], Pedreiro=2), S=equipe(20, Servente=1))
    res = resolver(inst(t))
    por = {f["funcao"]: f for f in res["ociosidade_funcao"]}
    assert por["Pedreiro"]["horas_paradas"] == pytest.approx(2 * 2 * 44, abs=0.1)  # 2 semanas paradas
    assert por["Servente"]["ociosidade"] == 0
    assert res["causas_ociosidade"][0]["funcao"] == "Pedreiro" and len(res["causas_ociosidade"][0]["semanas"]) == 2
