"""Biblioteca de atividades e regras de reconhecimento (arquivo Excel editado pelo engenheiro)."""
from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import openpyxl

from leitor_planilha.natureza import NATUREZAS
from leitor_planilha.texto import normalizar

from .grafo import achar_ciclo

TIPOS = ("rigida", "flexivel", "aguardar", "indireta")
PERIODOS_ESPECIAIS = ("INICIO_OBRA", "FIM_OBRA")
ABA_ATIVIDADES = "Atividades"
ABA_REGRAS = "Regras"

COLUNAS_ATIVIDADES = ("codigo", "etapa", "atividade", "depende_de", "tipo", "equipe_principal",
                      "observacao", "periodo_de", "periodo_ate")
COLUNAS_REGRAS = ("ordem", "prioridade", "atividade", "termos_no_grupo", "termos_na_descricao", "natureza")

_RE_CODIGO = re.compile(r"^[A-Z]+-\d{2,}$")
_RE_DEPENDENCIA = re.compile(r"^([A-Z]+-\d{2,})(?:\+(\d+)D)?$")

CAMINHO_PADRAO = Path(__file__).resolve().parent.parent / "dados" / "biblioteca_atividades.xlsx"


def caminho_biblioteca() -> Path:
    return Path(os.environ.get("CRONOGRAMA_BIBLIOTECA", CAMINHO_PADRAO))


@dataclass
class Dependencia:
    codigo: str
    espera_dias: int = 0

    def __str__(self) -> str:
        return self.codigo + (f"+{self.espera_dias}d" if self.espera_dias else "")


@dataclass
class Atividade:
    codigo: str
    etapa: str | None
    nome: str
    depende_de: list[Dependencia]
    tipo: str
    equipe_principal: str | None
    observacao: str | None
    periodo_de: str | None
    periodo_ate: str | None
    linha_excel: int
    ordem: int  # posição na biblioteca (ordem das etapas da obra)

    def como_dict(self) -> dict[str, Any]:
        return {
            "codigo": self.codigo, "etapa": self.etapa, "nome": self.nome,
            "depende_de": [{"codigo": d.codigo, "espera_dias": d.espera_dias} for d in self.depende_de],
            "depende_de_texto": formatar_dependencias(self.depende_de),
            "tipo": self.tipo, "equipe_principal": self.equipe_principal, "observacao": self.observacao,
            "periodo_de": self.periodo_de, "periodo_ate": self.periodo_ate,
            "linha_excel": self.linha_excel, "ordem": self.ordem,
        }


@dataclass
class Regra:
    ordem: int
    prioridade: int
    atividade: str
    termos_no_grupo: list[str]
    termos_na_descricao: list[str]
    natureza: str | None
    linha_excel: int


@dataclass
class Biblioteca:
    atividades: dict[str, Atividade]
    regras: list[Regra]
    caminho: str | None = None
    codigos_com_regra: set[str] = field(default_factory=set)

    def __post_init__(self):
        self.codigos_com_regra = {r.atividade for r in self.regras}

    def lista_atividades(self) -> list[dict[str, Any]]:
        return [a.como_dict() for a in self.atividades.values()]


class ErroBiblioteca(Exception):
    """Biblioteca inválida. `erros` é uma lista de dicts {aba, linha, mensagem}."""

    def __init__(self, erros: list[dict[str, Any]]):
        self.erros = erros
        texto = "; ".join(_formatar_erro(e) for e in erros[:10])
        super().__init__(f"Biblioteca de atividades inválida: {texto}")


def _formatar_erro(e: dict[str, Any]) -> str:
    onde = f"aba {e['aba']}, linha {e['linha']}: " if e.get("linha") else (f"aba {e['aba']}: " if e.get("aba") else "")
    return onde + e["mensagem"]


# --------------------------------------------------------------------------- texto


def interpretar_dependencias(texto: Any) -> tuple[list[Dependencia], list[str]]:
    """'FUN-04+3d, PRE-03' -> ([Dependencia('FUN-04', 3), Dependencia('PRE-03', 0)], erros)."""
    deps: list[Dependencia] = []
    erros: list[str] = []
    if texto is None:
        return deps, erros
    for parte in str(texto).split(","):
        p = re.sub(r"\s+", "", parte).upper()
        if not p:
            continue
        m = _RE_DEPENDENCIA.match(p)
        if not m:
            erros.append(f"dependência '{parte.strip()}' em formato inválido (use XXX-00 ou XXX-00+Nd)")
            continue
        deps.append(Dependencia(m.group(1), int(m.group(2) or 0)))
    return deps, erros


def formatar_dependencias(deps: list[Dependencia]) -> str:
    return ", ".join(str(d) for d in deps)


def _termos(valor: Any) -> list[str]:
    if valor is None:
        return []
    termos = []
    for t in str(valor).split("|"):
        ancora = t.strip().startswith("^")
        t = normalizar(t.strip().lstrip("^"))
        if t:
            termos.append(("^" if ancora else "") + t)
    return termos


