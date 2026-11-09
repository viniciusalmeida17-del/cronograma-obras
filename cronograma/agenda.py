"""Instância do cronograma, solução inicial (o mais cedo possível), caminho crítico, avaliação e verificação.

Unidades:
- início das tarefas em índice de dia útil do calendário;
- términos e esperas em dia corrido (offset desde a data de início), porque as esperas e as
  durações fixas (cura, testes) são em dias corridos.

Regra das dependências: B pode começar no primeiro dia útil com offset ≥ término de A + espera + 1.
(A termina na sexta; com +3d, sábado, domingo e segunda passam; B começa na terça.)
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable, Mapping

from .calendario import Calendario
from .modelo import AGUARDAR, ATIVIDADE_FINAL, RIGIDA, Modo, Tarefa

DIAS_POR_MES = 30.4375
LIMITE_RIGIDAS = 5


@dataclass
class ItemIndireto:
    """Item de indiretas cujo custo depende do prazo.

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
    indiretos: list[ItemIndireto] = field(default_factory=list)
    limite_rigidas: int = LIMITE_RIGIDAS
    max_por_funcao: dict[str, int] = field(default_factory=dict)
    max_total: int | None = None
    final: str = ATIVIDADE_FINAL

    def __post_init__(self) -> None:
        if self.final not in self.tarefas:
            # sem LIM-01 (redes de teste): a última tarefa é a que não tem sucessor; usa um marco virtual
            self.final = None  # type: ignore[assignment]
        self.ordem = ordem_tarefas(self.tarefas)
        self.sucessores: dict[str, list[tuple[str, int]]] = defaultdict(list)
        for t in self.tarefas.values():
            for a, w in t.deps:
                self.sucessores[a].append((t.codigo, w))
        self.funcoes = sorted({f for t in self.tarefas.values() for m in t.modos for f in m.equipe})
        cal = self.calendario
        self.offset_limite = cal.offset_de(self.limite)
        self.horizonte = max(1, cal.dias_uteis_ate(self.limite))  # dias úteis até a data limite

    # ------------------------------------------------------------------ durações

    def duracao(self, codigo: str, modo: int, inicio: int) -> int:
        m = self.tarefas[codigo].modos[modo]
        return m.duracao(self.calendario.horas_dia(inicio))

    def termino(self, codigo: str, modo: int, inicio: int) -> int:
        """Offset (dia corrido) do último dia da tarefa."""
        m = self.tarefas[codigo].modos[modo]
        cal = self.calendario
        if m.corridos:
            return cal.offset[inicio] + m.duracao(0) - 1
        return cal.offset[inicio + self.duracao(codigo, modo, inicio) - 1]

    def modo_mais_rapido(self, codigo: str, inicio: int) -> int:
        t = self.tarefas[codigo]
        return min(range(len(t.modos)), key=lambda k: (self.duracao(codigo, k, inicio), k))

    def modo_padrao(self, codigo: str, equipe_padrao: int | None) -> int:
        """Modo com a equipe padrão da principal (o mais próximo, se ele foi podado)."""
        t = self.tarefas[codigo]
        if t.travada or len(t.modos) == 1 or not equipe_padrao:
            return 0
        principal = t.funcao_principal or max(t.modos[-1].equipe, key=lambda f: t.modos[-1].equipe[f], default=None)
        melhor = 0
        for k, m in enumerate(t.modos):
            if principal and m.equipe.get(principal, 0) <= equipe_padrao:
                melhor = k
        return melhor

    def fim_da_obra(self, sol: Mapping[str, Mapping[str, Any]]) -> int:
        return max(a["fim"] for a in sol.values())


def ordem_tarefas(tarefas: Mapping[str, Tarefa]) -> list[str]:
    from atividades.grafo import ordem_topologica

    deps = {c: [a for a, _ in t.deps if a in tarefas] for c, t in tarefas.items()}
    return ordem_topologica(deps, sorted(tarefas, key=lambda c: (tarefas[c].ordem, c)))


