"""Rede de atividades da obra: quais atividades entram e a ordem entre elas.

A rede é um dicionário pronto para JSON:

    {
      "atividades": {codigo: {codigo, nome, etapa, tipo, total, total_bdi, n_itens,
                              periodo_de, periodo_ate, ordem_biblioteca, ...}},
      "dependencias": [{atividade, depende_de, espera_dias, tipo (TI/II), unidade (d/du), origem}],
    }

`origem` da dependência: "biblioteca", "herdada" (veio de uma atividade que saiu),
"fim" (atividade sem sucessor ligada à limpeza final) ou "usuario" (editada nesta obra).
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from .biblioteca import TIPOS, Biblioteca, Dependencia, formatar_dependencias, interpretar_dependencias
from .grafo import achar_ciclo, ordem_topologica

ATIVIDADE_FINAL = "LIM-01"
ATIVIDADES_SEMPRE = ("TES-01", ATIVIDADE_FINAL)  # entram em toda obra
INDIRETA = "indireta"


class ErroRede(Exception):
    pass


def totais_por_atividade(servicos: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    totais: dict[str, dict[str, Any]] = {}
    for s in servicos:
        cod = s.get("atividade_biblioteca")
        if not cod:
            continue
        t = totais.setdefault(cod, {"n_itens": 0, "total": 0.0, "total_bdi": 0.0})
        t["n_itens"] += 1
        t["total"] += s.get("total") or 0.0
        t["total_bdi"] += s.get("total_bdi") or 0.0
    for t in totais.values():
        t["total"] = round(t["total"], 2)
        t["total_bdi"] = round(t["total_bdi"], 2)
    return totais


def _sem_custo(biblioteca: Biblioteca, codigo: str) -> bool:
    """Atividade que nunca recebe serviço: tipo 'aguardar' ou sem nenhuma regra de reconhecimento."""
    a = biblioteca.atividades[codigo]
    return a.tipo == "aguardar" or codigo not in biblioteca.codigos_com_regra


def escolher_atividades(biblioteca: Biblioteca, com_servico: set[str]) -> set[str]:
    """Atividades que entram na obra."""
    entram = {c for c in com_servico if c in biblioteca.atividades}
    entram |= {c for c in ATIVIDADES_SEMPRE if c in biblioteca.atividades}
    # As sem custo entram se todas as atividades das quais dependem estiverem na obra.
    # Em ordem da biblioteca e repetindo, porque uma sem custo pode depender de outra.
    mudou = True
    while mudou:
        mudou = False
        for cod, a in biblioteca.atividades.items():
            if cod in entram or a.tipo == INDIRETA or not _sem_custo(biblioteca, cod):
                continue
            if a.depende_de and all(d.codigo in entram for d in a.depende_de):
                entram.add(cod)
                mudou = True
    return entram


def somar_elos(fica: Dependencia, herdado: Dependencia, codigo: str) -> Dependencia:
    """B depende de A (elo `fica`) e A, que saiu, depende de C (elo `herdado`): B passa a depender de C.

    Mantém o tipo do elo de quem fica (B) e soma as esperas; com unidades diferentes, tudo em dias úteis.
    """
    if fica.unidade == herdado.unidade or not fica.espera_dias or not herdado.espera_dias:
        unidade = fica.unidade if fica.espera_dias else herdado.unidade
        espera = fica.espera_dias + herdado.espera_dias
    else:
        unidade, espera = "du", fica.espera_uteis() + herdado.espera_uteis()
    return Dependencia(codigo, espera, fica.tipo, unidade if espera else "d")


def _maior(a: Dependencia | None, b: Dependencia) -> bool:
    """b é mais restritiva que a? Término-início vence início-início; no mesmo tipo, a maior espera."""
    if a is None:
        return True
    return (b.tipo == "TI", b.espera_uteis()) > (a.tipo == "TI", a.espera_uteis())


def _dependencias_efetivas(biblioteca: Biblioteca, entram: set[str]) -> dict[str, dict[str, tuple[Dependencia, str]]]:
    """Para cada atividade da obra: {depende_de: (Dependencia, origem)}, já com a herança das que saíram.

    Se B depende de A+x e A sai, B herda as dependências de A: C+y vira C+(x+y), com o tipo do elo de B.
    Se a mesma dependência chegar por dois caminhos, fica a mais restritiva.
    """
    memo: dict[str, dict[str, Dependencia]] = {}

    def herdadas(codigo: str) -> dict[str, Dependencia]:
        """Dependências (dentro da obra) de uma atividade que saiu."""
        if codigo in memo:
            return memo[codigo]
        res: dict[str, Dependencia] = {}
        for d in biblioteca.atividades[codigo].depende_de:
            candidatas = [d] if d.codigo in entram else [somar_elos(d, y, c) for c, y in herdadas(d.codigo).items()]
            for nova in candidatas:
                if _maior(res.get(nova.codigo), nova):
                    res[nova.codigo] = nova
        memo[codigo] = res
        return res

    efetivas: dict[str, dict[str, tuple[Dependencia, str]]] = {}
    for cod in entram:
        deps: dict[str, tuple[Dependencia, str]] = {}
        for d in biblioteca.atividades[cod].depende_de:
            if d.codigo in entram:
                candidatas = [(d, "biblioteca")]
            else:
                candidatas = [(somar_elos(d, y, c), "herdada") for c, y in herdadas(d.codigo).items()]
            for nova, origem in candidatas:
                atual = deps.get(nova.codigo)
                if _maior(atual[0] if atual else None, nova):
                    deps[nova.codigo] = (nova, origem)
        efetivas[cod] = deps
    return efetivas


def dep_para_dict(atividade: str, d: Dependencia, origem: str) -> dict[str, Any]:
    return {"atividade": atividade, "depende_de": d.codigo, "espera_dias": d.espera_dias, "tipo": d.tipo,
            "unidade": d.unidade, "origem": origem}


def dict_para_dep(d: Mapping[str, Any]) -> Dependencia:
    return Dependencia(d["depende_de"], int(d.get("espera_dias") or 0), d.get("tipo") or "TI", d.get("unidade") or "d")


def montar_rede(biblioteca: Biblioteca, servicos: Iterable[Mapping[str, Any]], excluir: Iterable[str] = ()) -> dict[str, Any]:
    """Monta a rede da obra a partir dos serviços já ligados.

    :param excluir: atividades a tirar da obra mesmo tendo serviço (os serviços continuam ligados).
    """
    servicos = list(servicos)
    totais = totais_por_atividade(servicos)
    entram = escolher_atividades(biblioteca, set(totais)) - set(excluir)
    if ATIVIDADE_FINAL not in entram and ATIVIDADE_FINAL in biblioteca.atividades and ATIVIDADE_FINAL not in excluir:
        entram.add(ATIVIDADE_FINAL)

    atividades: dict[str, dict[str, Any]] = {}
    for cod in sorted(entram, key=lambda c: biblioteca.atividades[c].ordem):
        a = biblioteca.atividades[cod]
        t = totais.get(cod, {"n_itens": 0, "total": 0.0, "total_bdi": 0.0})
        atividades[cod] = {
            "codigo": cod, "nome": a.nome, "etapa": a.etapa, "tipo": a.tipo,
            "tipo_biblioteca": a.tipo, "equipe_principal": a.equipe_principal, "observacao": a.observacao,
            "periodo_de": a.periodo_de if a.tipo == INDIRETA else None,
            "periodo_ate": a.periodo_ate if a.tipo == INDIRETA else None,
            "n_itens": t["n_itens"], "total": t["total"], "total_bdi": t["total_bdi"],
            "ordem_biblioteca": a.ordem, "editada": False,
            "execucao_padrao": a.execucao_padrao, "equipe_padrao": a.equipe_padrao,
            "equipe_max": a.equipe_max, "duracao_fixa_dias": a.duracao_fixa_dias, "tipo_producao": a.tipo_producao,
        }

    na_sequencia = {c for c, a in atividades.items() if a["tipo"] != INDIRETA}
    efetivas = _dependencias_efetivas(biblioteca, na_sequencia)
    dependencias = [
        dep_para_dict(cod, d, origem)
        for cod in sorted(efetivas, key=lambda c: atividades[c]["ordem_biblioteca"])
        for _, (d, origem) in sorted(efetivas[cod].items(), key=lambda x: atividades[x[0]]["ordem_biblioteca"])
    ]
    rede = {"atividades": atividades, "dependencias": dependencias}
    ligar_ao_fim(rede)
    validar_rede(rede)
    return rede


def ligar_ao_fim(rede: dict[str, Any]) -> None:
    """Toda atividade da sequência sem sucessor precisa terminar antes da limpeza final."""
    deps = [d for d in rede["dependencias"] if d["origem"] != "fim"]
    if ATIVIDADE_FINAL not in rede["atividades"]:
        rede["dependencias"] = deps
        return
    seq = [c for c, a in rede["atividades"].items() if a["tipo"] != INDIRETA]
    com_sucessor = {d["depende_de"] for d in deps}
    ja_no_fim = {d["depende_de"] for d in deps if d["atividade"] == ATIVIDADE_FINAL}
    for cod in seq:
        if cod == ATIVIDADE_FINAL or cod in com_sucessor or cod in ja_no_fim:
            continue
        deps.append(dep_para_dict(ATIVIDADE_FINAL, Dependencia(cod), "fim"))
    rede["dependencias"] = deps


def _grafo(rede: Mapping[str, Any]) -> dict[str, list[str]]:
    seq = {c for c, a in rede["atividades"].items() if a["tipo"] != INDIRETA}
    g: dict[str, list[str]] = {c: [] for c in seq}
    for d in rede["dependencias"]:
        if d["atividade"] in g:
            g[d["atividade"]].append(d["depende_de"])
    return g


def validar_rede(rede: Mapping[str, Any]) -> None:
    g = _grafo(rede)
    for cod, deps in g.items():
        for d in deps:
            if d not in g:
                raise ErroRede(f"{cod} depende de {d}, que não está na sequência desta obra.")
    ciclo = achar_ciclo(g)
    if ciclo:
        raise ErroRede("Ciclo nas dependências: " + " → ".join(ciclo) + " (cada uma depende da seguinte).")


def sequencia(rede: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Atividades da sequência em ordem de execução possível, com suas dependências."""
    g = _grafo(rede)
    preferencia = sorted(g, key=lambda c: rede["atividades"][c]["ordem_biblioteca"])
    ordem = ordem_topologica(g, preferencia)
    deps_por_ativ: dict[str, list[dict[str, Any]]] = {c: [] for c in g}
    for d in rede["dependencias"]:
        if d["atividade"] in deps_por_ativ:
            deps_por_ativ[d["atividade"]].append(d)
    saida = []
    for posicao, cod in enumerate(ordem, start=1):
        a = dict(rede["atividades"][cod])
        a["posicao"] = posicao
        a["dependencias"] = deps_por_ativ[cod]
        a["depende_de_texto"] = formatar_dependencias([dict_para_dep(d) for d in deps_por_ativ[cod]])
        saida.append(a)
    return saida


