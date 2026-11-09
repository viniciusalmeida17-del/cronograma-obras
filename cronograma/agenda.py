"""Instância do cronograma, solução inicial, caminho crítico, folgas, equipe por semana, custos e verificação.

Unidades:
- início das tarefas e "último dia útil" em índice de dia útil do calendário;
- término (`fim`) em dia corrido (offset desde a data de início), porque esperas `+Nd` e durações fixas
  (cura, testes) são em dias corridos.

Elos (B depende de A):
- TI +Nd:  B começa no 1º dia útil com offset ≥ término de A + N + 1 (A termina sexta, +3d → B na terça);
- TI +Ndu: B começa N dias úteis depois do dia útil seguinte ao término de A;
- II +Nd / +Ndu: B começa N dias (corridos/úteis) depois do início de A e não termina antes do término de A + N.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Mapping

from .calendario import Calendario
from .modelo import AGUARDAR, ATIVIDADE_FINAL, RIGIDA, Elo, Tarefa

DIAS_POR_MES = 30.4375
LIMITE_RIGIDAS = 5
MIN_SEMANAS_REDUCAO = 2


@dataclass
class ItemIndireto:
    """Custo (ou receita) que depende do prazo.

    tipo: "obra" (início ao fim da obra), "periodo" (entre atividades) ou "fixo" (não varia nesta versão).
    """
    descricao: str
    atividade: str | None
    tipo: str
    custo_mes: float = 0.0
    custo_total: float = 0.0
    de: str | None = None        # atividade (ou INICIO_OBRA)
    ate: str | None = None       # atividade (ou FIM_OBRA)
    unidade: str | None = None
    previsto_meses: float | None = None
    motivo: str | None = None


@dataclass
class Instancia:
    calendario: Calendario
    tarefas: dict[str, Tarefa]
    limite: date                                   # data limite (último dia do prazo)
    custo_hora: dict[str, float] = field(default_factory=dict)
    indiretos: list[ItemIndireto] = field(default_factory=list)      # custo real que varia com o prazo
    limite_rigidas: int = LIMITE_RIGIDAS
    max_por_funcao: dict[str, int] = field(default_factory=dict)
    max_total: int | None = None
    final: str = ATIVIDADE_FINAL
    transferiveis: set[str] = field(default_factory=set)            # funções que podem sair e voltar
    min_semanas_reducao: int = MIN_SEMANAS_REDUCAO
    custo_troca: float = 0.0                                        # R$ por pessoa que sai ou entra (transferíveis)
    receitas: list[ItemIndireto] = field(default_factory=list)      # receita com critério "mensal"

    def __post_init__(self) -> None:
        if self.final not in self.tarefas:
            self.final = None  # type: ignore[assignment]
        self.transferiveis = set(self.transferiveis or ())
        self.ordem = ordem_tarefas(self.tarefas)
        self.sucessores: dict[str, list[tuple[str, Elo]]] = defaultdict(list)
        for t in self.tarefas.values():
            for e in t.deps:
                self.sucessores[e.anterior].append((t.codigo, e))
        self.funcoes = sorted({f for t in self.tarefas.values() if t.propria for m in t.modos if not m.corridos
                               for f in m.equipe})
        cal = self.calendario
        self.offset_limite = cal.offset_de(self.limite)
        self.horizonte = max(1, cal.dias_uteis_ate(self.limite))  # dias úteis até a data limite

    # ------------------------------------------------------------------ durações e entradas da solução

    def duracao(self, codigo: str, modo: int, inicio: int) -> int:
        m = self.tarefas[codigo].modos[modo]
        return m.duracao(self.calendario.horas_dia(inicio))

    def entrada(self, codigo: str, modo: int, inicio: int, partes: list[tuple[int, int]] | None = None) -> dict[str, Any]:
        """Posição completa da tarefa: início, duração, último dia útil, término (offset) e partes."""
        m = self.tarefas[codigo].modos[modo]
        cal = self.calendario
        d = self.duracao(codigo, modo, inicio)
        if m.corridos:
            fim = cal.offset[inicio] + d - 1
            return {"inicio": inicio, "modo": modo, "duracao": d, "fim": fim, "ultimo": cal.ultimo_util_ate(fim)}
        if partes and len(partes) > 1:
            ultimo = partes[-1][0] + partes[-1][1] - 1
            return {"inicio": partes[0][0], "modo": modo, "duracao": d, "fim": cal.offset[ultimo], "ultimo": ultimo,
                    "partes": [tuple(p) for p in partes]}
        return {"inicio": inicio, "modo": modo, "duracao": d, "fim": cal.offset[inicio + d - 1], "ultimo": inicio + d - 1}

    def termino(self, codigo: str, modo: int, inicio: int) -> int:
        """Offset (dia corrido) do último dia da tarefa (sem divisão em partes)."""
        return self.entrada(codigo, modo, inicio)["fim"]

    def modo_mais_rapido(self, codigo: str, inicio: int) -> int:
        t = self.tarefas[codigo]
        return min(range(len(t.modos)), key=lambda k: (self.duracao(codigo, k, inicio), k))

    def modo_padrao(self, codigo: str, equipe_padrao: int | None) -> int:
        """Modo com a equipe padrão da principal (o mais próximo abaixo, se ele foi podado)."""
        t = self.tarefas[codigo]
        if t.travada or len(t.modos) == 1 or not equipe_padrao:
            return 0
        principal = t.funcao_principal or max(t.modos[-1].horas, key=lambda f: t.modos[-1].horas[f], default=None)
        melhor = 0
        for k, m in enumerate(t.modos):
            if principal and m.equipe.get(principal, 0) <= equipe_padrao:
                melhor = k
        return melhor

    def fim_da_obra(self, sol: Mapping[str, Mapping[str, Any]]) -> int:
        return max(a["fim"] for a in sol.values())


def ordem_tarefas(tarefas: Mapping[str, Tarefa]) -> list[str]:
    from atividades.grafo import ordem_topologica

    deps = {c: [e.anterior for e in t.deps if e.anterior in tarefas] for c, t in tarefas.items()}
    return ordem_topologica(deps, sorted(tarefas, key=lambda c: (tarefas[c].ordem, c)))


# --------------------------------------------------------------------------- elos


def termo_inicio(inst: Instancia, elo: Elo, a: Mapping[str, Any]) -> int:
    """Menor início (dia útil) de B permitido pelo elo, dado A posicionado."""
    cal = inst.calendario
    w = elo.espera
    if elo.tipo == "II":
        return a["inicio"] + w if elo.unidade == "du" else cal.indice_util(cal.offset[a["inicio"]] + w)
    return a["ultimo"] + 1 + w if elo.unidade == "du" else cal.indice_util(a["fim"] + w + 1)


def exigencia_termino(inst: Instancia, elo: Elo, a: Mapping[str, Any]) -> tuple[str, int] | None:
    """Elo II: B não termina antes de A + espera. ("idx", último dia útil mínimo) ou ("off", término mínimo)."""
    if elo.tipo != "II":
        return None
    if elo.unidade == "du":
        return ("idx", a["ultimo"] + elo.espera)
    return ("off", a["fim"] + elo.espera)


def termino_atende(exig: tuple[str, int], b: Mapping[str, Any]) -> bool:
    return (b["ultimo"] if exig[0] == "idx" else b["fim"]) >= exig[1]


def termo_pelo_termino(inst: Instancia, exig: tuple[str, int], b: Mapping[str, Any]) -> int:
    """Menor início de B para cumprir a exigência de término, mantendo o vão (último − início) de B."""
    alvo = exig[1] if exig[0] == "idx" else inst.calendario.indice_util(exig[1])
    return alvo - (b["ultimo"] - b["inicio"])


def liberacao(inst: Instancia, codigo: str, sol: Mapping[str, Mapping[str, Any]],
              b: Mapping[str, Any] | None = None) -> int:
    """Dia útil em que a tarefa fica liberada (0 se não tem anteriores).

    Com `b` (a própria tarefa posicionada), inclui o que os elos II exigem do término.
    """
    t = inst.tarefas[codigo]
    termos = [0]
    for e in t.deps:
        a = sol[e.anterior]
        termos.append(termo_inicio(inst, e, a))
        exig = exigencia_termino(inst, e, a)
        if exig and b is not None:
            termos.append(termo_pelo_termino(inst, exig, b))
    return max(termos)


def posicionar_cedo(inst: Instancia, codigo: str, modo: int, sol: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """A tarefa o mais cedo possível no modo dado, cumprindo os elos de início e de término."""
    t = inst.tarefas[codigo]
    s = liberacao(inst, codigo, sol)
    exigs = [x for x in (exigencia_termino(inst, e, sol[e.anterior]) for e in t.deps) if x]
    b = inst.entrada(codigo, modo, s)
    for _ in range(50):
        falta = [x for x in exigs if not termino_atende(x, b)]
        if not falta:
            break
        s = max([s + 1] + [termo_pelo_termino(inst, x, b) for x in falta])
        b = inst.entrada(codigo, modo, s)
    return b


def agendar_cedo(inst: Instancia, escolha: Mapping[str, int] | str = "padrao",
                 equipe_padrao: Mapping[str, int] | None = None) -> dict[str, dict[str, Any]]:
    """Cada tarefa o mais cedo possível. escolha: {codigo: modo}, "padrao" ou "rapido"."""
    sol: dict[str, dict[str, Any]] = {}
    for cod in inst.ordem:
        if isinstance(escolha, Mapping):
            modo = escolha.get(cod, 0)
        elif escolha == "rapido":
            modo = inst.modo_mais_rapido(cod, liberacao(inst, cod, sol))
        else:
            modo = inst.modo_padrao(cod, (equipe_padrao or {}).get(cod))
        sol[cod] = posicionar_cedo(inst, cod, modo, sol)
    return sol


def agendar_no_prazo(inst: Instancia, equipe_padrao: Mapping[str, int] | None = None) -> dict[str, dict[str, Any]]:
    """Equipe padrão, o mais cedo possível; enquanto passar do prazo, aumenta a equipe do caminho crítico."""
    escolha = {c: inst.modo_padrao(c, (equipe_padrao or {}).get(c)) for c in inst.tarefas}
    return agendar_cedo(inst, _no_prazo(inst, escolha))


def _pessoas(inst: Instancia, c: str, k: int) -> int:
    return sum(inst.tarefas[c].modos[k].equipe.values())


def _no_prazo(inst: Instancia, escolha: dict[str, int]) -> dict[str, int]:
    sol = agendar_cedo(inst, escolha)
    while inst.fim_da_obra(sol) > inst.offset_limite:
        fim = inst.fim_da_obra(sol)
        melhor = None
        cadeia = caminho_critico(inst, sol)
        for c in cadeia:
            k = escolha[c]
            if k + 1 >= len(inst.tarefas[c].modos):
                continue
            s2 = agendar_cedo(inst, {**escolha, c: k + 1})
            ganho = fim - inst.fim_da_obra(s2)
            if ganho > 0:
                nota = max(1, _pessoas(inst, c, k + 1) - _pessoas(inst, c, k)) / ganho
                if melhor is None or nota < melhor[0]:
                    melhor = (nota, c)
        if melhor is None:
            for c in cadeia:  # caminhos empatados: encurta a do caminho crítico que mais encurta por pessoa
                k = escolha[c]
                if k + 1 >= len(inst.tarefas[c].modos):
                    continue
                ganho = sol[c]["duracao"] - inst.duracao(c, k + 1, sol[c]["inicio"])
                if ganho > 0:
                    nota = max(1, _pessoas(inst, c, k + 1) - _pessoas(inst, c, k)) / ganho
                    if melhor is None or nota < melhor[0]:
                        melhor = (nota, c)
        if melhor is None:
            return escolha
        escolha[melhor[1]] += 1
        sol = agendar_cedo(inst, escolha)
    return escolha


def custo_rapido(inst: Instancia, sol: Mapping[str, Mapping[str, Any]]) -> float:
    """Custo (R$) da solução com os contratados mínimos: mão de obra paga + indiretos por tempo."""
    if inst.fim_da_obra(sol) > inst.offset_limite:
        return float("inf")
    contratados = contratados_minimos(inst, sol)
    total = 0.0
    pagas: dict[int, float] = {}
    for f, serie in contratados.items():
        custo = inst.custo_hora.get(f, 0.0)
        for s, c in enumerate(serie):
            if c:
                if s not in pagas:
                    pagas[s] = horas_pagas_semana(inst, s)
                total += c * pagas[s] * custo
        if f in inst.transferiveis and inst.custo_troca:
            total += inst.custo_troca * sum(abs(b - a) for a, b in zip([0] + serie, serie + [0]))
    return total + custo_por_periodo(inst, sol, inst.indiretos)[0]


def busca_local(inst: Instancia, equipe_padrao: Mapping[str, int] | None = None, segundos: float = 5.0
                ) -> dict[str, dict[str, Any]]:
    """Solução inicial: parte da equipe padrão e da menor equipe, cabe no prazo aumentando a equipe do caminho
    crítico, e depois troca o modo de uma tarefa por vez enquanto o custo cair (até `segundos`)."""
    import time

    fim_tempo = time.monotonic() + segundos
    partidas = [{c: inst.modo_padrao(c, (equipe_padrao or {}).get(c)) for c in inst.tarefas},
                {c: 0 for c in inst.tarefas}]
    melhor_custo, melhor_escolha = float("inf"), partidas[0]
    for p in partidas:
        e = _no_prazo(inst, dict(p))
        custo = custo_rapido(inst, agendar_cedo(inst, e))
        if custo < melhor_custo:
            melhor_custo, melhor_escolha = custo, e
    if melhor_custo == float("inf"):
        return agendar_cedo(inst, melhor_escolha)
    escolha = dict(melhor_escolha)
    mudou = True
    while mudou and time.monotonic() < fim_tempo:
        mudou = False
        for c in inst.ordem:
            if time.monotonic() >= fim_tempo:
                break
            for k in range(len(inst.tarefas[c].modos)):
                if k == escolha[c]:
                    continue
                custo = custo_rapido(inst, agendar_cedo(inst, {**escolha, c: k}))
                if custo < melhor_custo - 0.01:
                    melhor_custo, escolha[c], mudou = custo, k, True
    return agendar_cedo(inst, escolha)


# --------------------------------------------------------------------------- caminho crítico e folgas


def caminho_critico(inst: Instancia, sol: Mapping[str, Mapping[str, Any]]) -> list[str]:
    """Cadeia que determina o término: da última tarefa para trás, o elo que mais segura cada uma."""
    fim = inst.final if inst.final else max(sol, key=lambda c: (sol[c]["fim"], -inst.tarefas[c].ordem))
    cadeia = [fim]
    atual = fim
    while True:
        t = inst.tarefas[atual]
        if not t.deps:
            break
        b = sol[atual]

        def peso(e: Elo) -> tuple[int, int]:
            a = sol[e.anterior]
            termo = termo_inicio(inst, e, a)
            exig = exigencia_termino(inst, e, a)
            if exig:
                termo = max(termo, termo_pelo_termino(inst, exig, b))
            return termo, -inst.tarefas[e.anterior].ordem

        e = max(t.deps, key=peso)
        cadeia.append(e.anterior)
        atual = e.anterior
    return list(reversed(cadeia))


def folgas(inst: Instancia, sol: Mapping[str, Mapping[str, Any]]) -> dict[str, int]:
    """Folga total (dias úteis): quanto a tarefa pode atrasar sem atrasar as seguintes (na posição mais tarde
    delas) nem passar do término da obra."""
    fim_obra = inst.fim_da_obra(sol)
    tarde: dict[str, dict[str, Any]] = {}
    res = {}
    for cod in reversed(inst.ordem):
        a = sol[cod]
        if a.get("partes"):
            tarde[cod], res[cod] = a, 0
            continue
        succ = inst.sucessores.get(cod, [])

        def ok(s: int) -> bool:
            try:
                x = inst.entrada(cod, a["modo"], s)
            except IndexError:
                return False
            if x["fim"] > fim_obra:
                return False
            for b_cod, e in succ:
                b = tarde[b_cod]
                if b["inicio"] < termo_inicio(inst, e, x):
                    return False
                exig = exigencia_termino(inst, e, x)
                if exig and not termino_atende(exig, b):
                    return False
            return True

        s = a["inicio"]
        while s - a["inicio"] < 400 and ok(s + 1):
            s += 1
        tarde[cod] = inst.entrada(cod, a["modo"], s)
        res[cod] = s - a["inicio"]
    return res


# --------------------------------------------------------------------------- equipe por semana


def ocupacao_diaria(inst: Instancia, sol: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[int, int]]:
    """Pessoas em serviço por função em cada dia útil (só equipe própria)."""
    uso: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for cod, a in sol.items():
        equipe = inst.tarefas[cod].equipe_propria(a["modo"])
        if not equipe:
            continue
        for ini, d in a.get("partes") or [(a["inicio"], a["duracao"])]:
            for i in range(ini, ini + d):
                for f, n in equipe.items():
                    uso[f][i] += n
    return uso


def envelope_sobe_desce(serie: list[int]) -> list[int]:
    """Menor série ≥ a original que sobe até um pico e depois só desce."""
    esq, dir_ = [], []
    acc = 0
    for v in serie:
        acc = max(acc, v)
        esq.append(acc)
    acc = 0
    for v in reversed(serie):
        acc = max(acc, v)
        dir_.append(acc)
    dir_.reverse()
    return [min(a, b) for a, b in zip(esq, dir_)]


def reducoes_minimas(serie: list[int], semanas: int) -> list[int]:
    """Menor série ≥ a original em que toda redução dura pelo menos `semanas` semanas (sair e voltar)."""
    s = list(serie)
    mudou = True
    while mudou:
        mudou = False
        for w in range(1, len(s)):
            if s[w] < s[w - 1]:
                janela = s[w + 1:w + semanas]
                if janela and max(janela) > s[w]:
                    s[w] = min(s[w - 1], max(janela))
                    mudou = True
    return s


def reducao_respeitada(serie: list[int], semanas: int) -> bool:
    for w in range(1, len(serie)):
        if serie[w] < serie[w - 1] and any(v > serie[w] for v in serie[w + 1:w + semanas]):
            return False
    return True


def semanas_do_cronograma(inst: Instancia, fim_offset: int) -> int:
    """Número de semanas do início até o término (inclusive)."""
    cal = inst.calendario
    return (cal.data_do_offset(fim_offset) - cal.semana0).days // 7 + 1


def contratados_minimos(inst: Instancia, sol: Mapping[str, Mapping[str, Any]], n_semanas: int | None = None
                        ) -> dict[str, list[int]]:
    """Contratados por semana: maior ocupação diária da semana, com sobe-e-desce (ou, nas funções que podem
    sair e voltar, com reduções de pelo menos `min_semanas_reducao` semanas)."""
    cal = inst.calendario
    n = n_semanas or semanas_do_cronograma(inst, inst.fim_da_obra(sol))
    uso = ocupacao_diaria(inst, sol)
    res = {}
    for f in inst.funcoes:
        serie = [0] * n
        for i, q in uso.get(f, {}).items():
            s = cal.semana(i)
            if s < n:
                serie[s] = max(serie[s], q)
        res[f] = (reducoes_minimas(serie, inst.min_semanas_reducao) if f in inst.transferiveis
                  else envelope_sobe_desce(serie))
    return res


def dias_pagos_semana(inst: Instancia, semana: int) -> tuple[int, int]:
    """(dias de trabalho pagos na semana, quantos deles são feriado). Na semana do início, só a partir dele."""
    cal = inst.calendario
    seg = cal.segunda(semana)
    pagos = feriados = 0
    for k in range(cal.dias_semana):
        d = date.fromordinal(seg.toordinal() + k)
        if d < cal.inicio:
            continue
        pagos += 1
        if d in cal.feriados:
            feriados += 1
    return pagos, feriados


def horas_pagas_semana(inst: Instancia, semana: int) -> float:
    """Horas pagas a um contratado na semana: dias de trabalho da semana (feriados contam) × horas/dia."""
    pagos, _ = dias_pagos_semana(inst, semana)
    return pagos * inst.calendario.horas_semana(semana) / inst.calendario.dias_semana


def horas_feriado_semana(inst: Instancia, semana: int) -> float:
    _, feriados = dias_pagos_semana(inst, semana)
    return feriados * inst.calendario.horas_semana(semana) / inst.calendario.dias_semana


# --------------------------------------------------------------------------- custos e resumo


def custo_por_periodo(inst: Instancia, sol: Mapping[str, Mapping[str, Any]], itens_base: list[ItemIndireto]
                      ) -> tuple[float, list[dict[str, Any]]]:
    """Valor por mês × duração real do período de cada item (obra toda ou entre atividades)."""
    cal = inst.calendario
    fim_obra = inst.fim_da_obra(sol)
    total = 0.0
    itens = []
    for it in itens_base:
        if it.tipo == "fixo":
            itens.append({"descricao": it.descricao, "atividade": it.atividade, "tipo": "fixo",
                          "custo": round(it.custo_total, 2), "unidade": it.unidade, "motivo": it.motivo})
            continue
        ini = 0 if it.de in (None, "INICIO_OBRA") or it.de not in sol else cal.offset[sol[it.de]["inicio"]]
        fim = fim_obra if it.ate in (None, "FIM_OBRA") or it.ate not in sol else sol[it.ate]["fim"]
        dias = max(0, fim - ini + 1)
        meses = dias / DIAS_POR_MES
        custo = it.custo_mes * meses
        total += custo
        itens.append({"descricao": it.descricao, "atividade": it.atividade, "tipo": it.tipo, "unidade": it.unidade,
                      "custo_mes": round(it.custo_mes, 2), "previsto_meses": it.previsto_meses,
                      "de": it.de, "ate": it.ate, "motivo": it.motivo,
                      "inicio": cal.data_do_offset(ini).isoformat(), "termino": cal.data_do_offset(fim).isoformat(),
                      "meses": round(meses, 2), "custo": round(custo, 2)})
    return total, itens


def custo_indiretos(inst: Instancia, sol: Mapping[str, Mapping[str, Any]]) -> tuple[float, list[dict[str, Any]]]:
    return custo_por_periodo(inst, sol, inst.indiretos)


def resumir(inst: Instancia, sol: Mapping[str, Mapping[str, Any]], contratados: Mapping[str, list[int]]
            ) -> dict[str, Any]:
    """Equipe por semana, custos, receita, pico, ociosidade (total e por função), folgas e caminho crítico."""
    cal = inst.calendario
    fim_obra = inst.fim_da_obra(sol)
    n = max([semanas_do_cronograma(inst, fim_obra)] + [len(v) for v in contratados.values()])
    uso = ocupacao_diaria(inst, sol)
    ocupadas: dict[str, list[float]] = {f: [0.0] * n for f in inst.funcoes}
    for f, dias in uso.items():
        for i, q in dias.items():
            s = cal.semana(i)
            if s < n:
                ocupadas[f][s] += q * cal.horas_dia(i)
    pagas_semana = [horas_pagas_semana(inst, s) for s in range(n)]
    feriado_semana = [horas_feriado_semana(inst, s) for s in range(n)]
    semanas = []
    por_funcao: dict[str, dict[str, Any]] = {}
    custo_mo = horas_pagas = horas_ocup = horas_fer = homem_semana = 0.0
    pico = 0
    for s in range(n):
        total_semana = 0
        for f in inst.funcoes:
            serie = contratados.get(f) or []
            c = serie[s] if s < len(serie) else 0
            if not c and not ocupadas[f][s]:
                continue
            pagas = c * pagas_semana[s]
            fer = c * feriado_semana[s]
            custo = pagas * inst.custo_hora.get(f, 0.0)
            parada = max(0.0, pagas - fer - ocupadas[f][s])
            semanas.append({"semana": cal.segunda(s).isoformat(), "indice": s, "funcao": f, "contratados": c,
                            "horas_ocupadas": round(ocupadas[f][s], 2), "horas_pagas": round(pagas, 2),
                            "horas_feriado": round(fer, 2), "horas_paradas": round(parada, 2), "custo": round(custo, 2)})
            pf = por_funcao.setdefault(f, {"funcao": f, "horas_pagas": 0.0, "horas_feriado": 0.0, "horas_ocupadas": 0.0,
                                           "horas_paradas": 0.0, "semanas_paradas": []})
            pf["horas_pagas"] += pagas
            pf["horas_feriado"] += fer
            pf["horas_ocupadas"] += ocupadas[f][s]
            pf["horas_paradas"] += parada
            if parada > 0.5:
                pf["semanas_paradas"].append((parada, cal.segunda(s).isoformat()))
            custo_mo += custo
            horas_pagas += pagas
            horas_fer += fer
            horas_ocup += ocupadas[f][s]
            homem_semana += c
            total_semana += c
        pico = max(pico, total_semana)
    for f in inst.transferiveis & set(contratados):
        if inst.custo_troca:
            serie = list(contratados[f])
            custo_mo += inst.custo_troca * sum(abs(b - a) for a, b in zip([0] + serie, serie + [0]))
    ociosidade_funcao = []
    for pf in por_funcao.values():
        base = pf["horas_pagas"] - pf["horas_feriado"]
        semanas_top = sorted(pf.pop("semanas_paradas"), reverse=True)
        ociosidade_funcao.append({
            **{k: round(v, 2) for k, v in pf.items() if k != "funcao"}, "funcao": pf["funcao"],
            "ociosidade": round(100 * pf["horas_paradas"] / base, 2) if base > 0 else 0.0,
            "pode_sair_e_voltar": pf["funcao"] in inst.transferiveis,
            "semanas_mais_paradas": [{"semana": w, "horas_paradas": round(h, 1)} for h, w in semanas_top[:5]],
        })
    ociosidade_funcao.sort(key=lambda x: -x["horas_paradas"])
    causas = [{"funcao": x["funcao"], "horas_paradas": x["horas_paradas"], "ociosidade": x["ociosidade"],
               "semanas": [s["semana"] for s in x["semanas_mais_paradas"][:3]]}
              for x in ociosidade_funcao[:3] if x["horas_paradas"] > 0]
    custo_ind, itens_ind = custo_indiretos(inst, sol)
    receita, itens_rec = custo_por_periodo(inst, sol, inst.receitas)
    fl = folgas(inst, sol)
    cadeia = caminho_critico(inst, sol)
    critico = set(cadeia)
    atividades = []
    for cod in inst.ordem:
        a = sol[cod]
        t = inst.tarefas[cod]
        m = t.modos[a["modo"]]
        partes = a.get("partes")
        atividades.append({
            "codigo": cod, "nome": t.nome, "etapa": t.etapa, "tipo": t.tipo, "execucao": t.execucao,
            "inicio": cal.data(a["inicio"]).isoformat(), "termino": cal.data_do_offset(a["fim"]).isoformat(),
            "inicio_indice": a["inicio"], "duracao": a["duracao"], "unidade": "corridos" if m.corridos else "uteis",
            "equipe": t.equipe_propria(a["modo"]), "equipe_texto": m.texto_equipe(), "maquinas": dict(m.maquinas),
            "modo": a["modo"], "n_modos": len(t.modos), "travada": t.travada,
            "equipe_max": t.equipe_max, "maquinas_max": t.maquinas_max,
            "partes": [{"inicio": cal.data(i).isoformat(), "termino": cal.data(i + d - 1).isoformat(), "duracao": d}
                       for i, d in partes] if partes else None,
            "folga": fl[cod], "critica": cod in critico, "ordem": t.ordem,
            "dependencias": [{"depende_de": e.anterior, "tipo": e.tipo, "espera": e.espera, "unidade": e.unidade}
                             for e in t.deps],
        })
    base_ocio = horas_pagas - horas_fer
    return {
        "termino": cal.data_do_offset(fim_obra).isoformat(),
        "dias_uteis": cal.ultimo_util_ate(fim_obra) + 1,
        "pico": pico,
        "homem_semana": round(homem_semana, 2),
        "horas_pagas": round(horas_pagas, 2),
        "horas_feriado": round(horas_fer, 2),
        "horas_ocupadas": round(horas_ocup, 2),
        "ociosidade": round(100 * (base_ocio - horas_ocup) / base_ocio, 2) if base_ocio > 0 else 0.0,
        "ociosidade_funcao": ociosidade_funcao,
        "causas_ociosidade": causas,
        "custo_mao_de_obra": round(custo_mo, 2),
        "custo_indiretos": round(custo_ind, 2),
        "custo_total": round(custo_mo + custo_ind, 2),
        "receita_variavel": round(receita, 2),
        "resultado": round(receita - custo_mo - custo_ind, 2),
        "indiretos": itens_ind,
        "receitas": itens_rec,
        "atividades": atividades,
        "equipe_semana": semanas,
        "contratados": {f: list(v) for f, v in contratados.items()},
        "caminho_critico": cadeia,
    }


# --------------------------------------------------------------------------- verificação


def verificar(inst: Instancia, sol: Mapping[str, Mapping[str, Any]], contratados: Mapping[str, list[int]]
              ) -> list[str]:
    """Lista de restrições violadas (vazia = solução válida). Usada nos testes e como checagem final."""
    erros: list[str] = []
    for cod, t in inst.tarefas.items():
        a = sol.get(cod)
        if a is None:
            erros.append(f"{cod}: sem início")
            continue
        if not 0 <= a["modo"] < len(t.modos):
            erros.append(f"{cod}: modo inválido")
            continue
        esperado = inst.entrada(cod, a["modo"], a["inicio"], a.get("partes"))
        if any(a[k] != esperado[k] for k in ("duracao", "fim", "ultimo")):
            erros.append(f"{cod}: duração/término não confere com o modo")
        partes = a.get("partes")
        if partes:
            if len(partes) > t.partes_max or not t.pode_dividir():
                erros.append(f"{cod}: dividida em partes sem poder")
            if sum(d for _, d in partes) != a["duracao"] or any(d < t.parte_min for _, d in partes):
                erros.append(f"{cod}: partes não somam a duração ou têm menos de {t.parte_min} dias úteis")
            if any(p[0] + p[1] > q[0] for p, q in zip(partes, partes[1:])):
                erros.append(f"{cod}: partes sobrepostas")
        if t.travada and t.modos[a["modo"]].equipe and t.funcao_principal and \
                t.modos[a["modo"]].equipe.get(t.funcao_principal) != t.travada:
            erros.append(f"{cod}: equipe travada em {t.travada} não respeitada")
        for e in t.deps:
            ant = sol[e.anterior]
            if a["inicio"] < termo_inicio(inst, e, ant):
                erros.append(f"{cod}: começa antes do que o elo com {e.anterior} ({e}) permite")
            exig = exigencia_termino(inst, e, ant)
            if exig and not termino_atende(exig, a):
                erros.append(f"{cod}: termina antes do que o elo II com {e.anterior} ({e}) exige")
        lib = liberacao(inst, cod, sol, a)
        if t.tipo == RIGIDA and a["inicio"] > lib + inst.limite_rigidas:
            erros.append(f"{cod}: rígida começa {a['inicio'] - lib} dias úteis depois de liberada")
        if t.tipo == AGUARDAR and a["inicio"] > lib:
            erros.append(f"{cod}: espera não começa assim que liberada")
        if a["fim"] > inst.offset_limite:
            erros.append(f"{cod}: termina depois da data limite")
    cal = inst.calendario
    uso = ocupacao_diaria(inst, sol)
    for f, dias in uso.items():
        serie = contratados.get(f) or []
        for i, q in dias.items():
            s = cal.semana(i)
            c = serie[s] if s < len(serie) else 0
            if q > c:
                erros.append(f"{f}: {q} pessoas em serviço em {cal.data(i)} com {c} contratadas")
                break
    for f, serie in contratados.items():
        if f in inst.transferiveis:
            if not reducao_respeitada(list(serie), inst.min_semanas_reducao):
                erros.append(f"{f}: redução de menos de {inst.min_semanas_reducao} semanas ({serie})")
        else:
            desceu = False
            for a, b in zip(serie, serie[1:]):
                if b < a:
                    desceu = True
                elif b > a and desceu:
                    erros.append(f"{f}: contratados diminuem e depois aumentam de novo ({serie})")
                    break
        lim = inst.max_por_funcao.get(f)
        if lim is not None and max(serie, default=0) > lim:
            erros.append(f"{f}: mais de {lim} contratados")
    if inst.max_total is not None:
        n = max((len(v) for v in contratados.values()), default=0)
        for s in range(n):
            tot = sum(v[s] for v in contratados.values() if s < len(v))
            if tot > inst.max_total:
                erros.append(f"semana {cal.segunda(s)}: {tot} contratados (máximo {inst.max_total})")
                break
    return erros