# --------------------------------------------------------------------------- o mais cedo possível


def liberacao(inst: Instancia, codigo: str, fins: Mapping[str, int]) -> int:
    """Offset a partir do qual a tarefa pode começar (0 se não tem anteriores)."""
    t = inst.tarefas[codigo]
    return max((fins[a] + w + 1 for a, w in t.deps), default=0)


def agendar_cedo(inst: Instancia, escolha: Mapping[str, int] | str = "padrao",
                 equipe_padrao: Mapping[str, int] | None = None) -> dict[str, dict[str, Any]]:
    """Cada tarefa o mais cedo possível. escolha: {codigo: modo}, "padrao" ou "rapido"."""
    cal = inst.calendario
    sol: dict[str, dict[str, Any]] = {}
    fins: dict[str, int] = {}
    for cod in inst.ordem:
        lib = liberacao(inst, cod, fins)
        inicio = cal.indice_util(lib)
        if isinstance(escolha, Mapping):
            modo = escolha.get(cod, 0)
        elif escolha == "rapido":
            modo = inst.modo_mais_rapido(cod, inicio)
        else:
            modo = inst.modo_padrao(cod, (equipe_padrao or {}).get(cod))
        fim = inst.termino(cod, modo, inicio)
        fins[cod] = fim
        sol[cod] = {"inicio": inicio, "modo": modo, "fim": fim, "duracao": inst.duracao(cod, modo, inicio)}
    return sol


def agendar_no_prazo(inst: Instancia, equipe_padrao: Mapping[str, int] | None = None) -> dict[str, dict[str, Any]]:
    """Solução inicial: equipe padrão, o mais cedo possível; enquanto passar do prazo, aumenta a equipe
    da tarefa do caminho crítico que mais encurta por pessoa a mais."""
    escolha = {c: inst.modo_padrao(c, (equipe_padrao or {}).get(c)) for c in inst.tarefas}
    while True:
        sol = agendar_cedo(inst, escolha)
        if inst.fim_da_obra(sol) <= inst.offset_limite:
            return sol
        melhor = None
        for c in caminho_critico(inst, sol):
            k = escolha[c]
            t = inst.tarefas[c]
            if k + 1 >= len(t.modos):
                continue
            ganho = sol[c]["duracao"] - inst.duracao(c, k + 1, sol[c]["inicio"])
            pessoas = sum(t.modos[k + 1].equipe.values()) - sum(t.modos[k].equipe.values())
            nota = ganho / max(1, pessoas)
            if ganho > 0 and (melhor is None or nota > melhor[0]):
                melhor = (nota, c)
        if melhor is None:
            return sol
        escolha[melhor[1]] += 1


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
    return total + custo_indiretos(inst, sol)[0]


