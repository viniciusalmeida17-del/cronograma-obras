"""Tabela de funções (dados/funcoes.xlsx): quais linhas das composições são mão de obra, e de qual função."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import openpyxl

from leitor_planilha.texto import normalizar, para_numero

RAIZ = Path(__file__).resolve().parent.parent
CAMINHO_FUNCOES = RAIZ / "dados" / "funcoes.xlsx"
CAMINHO_PALAVRAS = RAIZ / "dados" / "palavras_subcomposicao.txt"

PRODUCAO = "producao"
INDIRETA = "indireta"
CATEGORIAS = (PRODUCAO, INDIRETA)

UNIDADES_MAO_DE_OBRA = {"H", "HORA", "HORAS", "MES", ""}
UNIDADES_EQUIPAMENTO = {"CHP", "CHI"}


class ErroFuncoes(Exception):
    def __init__(self, erros: list[dict[str, Any]]):
        self.erros = erros
        super().__init__("Tabela de funções inválida: " + "; ".join(
            (f"linha {e['linha']}: " if e.get("linha") else "") + e["mensagem"] for e in erros[:10]))


@dataclass
class RegraFuncao:
    ordem: int
    termos: list[str]
    funcao: str
    categoria: str
    linha_excel: int

    def casa(self, descricao_norm: str) -> bool:
        primeiro, *outros = self.termos
        return descricao_norm.startswith(primeiro) and all(t in descricao_norm for t in outros)


@dataclass
class TabelaFuncoes:
    regras: list[RegraFuncao]

    def identificar(self, descricao: Any) -> RegraFuncao | None:
        d = normalizar(descricao)
        if not d:
            return None
        for r in self.regras:
            if r.casa(d):
                return r
        return None

    def funcoes(self) -> list[str]:
        return list(dict.fromkeys(r.funcao for r in self.regras))


def carregar_funcoes(caminho: str | os.PathLike | None = None) -> TabelaFuncoes:
    caminho = Path(caminho or os.environ.get("CRONOGRAMA_FUNCOES", CAMINHO_FUNCOES))
    try:
        wb = openpyxl.load_workbook(caminho, read_only=True, data_only=True)
    except Exception as exc:
        raise ErroFuncoes([{"linha": None, "mensagem": f"Não foi possível abrir {caminho}: {exc}"}])
    try:
        ws = wb["Reconhecimento"] if "Reconhecimento" in wb.sheetnames else wb.worksheets[0]
        linhas = list(ws.iter_rows(values_only=True))
    finally:
        wb.close()
    if not linhas:
        raise ErroFuncoes([{"linha": None, "mensagem": "Aba vazia."}])
    cab = {normalizar(v).lower(): i for i, v in enumerate(linhas[0]) if v is not None}
    faltando = [c for c in ("ordem", "termos_na_descricao", "funcao", "categoria") if c not in cab]
    if faltando:
        raise ErroFuncoes([{"linha": 1, "mensagem": "Colunas não encontradas: " + ", ".join(faltando)}])
    regras, erros = [], []
    for n, l in enumerate(linhas[1:], start=2):
        val = lambda c: l[cab[c]] if cab[c] < len(l) else None  # noqa: E731
        termos_txt = val("termos_na_descricao")
        if termos_txt is None and val("funcao") is None:
            continue
        termos = [normalizar(t) for t in str(termos_txt or "").split("&") if normalizar(t)]
        funcao = str(val("funcao") or "").strip()
        categoria = normalizar(val("categoria")).lower() or PRODUCAO
        if not termos:
            erros.append({"linha": n, "mensagem": "termos_na_descricao vazio."})
        if not funcao:
            erros.append({"linha": n, "mensagem": "funcao vazia."})
        if categoria not in CATEGORIAS:
            erros.append({"linha": n, "mensagem": f"categoria '{categoria}' inválida (use producao ou indireta)."})
        ordem = para_numero(val("ordem"))
        if termos and funcao and categoria in CATEGORIAS:
            regras.append(RegraFuncao(int(ordem) if ordem is not None else n, termos, funcao, categoria, n))
    if erros:
        raise ErroFuncoes(erros)
    regras.sort(key=lambda r: r.ordem)
    return TabelaFuncoes(regras)


def carregar_palavras_subcomposicao(caminho: str | os.PathLike | None = None) -> list[str]:
    caminho = Path(caminho or os.environ.get("CRONOGRAMA_PALAVRAS", CAMINHO_PALAVRAS))
    palavras = []
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("#"):
            palavras.append(normalizar(linha))
    return palavras


# --------------------------------------------------------------------------- classificação de linhas


def unidade_norm(unidade: Any) -> str:
    return re.sub(r"\s+", "", normalizar(unidade))


def eh_equipamento(descricao: Any, unidade: Any) -> bool:
    d = normalizar(descricao)
    return unidade_norm(unidade) in UNIDADES_EQUIPAMENTO or d.startswith(("CHP", "CHI"))


def unidade_de_mao_de_obra(unidade: Any) -> bool:
    """H, HORA, MÊS, vazia ou um número (algumas composições SETOP repetem a quantidade na unidade)."""
    u = unidade_norm(unidade)
    if u in UNIDADES_MAO_DE_OBRA:
        return True
    if isinstance(unidade, (int, float)) and not isinstance(unidade, bool):
        return True
    return para_numero(u) is not None


def nome_equipamento(descricao: Any) -> str:
    """'ESCAVADEIRA ... - CHP DIURNO. AF_06/2014' e '... - CHI DIURNO...' -> mesmo nome."""
    d = re.sub(r"\s+", " ", str(descricao or "")).strip()
    d = re.sub(r"^(CHP|CHI)\s*[/\-:]?\s*", "", d, flags=re.IGNORECASE)
    d = re.split(r"\s*-\s*CH[PI]\b", d, flags=re.IGNORECASE)[0]
    d = re.split(r"\.?\s*AF_\d", d)[0]
    return d.strip(" .-") or str(descricao)


def eh_subcomposicao(descricao: Any, palavras: list[str]) -> bool:
    """A descrição indica um serviço (e não um material)?

    O trecho depois de " PARA " é ignorado: ele diz a finalidade de um material
    ("BLOCO CERÂMICO ... PARA ALVENARIA", "TELA ... PARA ALVENARIA").
    Também compara palavras inteiras ("MASSARANDUBA" não é "MASSA") e ignora a palavra
    seguida de ":" (atributo de material: "MESA (APLICAÇÃO: ESCRITÓRIO...)").
    """
    d = normalizar(descricao)
    d = re.split(r"\bPARA\b", d, maxsplit=1)[0]
    return any(re.search(rf"\b{re.escape(p)}\b(?!\s*:)", d) for p in palavras)
