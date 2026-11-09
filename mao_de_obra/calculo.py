"""Estimativas, duração por atividade e resumo da obra (funções puras, sem banco)."""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Iterable, Mapping

from .analise import BANCO, COMPOSICAO, ESTIMADO, MANUAL, SEM_MAO_DE_OBRA

PROPRIA = "propria"
TERCEIRIZADA = "terceirizada"
PERGUNTAR = "perguntar"
EXECUCOES = (PROPRIA, TERCEIRIZADA)
INDIRETA = "indireta"

PARAMETROS_PADRAO = {"horas_semana": 44.0, "dias_semana": 5, "rendimento": 0.90, "mudancas_jornada": []}
EQUIPE_PADRAO = 2
EQUIPE_MAX = 6
SEMANAS_POR_MES = 4.33


def horas_por_dia(parametros: Mapping[str, Any]) -> float:
    return float(parametros["horas_semana"]) / float(parametros["dias_semana"])


def _teto(x: float) -> int:
    """Arredonda para cima ignorando ruído de ponto flutuante (24.000000001 -> 24)."""
    return math.ceil(round(x, 6))


def calcular_duracao(
    horas_ajustadas: Mapping[str, float],
    horas_equipamento: Mapping[str, float],
    equipe_padrao: int,
    horas_dia: float,
) -> dict[str, Any] | None:
    """Duração (dias úteis) com a equipe padrão. None se não houver horas.

    Função principal = a de mais horas; ela recebe `equipe_padrao` pessoas; cada outra função
    recebe teto(equipe_padrao × horas da função ÷ horas da principal), mínimo 1.
    Duração = maior entre as funções (horas ÷ (pessoas × horas/dia)) e os equipamentos
    (horas ÷ horas/dia, uma máquina de cada), arredondada para cima.
    """
    horas = {f: h for f, h in horas_ajustadas.items() if h > 0}
    equip = {e: h for e, h in horas_equipamento.items() if h > 0}
    if not horas and not equip:
        return None
    equipe: dict[str, int] = {}
    dias_funcao: dict[str, float] = {}
    principal = None
    if horas:
        principal = max(horas, key=lambda f: (horas[f], f))
        hp = horas[principal]
        for f, h in horas.items():
            equipe[f] = equipe_padrao if f == principal else max(1, _teto(equipe_padrao * h / hp))
            dias_funcao[f] = h / (equipe[f] * horas_dia)
    dias_equip = {e: h / horas_dia for e, h in equip.items()}
    dias_pessoas = max(dias_funcao.values(), default=0.0)
    dias_maquinas = max(dias_equip.values(), default=0.0)
    limitante = "equipamento" if dias_maquinas > dias_pessoas else "mao_de_obra"
    return {
        "funcao_principal": principal,
        "equipe": equipe,
        "dias_por_funcao": {f: round(d, 2) for f, d in dias_funcao.items()},
        "dias_por_equipamento": {e: round(d, 2) for e, d in dias_equip.items()},
        "dias_exatos": round(max(dias_pessoas, dias_maquinas), 4),
        "dias": _teto(max(dias_pessoas, dias_maquinas)),
        "limitante": limitante,
    }


def semanas_do_prazo(valor: float | None, unidade: str | None) -> float | None:
    if not valor:
        return None
    fator = {"meses": SEMANAS_POR_MES, "semanas": 1.0, "dias": 1 / 7, "anos": 52.0}.get(unidade or "meses")
    return valor * fator if fator else None


# --------------------------------------------------------------------------- estimativas


def _soma_horas(analise: Mapping[str, Any], qtd: float, origens: Iterable[str] | None = None) -> dict[str, float]:
    tot: dict[str, float] = defaultdict(float)
    for h in analise["horas"]:
        if origens is None or h["origem"] in origens:
            tot[h["funcao"]] += h["horas_un"] * qtd
    return tot


def _completo(analise: Mapping[str, Any]) -> bool:
    return (analise["origem"] in (COMPOSICAO, BANCO, MANUAL) and not analise["pendentes"]
            and any(h["horas_un"] > 0 for h in analise["horas"]))


