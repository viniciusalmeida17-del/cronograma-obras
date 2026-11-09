"""Tarefas do cronograma (uma por atividade da sequência) e seus modos (tamanhos de equipe)."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

RIGIDA = "rigida"
FLEXIVEL = "flexivel"
AGUARDAR = "aguardar"
PROPRIA = "propria"
TERCEIRIZADA = "terceirizada"
ATIVIDADE_FINAL = "LIM-01"


def _teto(x: float) -> int:
    return math.ceil(round(x, 6))


@dataclass
class Modo:
    """Um jeito de executar a atividade.

    equipe: pessoas por função da equipe própria (vazio = não usa equipe própria).
    A duração vem de uma destas, nesta ordem:
      dias_corridos (cura, testes) → dias_uteis (terceirizada, manual) → horas ÷ (pessoas × horas/dia).
    """
    equipe: dict[str, int] = field(default_factory=dict)
    horas: dict[str, float] = field(default_factory=dict)          # horas ajustadas por função
    horas_equipamento: dict[str, float] = field(default_factory=dict)
    maquinas: dict[str, int] = field(default_factory=dict)
    dias_uteis: int | None = None
    dias_corridos: int | None = None

    @property
    def corridos(self) -> bool:
        return self.dias_corridos is not None

    def duracao(self, horas_dia: float) -> int:
        """Duração em dias úteis (ou corridos, se `corridos`)."""
        if self.dias_corridos is not None:
            return max(1, int(self.dias_corridos))
        if self.dias_uteis is not None:
            return max(1, int(self.dias_uteis))
        dias = 0.0
        for f, h in self.horas.items():
            if h > 0 and self.equipe.get(f):
                dias = max(dias, h / (self.equipe[f] * horas_dia))
        for e, h in self.horas_equipamento.items():
            if h > 0:
                dias = max(dias, h / (max(1, self.maquinas.get(e) or 1) * horas_dia))
        return max(1, _teto(dias))

    def texto_equipe(self) -> str:
        if not self.equipe:
            return ""
        return " + ".join(f"{n} {f.lower()}" for f, n in sorted(self.equipe.items(), key=lambda x: (-x[1], x[0])))


@dataclass
class Tarefa:
    codigo: str
    modos: list[Modo]
    tipo: str = RIGIDA                       # rigida, flexivel, aguardar
    deps: list[tuple[str, int]] = field(default_factory=list)  # (anterior, espera em dias corridos)
    execucao: str = PROPRIA
    nome: str | None = None
    etapa: str | None = None
    ordem: int = 0
    travada: int | None = None              # equipe travada (pessoas da função principal)
    funcao_principal: str | None = None

    @property
    def usa_equipe(self) -> bool:
        return any(m.equipe for m in self.modos)


def equipe_proporcional(horas: Mapping[str, float], principal_pessoas: int) -> tuple[str | None, dict[str, int]]:
    """Mesma regra da etapa 4: a principal recebe N; as outras teto(N × h ÷ h principal), mínimo 1."""
    horas = {f: h for f, h in horas.items() if h > 0}
    if not horas:
        return None, {}
    principal = max(horas, key=lambda f: (horas[f], f))
    hp = horas[principal]
    return principal, {f: principal_pessoas if f == principal else max(1, _teto(principal_pessoas * h / hp))
                       for f, h in horas.items()}


def modos_por_horas(
    horas: Mapping[str, float],
    horas_equipamento: Mapping[str, float] | None = None,
    maquinas: Mapping[str, int] | None = None,
    equipe_max: int = 6,
    travada: int | None = None,
    jornadas: Iterable[float] = (8.8,),
) -> list[Modo]:
    """Modos de 1 até `equipe_max` pessoas da função principal (ou só o travado).

    Tira os modos que não encurtam a duração em nenhuma jornada (mais gente sem ganho de prazo).
    """
    tamanhos = [travada] if travada else list(range(1, max(1, int(equipe_max)) + 1))
    jornadas = list(jornadas)
    modos: list[Modo] = []
    anteriores: tuple[int, ...] | None = None
    for n in tamanhos:
        _, equipe = equipe_proporcional(horas, n)
        m = Modo(equipe=equipe, horas={f: h for f, h in horas.items() if h > 0},
                 horas_equipamento={e: h for e, h in (horas_equipamento or {}).items() if h > 0},
                 maquinas=dict(maquinas or {}))
        duracoes = tuple(m.duracao(hd) for hd in jornadas)
        if anteriores is not None and duracoes == anteriores:
            continue
        anteriores = duracoes
        modos.append(m)
    return modos


def tarefas_da_obra(
    atividades: Iterable[Mapping[str, Any]],
    dependencias: Iterable[Mapping[str, Any]],
    travadas: Mapping[str, int] | None = None,
    jornadas: Iterable[float] = (8.8,),
) -> dict[str, Tarefa]:
    """Tarefas a partir do resultado da etapa 4 (`calcular_obra(...)["atividades"]`) e da rede da etapa 3."""
    travadas = travadas or {}
    jornadas = list(jornadas)
    tarefas: dict[str, Tarefa] = {}
    for a in atividades:
        if a["tipo"] == "indireta":
            continue
        cod = a["codigo"]
        dur = a.get("duracao") or {}
        calc = a.get("calculo") or {}
        execucao = a.get("execucao") or PROPRIA
        if dur.get("tipo") == "fixa" or dur.get("unidade") == "corridos":
            modos = [Modo(dias_corridos=int(dur["dias"]))]
        elif execucao == TERCEIRIZADA:
            modos = [Modo(dias_uteis=int(dur["dias"]))] if dur.get("dias") else []
        elif dur.get("tipo") == "manual":
            modos = [Modo(equipe=dict(calc.get("equipe") or {}), dias_uteis=int(dur["dias"]))]
        elif a.get("horas_ajustadas") or a.get("horas_equipamento"):
            modos = modos_por_horas(a.get("horas_ajustadas") or {}, a.get("horas_equipamento") or {},
                                    calc.get("maquinas") or {}, a.get("equipe_max") or 6, travadas.get(cod), jornadas)
        else:
            modos = []
        if not modos:
            raise ValueError(f"{cod}: atividade sem duração (resolva as pendências da etapa 4).")
        tarefas[cod] = Tarefa(
            codigo=cod, modos=modos, tipo=a["tipo"], execucao=execucao, nome=a.get("nome"), etapa=a.get("etapa"),
            ordem=a.get("ordem_biblioteca", 0), travada=travadas.get(cod), funcao_principal=a.get("funcao_principal"),
        )
    for d in dependencias:
        if d["atividade"] in tarefas and d["depende_de"] in tarefas:
            tarefas[d["atividade"]].deps.append((d["depende_de"], int(d.get("espera_dias") or 0)))
    return tarefas
