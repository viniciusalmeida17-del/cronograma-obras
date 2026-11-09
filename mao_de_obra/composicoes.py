"""Leitura das composições de custo que vêm na mesma pasta de trabalho da planilha.

Formato A — abas por disciplina: bloco começa numa linha com o número do item na coluna B e os
cabeçalhos UNIDADE / CONSUMO / PREÇO / PREÇO TOTAL; termina na linha com "PREÇO TOTAL" na coluna de preço.

Formato B — aba CPU (composições próprias): bloco começa na célula "Item:" (código da composição à
direita; número do item duas linhas abaixo, na coluna B), com seções MÃO-DE-OBRA, EQUIPAMENTO e
MATERIAL / SERVIÇO, e termina na linha TOTAL. Só é usado para itens sem composição no formato A.
"""
from __future__ import annotations

import os
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

import openpyxl

from leitor_planilha.texto import limpar_texto, normalizar, para_numero, texto_item

FORMATO_A = "A"
FORMATO_B = "B"
_RE_ITEM = re.compile(r"^\d+(\.\d+)*$")
SECOES_B = {"MAO-DE-OBRA": "mao_de_obra", "MAO DE OBRA": "mao_de_obra", "EQUIPAMENTO": "equipamento",
            "EQUIPAMENTOS": "equipamento", "MATERIAL / SERVICO": "material", "MATERIAL/SERVICO": "material",
            "MATERIAIS": "material", "MATERIAL": "material"}


@dataclass
class LinhaComposicao:
    codigo: str | None
    descricao: str | None
    unidade: Any            # texto original (pode ser número em algumas SETOP)
    coeficiente: float
    preco: float | None
    total: float | None
    linha_excel: int
    secao: str | None = None  # só formato B


@dataclass
class Composicao:
    item: str
    descricao: str | None
    aba: str
    linha_excel: int
    formato: str
    codigo: str | None = None
    linhas: list[LinhaComposicao] = field(default_factory=list)


@dataclass
class ResultadoComposicoes:
    composicoes: dict[str, Composicao]           # item -> composição escolhida (A tem prioridade)
    abas: dict[str, dict[str, int]]              # aba -> {"A": n, "B": n}
    alertas: list[str] = field(default_factory=list)

    def resumo_abas(self) -> list[dict[str, Any]]:
        return [{"aba": a, "formato_a": c.get(FORMATO_A, 0), "formato_b": c.get(FORMATO_B, 0)}
                for a, c in self.abas.items() if sum(c.values())]


def _txt(v: Any) -> str:
    return normalizar(v)


def codigo_texto(v: Any) -> str | None:
    """Código de insumo como texto: 92761 (número do Excel) -> '92761'."""
    return limpar_texto(v)


def _numero(v: Any) -> float | None:
    """'1,2434000' -> 1.2434; '4.789,18' -> 4789.18; '1.6898' -> 1.6898; 0.5 -> 0.5."""
    return para_numero(v)


# --------------------------------------------------------------------------- formato A


def _cabecalho_a(linha: list[Any]) -> dict[str, int] | None:
    t = [_txt(v) for v in linha]
    try:
        unidade = t.index("UNIDADE")
    except ValueError:
        return None
    consumo = next((i for i, x in enumerate(t) if x.startswith("CONSUMO")), None)
    total = next((i for i, x in enumerate(t) if x == "PRECO TOTAL"), None)
    preco = next((i for i, x in enumerate(t) if x == "PRECO"), None)
    if consumo is None or total is None or preco is None or unidade < 2:
        return None
    return {"codigo": unidade - 2, "descricao": unidade - 1, "unidade": unidade,
            "consumo": consumo, "preco": preco, "total": total}


def _ler_formato_a(aba: str, grade: list[list[Any]]) -> list[Composicao]:
    blocos: list[Composicao] = []
    i = 0
    while i < len(grade):
        linha = grade[i]
        col = _cabecalho_a(linha) if len(linha) > 1 else None
        item = texto_item(linha[1]) if col and len(linha) > 1 else None
        if not (col and item and _RE_ITEM.match(item)):
            i += 1
            continue
        comp = Composicao(item=item, descricao=limpar_texto(linha[2]) if len(linha) > 2 else None,
                          aba=aba, linha_excel=i + 1, formato=FORMATO_A)
        j = i + 1
        while j < len(grade):
            l = grade[j] + [None] * (col["total"] + 1 - len(grade[j]))
            if _txt(l[col["preco"]]) == "PRECO TOTAL":
                break
            if _cabecalho_a(l) and texto_item(l[1]):
                j -= 1  # bloco sem linha de fim: próximo bloco começa aqui
                break
            desc, cod = limpar_texto(l[col["descricao"]]), codigo_texto(l[col["codigo"]])
            if desc or cod:
                comp.linhas.append(LinhaComposicao(
                    codigo=cod, descricao=desc, unidade=l[col["unidade"]],
                    coeficiente=_numero(l[col["consumo"]]) or 0.0,
                    preco=_numero(l[col["preco"]]), total=_numero(l[col["total"]]), linha_excel=j + 1,
                ))
            j += 1
        blocos.append(comp)
        i = j + 1
    return blocos