def _texto(v: Any) -> str | None:
    if v is None:
        return None
    t = str(v).strip()
    return t or None


# --------------------------------------------------------------------------- leitura


def _cabecalho(ws) -> dict[str, int]:
    primeira = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), ())
    return {normalizar(v).lower(): i for i, v in enumerate(primeira) if v is not None}


def carregar_biblioteca(caminho: str | os.PathLike | None = None) -> Biblioteca:
    """Lê e valida a biblioteca. Lança ErroBiblioteca com todos os erros encontrados."""
    caminho = Path(caminho or caminho_biblioteca())
    try:
        wb = openpyxl.load_workbook(caminho, data_only=True, read_only=True)
    except FileNotFoundError:
        raise ErroBiblioteca([{"aba": None, "linha": None, "mensagem": f"Arquivo da biblioteca não encontrado: {caminho}"}])
    except Exception as exc:
        raise ErroBiblioteca([{"aba": None, "linha": None, "mensagem": f"Não foi possível abrir a biblioteca: {exc}"}])
    try:
        erros: list[dict[str, Any]] = []
        for aba in (ABA_ATIVIDADES, ABA_REGRAS):
            if aba not in wb.sheetnames:
                erros.append({"aba": aba, "linha": None, "mensagem": f"Aba '{aba}' não encontrada."})
        if erros:
            raise ErroBiblioteca(erros)
        atividades = _ler_atividades(wb[ABA_ATIVIDADES], erros)
        regras = _ler_regras(wb[ABA_REGRAS], erros)
    finally:
        wb.close()

    _validar(atividades, regras, erros)
    if erros:
        raise ErroBiblioteca(erros)
    return Biblioteca(atividades=atividades, regras=regras, caminho=str(caminho))


def _ler_atividades(ws, erros) -> dict[str, Atividade]:
    cab = _cabecalho(ws)
    faltando = [c for c in COLUNAS_ATIVIDADES if c not in cab]
    if faltando:
        erros.append({"aba": ABA_ATIVIDADES, "linha": 1, "mensagem": "Colunas não encontradas: " + ", ".join(faltando)})
        return {}
    atividades: dict[str, Atividade] = {}
    for n, linha in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        val = lambda c: linha[cab[c]] if cab[c] < len(linha) else None  # noqa: E731
        codigo = _texto(val("codigo"))
        if codigo is None:
            continue  # linha vazia ou linha TOTAL
        codigo = codigo.upper()
        if not _RE_CODIGO.match(codigo):
            erros.append({"aba": ABA_ATIVIDADES, "linha": n, "mensagem": f"Código '{codigo}' em formato inválido (use XXX-00)."})
            continue
        if codigo in atividades:
            erros.append({"aba": ABA_ATIVIDADES, "linha": n, "mensagem": f"Código {codigo} repetido (já aparece na linha {atividades[codigo].linha_excel})."})
            continue
        deps, erros_dep = interpretar_dependencias(val("depende_de"))
        for e in erros_dep:
            erros.append({"aba": ABA_ATIVIDADES, "linha": n, "mensagem": f"{codigo}: {e}."})
        tipo = (_texto(val("tipo")) or "").lower()
        if tipo not in TIPOS:
            erros.append({"aba": ABA_ATIVIDADES, "linha": n, "mensagem": f"{codigo}: tipo '{tipo or '(vazio)'}' inválido (use {', '.join(TIPOS)})."})
        atividades[codigo] = Atividade(
            codigo=codigo, etapa=_texto(val("etapa")), nome=_texto(val("atividade")) or codigo,
            depende_de=deps, tipo=tipo, equipe_principal=_texto(val("equipe_principal")),
            observacao=_texto(val("observacao")),
            periodo_de=(_texto(val("periodo_de")) or "").upper() or None,
            periodo_ate=(_texto(val("periodo_ate")) or "").upper() or None,
            linha_excel=n, ordem=len(atividades),
        )
    return atividades


def _ler_regras(ws, erros) -> list[Regra]:
    cab = _cabecalho(ws)
    faltando = [c for c in COLUNAS_REGRAS if c not in cab]
    if faltando:
        erros.append({"aba": ABA_REGRAS, "linha": 1, "mensagem": "Colunas não encontradas: " + ", ".join(faltando)})
        return []
    regras: list[Regra] = []
    ordens: dict[int, int] = {}
    for n, linha in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        val = lambda c: linha[cab[c]] if cab[c] < len(linha) else None  # noqa: E731
        atividade = _texto(val("atividade"))
        if atividade is None and val("ordem") is None:
            continue
        try:
            ordem = int(val("ordem"))
            prioridade = int(val("prioridade"))
        except (TypeError, ValueError):
            erros.append({"aba": ABA_REGRAS, "linha": n, "mensagem": "Ordem e prioridade precisam ser números inteiros."})
            continue
        if ordem in ordens:
            erros.append({"aba": ABA_REGRAS, "linha": n, "mensagem": f"Ordem {ordem} repetida (já aparece na linha {ordens[ordem]})."})
        ordens.setdefault(ordem, n)
        natureza = (_texto(val("natureza")) or "").lower() or None
        if natureza and natureza not in NATUREZAS:
            erros.append({"aba": ABA_REGRAS, "linha": n, "mensagem": f"Natureza '{natureza}' inválida (use {', '.join(NATUREZAS)})."})
        if not atividade:
            erros.append({"aba": ABA_REGRAS, "linha": n, "mensagem": "Regra sem atividade."})
            continue
        regras.append(Regra(
            ordem=ordem, prioridade=prioridade, atividade=atividade.upper(),
            termos_no_grupo=_termos(val("termos_no_grupo")),
            termos_na_descricao=_termos(val("termos_na_descricao")),
            natureza=natureza, linha_excel=n,
        ))
    return regras


