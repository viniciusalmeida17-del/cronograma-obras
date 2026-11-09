"""Tarefas do cronograma (uma por atividade da sequência), seus elos e seus modos (equipe e máquinas)."""
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
OPERADOR = "Operador/Motorista"
TAMANHOS_EQUIPE = (1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 20, 25, 30, 40, 50)
EQUIPE_MAX = 20
MAQUINAS_MAX = 6
PARTES_MAX = 3          # terceirizada pode ser feita em até 3 partes
PARTE_MIN = 5           # cada parte com pelo menos 5 dias úteis


def _teto(x: float) -> int:
    return math.ceil(round(x, 6))


@dataclass
class Elo:
    """B depende de `anterior`.

    tipo TI: B começa depois do término de A + espera. II: B começa depois do início de A + espera e não
    termina antes do término de A + espera. unidade: d (dias corridos) ou du (dias úteis).
    """
    anterior: str
    espera: int = 0
    tipo: str = "TI"
    unidade: str = "d"

    def __str__(self) -> str:
        return self.anterior + (":II" if self.tipo == "II" else "") + (f"+{self.espera}{self.unidade}" if self.espera else "")


@dataclass
class Modo:
    """Um jeito de executar a atividade.

    equipe: pessoas por função (em atividade própria, inclui 1 Operador/Motorista por máquina).
    A duração vem de uma destas, nesta ordem:
      dias_corridos (cura, testes) → dias_uteis (terceirizada, manual) →
      maior entre horas ÷ (pessoas × horas/dia), horas de equipamento ÷ (máquinas × horas/dia) e dias_minimos
      (concretagem: volume ÷ (m³ por caminhão × caminhões por dia)).
    """
    equipe: dict[str, int] = field(default_factory=dict)
    horas: dict[str, float] = field(default_factory=dict)          # horas ajustadas por função
    horas_equipamento: dict[str, float] = field(default_factory=dict)
    maquinas: dict[str, int] = field(default_factory=dict)
    dias_uteis: int | None = None
    dias_corridos: int | None = None
    dias_minimos: int | None = None

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
        return max(1, _teto(dias), int(self.dias_minimos or 0))

    def limitante(self, horas_dia: float) -> str:
        if self.dias_corridos is not None or self.dias_uteis is not None:
            return "fixa"
        pessoas = max((h / (self.equipe[f] * horas_dia) for f, h in self.horas.items() if h > 0 and self.equipe.get(f)),
                      default=0.0)
        maquinas = max((h / (max(1, self.maquinas.get(e) or 1) * horas_dia) for e, h in self.horas_equipamento.items()
                        if h > 0), default=0.0)
        if self.dias_minimos and self.dias_minimos >= _teto(max(pessoas, maquinas)):
            return "concretagem"
        return "equipamento" if maquinas > pessoas else "mao_de_obra"

    def texto_equipe(self) -> str:
        if not self.equipe:
            return ""
        return " + ".join(f"{n} {f.lower()}" for f, n in sorted(self.equipe.items(), key=lambda x: (-x[1], x[0])))


@dataclass
class Tarefa:
    codigo: str
    modos: list[Modo]
    tipo: str = RIGIDA                       # rigida, flexivel, aguardar
    deps: list[Any] = field(default_factory=list)  # Elo (aceita (anterior, espera) = TI em dias corridos)
    execucao: str = PROPRIA
    nome: str | None = None
    etapa: str | None = None
    ordem: int = 0
    travada: int | None = None              # equipe travada (pessoas da função principal)
    funcao_principal: str | None = None
    equipe_max: int | None = None
    maquinas_max: int | None = None
    partes_max: int = 1                      # terceirizada: até PARTES_MAX partes
    parte_min: int = PARTE_MIN

    def __post_init__(self) -> None:
        self.deps = [d if isinstance(d, Elo) else Elo(*d) for d in self.deps]

    @property
    def propria(self) -> bool:
        return self.execucao != TERCEIRIZADA

    @property
    def usa_equipe(self) -> bool:
        return self.propria and any(m.equipe for m in self.modos)

    def equipe_propria(self, modo: int) -> dict[str, int]:
        m = self.modos[modo]
        return dict(m.equipe) if self.propria and not m.corridos else {}

    def pode_dividir(self) -> bool:
        return self.partes_max > 1 and not any(m.corridos for m in self.modos)


