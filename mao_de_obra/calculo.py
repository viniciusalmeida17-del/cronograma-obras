"""Estimativas, duração por atividade e resumo da obra (funções puras, sem banco)."""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Iterable, Mapping

from leitor_planilha.texto import unidade_canonica

from .analise import BANCO, COMPOSICAO, ESTIMADO, MANUAL, REFERENCIA, SEM_MAO_DE_OBRA
from .funcoes import juntar_horas

PROPRIA = "propria"
TERCEIRIZADA = "terceirizada"
PERGUNTAR = "perguntar"
EXECUCOES = (PROPRIA, TERCEIRIZADA)
INDIRETA = "indireta"

PARAMETROS_PADRAO = {"horas_semana": 44.0, "dias_semana": 5, "rendimento": 0.90, "mudancas_jornada": [],
                     "volume_caminhao": 8.0, "caminhoes_dia": 3, "juntar": {},
                     "concreto_caminhao_m3": 3.0}
EQUIPE_PADRAO = 2
EQUIPE_MAX = 20
CONCRETAGEM = "concretagem"
LIMITE_ESTIMATIVA = 3.0  # horas estimadas por unidade ≤ 3 × a média dos serviços completos da atividade
SEMANAS_POR_MES = 4.33


def horas_por_dia(parametros: Mapping[str, Any]) -> float:
    return float(parametros["horas_semana"]) / float(parametros["dias_semana"])


def _teto(x: float) -> int:
    """Arredonda para cima ignorando ruído de ponto flutuante (24.000000001 -> 24)."""
    return math.ceil(round(x, 6))


def trocar_horas(horas: Mapping[str, float], trocas: Iterable[tuple[str, str]]) -> tuple[dict[str, float], list[dict[str, Any]]]:
    """Passa as horas de cada função de origem para a de destino (as horas não mudam; somam se o destino já existe).

    Devolve as horas novas e as trocas aplicadas [{origem, destino, horas}] (só as que tinham horas).
    """
    mapa = dict(trocas)
    res: dict[str, float] = {}
    aplicadas = []
    for f, h in horas.items():
        destino = mapa.get(f, f)
        res[destino] = res.get(destino, 0.0) + h
        if destino != f and h > 0:
            aplicadas.append({"origem": f, "destino": destino, "horas": round(h, 2)})
    return res, aplicadas


def destino_final(funcao: str, trocas: Iterable[tuple[str, str]], juntar: Mapping[str, str]) -> str:
    """Função que fica com as horas de `funcao` depois de trocar e juntar."""
    return next(iter(juntar_horas({dict(trocas).get(funcao, funcao): 1.0}, juntar)))


ORIGEM_DIGITADO = "digitado"
ORIGEM_COMPOSICAO = "composição"
ORIGEM_OUTRAS_OBRAS = "outras obras"
ORIGEM_BIBLIOTECA = "biblioteca"
SEM_ESTIMATIVA = "sem estimativa"
AVISO_SEM_PESSOAS = "sem estimativa de pessoas: digite na mão de obra"


def _fmt_h(h: float) -> str:
    return f"{h:.1f}".replace(".", ",") if h < 10 else f"{h:.0f}"


def nome_terceirizado(rotulo: str) -> str:
    return f"{rotulo} (terceirizado)"


ORIGEM_EQUIPE_PADRAO = "equipe padrão"
# origens da duração da terceirizada (ajuste 7.1)
DUR_DIGITADA = "digitada"
DUR_PRODUCAO_DIGITADA = "produção digitada"
DUR_FIXA = "fixa da biblioteca"