def busca_local(inst: Instancia, equipe_padrao: Mapping[str, int] | None = None, segundos: float = 5.0
                ) -> dict[str, dict[str, Any]]:
    """Solução inicial melhor que o "mais cedo com a equipe padrão":

    1. parte da equipe padrão e da menor equipe; enquanto passar do prazo, aumenta a equipe da tarefa do
       caminho crítico com o menor aumento de custo por dia ganho;
    2. troca o modo de uma tarefa por vez enquanto o custo cair (até `segundos`).
    """
    import time

    fim_tempo = time.monotonic() + segundos

    def avaliar_escolha(escolha: Mapping[str, int]) -> tuple[float, dict[str, dict[str, Any]]]:
        sol = agendar_cedo(inst, escolha)
        return custo_rapido(inst, sol), sol

    def no_prazo(escolha: dict[str, int]) -> dict[str, int]:
        sol = agendar_cedo(inst, escolha)
        while inst.fim_da_obra(sol) > inst.offset_limite:
            fim = inst.fim_da_obra(sol)
            melhor = None
            for c in caminho_critico(inst, sol):
                k = escolha[c]
                if k + 1 >= len(inst.tarefas[c].modos):
                    continue
                teste = {**escolha, c: k + 1}
                s2 = agendar_cedo(inst, teste)
                ganho = fim - inst.fim_da_obra(s2)
                if ganho <= 0:
                    continue
                pessoas = sum(inst.tarefas[c].modos[k + 1].equipe.values()) - sum(inst.tarefas[c].modos[k].equipe.values())
                nota = max(1, pessoas) / ganho
                if melhor is None or nota < melhor[0]:
                    melhor = (nota, c)
            if melhor is None:
                # caminhos empatados: encurta a tarefa do caminho crítico que mais encurta por pessoa
                for c in caminho_critico(inst, sol):
                    k = escolha[c]
                    t = inst.tarefas[c]
                    if k + 1 >= len(t.modos):
                        continue
                    ganho = sol[c]["duracao"] - inst.duracao(c, k + 1, sol[c]["inicio"])
                    pessoas = sum(t.modos[k + 1].equipe.values()) - sum(t.modos[k].equipe.values())
                    if ganho > 0 and (melhor is None or max(1, pessoas) / ganho < melhor[0]):
                        melhor = (max(1, pessoas) / ganho, c)
            if melhor is None:
                return escolha
            escolha[melhor[1]] += 1
            sol = agendar_cedo(inst, escolha)
        return escolha

    partidas = [{c: inst.modo_padrao(c, (equipe_padrao or {}).get(c)) for c in inst.tarefas},
                {c: 0 for c in inst.tarefas}]
    melhor_custo, melhor_escolha = float("inf"), partidas[0]
    for p in partidas:
        e = no_prazo(dict(p))
        custo, _ = avaliar_escolha(e)
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
                custo, _ = avaliar_escolha({**escolha, c: k})
                if custo < melhor_custo - 0.01:
                    melhor_custo, escolha[c], mudou = custo, k, True
    return agendar_cedo(inst, escolha)


def caminho_critico(inst: Instancia, sol: Mapping[str, Mapping[str, Any]]) -> list[str]:
    """Cadeia que determina o término: da última tarefa para trás, a anterior que mais segura a liberação."""
    fim = inst.final if inst.final else max(sol, key=lambda c: sol[c]["fim"])
    cadeia = [fim]
    atual = fim
    while True:
        t = inst.tarefas[atual]
        if not t.deps:
            break
        ant, w = max(t.deps, key=lambda d: (sol[d[0]]["fim"] + d[1], -inst.tarefas[d[0]].ordem))
        cadeia.append(ant)
        atual = ant
    return list(reversed(cadeia))


def folgas(inst: Instancia, sol: Mapping[str, Mapping[str, Any]]) -> dict[str, int]:
    """Folga total (dias úteis) de cada tarefa com os modos escolhidos, mantendo o término da obra."""
    cal = inst.calendario
    fim_obra = inst.fim_da_obra(sol)
    inicio_tarde: dict[str, int] = {}
    for cod in reversed(inst.ordem):
        a = sol[cod]
        succ = inst.sucessores.get(cod, [])
        limite = min((cal.offset[inicio_tarde[b]] - w - 1 for b, w in succ), default=fim_obra)
        m = inst.tarefas[cod].modos[a["modo"]]
        if m.corridos:
            ultimo_inicio = cal.ultimo_util_ate(limite - m.duracao(0) + 1)
        else:
            ultimo_inicio = cal.ultimo_util_ate(limite) - a["duracao"] + 1
        inicio_tarde[cod] = max(a["inicio"], ultimo_inicio)
    return {c: inicio_tarde[c] - sol[c]["inicio"] for c in sol}


# --------------------------------------------------------------------------- equipe por semana