def equipe_proporcional(horas: Mapping[str, float], principal_pessoas: int) -> tuple[str | None, dict[str, int]]:
    """Mesma regra da etapa 4: a principal recebe N; as outras teto(N × h ÷ h principal), mínimo 1."""
    horas = {f: h for f, h in horas.items() if h > 0}
    if not horas:
        return None, {}
    principal = max(horas, key=lambda f: (horas[f], f))
    hp = horas[principal]
    return principal, {f: principal_pessoas if f == principal else max(1, _teto(principal_pessoas * h / hp))
                       for f, h in horas.items()}


def tamanhos_de_equipe(equipe_max: int) -> list[int]:
    """1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 20 … até a equipe máxima (e ela própria)."""
    t = [n for n in TAMANHOS_EQUIPE if n <= equipe_max]
    if equipe_max not in t:
        t.append(equipe_max)
    return t


def modos_por_horas(
    horas: Mapping[str, float],
    horas_equipamento: Mapping[str, float] | None = None,
    maquinas: Mapping[str, int] | None = None,
    equipe_max: int = EQUIPE_MAX,
    travada: int | None = None,
    jornadas: Iterable[float] = (8.8,),
    maquinas_max: int | None = None,
    dias_minimos: int | None = None,
    propria: bool = True,
) -> list[Modo]:
    """Modos com 1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 20 pessoas da função principal (até a máxima) ou só o travado.

    Máquinas: com `maquinas_max`, para cada tamanho de equipe o otimizador recebe a menor quantidade de cada
    equipamento que não deixa a máquina segurar a equipe (até o máximo) e também o modo com todas as máquinas.
    Sem `maquinas_max`, usa as `maquinas` fixas (padrão 1). Em atividade própria, cada máquina traz 1
    Operador/Motorista. Ficam só os modos que encurtam a duração em relação a um modo com menos gente.
    """
    horas = {f: h for f, h in horas.items() if h > 0}
    equip = {e: h for e, h in (horas_equipamento or {}).items() if h > 0}
    jornadas = list(jornadas)
    hd0 = jornadas[0]
    tamanhos = [travada] if travada else (tamanhos_de_equipe(int(equipe_max)) if horas else [1])
    candidatos: list[Modo] = []
    for n in tamanhos:
        _, equipe = equipe_proporcional(horas, n)
        opcoes_maq: list[dict[str, int]] = []
        if not equip:
            opcoes_maq.append({})
        elif not maquinas_max:
            opcoes_maq.append({e: max(1, int((maquinas or {}).get(e) or 1)) for e in equip})
        else:
            dias_equipe = max((h / (equipe[f] * hd0) for f, h in horas.items() if equipe.get(f)), default=0.0)
            if dias_equipe > 0:
                opcoes_maq.append({e: min(maquinas_max, max(1, _teto(h / (dias_equipe * hd0)))) for e, h in equip.items()})
            opcoes_maq.append({e: maquinas_max for e in equip})
            if not horas:  # só máquinas: um modo por quantidade
                opcoes_maq = [{e: k for e in equip} for k in range(1, maquinas_max + 1)]
        for maq in opcoes_maq:
            eq = dict(equipe)
            if propria and maq and maquinas_max:
                eq[OPERADOR] = eq.get(OPERADOR, 0) + sum(maq.values())
            candidatos.append(Modo(equipe=eq, horas=dict(horas), horas_equipamento=dict(equip), maquinas=maq,
                                   dias_minimos=dias_minimos))
    # tira modos dominados: mais gente (ou máquinas) sem encurtar em nenhuma jornada
    def recursos(m: Modo) -> tuple[int, int]:
        return (sum(m.equipe.values()) + (0 if propria else sum(m.maquinas.values())), sum(m.maquinas.values()))

    modos: list[Modo] = []
    for m in sorted(candidatos, key=recursos):
        dur = [m.duracao(hd) for hd in jornadas]
        if any(all(d2 <= d for d2, d in zip([k.duracao(hd) for hd in jornadas], dur)) for k in modos):
            continue
        modos.append(m)
    return modos


