"""Importação da tabela analítica de composições do SINAPI (CAIXA) para o banco de coeficientes.

O usuário baixa no site da CAIXA a planilha de composições analíticas (estado e mês que quiser) e anexa.
As colunas são achadas pelo texto do cabeçalho (o formato muda de tempos em tempos); se alguma não for
reconhecida, a tela pede o mapeamento manual, como no leitor de planilha.

Para cada composição: horas por unidade das linhas de mão de obra (pela funcoes.xlsx, unidade H),
expandindo as composições auxiliares (item do tipo COMPOSIÇÃO) em profundidade.
"""
from __future__ import annotations

import os
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

import openpyxl

from leitor_planilha.texto import normalizar, para_numero

from .funcoes import INDIRETA, OPERADOR, TabelaFuncoes, unidade_de_mao_de_obra, unidade_norm

CAMPOS_SINAPI = ("codigo_composicao", "tipo_item", "codigo_item", "descricao_item", "unidade_item", "coeficiente")
ROTULOS_SINAPI = {
    "codigo_composicao": "Código da composição", "tipo_item": "Tipo do item", "codigo_item": "Código do item",
    "descricao_item": "Descrição do item", "unidade_item": "Unidade do item", "coeficiente": "Coeficiente",
}
# textos aceitos no cabeçalho (sem acento, maiúsculas), do mais específico para o mais genérico
SINONIMOS = {
    "codigo_composicao": ("CODIGO DA COMPOSICAO", "CODIGO COMPOSICAO", "COD COMPOSICAO", "CODIGO DA CPU"),
    "tipo_item": ("TIPO ITEM", "TIPO DO ITEM", "TIPO DE ITEM", "TIPO"),
    "codigo_item": ("CODIGO ITEM", "CODIGO DO ITEM", "COD ITEM", "CODIGO DO INSUMO/COMPOSICAO", "CODIGO INSUMO"),
    "descricao_item": ("DESCRICAO ITEM", "DESCRICAO DO ITEM", "DESCRICAO DO INSUMO/COMPOSICAO", "DESCRICAO"),
    "unidade_item": ("UNIDADE ITEM", "UNIDADE DO ITEM", "UNIDADE", "UND", "UN"),
    "coeficiente": ("COEFICIENTE", "COEF", "QUANTIDADE", "CONSUMO"),
}
LINHAS_CABECALHO = 40


class ErroSinapi(Exception):
    pass


@dataclass
class ResultadoSinapi:
    aba: str | None
    linha_cabecalho: int | None
    cabecalho: list[str]
    mapeamento: dict[str, int]
    faltando: list[str]
    composicoes: dict[str, dict[str, float]] = field(default_factory=dict)  # código -> {funcao: h/un}
    n_composicoes_lidas: int = 0
    n_linhas: int = 0

    @property
    def precisa_mapeamento(self) -> bool:
        return bool(self.faltando)


def _mapear(cabecalho: list[str]) -> dict[str, int]:
    norm = [normalizar(c).replace(".", "") if c is not None else "" for c in cabecalho]
    mapa: dict[str, int] = {}
    usados: set[int] = set()
    for campo in CAMPOS_SINAPI:
        for sinonimo in SINONIMOS[campo]:
            for i, texto in enumerate(norm):
                if i in usados or not texto:
                    continue
                if texto == sinonimo or (len(sinonimo) > 6 and texto.startswith(sinonimo)):
                    mapa[campo] = i
                    usados.add(i)
                    break
            if campo in mapa:
                break
    return mapa


def _achar_cabecalho(ws) -> tuple[int | None, list[str], dict[str, int]]:
    melhor: tuple[int | None, list[str], dict[str, int]] = (None, [], {})
    for n, linha in enumerate(ws.iter_rows(min_row=1, max_row=LINHAS_CABECALHO, values_only=True), start=1):
        cab = ["" if v is None else str(v) for v in linha]
        mapa = _mapear(cab)
        if melhor[0] is None and sum(1 for v in cab if v.strip()) >= 5 and \
                all(not v.replace(".", "").isdigit() for v in cab if v.strip()):
            melhor = (n, cab, {})  # provável cabeçalho, para a tela de mapeamento
        if len(mapa) >= 3 and len(mapa) > len(melhor[2]):
            melhor = (n, cab, mapa)
        if len(mapa) == len(CAMPOS_SINAPI):
            break
    return melhor