def ocupacao_diaria(inst: Instancia, sol: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[int, int]]:
    """Pessoas em serviço por função em cada dia útil (só equipe própria)."""
    uso: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for cod, a in sol.items():
        m = inst.tarefas[cod].modos[a["modo"]]
        if not m.equipe or m.corridos:
            continue
        for i in range(a["inicio"], a["inicio"] + a["duracao"]):
            for f, n in m.equipe.items():
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


def semanas_do_cronograma(inst: Instancia, fim_offset: int) -> int:
    """Número de semanas do início até o término (inclusive)."""
    cal = inst.calendario
    return (cal.data_do_offset(fim_offset) - cal.semana0).days // 7 + 1


def contratados_minimos(inst: Instancia, sol: Mapping[str, Mapping[str, Any]], n_semanas: int | None = None
                        ) -> dict[str, list[int]]:
    """Contratados por semana: maior ocupação diária da semana, com o envelope de sobe-e-desce."""
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
        res[f] = envelope_sobe_desce(serie)
    return res


def horas_pagas_semana(inst: Instancia, semana: int) -> float:
    """Horas pagas a um contratado na semana: dias de trabalho da semana (feriados contam) × horas/dia.

    Na semana do início, só os dias a partir do início.
    """
    cal = inst.calendario
    seg = cal.segunda(semana)
    dias = sum(1 for k in range(cal.dias_semana) if (seg.toordinal() + k) >= cal.inicio.toordinal())
    return dias * cal.horas_semana(semana) / cal.dias_semana


# --------------------------------------------------------------------------- custos e resumo


def custo_indiretos(inst: Instancia, sol: Mapping[str, Mapping[str, Any]]) -> tuple[float, list[dict[str, Any]]]:
    """Indiretos que variam com o prazo, com o período real de cada item."""
    cal = inst.calendario
    fim_obra = inst.fim_da_obra(sol)
    total = 0.0
    itens = []
    for it in inst.indiretos:
        if it.tipo == "fixo":
            itens.append({"descricao": it.descricao, "atividade": it.atividade, "tipo": "fixo", "custo": round(it.custo_total, 2),
                          "unidade": it.unidade, "motivo": it.motivo})
            continue
        ini = 0 if it.de in (None, "INICIO_OBRA") or it.de not in sol else cal.offset[sol[it.de]["inicio"]]
        fim = fim_obra if it.ate in (None, "FIM_OBRA") or it.ate not in sol else sol[it.ate]["fim"]
        dias = max(0, fim - ini + 1)
        meses = dias / DIAS_POR_MES
        custo = it.custo_mes * meses
        total += custo
        itens.append({"descricao": it.descricao, "atividade": it.atividade, "tipo": it.tipo, "unidade": it.unidade,
                      "custo_mes": round(it.custo_mes, 2), "previsto_meses": it.previsto_meses,
                      "de": it.de, "ate": it.ate,
                      "inicio": cal.data_do_offset(ini).isoformat(), "termino": cal.data_do_offset(fim).isoformat(),
                      "meses": round(meses, 2), "custo": round(custo, 2)})
    return total, itens


