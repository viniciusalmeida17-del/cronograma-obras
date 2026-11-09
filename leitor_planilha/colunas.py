"""Localização da linha de cabeçalho e mapeamento das colunas pelo nome."""
from __future__ import annotations

import re
from typing import Any, Callable, Sequence

from .texto import normalizar

CAMPOS = (
    "item",
    "base",
    "codigo",
    "descricao",
    "unidade",
    "quantidade",
    "preco_unit",
    "preco_unit_bdi",
    "total",
    "total_bdi",
)
OBRIGATORIOS = ("item", "descricao", "unidade", "quantidade")

ROTULOS_CAMPOS = {
    "item": "Item",
    "base": "Base / Referência",
    "codigo": "Código",
    "descricao": "Descrição",
    "unidade": "Unidade",
    "quantidade": "Quantidade",
    "preco_unit": "Valor unitário",
    "preco_unit_bdi": "Valor unitário (com BDI)",
    "total": "Custo total",
    "total_bdi": "Custo total (com BDI)",
}

LINHAS_BUSCA_CABECALHO = 30


def _palavras(texto: str) -> list[str]:
    return [p for p in re.split(r"[^A-Z0-9%]+", texto) if p]


def _primeira_palavra_em(opcoes: set[str]) -> Callable[[str], bool]:
    def teste(t: str) -> bool:
        p = _palavras(t)
        return bool(p) and p[0] in opcoes

    return teste


def _unitario(com_bdi: bool) -> Callable[[str], bool]:
    def teste(t: str) -> bool:
        if not re.search(r"\b(VALOR|PRECO|CUSTO)\s+UNIT", t):
            return False
        return ("BDI" in t) == com_bdi

    return teste


def _total(com_bdi: bool) -> Callable[[str], bool]:
    def teste(t: str) -> bool:
        if not re.search(r"\b(CUSTO|VALOR|PRECO)\s+TOTAL", t) and t != "TOTAL":
            return False
        return ("BDI" in t) == com_bdi

    return teste


# Ordem importa: campos mais específicos primeiro.
_TESTES: list[tuple[str, Callable[[str], bool]]] = [
    ("item", _primeira_palavra_em({"ITEM", "ITENS"})),
    ("codigo", _primeira_palavra_em({"CODIGO", "COD"})),
    ("base", _primeira_palavra_em({"REF", "REFERENCIA", "FONTE", "BASE"})),
    ("descricao", _primeira_palavra_em({"SERVICO", "SERVICOS", "DESCRICAO", "DISCRIMINACAO"})),
    ("unidade", _primeira_palavra_em({"UND", "UNID", "UNIDADE", "UN"})),
    ("quantidade", _primeira_palavra_em({"QUANT", "QUANTIDADE", "QTD", "QTDE"})),
    ("preco_unit_bdi", _unitario(True)),
    ("preco_unit", _unitario(False)),
    ("total_bdi", _total(True)),
    ("total", _total(False)),
]


def campo_do_cabecalho(texto: Any) -> str | None:
    t = normalizar(texto)
    if not t:
        return None
    for campo, teste in _TESTES:
        if teste(t):
            return campo
    return None


def mapear_colunas(linha: Sequence[Any]) -> dict[str, int]:
    """Mapeia campo -> índice (0-based) da coluna. A primeira coluna que casa vence."""
    mapa: dict[str, int] = {}
    for idx, valor in enumerate(linha):
        campo = campo_do_cabecalho(valor)
        if campo and campo not in mapa:
            mapa[campo] = idx
    return mapa


def eh_cabecalho(linha: Sequence[Any]) -> bool:
    mapa = mapear_colunas(linha)
    return all(c in mapa for c in OBRIGATORIOS)


def achar_cabecalho(linhas: Sequence[Sequence[Any]], limite: int = LINHAS_BUSCA_CABECALHO) -> int | None:
    """Índice (0-based) da linha de cabeçalho nas primeiras `limite` linhas, ou None."""
    for i, linha in enumerate(linhas[:limite]):
        if eh_cabecalho(linha):
            return i
    return None


def pontuacao_cabecalho(linha: Sequence[Any]) -> int:
    """Quantos campos (de todos) a linha reconhece — usado para sugerir a linha mais provável."""
    return len(mapear_colunas(linha))