def ler_sinapi(caminho: str | os.PathLike, funcoes: TabelaFuncoes, mapeamento: dict[str, int] | None = None,
               aba: str | None = None, linha_cabecalho: int | None = None) -> ResultadoSinapi:
    """Lê a tabela analítica e calcula as horas por unidade de cada composição.

    Sem `mapeamento`, acha a aba e as colunas pelo cabeçalho. Se faltar coluna, devolve o resultado com
    `faltando` (e o cabeçalho para a tela de mapeamento), sem composições.
    """
    try:
        wb = openpyxl.load_workbook(caminho, read_only=True, data_only=True)
    except Exception as exc:
        raise ErroSinapi(f"Não foi possível abrir o arquivo: {exc}")
    try:
        abas = [aba] if aba else wb.sheetnames
        escolhida, n_cab, cab, mapa = None, None, [], {}
        for nome in abas:
            if nome not in wb.sheetnames:
                raise ErroSinapi(f"Aba '{nome}' não encontrada.")
            ws = wb[nome]
            if linha_cabecalho:
                linha = next(ws.iter_rows(min_row=linha_cabecalho, max_row=linha_cabecalho, values_only=True), ())
                c = ["" if v is None else str(v) for v in linha]
                n, m = linha_cabecalho, _mapear(c)
            else:
                n, c, m = _achar_cabecalho(ws)
            if len(m) > len(mapa) or escolhida is None:
                escolhida, n_cab, cab, mapa = nome, n, c, m
            if len(m) == len(CAMPOS_SINAPI):
                break
        if mapeamento:
            mapa = {k: int(v) for k, v in mapeamento.items() if k in CAMPOS_SINAPI and v not in (None, "")}
        faltando = [c for c in CAMPOS_SINAPI if c not in mapa]
        res = ResultadoSinapi(escolhida, n_cab, cab, mapa, faltando)
        if faltando:
            return res
        linhas = wb[escolhida].iter_rows(min_row=(n_cab or 0) + 1, values_only=True)
        itens: dict[str, list[tuple[str, str, Any, Any, float]]] = defaultdict(list)
        for linha in linhas:
            val = lambda c: linha[mapa[c]] if mapa[c] < len(linha) else None  # noqa: E731
            comp = normalizar(val("codigo_composicao")).replace(" ", "")
            cod_item = normalizar(val("codigo_item")).replace(" ", "")
            tipo = normalizar(val("tipo_item"))
            coef = para_numero(val("coeficiente"))
            if not comp or not cod_item or coef is None:
                continue  # linha de título da composição, vazia ou de total
            if comp.endswith(".0"):
                comp = comp[:-2]
            if cod_item.endswith(".0"):
                cod_item = cod_item[:-2]
            itens[comp].append((tipo, cod_item, val("descricao_item"), val("unidade_item"), float(coef)))
            res.n_linhas += 1
    finally:
        wb.close()
    res.n_composicoes_lidas = len(itens)
    res.composicoes = horas_das_composicoes(itens, funcoes)
    return res


def horas_das_composicoes(itens: dict[str, list[tuple[str, str, Any, Any, float]]], funcoes: TabelaFuncoes
                          ) -> dict[str, dict[str, float]]:
    """Horas por unidade de cada composição, expandindo as auxiliares (sem ciclo)."""
    memo: dict[str, dict[str, float]] = {}

    def horas(codigo: str, pilha: tuple[str, ...]) -> dict[str, float]:
        if codigo in memo:
            return memo[codigo]
        tot: dict[str, float] = defaultdict(float)
        for tipo, cod_item, desc, un, coef in itens.get(codigo, []):
            regra = funcoes.identificar(desc)
            if regra and unidade_de_mao_de_obra(un) and unidade_norm(un) != "MES":
                if regra.categoria != INDIRETA and regra.funcao != OPERADOR:
                    tot[regra.funcao] += coef
                continue
            if cod_item in itens and cod_item not in pilha and (not tipo or tipo.startswith("COMPOSI")):
                for f, h in horas(cod_item, pilha + (cod_item,)).items():
                    tot[f] += h * coef
        memo[codigo] = {f: round(h, 6) for f, h in tot.items() if h > 0}
        return memo[codigo]

    return {c: h for c in itens if (h := horas(c, (c,)))}