def indiretas(rede: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [a for a in rede["atividades"].values() if a["tipo"] == INDIRETA]


def editar_atividade(
    rede: dict[str, Any], codigo: str, tipo: str | None = None, depende_de: str | list[Dependencia] | None = None
) -> dict[str, Any]:
    """Muda tipo e/ou dependências de uma atividade só nesta obra. Retorna uma nova rede (valida ciclo)."""
    codigo = codigo.upper()
    if codigo not in rede["atividades"]:
        raise ErroRede(f"A atividade {codigo} não está nesta obra.")
    nova = {
        "atividades": {c: dict(a) for c, a in rede["atividades"].items()},
        "dependencias": [dict(d) for d in rede["dependencias"]],
    }
    ativ = nova["atividades"][codigo]
    if tipo is not None:
        if tipo not in TIPOS:
            raise ErroRede(f"Tipo '{tipo}' inválido.")
        if (tipo == INDIRETA) != (ativ["tipo"] == INDIRETA):
            raise ErroRede("Não é possível transformar uma atividade em indireta (ou o contrário) nesta tela.")
        ativ["tipo"] = tipo
        ativ["editada"] = True
    if depende_de is not None:
        if ativ["tipo"] == INDIRETA:
            raise ErroRede("Atividade indireta não tem dependências.")
        if isinstance(depende_de, str):
            deps, erros = interpretar_dependencias(depende_de)
            if erros:
                raise ErroRede("; ".join(erros))
        else:
            deps = list(depende_de)
        vistos: dict[str, Dependencia] = {}
        for d in deps:
            if d.codigo == codigo:
                raise ErroRede(f"{codigo} não pode depender dela mesma.")
            if d.codigo not in nova["atividades"]:
                raise ErroRede(f"{d.codigo} não está nesta obra.")
            if nova["atividades"][d.codigo]["tipo"] == INDIRETA:
                raise ErroRede(f"{d.codigo} é indireta e não entra na sequência.")
            if _maior(vistos.get(d.codigo), d):
                vistos[d.codigo] = d
        nova["dependencias"] = [d for d in nova["dependencias"] if d["atividade"] != codigo]
        nova["dependencias"] += [dep_para_dict(codigo, d, "usuario") for d in vistos.values()]
        ativ["editada"] = True
    ligar_ao_fim(nova)
    validar_rede(nova)
    return nova


def dependencias_de(rede: Mapping[str, Any], codigo: str, incluir_fim: bool = True) -> list[Dependencia]:
    return [
        dict_para_dep(d)
        for d in rede["dependencias"]
        if d["atividade"] == codigo and (incluir_fim or d["origem"] != "fim")
    ]