def terceirizado_da_atividade(ativ: Mapping[str, Any], ex: Mapping[str, Any], calc: Mapping[str, Any] | None,
                              ajustadas: Mapping[str, float], duracao: Mapping[str, Any] | None, horas_dia: float,
                              padrao_outras_obras: int | None = None) -> dict[str, Any]:
    """Nome e pessoas do terceirizado. Pessoas (ajuste 7.1), nesta ordem: digitado nesta obra → último valor
    digitado em outra obra → pessoas_terceirizado da biblioteca → equipe_padrao da atividade → 0 (sem estimativa).
    As horas da composição não definem mais a equipe: ficam só no detalhe (horas por função).
    """
    principal = (calc or {}).get("funcao_principal") or ativ.get("equipe_principal")
    rotulo = (ativ.get("rotulo_terceirizado") or "").strip() or principal or ativ.get("nome") or ativ.get("codigo")
    digitado = ex.get("pessoas_terceirizado")
    equipe_padrao = ex.get("equipe_padrao") or ativ.get("equipe_padrao")
    if digitado:
        pessoas, origem = int(digitado), ORIGEM_DIGITADO
    elif padrao_outras_obras:
        pessoas, origem = int(padrao_outras_obras), ORIGEM_OUTRAS_OBRAS
    elif ativ.get("pessoas_terceirizado"):
        pessoas, origem = int(ativ["pessoas_terceirizado"]), ORIGEM_BIBLIOTECA
    elif equipe_padrao:
        pessoas, origem = int(equipe_padrao), ORIGEM_EQUIPE_PADRAO
    else:
        pessoas, origem = 0, SEM_ESTIMATIVA
    return {"rotulo": rotulo, "nome": nome_terceirizado(rotulo), "rotulo_obra": ativ.get("rotulo_terceirizado") or "",
            "rotulo_biblioteca": ativ.get("rotulo_terceirizado_biblioteca") or "",
            "pessoas": pessoas, "origem": origem, "detalhe": {}, "por_modo": False,
            "horas_composicao": {f: round(h, 2) for f, h in ajustadas.items() if h > 0},
            "digitado": int(digitado) if digitado else None, "padrao_outras_obras": padrao_outras_obras,
            "pessoas_biblioteca": ativ.get("pessoas_terceirizado"),
            "aviso": AVISO_SEM_PESSOAS if origem == SEM_ESTIMATIVA else None}


def quantidades_por_unidade(servicos: Iterable[Mapping[str, Any]]) -> dict[str, float]:
    q: dict[str, float] = defaultdict(float)
    for s in servicos:
        if s.get("unidade"):
            q[unidade_canonica(s["unidade"])] += s.get("quantidade") or 0.0
    return dict(q)


def duracao_terceirizada(ativ: Mapping[str, Any], ex: Mapping[str, Any], quantidades: Mapping[str, float],
                         ajustadas: Mapping[str, float], equip: Mapping[str, float], calc: Mapping[str, Any] | None,
                         pessoas: int, horas_dia: float, producao_outras_obras: str | None = None
                         ) -> tuple[dict[str, Any] | None, list[str]]:
    """Duração da instalação da terceirizada (ajuste 7.1), nesta ordem: digitada → produção digitada (ou padrão de
    outras obras) → producao_terceirizado da biblioteca → horas da composição ÷ (pessoas × horas/dia) (ou as horas de
    equipamento ÷ máquinas, o maior) → nenhuma (None: pendência). Devolve (duração, avisos)."""
    from atividades.biblioteca import formatar_producao, interpretar_producao

    avisos: list[str] = []
    if ex.get("duracao_manual"):
        return {"dias": int(ex["duracao_manual"]), "unidade": "uteis", "tipo": "manual", "origem": DUR_DIGITADA}, avisos
    if ativ.get("duracao_fixa_dias"):
        return {"dias": int(ativ["duracao_fixa_dias"]), "unidade": "corridos", "tipo": "fixa", "origem": DUR_FIXA}, avisos
    opcoes = []
    if ex.get("producao_terceirizado"):
        opcoes.append((ex["producao_terceirizado"], DUR_PRODUCAO_DIGITADA))
    elif producao_outras_obras:
        opcoes.append((producao_outras_obras, ORIGEM_OUTRAS_OBRAS))
    if ativ.get("producao_terceirizado"):
        opcoes.append((ativ["producao_terceirizado"], ORIGEM_BIBLIOTECA))
    for texto, origem in opcoes:
        try:
            prod = interpretar_producao(texto)
        except ValueError as e:
            avisos.append(f"{ativ.get('codigo')}: {e}.")
            continue
        if not prod:
            continue
        valor, un = prod
        base = {"unidade": "uteis", "tipo": "producao", "origem": origem, "producao": formatar_producao(prod)}
        if un is None:
            return {**base, "dias": max(1, _teto(valor))}, avisos
        qtd = quantidades.get(unidade_canonica(un), 0.0)
        if qtd <= 0:
            avisos.append(f"{ativ.get('codigo')}: produção '{formatar_producao(prod)}' ({origem}), mas nenhum serviço "
                          f"da atividade está em {un}; usando a opção seguinte.")
            continue
        return {**base, "dias": max(1, _teto(qtd / valor)), "quantidade": round(qtd, 4), "unidade_producao": un}, avisos
    horas = {f: h for f, h in ajustadas.items() if h > 0}
    eq = {e: h for e, h in equip.items() if h > 0}
    if (horas or eq) and pessoas > 0:
        dias = sum(horas.values()) / (pessoas * horas_dia) if horas else 0.0
        maq = (calc or {}).get("maquinas") or {}
        for e, h in eq.items():
            dias = max(dias, h / (max(1, int(maq.get(e) or 1)) * horas_dia))
        return {"dias": max(1, _teto(dias)), "unidade": "uteis", "tipo": "composicao", "origem": ORIGEM_COMPOSICAO}, avisos
    return None, avisos


