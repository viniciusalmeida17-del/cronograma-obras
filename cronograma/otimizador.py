"""Otimizador do cronograma com OR-Tools CP-SAT.

Variáveis: início (dia útil) e modo de cada tarefa; contratados C[f][s] de cada função em cada semana.
Restrições: dependências com espera (em dias corridos), rígidas até `limite_rigidas` dias úteis depois de
liberadas, capacidade diária ≤ C da semana, C sobe até um pico e depois só desce, prazo, máximos opcionais.
Objetivo: mão de obra própria paga (C × horas × custo/h) + indiretos que variam com o prazo + desempate
por terminar mais cedo.
"""
from __future__ import annotations

import os
import threading
import time
from typing import Any, Callable

from .agenda import (
    DIAS_POR_MES,
    Instancia,
    agendar_cedo,
    agendar_no_prazo,  # noqa: F401
    busca_local,
    caminho_critico,
    contratados_minimos,
    horas_pagas_semana,
    resumir,
    verificar,
)
from .modelo import AGUARDAR, RIGIDA

OTIMO = "otimo"
MELHOR = "melhor_encontrado"
IMPOSSIVEL = "impossivel"
SEM_SOLUCAO = "sem_solucao"
CENTAVOS = 100


def _cp():
    try:
        from ortools.sat.python import cp_model
    except ImportError as exc:  # pragma: no cover - depende da instalação
        raise RuntimeError(
            "O pacote ortools não está instalado. Rode: py -m pip install -r requirements.txt "
            "(o OR-Tools precisa de Python 3.10 a 3.14)."
        ) from exc
    return cp_model


def custo_da_solucao(inst: Instancia, resumo: dict[str, Any]) -> float:
    return resumo["custo_mao_de_obra"] + resumo["custo_indiretos"]


def avaliar(inst: Instancia, sol: dict[str, dict[str, Any]], contratados: dict[str, list[int]] | None = None
            ) -> dict[str, Any]:
    contratados = contratados or contratados_minimos(inst, sol)
    res = resumir(inst, sol, contratados)
    res["violacoes"] = verificar(inst, sol, contratados)
    return res


def menor_prazo(inst: Instancia) -> dict[str, Any]:
    """Término com todas as atividades o mais cedo possível e com a equipe máxima (caminho crítico mínimo)."""
    sol = agendar_cedo(inst, "rapido")
    cal = inst.calendario
    fim = inst.fim_da_obra(sol)
    return {
        "termino": cal.data_do_offset(fim).isoformat(),
        "dias_uteis": cal.ultimo_util_ate(fim) + 1,
        "dias_corridos": fim + 1,
        "meses": round((fim + 1) / DIAS_POR_MES, 2),
        "caminho_critico": caminho_critico(inst, sol),
        "solucao": sol,
    }


class _Progresso(object):
    def __init__(self) -> None:
        self.solucoes = 0
        self.melhor: float | None = None
        self.inicio = time.monotonic()


