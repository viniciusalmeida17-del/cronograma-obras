"""Leitura dos dados gerais da obra (acima do cabeçalho)."""
from __future__ import annotations

import re
from typing import Any, Sequence

from .texto import limpar_texto, normalizar, para_numero

Grade = Sequence[Sequence[Any]]

_UNIDADES_PRAZO = {
    "DIA": "dias",
    "DIAS": "dias",
    "SEMANA": "semanas",
    "SEMANAS": "semanas",
    "MES": "meses",
    "MESES": "meses",
    "ANO": "anos",
    "ANOS": "anos",
}


def interpretar_prazo(valor: Any) -> tuple[float | None, str | None]:
    """"12 MESES" -> (12, "meses"); "180 dias corridos" -> (180, "dias"); 12 -> (12, None)."""
    if valor is None:
        return None, None
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        return float(valor), None
    t = normalizar(valor)
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*([A-Z]+)?", t)
    if not m:
        return None, None
    numero = float(m.group(1).replace(",", "."))
    unidade = _UNIDADES_PRAZO.get(m.group(2) or "")
    return numero, unidade


def interpretar_bdi(valor: Any) -> float | None:
    """BDI como fração. Aceita 0.2522, "25,22%" ou 25.22 (assumido como %)."""
    numero = para_numero(valor)
    if numero is None:
        return None
    if numero > 1:
        numero = numero / 100
    return round(numero, 6)


def _celula(grade: Grade, r: int, c: int) -> Any:
    if 0 <= r < len(grade) and 0 <= c < len(grade[r]):
        return grade[r][c]
    return None


def _vazio(v: Any) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def _abaixo(grade: Grade, r: int, c: int, ate: int, max_saltos: int = 2) -> tuple[Any, int] | None:
    for rr in range(r + 1, min(ate, r + 1 + max_saltos)):
        v = _celula(grade, rr, c)
        if not _vazio(v):
            return v, rr
    return None


def _a_direita(grade: Grade, r: int, c: int) -> tuple[Any, int] | None:
    linha = grade[r]
    for cc in range(c + 1, len(linha)):
        if not _vazio(linha[cc]):
            return linha[cc], cc
    return None


def _procurar_rotulo(grade: Grade, ate: int, teste) -> tuple[int, int] | None:
    for r in range(min(ate, len(grade))):
        for c, v in enumerate(grade[r]):
            if isinstance(v, str) and teste(normalizar(v)):
                return r, c
    return None


def ler_dados_obra(grade: Grade, linha_cabecalho: int) -> dict[str, Any]:
    """Procura os rótulos acima do cabeçalho. `grade` é a lista de linhas (0-based)."""
    obra: dict[str, Any] = {
        "nome": None,
        "prazo_valor": None,
        "prazo_unidade": None,
        "prazo_texto": None,
        "bdi": None,
        "desoneracao": None,
        "referencias": [],
    }
    ate = linha_cabecalho

    # Nome da obra: "OBRA:" -> célula à direita (ou texto após o rótulo na mesma célula).
    pos = _procurar_rotulo(grade, ate, lambda t: re.match(r"^OBRA\b\s*:?", t) is not None)
    if pos:
        r, c = pos
        bruto = str(grade[r][c])
        resto = re.sub(r"^\s*OBRA\s*:?", "", bruto, flags=re.IGNORECASE).strip()
        achado = (resto, c) if resto else _a_direita(grade, r, c)
        if achado:
            obra["nome"] = limpar_texto(achado[0])

    # Prazo: célula abaixo de "PRAZO..." (ou à direita).
    pos = _procurar_rotulo(grade, ate, lambda t: t.startswith("PRAZO"))
    if pos:
        r, c = pos
        achado = _abaixo(grade, r, c, ate) or _a_direita(grade, r, c)
        if achado:
            obra["prazo_texto"] = limpar_texto(achado[0])
            obra["prazo_valor"], obra["prazo_unidade"] = interpretar_prazo(achado[0])

    # BDI: célula abaixo de "BDI ..." (fração).
    pos = _procurar_rotulo(grade, ate, lambda t: t.startswith("BDI"))
    if pos:
        r, c = pos
        achado = _abaixo(grade, r, c, ate) or _a_direita(grade, r, c)
        if achado:
            obra["bdi"] = interpretar_bdi(achado[0])

    # Tipo de desoneração: célula abaixo de "TIPO" (ou rótulo com "DESONERA").
    pos = _procurar_rotulo(grade, ate, lambda t: t in ("TIPO", "TIPO:") or t.startswith("DESONERA"))
    if pos:
        r, c = pos
        achado = _abaixo(grade, r, c, ate) or _a_direita(grade, r, c)
        if achado:
            obra["desoneracao"] = limpar_texto(achado[0])

    # Referências de preço: lista abaixo de "REFERÊNCIAS".
    pos = _procurar_rotulo(grade, ate, lambda t: t.startswith("REFERENCIA"))
    if pos:
        r, c = pos
        refs = []
        for rr in range(r + 1, ate):
            v = _celula(grade, rr, c)
            if _vazio(v):
                break
            refs.append(limpar_texto(v))
        obra["referencias"] = refs

    return obra