def aplicar_estimativas(
    servicos: list[Mapping[str, Any]],
    analises: dict[Any, dict[str, Any]],
    atividades: Mapping[str, Mapping[str, Any]],
    execucao: Mapping[str, str | None],
) -> list[dict[str, Any]]:
    """Acrescenta horas 'estimado' (custo × razão horas/custo) onde falta mão de obra.

    Razão dos serviços completos da mesma atividade; senão da mesma etapa; senão da obra.
    Não estima itens de atividades indiretas nem de terceirizadas sem horas.
    Altera `analises` (horas e pendentes) e devolve avisos.
    """
    avisos: list[dict[str, Any]] = []
    ctx: dict[tuple[str, str], dict[str, Any]] = defaultdict(lambda: {"horas": defaultdict(float), "custo": 0.0})
    horas_reais_ativ: dict[str, float] = defaultdict(float)
    for s in servicos:
        cod = s.get("atividade_biblioteca")
        a = analises.get(s["id"])
        ativ = atividades.get(cod)
        if not a or not ativ or ativ["tipo"] == INDIRETA:
            continue
        qtd = s.get("quantidade") or 0.0
        horas_reais_ativ[cod] += sum(h["horas_un"] for h in a["horas"] if h["origem"] != ESTIMADO) * qtd
        if _completo(a) and (s.get("total") or 0) > 0:
            for chave in (("atividade", cod), ("etapa", ativ.get("etapa") or ""), ("obra", "")):
                for f, h in _soma_horas(a, qtd).items():
                    ctx[chave]["horas"][f] += h
                ctx[chave]["custo"] += s["total"]

    def razao(cod: str) -> tuple[str, dict[str, float]] | None:
        ativ = atividades[cod]
        for nivel, chave in (("atividade", ("atividade", cod)), ("etapa", ("etapa", ativ.get("etapa") or "")), ("obra", ("obra", ""))):
            c = ctx.get(chave)
            if c and c["custo"] > 0 and sum(c["horas"].values()) > 0:
                return nivel, {f: h / c["custo"] for f, h in c["horas"].items()}
        return None

    for s in servicos:
        cod = s.get("atividade_biblioteca")
        a = analises.get(s["id"])
        ativ = atividades.get(cod)
        if not a or not ativ:
            continue
        a["horas"] = [h for h in a["horas"] if h["origem"] != ESTIMADO]
        precisa = a["origem"] == ESTIMADO or bool(a["pendentes"])
        if not precisa or a["origem"] == MANUAL:
            continue
        a["estimativa"] = None
        if ativ["tipo"] == INDIRETA:
            continue
        if execucao.get(cod) == TERCEIRIZADA and horas_reais_ativ[cod] <= 0:
            continue  # terceirizada sem horas: duração digitada pelo usuário
        qtd = s.get("quantidade") or 0.0
        if a.get("estimar_servico_inteiro"):
            custo = s.get("total") or 0.0
        else:
            custo = sum((p["total_linha"] or 0.0) for p in a["pendentes"]) * qtd
        r = razao(cod)
        if r is None or qtd <= 0:
            avisos.append({"servico": s["id"], "mensagem": f"Item {s['item']}: não há serviços completos para estimar as horas."})
            continue
        nivel, por_funcao = r
        for f, k in por_funcao.items():
            if k * custo > 0:
                a["horas"].append({"funcao": f, "horas_un": k * custo / qtd, "origem": ESTIMADO})
        razao_total = sum(por_funcao.values())
        for p in a["pendentes"]:
            p["horas_estimadas"] = round((p["total_linha"] or 0.0) * qtd * razao_total, 4)
        a["estimativa"] = {"nivel": nivel, "custo": round(custo, 2), "razao_h_por_real": round(razao_total, 6),
                           "horas": round(custo * razao_total, 2)}
    return avisos


# --------------------------------------------------------------------------- resumo