def otimizar(
    inst: Instancia,
    tempo_limite: float = 60.0,
    equipe_padrao: dict[str, int] | None = None,
    progresso: Callable[[dict[str, Any]], None] | None = None,
    parar: threading.Event | None = None,
    workers: int = 0,
) -> dict[str, Any]:
    """Resolve um cenário. Devolve o resumo da solução (ver `agenda.resumir`) com `situacao`."""
    cal = inst.calendario
    rapido = menor_prazo(inst)
    if rapido["solucao"] and inst.fim_da_obra(rapido["solucao"]) > inst.offset_limite:
        return {"situacao": IMPOSSIVEL, "menor_prazo": {k: v for k, v in rapido.items() if k != "solucao"},
                "mensagem": "Nem com a equipe máxima a obra termina na data limite."}

    # solução inicial: o mais cedo possível com a equipe padrão (se não couber, com a equipe máxima)
    inicial = busca_local(inst, equipe_padrao, min(15.0, max(3.0, 0.25 * tempo_limite)))
    if inst.fim_da_obra(inicial) > inst.offset_limite:
        inicial = rapido["solucao"]
    c_inicial = contratados_minimos(inst, inicial)
    av_inicial = avaliar(inst, inicial, c_inicial)
    inicial_valida = not av_inicial["violacoes"]

    cp_model = _cp()
    m = cp_model.CpModel()
    H = inst.horizonte
    off = cal.offset[:H]
    lim = inst.offset_limite
    n_semanas = cal.semana(H - 1) + 1
    max_espera = max((w for t in inst.tarefas.values() for _, w in t.deps), default=0)
    # primeiro dia útil com offset >= c, para c até além do limite (H = fora do horizonte)
    tam_tabela = lim + max_espera + 3
    idx_de_offset = [min(cal.indice_util(c), H) for c in range(tam_tabela)]
    jornadas_variam = len({cal.horas_dia(i) for i in range(H)}) > 1

    s, cs, fc, x = {}, {}, {}, {}
    intervalos: dict[str, list[tuple[Any, int]]] = {f: [] for f in inst.funcoes}
    for cod in inst.ordem:
        t = inst.tarefas[cod]
        s[cod] = m.NewIntVar(0, H - 1, f"s_{cod}")
        cs[cod] = m.NewIntVar(0, off[-1], f"cs_{cod}")
        m.AddElement(s[cod], off, cs[cod])
        fc[cod] = m.NewIntVar(0, lim, f"fc_{cod}")
        modos = t.modos
        x[cod] = [m.NewBoolVar(f"x_{cod}_{k}") for k in range(len(modos))]
        m.AddExactlyOne(x[cod])
        if modos[0].corridos:
            m.Add(fc[cod] == cs[cod] + modos[0].duracao(0) - 1)
            continue
        dur_modos = []
        for k, modo in enumerate(modos):
            if jornadas_variam:
                tabela = [modo.duracao(cal.horas_dia(i)) for i in range(H)]
                dk = m.NewIntVar(min(tabela), max(tabela), f"d_{cod}_{k}")
                m.AddElement(s[cod], tabela, dk)
                dur_modos.append((dk, min(tabela), max(tabela)))
            else:
                d = modo.duracao(cal.horas_dia(0))
                dur_modos.append((d, d, d))
        dmin = min(v[1] for v in dur_modos)
        dmax = max(v[2] for v in dur_modos)
        d_tar = m.NewIntVar(dmin, dmax, f"d_{cod}")
        for k, (dk, _, _) in enumerate(dur_modos):
            m.Add(d_tar == dk).OnlyEnforceIf(x[cod][k])
        e = m.NewIntVar(0, H - 1, f"e_{cod}")
        m.Add(e == s[cod] + d_tar - 1)
        m.AddElement(e, off, fc[cod])
        for k, modo in enumerate(modos):
            if not modo.equipe:
                continue
            dk, a, b = dur_modos[k]
            if isinstance(dk, int):
                iv = m.NewOptionalFixedSizeIntervalVar(s[cod], dk, x[cod][k], f"iv_{cod}_{k}")
            else:
                fim_k = m.NewIntVar(0, H - 1 + b, f"f_{cod}_{k}")
                iv = m.NewOptionalIntervalVar(s[cod], dk, fim_k, x[cod][k], f"iv_{cod}_{k}")
            for f, q in modo.equipe.items():
                intervalos[f].append((iv, q))
        # modos que estouram o máximo de pessoas ficam proibidos
        for k, modo in enumerate(modos):
            if any(inst.max_por_funcao.get(f) is not None and q > inst.max_por_funcao[f] for f, q in modo.equipe.items()) \
                    or (inst.max_total is not None and sum(modo.equipe.values()) > inst.max_total):
                m.Add(x[cod][k] == 0)

    # dependências, liberação e rígidas
    for cod in inst.ordem:
        t = inst.tarefas[cod]
        termos = []
        for a, w in t.deps:
            m.Add(cs[cod] >= fc[a] + w + 1)
            termos.append(fc[a] + w + 1)
        if t.tipo not in (RIGIDA, AGUARDAR):
            continue
        folga = 0 if t.tipo == AGUARDAR else inst.limite_rigidas
        if not termos:
            m.Add(s[cod] <= folga)
            continue
        r = m.NewIntVar(0, tam_tabela - 1, f"lib_{cod}")
        m.AddMaxEquality(r, termos)
        ri = m.NewIntVar(0, H, f"libi_{cod}")
        m.AddElement(r, idx_de_offset, ri)
        m.Add(s[cod] <= ri + folga)

    # contratados por semana, capacidade e sobe-e-desce
    semanas_ini = {}
    for i in range(H):
        semanas_ini.setdefault(cal.semana(i), [i, i])[1] = i
    C: dict[str, list[Any]] = {}
    custo_termos = []
    pagas = [horas_pagas_semana(inst, w) for w in range(n_semanas)]
    for f in inst.funcoes:
        soma = sum(q for _, q in intervalos[f])
        teto = soma if inst.max_por_funcao.get(f) is None else min(soma, inst.max_por_funcao[f])
        if inst.max_total is not None:
            teto = min(teto, inst.max_total)
        teto = max(teto, 1)
        C[f] = [m.NewIntVar(0, teto, f"C_{f}_{w}") for w in range(n_semanas)]
        demandas = [q for _, q in intervalos[f]]
        ivs = [iv for iv, _ in intervalos[f]]
        for w, (i0, i1) in semanas_ini.items():
            ivs.append(m.NewFixedSizeIntervalVar(i0, i1 - i0 + 1, f"cap_{f}_{w}"))
            demandas.append(teto - C[f][w])
        m.AddCumulative(ivs, demandas, teto)
        p = [m.NewBoolVar(f"p_{f}_{w}") for w in range(n_semanas - 1)]
        for w in range(n_semanas - 1):
            if w:
                m.AddImplication(p[w - 1], p[w])
            m.Add(C[f][w] <= C[f][w + 1]).OnlyEnforceIf(p[w].Not())
            m.Add(C[f][w] >= C[f][w + 1]).OnlyEnforceIf(p[w])
        custo_h = max(inst.custo_hora.get(f, 0.0), 0.01)
        for w in range(n_semanas):
            custo_termos.append(C[f][w] * round(CENTAVOS * pagas[w] * custo_h))
    if inst.max_total is not None and inst.funcoes:
        for w in range(n_semanas):
            m.Add(sum(C[f][w] for f in inst.funcoes) <= inst.max_total)

    # indiretos que variam com o prazo e desempate (terminar mais cedo)
    fim_obra = m.NewIntVar(0, lim, "fim_obra")
    m.AddMaxEquality(fim_obra, [fc[c] for c in inst.ordem])
    for it in inst.indiretos:
        if it.tipo == "fixo" or it.custo_mes <= 0:
            continue
        por_dia = round(CENTAVOS * it.custo_mes / DIAS_POR_MES)
        ini = 0 if it.de in (None, "INICIO_OBRA") or it.de not in cs else cs[it.de]
        fim = fim_obra if it.ate in (None, "FIM_OBRA") or it.ate not in fc else fc[it.ate]
        custo_termos.append(por_dia * (fim - ini + 1))
    custo_termos.append(fim_obra)
    m.Minimize(sum(custo_termos))

    # dica: a solução inicial
    if inicial_valida:
        for cod, a in inicial.items():
            m.AddHint(s[cod], a["inicio"])
            for k, xv in enumerate(x[cod]):
                m.AddHint(xv, 1 if k == a["modo"] else 0)
        for f in inst.funcoes:
            serie = c_inicial.get(f, [])
            for w in range(n_semanas):
                m.AddHint(C[f][w], serie[w] if w < len(serie) else 0)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(tempo_limite)
    solver.parameters.num_workers = workers or max(8, os.cpu_count() or 8)
    estado = _Progresso()

    class Retorno(cp_model.CpSolverSolutionCallback):
        def on_solution_callback(self_cb) -> None:  # noqa: N805
            estado.solucoes += 1
            estado.melhor = self_cb.ObjectiveValue() / CENTAVOS
            if progresso:
                progresso({"solucoes": estado.solucoes, "melhor": estado.melhor,
                           "segundos": round(time.monotonic() - estado.inicio, 1)})
            if parar is not None and parar.is_set():
                self_cb.StopSearch()

    status = solver.Solve(m, Retorno())
    segundos = round(time.monotonic() - estado.inicio, 2)

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        sol = {}
        for cod in inst.ordem:
            k = next(k for k, xv in enumerate(x[cod]) if solver.Value(xv))
            ini = solver.Value(s[cod])
            sol[cod] = {"inicio": ini, "modo": k, "duracao": inst.duracao(cod, k, ini), "fim": inst.termino(cod, k, ini)}
        contratados = {f: [solver.Value(v) for v in C[f]] for f in inst.funcoes}
        contratados = _cortar(contratados, inst, sol)
        res = avaliar(inst, sol, contratados)
        res["situacao"] = OTIMO if status == cp_model.OPTIMAL else MELHOR
        if inicial_valida and custo_da_solucao(inst, av_inicial) < custo_da_solucao(inst, res) - 0.01:
            res = av_inicial
            res["situacao"] = MELHOR
            res["origem"] = "solucao_inicial"
        else:
            res["origem"] = "otimizador"
    elif status == cp_model.INFEASIBLE:
        return {"situacao": IMPOSSIVEL, "menor_prazo": {k: v for k, v in rapido.items() if k != "solucao"},
                "segundos": segundos,
                "mensagem": "Não há cronograma que respeite todas as restrições (prazo, rígidas e máximos de pessoas)."}
    elif inicial_valida:
        res = av_inicial
        res["situacao"] = MELHOR
        res["origem"] = "solucao_inicial"
    else:
        return {"situacao": SEM_SOLUCAO, "segundos": segundos,
                "menor_prazo": {k: v for k, v in rapido.items() if k != "solucao"},
                "mensagem": "O otimizador não achou solução no tempo limite. Aumente o tempo limite."}
    res["segundos"] = segundos
    res["limite_inferior"] = round(solver.BestObjectiveBound() / CENTAVOS, 2) if status in (
        cp_model.OPTIMAL, cp_model.FEASIBLE) else None
    res["solucao"] = sol if res.get("origem") == "otimizador" else inicial
    res["menor_prazo"] = {k: v for k, v in rapido.items() if k != "solucao"}
    return res


def _cortar(contratados: dict[str, list[int]], inst: Instancia, sol: dict[str, dict[str, Any]]) -> dict[str, list[int]]:
    """Tira as semanas depois do término da obra (C é zero lá, mas não precisa aparecer)."""
    from .agenda import semanas_do_cronograma

    n = semanas_do_cronograma(inst, inst.fim_da_obra(sol))
    return {f: v[:n] for f, v in contratados.items()}