def resumir(inst: Instancia, sol: Mapping[str, Mapping[str, Any]], contratados: Mapping[str, list[int]]
            ) -> dict[str, Any]:
    """Equipe por semana, custos, pico, ociosidade, folgas e caminho crítico de uma solução."""
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
    semanas = []
    custo_mo = horas_pagas = horas_ocup = homem_semana = 0.0
    pico = 0
    for s in range(n):
        total_semana = 0
        for f in inst.funcoes:
            c = (contratados.get(f) or [])[s] if s < len(contratados.get(f) or []) else 0
            if not c and not ocupadas[f][s]:
                continue
            pagas = c * pagas_semana[s]
            custo = pagas * inst.custo_hora.get(f, 0.0)
            semanas.append({"semana": cal.segunda(s).isoformat(), "indice": s, "funcao": f, "contratados": c,
                            "horas_ocupadas": round(ocupadas[f][s], 2), "horas_pagas": round(pagas, 2),
                            "custo": round(custo, 2)})
            custo_mo += custo
            horas_pagas += pagas
            horas_ocup += ocupadas[f][s]
            homem_semana += c
            total_semana += c
        pico = max(pico, total_semana)
    custo_ind, itens_ind = custo_indiretos(inst, sol)
    fl = folgas(inst, sol)
    critico = set(caminho_critico(inst, sol))
    atividades = []
    for cod in inst.ordem:
        a = sol[cod]
        t = inst.tarefas[cod]
        m = t.modos[a["modo"]]
        atividades.append({
            "codigo": cod, "nome": t.nome, "etapa": t.etapa, "tipo": t.tipo, "execucao": t.execucao,
            "inicio": cal.data(a["inicio"]).isoformat(), "termino": cal.data_do_offset(a["fim"]).isoformat(),
            "inicio_indice": a["inicio"], "duracao": a["duracao"], "unidade": "corridos" if m.corridos else "uteis",
            "equipe": dict(m.equipe) if not m.corridos else {}, "equipe_texto": m.texto_equipe(),
            "modo": a["modo"], "n_modos": len(t.modos), "travada": t.travada,
            "folga": fl[cod], "critica": cod in critico, "ordem": t.ordem,
        })
    return {
        "termino": cal.data_do_offset(fim_obra).isoformat(),
        "dias_uteis": cal.ultimo_util_ate(fim_obra) + 1,
        "pico": pico,
        "homem_semana": round(homem_semana, 2),
        "horas_pagas": round(horas_pagas, 2),
        "horas_ocupadas": round(horas_ocup, 2),
        "ociosidade": round(100 * (1 - horas_ocup / horas_pagas), 2) if horas_pagas else 0.0,
        "custo_mao_de_obra": round(custo_mo, 2),
        "custo_indiretos": round(custo_ind, 2),
        "custo_total": round(custo_mo + custo_ind, 2),
        "indiretos": itens_ind,
        "atividades": atividades,
        "equipe_semana": semanas,
        "contratados": {f: list(v) for f, v in contratados.items()},
        "caminho_critico": [c for c in caminho_critico(inst, sol)],
    }


# --------------------------------------------------------------------------- verificação


def verificar(inst: Instancia, sol: Mapping[str, Mapping[str, Any]], contratados: Mapping[str, list[int]]
              ) -> list[str]:
    """Lista de restrições violadas (vazia = solução válida). Usada nos testes e como checagem final."""
    cal = inst.calendario
    erros: list[str] = []
    fins = {c: a["fim"] for c, a in sol.items()}
    for cod, t in inst.tarefas.items():
        a = sol.get(cod)
        if a is None:
            erros.append(f"{cod}: sem início")
            continue
        if not 0 <= a["modo"] < len(t.modos):
            erros.append(f"{cod}: modo inválido")
            continue
        if a["duracao"] != inst.duracao(cod, a["modo"], a["inicio"]) or a["fim"] != inst.termino(cod, a["modo"], a["inicio"]):
            erros.append(f"{cod}: duração/término não confere com o modo")
        if t.travada and t.modos[a["modo"]].equipe and max(t.modos[a["modo"]].equipe.values()) != t.travada:
            erros.append(f"{cod}: equipe travada em {t.travada} não respeitada")
        lib = liberacao(inst, cod, fins)
        if cal.offset[a["inicio"]] < lib:
            erros.append(f"{cod}: começa antes de liberar")
        lib_idx = cal.indice_util(lib)
        if t.tipo == RIGIDA and a["inicio"] > lib_idx + inst.limite_rigidas:
            erros.append(f"{cod}: rígida começa {a['inicio'] - lib_idx} dias úteis depois de liberada")
        if t.tipo == AGUARDAR and a["inicio"] > lib_idx:
            erros.append(f"{cod}: espera não começa assim que liberada")
        if a["fim"] > inst.offset_limite:
            erros.append(f"{cod}: termina depois da data limite")
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