def calcular_obra(
    servicos: list[Mapping[str, Any]],
    analises: dict[Any, dict[str, Any]],
    atividades: Mapping[str, Mapping[str, Any]],
    execucao: Mapping[str, Mapping[str, Any]],
    parametros: Mapping[str, Any],
    prazo: tuple[float | None, str | None] = (None, None),
) -> dict[str, Any]:
    """Resumo por atividade e da obra. `execucao`: codigo -> {execucao, rendimento, equipe_padrao, duracao_manual}."""
    params = {**PARAMETROS_PADRAO, **{k: v for k, v in parametros.items() if v is not None}}
    hd = horas_por_dia(params)
    escolha = {c: (execucao.get(c) or {}).get("execucao") for c in atividades}
    avisos = aplicar_estimativas(servicos, analises, atividades, escolha)

    por_ativ: dict[str, list] = defaultdict(list)
    for s in servicos:
        if s.get("atividade_biblioteca") in atividades and s["id"] in analises:
            por_ativ[s["atividade_biblioteca"]].append(s)

    resultado_ativ = []
    equipe_indireta: dict[str, float] = defaultdict(float)
    custo_por_origem: dict[str, float] = defaultdict(float)
    horas_funcao_propria: dict[str, float] = defaultdict(float)
    pendencias: list[dict[str, Any]] = []

    for cod, ativ in atividades.items():
        ex = execucao.get(cod) or {}
        servs = por_ativ.get(cod, [])
        if ativ["tipo"] == INDIRETA:
            for s in servs:
                for f, q in analises[s["id"]]["indireta"].items():
                    equipe_indireta[f] += q
            continue
        brutas: dict[str, float] = defaultdict(float)
        por_origem: dict[str, float] = defaultdict(float)
        equip: dict[str, float] = defaultdict(float)
        custo_origem_ativ: dict[str, float] = defaultdict(float)
        for s in servs:
            a = analises[s["id"]]
            qtd = s.get("quantidade") or 0.0
            for h in a["horas"]:
                brutas[h["funcao"]] += h["horas_un"] * qtd
                por_origem[h["origem"]] += h["horas_un"] * qtd
            for e, h in a["equipamentos"].items():
                equip[e] += h * qtd
            custo_por_origem[a["origem"]] += s.get("total") or 0.0
            custo_origem_ativ[a["origem"]] += s.get("total") or 0.0
        rendimento = ex.get("rendimento") or params["rendimento"]
        ajustadas = {f: h / rendimento for f, h in brutas.items()}
        equipe_padrao = int(ex.get("equipe_padrao") or ativ.get("equipe_padrao") or EQUIPE_PADRAO)
        calc = calcular_duracao(ajustadas, equip, equipe_padrao, hd)
        execucao_escolhida = ex.get("execucao")

        if ex.get("duracao_manual"):
            duracao = {"dias": ex["duracao_manual"], "unidade": "uteis", "tipo": "manual"}
        elif ativ.get("duracao_fixa_dias"):
            duracao = {"dias": ativ["duracao_fixa_dias"], "unidade": "corridos", "tipo": "fixa"}
        elif calc:
            duracao = {"dias": calc["dias"], "unidade": "uteis", "tipo": "calculada"}
        else:
            duracao = None
        if execucao_escolhida is None:
            pendencias.append({"tipo": "execucao", "atividade": cod,
                               "mensagem": f"{cod}: escolha se a execução é própria ou terceirizada."})
        if duracao is None:
            motivo = "terceirizada sem horas" if execucao_escolhida == TERCEIRIZADA else "sem horas de mão de obra"
            pendencias.append({"tipo": "duracao", "atividade": cod,
                               "mensagem": f"{cod}: {motivo}; informe a duração em dias úteis."})
        if execucao_escolhida == PROPRIA:
            for f, h in ajustadas.items():
                horas_funcao_propria[f] += h
        resultado_ativ.append({
            "codigo": cod, "nome": ativ.get("nome"), "etapa": ativ.get("etapa"), "tipo": ativ["tipo"],
            "execucao": execucao_escolhida, "execucao_padrao": ativ.get("execucao_padrao") or PROPRIA,
            "rendimento": rendimento, "rendimento_especifico": ex.get("rendimento"),
            "equipe_padrao": equipe_padrao, "equipe_padrao_biblioteca": ativ.get("equipe_padrao") or EQUIPE_PADRAO,
            "equipe_max": ativ.get("equipe_max") or EQUIPE_MAX,
            "n_itens": len(servs),
            "total": round(sum(s.get("total") or 0 for s in servs), 2),
            "horas_brutas": {f: round(h, 2) for f, h in sorted(brutas.items(), key=lambda x: -x[1])},
            "horas_ajustadas": {f: round(h, 2) for f, h in sorted(ajustadas.items(), key=lambda x: -x[1])},
            "horas_por_origem": {o: round(h, 2) for o, h in por_origem.items() if h},
            "custo_por_origem": {o: round(c, 2) for o, c in custo_origem_ativ.items() if c},
            "horas_equipamento": {e: round(h, 2) for e, h in sorted(equip.items(), key=lambda x: -x[1])},
            "funcao_principal": calc["funcao_principal"] if calc else None,
            "calculo": calc,
            "duracao": duracao,
            "duracao_manual": ex.get("duracao_manual"),
            "duracao_fixa_dias": ativ.get("duracao_fixa_dias"),
            "ordem_biblioteca": ativ.get("ordem_biblioteca", 0),
        })

    semanas = semanas_do_prazo(*prazo)
    resumo_funcoes = []
    for f, h in sorted(horas_funcao_propria.items(), key=lambda x: -x[1]):
        media = h / (semanas * params["horas_semana"]) if semanas else None
        resumo_funcoes.append({"funcao": f, "horas_ajustadas": round(h, 2),
                               "media_pessoas": round(media, 2) if media is not None else None})

    custo_total = sum(custo_por_origem.values())
    cobertura = {o: {"custo": round(custo_por_origem.get(o, 0.0), 2),
                     "percentual": round(100 * custo_por_origem.get(o, 0.0) / custo_total, 2) if custo_total else 0.0}
                 for o in (COMPOSICAO, BANCO, ESTIMADO, MANUAL, SEM_MAO_DE_OBRA)}
    com_horas = sum(cobertura[o]["custo"] for o in (COMPOSICAO, BANCO, ESTIMADO, MANUAL))
    return {
        "parametros": {**params, "horas_por_dia": round(hd, 4)},
        "atividades": sorted(resultado_ativ, key=lambda a: a["ordem_biblioteca"]),
        "equipe_indireta": [{"funcao": f, "pessoas": round(q, 4)} for f, q in equipe_indireta.items()],
        "resumo_funcoes": resumo_funcoes,
        "semanas_prazo": round(semanas, 2) if semanas else None,
        "cobertura": cobertura,
        "cobertura_com_horas": round(100 * com_horas / custo_total, 2) if custo_total else 0.0,
        "custo_sem_indiretas": round(custo_total, 2),
        "pendencias": pendencias,
        "avisos": avisos,
    }
