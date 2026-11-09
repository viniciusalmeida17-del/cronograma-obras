"""Etapa 5 — redes pequenas de teste, com resultado conhecido."""
from datetime import date

import pytest

from cronograma import Calendario, Modo, Tarefa, data_limite, feriados_nacionais, modos_por_horas, pascoa
from cronograma.agenda import (
    Instancia,
    agendar_cedo,
    envelope_sobe_desce,
    ocupacao_diaria,
    verificar,
)
from cronograma.otimizador import IMPOSSIVEL, otimizar

SEGUNDA = "2025-08-04"  # segunda-feira sem feriado por perto
VALIDAS = ("otimo", "melhor_encontrado")


def equipe(dias, deps=(), tipo="rigida", **pessoas):
    return Tarefa(codigo="", modos=[Modo(equipe=pessoas or {"Pedreiro": 1}, dias_uteis=dias)], tipo=tipo,
                  deps=list(deps))


def rede(**tarefas):
    for cod, t in tarefas.items():
        t.codigo = cod
    return tarefas


def inst(tarefas, inicio=SEGUNDA, limite_dias=200, cal=None, **kw):
    cal = cal or Calendario(inicio)
    return Instancia(cal, tarefas, cal.data(limite_dias - 1), custo_hora=kw.pop("custo_hora", {"Pedreiro": 24.43,
                                                                                               "Servente": 17.77}), **kw)


def resolver(i, segundos=10):
    res = otimizar(i, segundos)
    assert res["situacao"] in VALIDAS, res
    assert res["violacoes"] == []
    return res


def por_codigo(res):
    return {a["codigo"]: a for a in res["atividades"]}


# ------------------------------------------------------------------ calendário


def test_feriados_moveis_e_fixos():
    assert pascoa(2025) == date(2025, 4, 20)
    assert pascoa(2026) == date(2026, 4, 5)
    f = feriados_nacionais(2026)
    assert f[date(2026, 2, 16)] == "Carnaval (segunda)" and f[date(2026, 2, 17)] == "Carnaval (terça)"
    assert f[date(2026, 4, 3)] == "Sexta-feira Santa"
    assert f[date(2026, 6, 4)] == "Corpus Christi"
    assert date(2026, 4, 21) in f and date(2026, 11, 20) in f and date(2026, 12, 25) in f


def test_feriado_local_e_sabado():
    cal = Calendario("2025-08-04", feriados_locais=[{"data": "2025-08-06", "nome": "Aniversário da cidade"}])
    assert [d.isoformat() for d in cal.uteis[:4]] == ["2025-08-04", "2025-08-05", "2025-08-07", "2025-08-08"]
    cal6 = Calendario("2025-08-04", dias_semana=6)
    assert cal6.uteis[5] == date(2025, 8, 9)  # sábado
    assert cal6.horas_dia(0) == pytest.approx(44 / 6)


def test_data_limite():
    assert data_limite(date(2025, 3, 3), 12) == date(2026, 3, 2)
    assert data_limite(date(2025, 1, 31), 1) == date(2025, 2, 27)


# ------------------------------------------------------------------ casos da especificação


def test_dependencia_com_espera():
    """A (5 dias úteis, começa segunda) → B com A+3d: B começa no 1º dia útil depois de 3 dias corridos do fim de A."""
    t = rede(A=equipe(5), B=equipe(3, [("A", 3)]))
    i = inst(t, limite_rigidas=0)
    cedo = agendar_cedo(i, {"A": 0, "B": 0})
    cal = i.calendario
    assert cal.data_do_offset(cedo["A"]["fim"]) == date(2025, 8, 8)       # sexta
    assert cal.data(cedo["B"]["inicio"]) == date(2025, 8, 12)              # sáb, dom, seg passam → terça
    res = por_codigo(resolver(i))
    assert res["A"]["inicio"] == "2025-08-04" and res["B"]["inicio"] == "2025-08-12"