# --------------------------------------------------------------------------- formato B


def _colunas_b(cabecalho: list[Any], seguinte: list[Any]) -> dict[str, int]:
    col: dict[str, int] = {}
    for linha in (cabecalho, seguinte):
        for idx, v in enumerate(linha):
            t = _txt(v)
            if t in ("DESCRICAO", "CATEGORIA FUNCIONAL") and "descricao" not in col:
                col["descricao"] = idx
            elif t.startswith("REF") and "ref" not in col:
                col["ref"] = idx
            elif t.startswith("CODIGO") and "codigo" not in col:
                col["codigo"] = idx
            elif t == "UNIDADE":
                col["unidade"] = idx
            elif t.startswith("QUANT"):
                col["quantidade"] = idx
            elif t.startswith("CUSTO") and "TOTAL" in t:
                col["total"] = idx
            elif t.startswith("CUSTO"):
                col["preco"] = idx
    return col


def _ler_formato_b(aba: str, grade: list[list[Any]]) -> list[Composicao]:
    blocos: list[Composicao] = []
    for i, linha in enumerate(grade):
        for c, v in enumerate(linha):
            if _txt(v) != "ITEM:":
                continue
            codigo = next((codigo_texto(x) for x in linha[c + 1:] if limpar_texto(x)), None)
            if i + 2 >= len(grade) or len(grade[i + 2]) < 2:
                continue
            item = texto_item(grade[i + 2][1])
            if not item or not _RE_ITEM.match(item):
                continue
            descricao = next((limpar_texto(x) for x in (grade[i + 1][2:] if i + 1 < len(grade) else []) if limpar_texto(x)), None)
            comp = Composicao(item=item, descricao=descricao, aba=aba, linha_excel=i + 1,
                              formato=FORMATO_B, codigo=codigo)
            secao, col = None, {}
            for j in range(i + 3, len(grade)):
                l = grade[j]
                b = _txt(l[1]) if len(l) > 1 else ""
                if b == "TOTAL" or _txt(l[c] if c < len(l) else None) == "ITEM:":
                    break
                if b in SECOES_B:
                    secao = SECOES_B[b]
                    col = _colunas_b(l, grade[j + 1] if j + 1 < len(grade) else [])
                    continue
                if not secao or "descricao" not in col:
                    continue
                l = l + [None] * (max(col.values()) + 1 - len(l))
                desc = limpar_texto(l[col["descricao"]])
                if not desc or _txt(desc) in ("DESCRICAO",) or re.match(r"^\d+\.\s*TOTAL", _txt(desc)):
                    continue
                comp.linhas.append(LinhaComposicao(
                    codigo=codigo_texto(l[col["codigo"]]) if "codigo" in col else None, descricao=desc,
                    unidade=l[col["unidade"]] if "unidade" in col else None,
                    coeficiente=_numero(l[col["quantidade"]]) if "quantidade" in col and _numero(l[col["quantidade"]]) is not None else 0.0,
                    preco=_numero(l[col["preco"]]) if "preco" in col else None,
                    total=_numero(l[col["total"]]) if "total" in col else None,
                    linha_excel=j + 1, secao=secao,
                ))
            blocos.append(comp)
    return blocos


# --------------------------------------------------------------------------- leitura geral


def ler_composicoes(caminho: str | os.PathLike, aba_planilha: str | None = None) -> ResultadoComposicoes:
    """Procura composições em todas as abas, menos a da planilha orçamentária."""
    wb = openpyxl.load_workbook(caminho, read_only=True, data_only=True)
    try:
        grades = {}
        for ws in wb.worksheets:
            if aba_planilha is not None and ws.title == aba_planilha:
                continue
            grades[ws.title] = [list(r) for r in ws.iter_rows(values_only=True)]
    finally:
        wb.close()

    por_formato: dict[str, dict[str, Composicao]] = {FORMATO_A: {}, FORMATO_B: {}}
    abas: dict[str, Counter] = {}
    alertas: list[str] = []
    for aba, grade in grades.items():
        abas[aba] = Counter()
        for leitor, formato in ((_ler_formato_a, FORMATO_A), (_ler_formato_b, FORMATO_B)):
            for comp in leitor(aba, grade):
                abas[aba][formato] += 1
                existente = por_formato[formato].get(comp.item)
                if existente:
                    alertas.append(f"Item {comp.item}: composição repetida (formato {formato}) em {existente.aba} "
                                   f"linha {existente.linha_excel} e {aba} linha {comp.linha_excel}; usada a primeira.")
                    continue
                por_formato[formato][comp.item] = comp

    composicoes = dict(por_formato[FORMATO_B])
    composicoes.update(por_formato[FORMATO_A])  # A tem prioridade
    return ResultadoComposicoes(composicoes, {a: dict(c) for a, c in abas.items()}, alertas)
