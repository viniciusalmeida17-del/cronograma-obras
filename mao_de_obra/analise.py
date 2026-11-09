"""Mão de obra e equipamentos de cada serviço, a partir das composições.

Para cada linha de uma composição:
1. equipamento (CHP/CHI)                → horas de equipamento;
2. mão de obra (tabela de funções)       → horas por função (categoria indireta: só a equipe fixa, unidade MÊS);
3. código de um item da planilha          → expande a subcomposição (horas × coeficiente), em profundidade;
4. código no banco de coeficientes        → horas do banco × coeficiente;
5. descrição de serviço (palavras-chave)  → subcomposição pendente (horas estimadas depois);
6. o resto é material.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Protocol

from leitor_planilha.texto import normalizar

from .composicoes import Composicao
from .funcoes import (
    INDIRETA,
    TabelaFuncoes,
    eh_equipamento,
    eh_subcomposicao,
    nome_equipamento,
    unidade_de_mao_de_obra,
    unidade_norm,
)

COMPOSICAO = "composicao"
BANCO = "banco"
ESTIMADO = "estimado"
SEM_MAO_DE_OBRA = "sem_mao_de_obra"
MANUAL = "manual"
ORIGENS = (COMPOSICAO, BANCO, ESTIMADO, MANUAL, SEM_MAO_DE_OBRA)


class ConsultaBanco(Protocol):
    def buscar(self, base: str | None, codigo: str | None) -> dict[str, float] | None: ...
    def buscar_codigo(self, codigo: str | None) -> dict[str, float] | None: ...


class BancoVazio:
    def buscar(self, base, codigo):
        return None

    def buscar_codigo(self, codigo):
        return None


def chave_codigo(codigo: Any) -> str:
    return normalizar(codigo).replace(" ", "")


@dataclass
class AnaliseComposicao:
    """Resultado por unidade do serviço."""
    horas: dict[tuple[str, str], float] = field(default_factory=lambda: defaultdict(float))  # (funcao, origem) -> h/un
    equipamentos: dict[str, float] = field(default_factory=lambda: defaultdict(float))       # nome -> h/un
    pendentes: list[dict[str, Any]] = field(default_factory=list)
    indireta: dict[str, float] = field(default_factory=lambda: defaultdict(float))           # funcao -> pessoas/mês
    expandidos: list[dict[str, Any]] = field(default_factory=list)
    # funcao -> [horas, R$, horas "com encargos", R$ "com encargos"] das linhas de mão de obra com preço
    custos: dict[str, list[float]] = field(default_factory=lambda: defaultdict(lambda: [0.0, 0.0, 0.0, 0.0]))

    def total_horas(self) -> float:
        return sum(self.horas.values())


class Analisador:
    def __init__(
        self,
        composicoes: Mapping[str, Composicao],
        funcoes: TabelaFuncoes,
        palavras: list[str],
        codigo_para_item: Mapping[str, str],
        banco: ConsultaBanco | None = None,
    ):
        self.composicoes = composicoes
        self.funcoes = funcoes
        self.palavras = palavras
        self.codigo_para_item = codigo_para_item
        self.banco = banco or BancoVazio()
        self._memo: dict[str, AnaliseComposicao] = {}

    def analisar_composicao(self, item: str, pilha: tuple[str, ...] = ()) -> AnaliseComposicao:
        if item in self._memo:
            return self._memo[item]
        comp = self.composicoes[item]
        res = AnaliseComposicao()
        pilha = pilha + (item,)
        for linha in comp.linhas:
            coef = linha.coeficiente or 0.0
            if eh_equipamento(linha.descricao, linha.unidade):
                res.equipamentos[nome_equipamento(linha.descricao)] += coef
                continue
            regra = self.funcoes.identificar(linha.descricao)
            if regra and unidade_de_mao_de_obra(linha.unidade):
                if regra.categoria == INDIRETA:
                    if unidade_norm(linha.unidade) == "MES":
                        res.indireta[regra.funcao] += coef
                    continue  # em composição de serviço, indireta é ignorada
                res.horas[(regra.funcao, COMPOSICAO)] += coef
                if linha.preco and linha.preco > 0:
                    acc = res.custos[regra.funcao]
                    acc[0] += coef
                    acc[1] += coef * linha.preco
                    if "ENCARGOS" in normalizar(linha.descricao):
                        acc[2] += coef
                        acc[3] += coef * linha.preco
                continue
            codigo = chave_codigo(linha.codigo)
            sub_item = self.codigo_para_item.get(codigo) if codigo else None
            if sub_item and sub_item in self.composicoes and sub_item not in pilha:
                sub = self.analisar_composicao(sub_item, pilha)
                for chave, h in sub.horas.items():
                    res.horas[chave] += h * coef
                for nome, h in sub.equipamentos.items():
                    res.equipamentos[nome] += h * coef
                for funcao, valores in sub.custos.items():
                    acc = res.custos[funcao]
                    for k, v in enumerate(valores):
                        acc[k] += v * coef
                for p in sub.pendentes:
                    res.pendentes.append({**p, "coeficiente": p["coeficiente"] * coef,
                                          "total_linha": (p["total_linha"] or 0.0) * coef,
                                          "via": [linha.codigo] + p.get("via", [])})
                res.expandidos.append({"codigo": linha.codigo, "item": sub_item, "coeficiente": coef,
                                       "horas_un": sub.total_horas() * coef})
                continue
            do_banco = self.banco.buscar_codigo(codigo) if codigo else None
            if do_banco:
                for funcao, h in do_banco.items():
                    res.horas[(funcao, BANCO)] += h * coef
                res.expandidos.append({"codigo": linha.codigo, "item": None, "coeficiente": coef,
                                       "horas_un": sum(do_banco.values()) * coef, "banco": True})
                continue
            if eh_subcomposicao(linha.descricao, self.palavras):
                res.pendentes.append({"codigo": linha.codigo, "descricao": linha.descricao,
                                      "unidade": None if linha.unidade is None else str(linha.unidade),
                                      "coeficiente": coef, "total_linha": linha.total or 0.0, "via": []})
        self._memo[item] = res
        return res

    def analisar_servico(self, servico: Mapping[str, Any], manual: Mapping[str, float] | None = None) -> dict[str, Any]:
        """Análise de um serviço (por unidade). Ainda sem as estimativas (dependem da obra).

        horas: [{funcao, horas_un, origem}] · equipamentos: {nome: h/un} · pendentes: [...] ·
        indireta: {funcao: pessoas/mês} · origem: composicao | banco | estimado | manual | sem_mao_de_obra
        """
        res = self._analisar_servico(servico, manual)
        res["horas"] = [{"funcao": f, "horas_un": h, "origem": o} for (f, o), h in res["horas"].items()]
        return res

    def _analisar_servico(self, servico: Mapping[str, Any], manual: Mapping[str, float] | None = None) -> dict[str, Any]:
        item = servico.get("item")
        comp = self.composicoes.get(item) if item else None
        base = {
            "linha_excel": servico.get("linha_excel"), "item": item,
            "composicao": {"aba": comp.aba, "linha": comp.linha_excel, "formato": comp.formato} if comp else None,
            "horas": {}, "equipamentos": {}, "pendentes": [], "indireta": {}, "expandidos": [],
            # funcao -> horas e R$ por unidade das linhas de mão de obra com preço (todas e só as "com encargos")
            "custos_mo": {},
        }
        if comp:
            a = self.analisar_composicao(item)
            base.update(
                equipamentos={k: v for k, v in a.equipamentos.items() if v},
                pendentes=[dict(p) for p in a.pendentes],
                indireta={k: v for k, v in a.indireta.items() if v},
                expandidos=a.expandidos,
                custos_mo={f: {"horas_un": v[0], "custo_un": v[1], "horas_un_encargos": v[2], "custo_un_encargos": v[3]}
                           for f, v in a.custos.items() if v[0] > 0 and v[1] > 0},
            )
            horas = {k: v for k, v in a.horas.items() if v}
        else:
            horas = {}

        if manual:
            base["horas"] = {(f, MANUAL): h for f, h in manual.items() if h}
            base["origem"] = MANUAL
            base["pendentes"] = []
            return base
        if comp:
            base["horas"] = horas
            if horas:
                base["origem"] = COMPOSICAO
            elif base["pendentes"]:
                base["origem"] = ESTIMADO
            else:
                base["origem"] = SEM_MAO_DE_OBRA
            return base
        do_banco = self.banco.buscar(servico.get("base"), servico.get("codigo"))
        if do_banco:
            base["horas"] = {(f, BANCO): h for f, h in do_banco.items() if h}
            base["origem"] = BANCO
            return base
        base["origem"] = ESTIMADO  # sem composição e sem banco: estimar pelo custo
        base["estimar_servico_inteiro"] = True
        return base


def mapa_codigo_item(servicos: Iterable[Mapping[str, Any]]) -> dict[str, str]:
    """Código do serviço na planilha -> item (o primeiro, se o código se repetir)."""
    mapa: dict[str, str] = {}
    for s in servicos:
        c = chave_codigo(s.get("codigo"))
        if c and s.get("item"):
            mapa.setdefault(c, s["item"])
    return mapa


def horas_por_funcao(horas: Mapping[tuple[str, str], float]) -> dict[str, float]:
    total: dict[str, float] = defaultdict(float)
    for (funcao, _), h in horas.items():
        total[funcao] += h
    return dict(total)