def test_espera_zero_comeca_no_proximo_dia_util():
    t = rede(A=equipe(5), B=equipe(2, [("A", 0)]))
    cedo = agendar_cedo(inst(t), {"A": 0, "B": 0})
    assert Calendario(SEGUNDA).data(cedo["B"]["inicio"]) == date(2025, 8, 11)


def test_feriado_de_carnaval_atrasa_dois_dias_uteis():
    """5 dias úteis começando na quinta antes do Carnaval de 2026 terminam 2 dias úteis depois do normal."""
    t = rede(A=equipe(5))
    i = inst(t, inicio="2026-02-12")
    a = agendar_cedo(i, {"A": 0})["A"]
    assert i.calendario.data_do_offset(a["fim"]) == date(2026, 2, 20)   # qui, sex, (seg e ter de Carnaval), qua, qui, sex
    sem_feriado = inst(rede(A=equipe(5)), inicio="2026-03-05")          # mesma quinta-feira, sem feriado
    b = agendar_cedo(sem_feriado, {"A": 0})["A"]
    assert sem_feriado.calendario.data_do_offset(b["fim"]) == date(2026, 3, 11)  # quarta
    # dois dias úteis a mais: sexta em vez de quarta
    assert (date(2026, 2, 20) - date(2026, 2, 12)).days - (date(2026, 3, 11) - date(2026, 3, 5)).days == 2


def test_rigida_comeca_ate_5_dias_uteis_depois_de_liberada():
    """B rígida liberada no dia 10 começa entre o dia 10 e o dia 15; o otimizador tem motivo para atrasá-la."""
    # C ocupa 1 pedreiro dos dias 0 a 16; B também usa pedreiro: deixar B para depois de C evita contratar 2.
    t = rede(A=equipe(10, Servente=1), B=equipe(3, [("A", 0)], Pedreiro=1), C=equipe(17, Pedreiro=1))
    i = inst(t, limite_rigidas=5)
    res = resolver(i)
    a = por_codigo(res)
    liberada = a["A"]["inicio_indice"] + 10                       # dia útil seguinte ao término de A
    assert liberada <= a["B"]["inicio_indice"] <= liberada + 5
    i.tarefas["A"].tipo = "aguardar"                                # A começa no dia 0 → B liberada no dia 10
    ini_b = por_codigo(resolver(i))["B"]["inicio_indice"]
    assert 10 <= ini_b <= 15
    # sem o limite (flexível), o otimizador empurra B para depois de C (dia 17)
    i.tarefas["B"].tipo = "flexivel"
    ini_flex = Calendario(SEGUNDA).uteis.index(date.fromisoformat(por_codigo(resolver(i))["B"]["inicio"]))
    assert ini_flex >= 17
    # a verificação acusa uma rígida que começa 6 dias úteis depois da liberação
    i.tarefas["B"].tipo = "rigida"
    i.tarefas["A"].tipo = "rigida"
    sol = agendar_cedo(i, {c: 0 for c in t})
    sol["B"] = i.entrada("B", 0, 16)
    erros = verificar(i, sol, {"Pedreiro": [5] * 10, "Servente": [5] * 10})
    assert any("B: rígida começa 6 dias úteis" in e for e in erros)


def test_flexivel_vai_para_o_vale():
    """A (2 pedreiros) → M (1 pedreiro) → B (2 pedreiros), rígidas; F flexível de 1 pedreiro com janela larga."""
    t = rede(A=equipe(5, Pedreiro=2), M=equipe(5, [("A", 0)], Pedreiro=1), B=equipe(5, [("M", 0)], Pedreiro=2),
             F=equipe(5, tipo="flexivel", Pedreiro=1))
    i = inst(t, limite_rigidas=0)
    res = resolver(i)
    a = por_codigo(res)
    assert a["F"]["inicio"] == a["M"]["inicio"] and a["F"]["termino"] == a["M"]["termino"]
    assert max(res["contratados"]["Pedreiro"]) == 2          # sem aumentar o pico
    assert res["contratados"]["Pedreiro"] == [2, 2, 2]
    assert res["ociosidade"] == pytest.approx(0.0)


