"""Funções de grafo: ciclo e ordenação topológica.

O grafo é um dicionário  atividade -> lista de atividades das quais ela depende.
"""
from __future__ import annotations

from typing import Iterable, Mapping, Sequence


def achar_ciclo(deps: Mapping[str, Iterable[str]]) -> list[str] | None:
    """Retorna o caminho de um ciclo ou None. ['A', 'B', 'A'] = A depende de B, que depende de A."""
    BRANCO, CINZA, PRETO = 0, 1, 2
    cor = {n: BRANCO for n in deps}
    pilha: list[str] = []

    def visitar(n: str) -> list[str] | None:
        cor[n] = CINZA
        pilha.append(n)
        for d in deps.get(n, ()):
            if d not in cor:
                continue  # referência externa: validada em outro lugar
            if cor[d] == CINZA:
                return pilha[pilha.index(d):] + [d]
            if cor[d] == BRANCO:
                achado = visitar(d)
                if achado:
                    return achado
        pilha.pop()
        cor[n] = PRETO
        return None

    for n in deps:
        if cor[n] == BRANCO:
            achado = visitar(n)
            if achado:
                return achado  # cada uma depende da seguinte
    return None


def ordem_topologica(deps: Mapping[str, Iterable[str]], preferencia: Sequence[str] | None = None) -> list[str]:
    """Ordem em que as atividades podem ser executadas (Kahn).

    Entre as que estão prontas ao mesmo tempo, segue a ordem de `preferencia`
    (normalmente a ordem da biblioteca, que acompanha as etapas da obra).
    """
    posicao = {n: i for i, n in enumerate(preferencia or [])}
    nos = list(deps)
    pendentes = {n: {d for d in deps[n] if d in deps} for n in nos}
    sucessores: dict[str, list[str]] = {n: [] for n in nos}
    for n, ds in pendentes.items():
        for d in ds:
            sucessores[d].append(n)

    chave = lambda n: (posicao.get(n, len(posicao)), n)  # noqa: E731
    prontos = sorted((n for n in nos if not pendentes[n]), key=chave)
    ordem: list[str] = []
    while prontos:
        n = prontos.pop(0)
        ordem.append(n)
        for s in sucessores[n]:
            pendentes[s].discard(n)
            if not pendentes[s]:
                prontos.append(s)
        prontos.sort(key=chave)
    if len(ordem) != len(nos):
        ciclo = achar_ciclo(deps)
        raise ValueError("Ciclo nas dependências: " + " → ".join(ciclo or []))
    return ordem