def texto_detalhe(detalhe: Mapping[str, int]) -> str:
    """{'Eletricista': 2, 'Ajudante de eletricista': 1} → '2 eletricistas + 1 ajudante de eletricista'."""
    partes = []
    for f, n in sorted(detalhe.items(), key=lambda x: (-x[1], x[0])):
        nome = f.lower()
        if n > 1:
            pal = nome.split(" ")
            pal[0] = pal[0] + ("es" if pal[0].endswith(("r", "z")) else "s")
            nome = " ".join(pal)
        partes.append(f"{n} {nome}")
    return " + ".join(partes)


def calcular_duracao(
    horas_ajustadas: Mapping[str, float],
    horas_equipamento: Mapping[str, float],
    equipe_padrao: int,
    horas_dia: float,
    maquinas: Mapping[str, int] | None = None,
    dias_minimos: int | None = None,
    principal: str | None = None,
) -> dict[str, Any] | None:
    """Duração (dias úteis) com a equipe padrão. None se não houver horas.

    Função principal = a de mais horas (ou `principal`, se informada e com horas); ela recebe `equipe_padrao` pessoas; cada outra função
    recebe teto(equipe_padrao × horas da função ÷ horas da principal), mínimo 1.
    Duração = maior entre as funções (horas ÷ (pessoas × horas/dia)) e os equipamentos
    (horas ÷ (máquinas × horas/dia); padrão 1 máquina de cada), arredondada para cima.
    """
    horas = {f: h for f, h in horas_ajustadas.items() if h > 0}
    equip = {e: h for e, h in horas_equipamento.items() if h > 0}
    if not horas and not equip and not dias_minimos:
        return None
    equipe: dict[str, int] = {}
    dias_funcao: dict[str, float] = {}
    if not horas:
        principal = None
    else:
        if principal not in horas:
            principal = max(horas, key=lambda f: (horas[f], f))
        hp = horas[principal]
        for f, h in horas.items():
            equipe[f] = equipe_padrao if f == principal else max(1, _teto(equipe_padrao * h / hp))
            dias_funcao[f] = h / (equipe[f] * horas_dia)
    maquinas = maquinas or {}
    qtd_maquinas = {e: max(1, int(maquinas.get(e) or 1)) for e in equip}
    dias_equip = {e: h / (qtd_maquinas[e] * horas_dia) for e, h in equip.items()}
    dias_pessoas = max(dias_funcao.values(), default=0.0)
    dias_maquinas = max(dias_equip.values(), default=0.0)
    limitante = "equipamento" if dias_maquinas > dias_pessoas else "mao_de_obra"
    exatos = max(dias_pessoas, dias_maquinas)
    if dias_minimos and dias_minimos > _teto(exatos):
        limitante, exatos = CONCRETAGEM, float(dias_minimos)
    return {
        "funcao_principal": principal,
        "equipe": equipe,
        "dias_por_funcao": {f: round(d, 2) for f, d in dias_funcao.items()},
        "dias_por_equipamento": {e: round(d, 2) for e, d in dias_equip.items()},
        "maquinas": qtd_maquinas,
        "dias_exatos": round(exatos, 4),
        "dias": max(1, _teto(exatos)),
        "limitante": limitante,
        "dias_concretagem": dias_minimos,
    }


def dias_concretagem(volume_m3: float, volume_caminhao: float, caminhoes_dia: float) -> int | None:
    """Duração mínima pela concretagem: teto(volume ÷ (m³ por caminhão × caminhões por dia))."""
    if not volume_m3 or volume_m3 <= 0 or not volume_caminhao or not caminhoes_dia:
        return None
    return _teto(volume_m3 / (float(volume_caminhao) * float(caminhoes_dia)))


def semanas_do_prazo(valor: float | None, unidade: str | None) -> float | None:
    if not valor:
        return None
    fator = {"meses": SEMANAS_POR_MES, "semanas": 1.0, "dias": 1 / 7, "anos": 52.0}.get(unidade or "meses")
    return valor * fator if fator else None