def test_sobe_e_desce_sem_vale():
    """Duas atividades de 2 pedreiros separadas por uma espera de 28 dias: a equipe não é demitida e recontratada."""
    t = rede(A=equipe(5, Pedreiro=2), B=equipe(5, [("A", 28)], Pedreiro=2), S=equipe(3, Servente=1))
    res = resolver(inst(t))
    serie = res["contratados"]["Pedreiro"]
    assert serie == envelope_sobe_desce(serie)
    assert min(serie[serie.index(2):len(serie) - serie[::-1].index(2)]) == 2  # fica 2 no intervalo
    assert res["ociosidade"] > 0


@pytest.mark.parametrize("serie, valida", [([0, 2, 3, 3, 1, 0], True), ([2, 2, 1, 2], False), ([1, 0, 1], False),
                                           ([0, 0, 4, 4], True)])
def test_verificacao_do_sobe_e_desce(serie, valida):
    t = rede(A=equipe(1, Pedreiro=1))
    i = inst(t)
    sol = agendar_cedo(i, {"A": 0})
    erros = verificar(i, sol, {"Pedreiro": serie})
    assert (not any("diminuem e depois aumentam" in e for e in erros)) is valida


def test_capacidade_em_todo_dia_util():
    t = rede(A=equipe(7, Pedreiro=2, Servente=1), B=equipe(4, tipo="flexivel", Pedreiro=1),
             C=equipe(6, [("A", 0)], Pedreiro=1, Servente=2), D=equipe(3, [("B", 2)], tipo="flexivel", Servente=1))
    i = inst(t)
    res = resolver(i)
    cal = i.calendario
    sol = {a["codigo"]: {"inicio": a["inicio_indice"], "modo": a["modo"], "duracao": a["duracao"],
                         "fim": cal.offset_de(date.fromisoformat(a["termino"]))} for a in res["atividades"]}
    for f, dias in ocupacao_diaria(i, sol).items():
        for dia, q in dias.items():
            assert q <= res["contratados"][f][cal.semana(dia)]


def test_terceirizada_fora_da_equipe_por_semana():
    t = rede(A=equipe(5, Pedreiro=1), T=Tarefa("T", [Modo(dias_uteis=8)], deps=[("A", 0)], execucao="terceirizada"))
    res = resolver(inst(t))
    a = por_codigo(res)
    assert a["T"]["equipe"] == {} and a["T"]["duracao"] == 8
    assert {e["funcao"] for e in res["equipe_semana"]} == {"Pedreiro"}
    # o pedreiro não fica contratado durante a terceirizada (ela não usa a equipe própria)
    assert res["contratados"]["Pedreiro"] == [1, 0, 0]


def test_prazo_impossivel_informa_o_menor_prazo():
    """Caminho crítico mínimo de 30 dias úteis com prazo de 20: impossível, informando os 30 dias."""
    t = rede(A=equipe(10), B=equipe(12, [("A", 0)]), C=equipe(8, [("B", 0)]), D=equipe(3, tipo="flexivel"))
    res = otimizar(inst(t, limite_dias=20), 5)
    assert res["situacao"] == IMPOSSIVEL
    assert res["menor_prazo"]["dias_uteis"] == 30
    assert res["menor_prazo"]["caminho_critico"] == ["A", "B", "C"]
    assert resolver(inst(t, limite_dias=30))["dias_uteis"] == 30


def test_menor_prazo_usa_a_equipe_maxima():
    modos = modos_por_horas({"Pedreiro": 88 * 6}, equipe_max=6)
    t = rede(A=Tarefa("A", modos))
    res = otimizar(inst(t, limite_dias=5), 5)
    assert res["situacao"] == IMPOSSIVEL and res["menor_prazo"]["dias_uteis"] == 10  # 528 h ÷ (6 × 8,8 h)