def modos_da_atividade(a: Mapping[str, Any], travada: int | None = None, jornadas: Iterable[float] = (8.8,),
                       maquinas_max: int | None = MAQUINAS_MAX, equipe_max: int | None = None,
                       dias_uteis: int | None = None) -> list[Modo]:
    """Modos de uma atividade da etapa 4 (com limites alterados, para o diagnóstico de prazo)."""
    jornadas = list(jornadas)
    dur = a.get("duracao") or {}
    calc = a.get("calculo") or {}
    execucao = a.get("execucao") or PROPRIA
    tem_horas = bool(a.get("horas_ajustadas") or a.get("horas_equipamento"))
    if dur.get("tipo") == "fixa" or dur.get("unidade") == "corridos":
        return [Modo(dias_corridos=int(dur["dias"]))]
    if dur.get("tipo") == "manual" or dias_uteis:
        equipe = dict(calc.get("equipe") or {}) if execucao != TERCEIRIZADA else {}
        return [Modo(equipe=equipe, dias_uteis=int(dias_uteis or dur["dias"]))]
    if tem_horas:
        return modos_por_horas(a.get("horas_ajustadas") or {}, a.get("horas_equipamento") or {},
                               calc.get("maquinas") or {}, equipe_max or a.get("equipe_max") or EQUIPE_MAX, travada,
                               jornadas, maquinas_max, a.get("dias_concretagem"), execucao != TERCEIRIZADA)
    if dur.get("dias"):
        return [Modo(dias_uteis=int(dur["dias"]), dias_minimos=a.get("dias_concretagem"))]
    return []


def tarefas_da_obra(
    atividades: Iterable[Mapping[str, Any]],
    dependencias: Iterable[Mapping[str, Any]],
    travadas: Mapping[str, int] | None = None,
    jornadas: Iterable[float] = (8.8,),
    maquinas_max: Mapping[str, int] | int | None = MAQUINAS_MAX,
    dividir_terceirizadas: bool = True,
) -> dict[str, Tarefa]:
    """Tarefas a partir do resultado da etapa 4 (`calcular_obra(...)["atividades"]`) e da rede da etapa 3."""
    travadas = travadas or {}
    jornadas = list(jornadas)
    tarefas: dict[str, Tarefa] = {}
    for a in atividades:
        if a["tipo"] == "indireta":
            continue
        cod = a["codigo"]
        maq_max = maquinas_max.get(cod, MAQUINAS_MAX) if isinstance(maquinas_max, Mapping) else maquinas_max
        execucao = a.get("execucao") or PROPRIA
        modos = modos_da_atividade(a, travadas.get(cod), jornadas, maq_max)
        if not modos:
            raise ValueError(f"{cod}: atividade sem duração (resolva as pendências da etapa 4).")
        tarefas[cod] = Tarefa(
            codigo=cod, modos=modos, tipo=a["tipo"], execucao=execucao, nome=a.get("nome"), etapa=a.get("etapa"),
            ordem=a.get("ordem_biblioteca", 0), travada=travadas.get(cod), funcao_principal=a.get("funcao_principal"),
            equipe_max=a.get("equipe_max") or EQUIPE_MAX, maquinas_max=maq_max,
            partes_max=PARTES_MAX if (execucao == TERCEIRIZADA and dividir_terceirizadas) else 1,
        )
    for d in dependencias:
        if d["atividade"] in tarefas and d["depende_de"] in tarefas:
            tarefas[d["atividade"]].deps.append(Elo(d["depende_de"], int(d.get("espera_dias") or 0),
                                                    d.get("tipo") or "TI", d.get("unidade") or "d"))
    return tarefas