def _validar(atividades: dict[str, Atividade], regras: list[Regra], erros: list[dict[str, Any]]) -> None:
    for a in atividades.values():
        for d in a.depende_de:
            if d.codigo not in atividades:
                erros.append({"aba": ABA_ATIVIDADES, "linha": a.linha_excel, "mensagem": f"{a.codigo} depende de {d.codigo}, que não existe."})
            elif d.codigo == a.codigo:
                erros.append({"aba": ABA_ATIVIDADES, "linha": a.linha_excel, "mensagem": f"{a.codigo} depende dela mesma."})
        for campo in ("periodo_de", "periodo_ate"):
            p = getattr(a, campo)
            if p and p not in PERIODOS_ESPECIAIS and p not in atividades:
                erros.append({"aba": ABA_ATIVIDADES, "linha": a.linha_excel, "mensagem": f"{a.codigo}: {campo} '{p}' não é INICIO_OBRA, FIM_OBRA nem um código existente."})
        if a.tipo == "indireta" and a.depende_de:
            erros.append({"aba": ABA_ATIVIDADES, "linha": a.linha_excel, "mensagem": f"{a.codigo}: atividade indireta não entra na sequência; deixe depende_de vazio."})
    for r in regras:
        if r.atividade not in atividades:
            erros.append({"aba": ABA_REGRAS, "linha": r.linha_excel, "mensagem": f"Regra {r.ordem} aponta para a atividade {r.atividade}, que não existe."})
    ciclo = achar_ciclo({c: [d.codigo for d in a.depende_de] for c, a in atividades.items()})
    if ciclo:
        linhas = sorted({atividades[c].linha_excel for c in ciclo})
        erros.append({"aba": ABA_ATIVIDADES, "linha": linhas[0], "mensagem": "Ciclo nas dependências: " + " → ".join(ciclo) + f" (cada uma depende da seguinte; linhas {', '.join(map(str, linhas))})."})


# --------------------------------------------------------------------------- gravação


def salvar_atividade_na_biblioteca(
    codigo: str, tipo: str, depende_de: list[Dependencia] | None, caminho: str | os.PathLike | None = None
) -> Path:
    """Grava tipo e depende_de de uma atividade no Excel da biblioteca (depende_de=None mantém o atual).

    Antes, valida a biblioteca resultante (ciclo, códigos) e faz uma cópia de segurança.
    Retorna o caminho da cópia de segurança.
    """
    caminho = Path(caminho or caminho_biblioteca())
    biblioteca = carregar_biblioteca(caminho)
    codigo = codigo.upper()
    if codigo not in biblioteca.atividades:
        raise ErroBiblioteca([{"aba": ABA_ATIVIDADES, "linha": None, "mensagem": f"Atividade {codigo} não existe na biblioteca."}])
    if tipo not in TIPOS:
        raise ErroBiblioteca([{"aba": ABA_ATIVIDADES, "linha": None, "mensagem": f"Tipo '{tipo}' inválido."}])
    atividade = biblioteca.atividades[codigo]
    atividade.tipo = tipo
    if depende_de is not None:
        atividade.depende_de = list(depende_de)
    erros: list[dict[str, Any]] = []
    _validar(biblioteca.atividades, biblioteca.regras, erros)
    if erros:
        raise ErroBiblioteca(erros)

    pasta_backup = caminho.parent / "backup"
    pasta_backup.mkdir(exist_ok=True)
    backup = pasta_backup / f"{caminho.stem}_{datetime.now():%Y%m%d_%H%M%S_%f}{caminho.suffix}"
    shutil.copy2(caminho, backup)

    wb = openpyxl.load_workbook(caminho)  # sem data_only: preserva fórmulas
    ws = wb[ABA_ATIVIDADES]
    cab = _cabecalho(ws)
    linha = atividade.linha_excel
    ws.cell(linha, cab["tipo"] + 1).value = tipo
    if depende_de is not None:
        ws.cell(linha, cab["depende_de"] + 1).value = formatar_dependencias(depende_de) or None
    wb.save(caminho)
    return backup