def trocas_da_atividade(ativ: Mapping[str, Any]) -> list[tuple[str, str]]:
    """trocar_funcoes da cópia da atividade na obra ('Pintor > Servente; ...')."""
    from atividades.biblioteca import interpretar_trocas

    return interpretar_trocas(ativ.get("trocar_funcoes"))[0]


# --------------------------------------------------------------------------- estimativas


def _soma_horas(analise: Mapping[str, Any], qtd: float, origens: Iterable[str] | None = None) -> dict[str, float]:
    tot: dict[str, float] = defaultdict(float)
    for h in analise["horas"]:
        if origens is None or h["origem"] in origens:
            tot[h["funcao"]] += h["horas_un"] * qtd
    return tot


def _completo(analise: Mapping[str, Any]) -> bool:
    return (analise["origem"] in (COMPOSICAO, BANCO, REFERENCIA, MANUAL) and not analise["pendentes"]
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
    media_ativ: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])  # horas, quantidade dos completos
    for s in servicos:
        cod = s.get("atividade_biblioteca")
        a = analises.get(s["id"])
        ativ = atividades.get(cod)
        if not a or not ativ or ativ["tipo"] == INDIRETA:
            continue
        qtd = s.get("quantidade") or 0.0
        horas_reais_ativ[cod] += sum(h["horas_un"] for h in a["horas"] if h["origem"] != ESTIMADO) * qtd
        if _completo(a) and qtd > 0:
            media_ativ[cod][0] += sum(h["horas_un"] for h in a["horas"]) * qtd
            media_ativ[cod][1] += qtd
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
        razao_total = sum(por_funcao.values())
        # proteção: horas estimadas por unidade > 3 × média dos serviços completos da mesma atividade
        fator, limite_un = 1.0, None
        hm, qm = media_ativ.get(cod, (0.0, 0.0))
        estimadas_un = custo * razao_total / qtd
        if qm > 0 and hm > 0 and estimadas_un > LIMITE_ESTIMATIVA * hm / qm:
            limite_un = LIMITE_ESTIMATIVA * hm / qm
            fator = limite_un / estimadas_un
        for f, k in por_funcao.items():
            if k * custo > 0:
                a["horas"].append({"funcao": f, "horas_un": k * custo * fator / qtd, "origem": ESTIMADO})
        for p in a["pendentes"]:
            p["horas_estimadas"] = round((p["total_linha"] or 0.0) * qtd * razao_total * fator, 4)
        a["estimativa"] = {"nivel": nivel, "custo": round(custo, 2), "razao_h_por_real": round(razao_total, 6),
                           "horas": round(custo * razao_total * fator, 2), "limitada": limite_un is not None,
                           "horas_sem_limite": round(custo * razao_total, 2) if limite_un is not None else None,
                           "limite_h_un": round(limite_un, 4) if limite_un is not None else None}
        if limite_un is not None:
            avisos.append({"servico": s["id"], "limitada": True,
                           "mensagem": f"Item {s['item']}: estimativa limitada a 3 × a média da atividade "
                                       f"({limite_un:.3f} h/un), revisar."})
    return avisos


# --------------------------------------------------------------------------- resumo


