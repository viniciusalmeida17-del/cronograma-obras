"""Tabela de funções (dados/funcoes.xlsx): quais linhas das composições são mão de obra, e de qual função."""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import openpyxl

from leitor_planilha.texto import normalizar, para_numero

RAIZ = Path(__file__).resolve().parent.parent
CAMINHO_FUNCOES = RAIZ / "dados" / "funcoes.xlsx"
CAMINHO_PALAVRAS = RAIZ / "dados" / "palavras_subcomposicao.txt"
CAMINHO_REFERENCIAS = RAIZ / "dados" / "produtividade_referencia.xlsx"

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


OPERADOR = "Operador/Motorista"   # vem com as máquinas (1 por máquina em atividade própria)


@dataclass
class TabelaFuncoes:
    regras: list[RegraFuncao]
    # aba "Juntar funções": funcao -> função que pode fazer o serviço; e as que juntam por padrão
    juntar_possivel: dict[str, str] = field(default_factory=dict)
    juntar_padrao: dict[str, str] = field(default_factory=dict)

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

    @property
    def assinatura(self) -> str:
        """Muda quando o conteúdo da tabela muda (regras ou aba Juntar funções): as obras salvas são reprocessadas."""
        conteudo = json.dumps([[(r.ordem, r.termos, r.funcao, r.categoria) for r in self.regras],
                               sorted(self.juntar_possivel.items()), sorted(self.juntar_padrao.items())],
                              ensure_ascii=False)
        return hashlib.sha1(conteudo.encode("utf-8")).hexdigest()[:16]


def carregar_funcoes(caminho: str | os.PathLike | None = None) -> TabelaFuncoes:
    caminho = Path(caminho or os.environ.get("CRONOGRAMA_FUNCOES", CAMINHO_FUNCOES))
    try:
        wb = openpyxl.load_workbook(caminho, read_only=True, data_only=True)
    except Exception as exc:
        raise ErroFuncoes([{"linha": None, "mensagem": f"Não foi possível abrir {caminho}: {exc}"}])
    try:
        ws = wb["Reconhecimento"] if "Reconhecimento" in wb.sheetnames else wb.worksheets[0]
        linhas = list(ws.iter_rows(values_only=True))
        aba_juntar = next((n for n in wb.sheetnames if normalizar(n) == "JUNTAR FUNCOES"), None)
        linhas_juntar = list(wb[aba_juntar].iter_rows(values_only=True)) if aba_juntar else []
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
    possivel, padrao = _ler_juntar(linhas_juntar, {r.funcao for r in regras}, erros)
    if erros:
        raise ErroFuncoes(erros)
    regras.sort(key=lambda r: r.ordem)
    return TabelaFuncoes(regras, possivel, padrao)


def _ler_juntar(linhas: list[tuple], funcoes: set[str], erros: list[dict[str, Any]]) -> tuple[dict[str, str], dict[str, str]]:
    """Aba "Juntar funções": funcao | pode_ser_feita_por | juntar_por_padrao (sim/não)."""
    if not linhas:
        return {}, {}
    cab = {normalizar(v).lower(): i for i, v in enumerate(linhas[0]) if v is not None}
    if not {"funcao", "pode_ser_feita_por"} <= set(cab):
        erros.append({"linha": 1, "mensagem": "Aba Juntar funções: colunas funcao e pode_ser_feita_por não encontradas."})
        return {}, {}
    possivel, padrao = {}, {}
    for n, l in enumerate(linhas[1:], start=2):
        val = lambda c: l[cab[c]] if c in cab and cab[c] < len(l) else None  # noqa: E731
        f = str(val("funcao") or "").strip()
        destino = str(val("pode_ser_feita_por") or "").strip()
        if not f or not destino or destino in ("—", "-"):
            continue
        if destino == f:
            erros.append({"linha": n, "mensagem": f"Juntar funções: {f} não pode ser juntada com ela mesma."})
            continue
        possivel[f] = destino
        if normalizar(val("juntar_por_padrao")) in ("SIM", "S", "1", "TRUE", "X"):
            padrao[f] = destino
    return possivel, padrao


def juntar_horas(horas: dict[str, float], juntar: dict[str, str]) -> dict[str, float]:
    """Passa as horas de cada função juntada para a função de destino (em cadeia, sem ciclo)."""
    res: dict[str, float] = {}
    for f, h in horas.items():
        destino, vistos = f, {f}
        while destino in juntar and juntar[destino] not in vistos:
            destino = juntar[destino]
            vistos.add(destino)
        res[destino] = res.get(destino, 0.0) + h
    return res


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


def carregar_referencias(funcoes: TabelaFuncoes, caminho: str | os.PathLike | None = None) -> dict[str, dict[str, float]]:
    """dados/produtividade_referencia.xlsx: código -> {função: horas por unidade}.

    A descrição da mão de obra vira função pela tabela de funções (ex.: operador de betoneira → Servente).
    Arquivo ausente = sem referências.
    """
    caminho = Path(caminho or os.environ.get("CRONOGRAMA_REFERENCIAS", CAMINHO_REFERENCIAS))
    if not caminho.exists():
        return {}
    wb = openpyxl.load_workbook(caminho, read_only=True, data_only=True)
    try:
        ws = wb["Referencias"] if "Referencias" in wb.sheetnames else wb.worksheets[0]
        linhas = list(ws.iter_rows(values_only=True))
    finally:
        wb.close()
    if not linhas:
        return {}
    cab = {normalizar(v).lower(): i for i, v in enumerate(linhas[0]) if v is not None}
    col_mo = next((i for k, i in cab.items() if k.startswith("mao_de_obra") or k.startswith("mao de obra")), None)
    col_h = next((i for k, i in cab.items() if k.startswith("horas")), None)
    if "codigo" not in cab or col_mo is None or col_h is None:
        raise ErroFuncoes([{"linha": 1, "mensagem": f"{caminho.name}: colunas codigo, mao_de_obra e horas_por_unidade não encontradas."}])
    res: dict[str, dict[str, float]] = {}
    for l in linhas[1:]:
        codigo = normalizar(l[cab["codigo"]]).replace(" ", "") if cab["codigo"] < len(l) else ""
        h = para_numero(l[col_h]) if col_h < len(l) else None
        regra = funcoes.identificar(l[col_mo]) if col_mo < len(l) else None
        if not codigo or not h or regra is None or regra.categoria != PRODUCAO or regra.funcao == OPERADOR:
            continue
        res.setdefault(codigo, {})
        res[codigo][regra.funcao] = res[codigo].get(regra.funcao, 0.0) + float(h)
    return res