def test_jornada_menor_aumenta_a_duracao():
    """44 h até uma data e 40 h depois: a mesma atividade dura mais quando começa depois da mudança."""
    cal = Calendario(SEGUNDA, horas_semana=44, mudancas_jornada=[{"a_partir_de": "2025-09-01", "horas_semana": 40}])
    t = rede(X=Tarefa("X", modos_por_horas({"Pedreiro": 88}, equipe_max=1, jornadas=cal.jornadas())))
    i = inst(t, cal=cal)
    antes = 0
    depois = cal.uteis.index(date(2025, 9, 1))
    assert i.duracao("X", 0, antes) == 10    # 88 h ÷ 8,8 h/dia
    assert i.duracao("X", 0, depois) == 11   # 88 h ÷ 8 h/dia
    # numa rede, com uma antecessora que empurra X para depois da mudança
    t2 = rede(P=equipe(20, Servente=1), X=Tarefa("X", modos_por_horas({"Pedreiro": 88}, equipe_max=1, jornadas=cal.jornadas()),
                                                 deps=[("P", 0)]))
    res = resolver(inst(t2, cal=cal))
    assert por_codigo(res)["X"]["duracao"] == 11
    pag = {e["semana"]: e["horas_pagas"] for e in res["equipe_semana"] if e["funcao"] == "Pedreiro"}
    assert set(pag.values()) == {40.0}  # semana de 40 h paga 40 h por pessoa


def test_equipe_travada_usa_sempre_o_mesmo_tamanho():
    horas = {"Armador": 264, "Servente": 132}
    livres = modos_por_horas(horas, equipe_max=6)
    assert len(livres) > 1
    travada = modos_por_horas(horas, equipe_max=6, travada=3)
    assert len(travada) == 1 and travada[0].equipe == {"Armador": 3, "Servente": 2}
    t = rede(F=Tarefa("F", travada, travada=3), G=equipe(4, [("F", 0)], Pedreiro=1))
    res = resolver(inst(t, limite_dias=60))
    assert por_codigo(res)["F"]["equipe"]["Armador"] == 3
    assert max(res["contratados"]["Armador"]) == 3


def test_modos_sem_ganho_de_prazo_sao_retirados():
    # equipamento limita: mais gente não encurta
    m = modos_por_horas({"Servente": 10}, {"Caminhão": 88}, equipe_max=6)
    assert len(m) == 1


def test_aguardar_comeca_assim_que_liberada():
    t = rede(A=equipe(5, Pedreiro=1), CURA=Tarefa("CURA", [Modo(dias_corridos=7)], tipo="aguardar", deps=[("A", 0)]),
             B=equipe(2, [("CURA", 0)], Pedreiro=1))
    a = por_codigo(resolver(inst(t)))
    assert a["CURA"]["inicio"] == "2025-08-11" and a["CURA"]["termino"] == "2025-08-17"  # 7 dias corridos
    assert a["B"]["inicio"] == "2025-08-18"
    assert a["CURA"]["unidade"] == "corridos"


def test_maximo_de_pessoas_por_funcao():
    t = rede(A=Tarefa("A", modos_por_horas({"Pedreiro": 8.8 * 30}, equipe_max=6)))
    livre = resolver(inst(t, limite_dias=10))
    assert max(livre["contratados"]["Pedreiro"]) >= 3
    limitado = otimizar(inst(t, limite_dias=10, max_por_funcao={"Pedreiro": 2}), 5)
    assert limitado["situacao"] == IMPOSSIVEL  # 30 dias-pessoa em 10 dias com 2 pedreiros não cabe
    ok = resolver(inst(t, limite_dias=15, max_por_funcao={"Pedreiro": 2}))
    assert max(ok["contratados"]["Pedreiro"]) <= 2


def test_caminho_critico_e_folga():
    t = rede(A=equipe(5), B=equipe(10, [("A", 0)]), C=equipe(2, [("A", 0)], tipo="flexivel", Servente=1),
             FIM=equipe(1, [("B", 0), ("C", 0)]))
    i = inst(t, limite_rigidas=0)
    i.final = "FIM"
    res = resolver(i)
    a = por_codigo(res)
    assert res["caminho_critico"] == ["A", "B", "FIM"]
    assert a["A"]["critica"] and a["B"]["critica"] and not a["C"]["critica"]
    assert a["C"]["folga"] >= 8