def calcular_obra(
    servicos: list[Mapping[str, Any]],
    analises: dict[Any, dict[str, Any]],
    atividades: Mapping[str, Mapping[str, Any]],
    execucao: Mapping[str, Mapping[str, Any]],
    parametros: Mapping[str, Any],
    prazo: tuple[float | None, str | None] = (None, None),
    pessoas_padrao: Mapping[str, int] | None = None,
    producao_padrao: Mapping[str, str] | None = None,
    funcoes_terceirizadas: Iterable[str] = (),
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
        # ajuste 7.1: em atividade própria, horas de função que a empresa não tem (Serralheiro, Montador) ficam fora
        horas_de_terceirizado: dict[str, float] = {}
        if ex.get("execucao") == PROPRIA:
            for f in [f for f in brutas if f in set(funcoes_terceirizadas)]:
                if brutas[f] > 0:
                    horas_de_terceirizado[f] = round(brutas[f], 2)
                del brutas[f]
        juntar = params.get("juntar") or {}
        # ordem (item 6): composição → funcoes.xlsx → trocar_funcoes da atividade → juntar funções
        trocas = trocas_da_atividade(ativ) if ex.get("execucao") == PROPRIA else []
        principal_forcada = None
        trocas_aplicadas: list[dict[str, Any]] = []
        if trocas:
            antes = juntar_horas(dict(brutas), juntar)
            principal_antes = max(antes, key=lambda f: (antes[f], f)) if any(v > 0 for v in antes.values()) else None
            brutas, trocas_aplicadas = trocar_horas(dict(brutas), trocas)
            if principal_antes in dict(trocas):
                # a função principal foi trocada: a de destino passa a ser a principal (equipe padrão e máxima)
                principal_forcada = destino_final(principal_antes, trocas, juntar)
        brutas = defaultdict(float, juntar_horas(dict(brutas), juntar))
        rendimento = ex.get("rendimento") or params["rendimento"]
        ajustadas = {f: h / rendimento for f, h in brutas.items()}
        equipe_padrao = int(ex.get("equipe_padrao") or ativ.get("equipe_padrao") or EQUIPE_PADRAO)
        volume = sum((s.get("quantidade") or 0.0) for s in servs if unidade_canonica(s.get("unidade")) == "M3")
        minimo = (dias_concretagem(volume, params["volume_caminhao"], params["caminhoes_dia"])
                  if ativ.get("tipo_producao") == CONCRETAGEM else None)
        calc = calcular_duracao(ajustadas, equip, equipe_padrao, hd, ex.get("maquinas"), minimo, principal_forcada)
        execucao_escolhida = ex.get("execucao")

        terceirizado = None
        avisos_terc: list[str] = []
        if execucao_escolhida == TERCEIRIZADA:
            terceirizado = terceirizado_da_atividade(ativ, ex, calc, ajustadas, None, hd, (pessoas_padrao or {}).get(cod))
            duracao, avisos_terc = duracao_terceirizada(ativ, ex, quantidades_por_unidade(servs), ajustadas, equip, calc,
                                                        terceirizado["pessoas"], hd, (producao_padrao or {}).get(cod))
            terceirizado["duracao_origem"] = (duracao or {}).get("origem")
            terceirizado["duracao_tipo"] = (duracao or {}).get("tipo")
            terceirizado["producao"] = (duracao or {}).get("producao")
            for t in avisos_terc:
                avisos.append({"atividade": cod, "mensagem": t})
        elif ex.get("duracao_manual"):
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
            if execucao_escolhida == TERCEIRIZADA:
                msg = f"{cod}: terceirizada sem produção nem horas; informe a produção (ex.: 150 M2/dia) ou a duração."
            else:
                msg = f"{cod}: sem horas de mão de obra; informe a duração em dias úteis."
            pendencias.append({"tipo": "duracao", "atividade": cod, "mensagem": msg})
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
            "trocar_funcoes": ativ.get("trocar_funcoes") or "",
            "trocar_funcoes_biblioteca": ativ.get("trocar_funcoes_biblioteca") or "",
            "trocas_aplicadas": trocas_aplicadas,
            "horas_de_terceirizado": horas_de_terceirizado,
            "avisos_terceirizado": [f"{_fmt_h(h)} h de {f} são de terceirizado e não entram na equipe própria"
                                    for f, h in horas_de_terceirizado.items()],
            "horas_ajustadas": {f: round(h, 2) for f, h in sorted(ajustadas.items(), key=lambda x: -x[1])},
            "horas_por_origem": {o: round(h, 2) for o, h in por_origem.items() if h},
            "custo_por_origem": {o: round(c, 2) for o, c in custo_origem_ativ.items() if c},
            "horas_equipamento": {e: round(h, 2) for e, h in sorted(equip.items(), key=lambda x: -x[1])},
            "funcao_principal": calc["funcao_principal"] if calc else None,
            "calculo": calc,
            "duracao": duracao,
            "duracao_manual": ex.get("duracao_manual"),
            "duracao_fixa_dias": ativ.get("duracao_fixa_dias"),
            "tipo_producao": ativ.get("tipo_producao"),
            "volume_m3": round(volume, 4) if ativ.get("tipo_producao") == CONCRETAGEM else None,
            "dias_concretagem": minimo,
            "ordem_biblioteca": ativ.get("ordem_biblioteca", 0),
            "terceirizado": terceirizado,
            "rotulo_terceirizado": ativ.get("rotulo_terceirizado") or "",
            "rotulo_terceirizado_biblioteca": ativ.get("rotulo_terceirizado_biblioteca") or "",
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
                 for o in (COMPOSICAO, BANCO, REFERENCIA, ESTIMADO, MANUAL, SEM_MAO_DE_OBRA)}
    com_horas = sum(cobertura[o]["custo"] for o in (COMPOSICAO, BANCO, REFERENCIA, ESTIMADO, MANUAL))
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
