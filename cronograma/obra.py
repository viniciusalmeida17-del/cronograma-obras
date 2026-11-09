"""Etapa 5 aplicada a uma obra gravada no banco: parâmetros, cenários, comparação e cronograma escolhido."""
from __future__ import annotations

import io
import re
import threading
from collections import defaultdict
from datetime import date
from typing import Any, Callable, Iterable

from armazenamento import Banco
from atividades.biblioteca import Biblioteca
from leitor_planilha.texto import unidade_canonica
from mao_de_obra import obra as etapa4

from .agenda import DIAS_POR_MES, Instancia, ItemIndireto
from .calendario import Calendario, data_limite, para_data, segunda_da_semana
from .modelo import PROPRIA, tarefas_da_obra
from .otimizador import IMPOSSIVEL, MELHOR, OTIMO, otimizar

_RE_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
VALIDAS = (OTIMO, MELHOR)


class ErroCronograma(Exception):
    pass


# --------------------------------------------------------------------------- custos por hora


def custos_das_composicoes(banco: Banco, obra_id: int) -> dict[str, dict[str, Any]]:
    """Custo/h inicial de cada função: média ponderada pelas horas do preço das linhas de mão de obra.

    Usa só as linhas "com encargos complementares" quando a função tem alguma; senão todas.
    """
    linhas = banco.carregar_custos_mao_de_obra(obra_id)
    acc: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])
    for l in linhas:
        q = l["quantidade"] or 0.0
        a = acc[l["funcao"]]
        a[0] += l["horas_un"] * q
        a[1] += l["custo_un"] * q
        a[2] += l["horas_un_encargos"] * q
        a[3] += l["custo_un_encargos"] * q
    res = {}
    for f, (h, c, he, ce) in acc.items():
        if he > 0:
            res[f] = {"custo_hora": round(ce / he, 2), "horas": round(he, 2), "base": "com encargos"}
        elif h > 0:
            res[f] = {"custo_hora": round(c / h, 2), "horas": round(h, 2), "base": "todas as linhas"}
    return res


def _funcoes_proprias(estado: dict[str, Any]) -> list[str]:
    horas: dict[str, float] = defaultdict(float)
    for a in estado["atividades"]:
        if a["execucao"] == PROPRIA and a["tipo"] != "indireta":
            for f, h in a["horas_ajustadas"].items():
                horas[f] += h
    return sorted(horas, key=lambda f: -horas[f])


def custos_efetivos(banco: Banco, obra_id: int, funcoes: Iterable[str]) -> dict[str, dict[str, Any]]:
    """Custo/h por função: o desta obra → o último usado (outra obra) → o das composições."""
    cal = banco.carregar_calendario(obra_id)
    ultimos = banco.custos_hora_padrao()
    comp = custos_das_composicoes(banco, obra_id)
    res = {}
    for f in funcoes:
        if cal["custos_hora"].get(f) is not None:
            res[f] = {"custo_hora": cal["custos_hora"][f], "origem": "obra"}
        elif f in ultimos:
            res[f] = {"custo_hora": ultimos[f], "origem": "ultimo_usado"}
        elif f in comp:
            res[f] = {"custo_hora": comp[f]["custo_hora"], "origem": "composicoes"}
        else:
            res[f] = {"custo_hora": None, "origem": "faltando"}
        res[f]["composicoes"] = (comp.get(f) or {}).get("custo_hora")
    return res


# --------------------------------------------------------------------------- parâmetros


def _estado_etapa4(banco: Banco, obra_id: int, biblioteca: Biblioteca | None) -> dict[str, Any]:
    try:
        estado = etapa4.estado_mao_de_obra(banco, obra_id, biblioteca)
    except etapa4.ErroMaoDeObra as exc:
        raise ErroCronograma(str(exc))
    if not banco.carregar_custos_mao_de_obra(obra_id) and banco.arquivo_da_obra(obra_id):
        # obra analisada antes da etapa 5: relê as composições para ter os custos por hora
        estado = etapa4.analisar_obra(banco, obra_id, biblioteca)
    return estado


def prazos_padrao(prazo: float | None) -> list[float]:
    if not prazo:
        return []
    p = int(round(prazo))
    return [float(x) for x in (p - 3, p - 2, p - 1, p) if x > 0]


def prazo_licitacao_meses(obra: dict[str, Any]) -> float | None:
    v, u = obra.get("prazo_valor"), obra.get("prazo_unidade") or "meses"
    if not v:
        return None
    return {"meses": 1.0, "anos": 12.0, "semanas": 7 / DIAS_POR_MES, "dias": 1 / DIAS_POR_MES}.get(u, 1.0) * float(v)


def parametros_cronograma(banco: Banco, obra_id: int, biblioteca: Biblioteca | None = None) -> dict[str, Any]:
    estado = _estado_etapa4(banco, obra_id, biblioteca)
    cal = banco.carregar_calendario(obra_id)
    obra = banco.carregar_obra(obra_id)["obra"]
    prazo = prazo_licitacao_meses(obra)
    funcoes = _funcoes_proprias(estado)
    p4 = banco.carregar_parametros(obra_id)
    travadas = banco.equipes_travadas(obra_id)
    atividades = [{"codigo": a["codigo"], "nome": a["nome"], "funcao_principal": a["funcao_principal"],
                   "equipe_padrao": a["equipe_padrao"], "equipe_max": a["equipe_max"], "travada": travadas.get(a["codigo"])}
                  for a in estado["atividades"] if a["execucao"] == PROPRIA and a["funcao_principal"]
                  and (a.get("duracao") or {}).get("tipo") == "calculada"]
    return {
        **cal,
        "prazos": cal["prazos"] or prazos_padrao(prazo),
        "prazo_licitacao": prazo,
        "dias_semana": p4["dias_semana"], "horas_semana": p4["horas_semana"], "mudancas_jornada": p4["mudancas_jornada"],
        "custos": custos_efetivos(banco, obra_id, funcoes),
        "funcoes": funcoes,
        "atividades_proprias": atividades,
        "pendencias_etapa4": estado["pendencias"],
        "obra": {k: obra.get(k) for k in ("id", "nome", "prazo_valor", "prazo_unidade")},
    }


def _inteiro(valor: Any, nome: str, minimo: int, maximo: int, vazio_ok: bool = False) -> int | None:
    if valor in (None, ""):
        if vazio_ok:
            return None
        raise ErroCronograma(f"Informe {nome}.")
    try:
        v = float(str(valor).replace(",", "."))
    except ValueError:
        raise ErroCronograma(f"{nome[0].upper() + nome[1:]} inválido.")
    if v != int(v) or not minimo <= v <= maximo:
        raise ErroCronograma(f"{nome[0].upper() + nome[1:]} deve ser um número inteiro entre {minimo} e {maximo}.")
    return int(v)


def salvar_parametros_cronograma(banco: Banco, obra_id: int, dados: dict[str, Any]) -> None:
    c = banco.carregar_calendario(obra_id)
    if "data_inicio" in dados:
        d = str(dados["data_inicio"] or "").strip()
        if d and not _RE_DATA.match(d):
            raise ErroCronograma("Data de início inválida (use AAAA-MM-DD).")
        try:
            c["data_inicio"] = para_data(d).isoformat() if d else None
        except ValueError:
            raise ErroCronograma("Data de início inválida.")
    if "feriados_locais" in dados:
        feriados = []
        for f in dados["feriados_locais"] or []:
            f = f if isinstance(f, dict) else {"data": f}
            d = str(f.get("data") or "").strip()
            if not d:
                continue
            try:
                feriados.append({"data": para_data(d).isoformat(), "nome": (f.get("nome") or "").strip() or "Feriado local"})
            except ValueError:
                raise ErroCronograma(f"Data inválida no feriado local: '{d}' (use AAAA-MM-DD).")
        c["feriados_locais"] = sorted(feriados, key=lambda f: f["data"])
    if "limite_rigidas" in dados:
        c["limite_rigidas"] = _inteiro(dados["limite_rigidas"], "o limite das rígidas (dias úteis)", 0, 60)
    if "tempo_limite" in dados:
        c["tempo_limite"] = _inteiro(dados["tempo_limite"], "o tempo limite do otimizador (segundos)", 5, 3600)
    if "max_pessoas_total" in dados:
        c["max_pessoas_total"] = _inteiro(dados["max_pessoas_total"], "o máximo de pessoas no canteiro", 1, 1000, True)
    if "max_por_funcao" in dados:
        c["max_por_funcao"] = {}
        for f, v in (dados["max_por_funcao"] or {}).items():
            n = _inteiro(v, f"o máximo de {f}", 1, 1000, True)
            if n is not None:
                c["max_por_funcao"][f] = n
    if "custos_hora" in dados:
        custos = {}
        for f, v in (dados["custos_hora"] or {}).items():
            if v in (None, ""):
                continue
            try:
                x = float(str(v).replace(",", "."))
            except ValueError:
                raise ErroCronograma(f"Custo por hora inválido para {f}.")
            if not 0 < x < 10000:
                raise ErroCronograma(f"Custo por hora de {f} deve ser maior que zero.")
            custos[f] = round(x, 2)
        c["custos_hora"] = custos
        banco.lembrar_custos_hora(custos)
    if "prazos" in dados:
        prazos = []
        for p in dados["prazos"] or []:
            if p in (None, ""):
                continue
            try:
                v = float(str(p).replace(",", "."))
            except ValueError:
                raise ErroCronograma(f"Prazo inválido: '{p}'.")
            if not 0 < v <= 120:
                raise ErroCronograma("Os prazos devem estar entre 1 e 120 meses.")
            prazos.append(v)
        c["prazos"] = sorted(set(prazos))
    banco.salvar_calendario(obra_id, c)


def travar_equipe(banco: Banco, obra_id: int, codigo: str, pessoas: Any, biblioteca: Biblioteca | None = None) -> None:
    """Trava o tamanho da equipe (pessoas da função principal) de uma atividade própria. Vazio destrava."""
    estado = _estado_etapa4(banco, obra_id, biblioteca)
    a = next((a for a in estado["atividades"] if a["codigo"] == codigo), None)
    if a is None or a["execucao"] != PROPRIA or not a["funcao_principal"]:
        raise ErroCronograma(f"{codigo}: só dá para travar a equipe de atividade própria com horas.")
    n = _inteiro(pessoas, "o tamanho da equipe", 1, a["equipe_max"], True)
    banco.travar_equipe(obra_id, codigo, n)


# --------------------------------------------------------------------------- instância


def calendario_da_obra(banco: Banco, obra_id: int) -> Calendario:
    c = banco.carregar_calendario(obra_id)
    if not c["data_inicio"]:
        raise ErroCronograma("Informe a data de início da obra nos parâmetros do cronograma.")
    p4 = banco.carregar_parametros(obra_id)
    return Calendario(c["data_inicio"], p4["dias_semana"], p4["horas_semana"], p4["mudancas_jornada"],
                      c["feriados_locais"])


def indiretos_da_obra(servicos: list[dict[str, Any]], atividades: dict[str, dict[str, Any]],
                      prazo_licitacao: float | None) -> list[ItemIndireto]:
    """Itens das atividades indiretas, com o custo por mês quando ele varia com o prazo (item 5 da especificação)."""
    itens = []
    for s in servicos:
        a = atividades.get(s.get("atividade_biblioteca"))
        if not a or a["tipo"] != "indireta":
            continue
        total = s.get("total") or 0.0
        de, ate = a.get("periodo_de") or "INICIO_OBRA", a.get("periodo_ate") or "FIM_OBRA"
        toda = de == "INICIO_OBRA" and ate == "FIM_OBRA"
        un = unidade_canonica(s.get("unidade"))
        base = dict(descricao=f"{s['item']} {s.get('descricao') or ''}".strip(), atividade=a["codigo"],
                    custo_total=total, de=de, ate=ate, unidade=s.get("unidade"))
        if un == "MES" and toda and prazo_licitacao:
            itens.append(ItemIndireto(tipo="obra", custo_mes=total / prazo_licitacao, previsto_meses=prazo_licitacao, **base))
        elif un == "MES" and not toda and s.get("quantidade"):
            itens.append(ItemIndireto(tipo="periodo", custo_mes=total / s["quantidade"], previsto_meses=s["quantidade"],
                                      **base))
        elif un == "M2/MES":
            itens.append(ItemIndireto(tipo="fixo", motivo="não varia com o prazo nesta versão", **base))
        else:
            itens.append(ItemIndireto(tipo="fixo", motivo="custo fixo", **base))
    return itens


def montar_instancia(banco: Banco, obra_id: int, prazo_meses: float, biblioteca: Biblioteca | None = None,
                     estado: dict[str, Any] | None = None) -> tuple[Instancia, dict[str, Any]]:
    estado = estado or _estado_etapa4(banco, obra_id, biblioteca)
    if estado["pendencias"]:
        raise ErroCronograma("Resolva as pendências da etapa 4 antes do cronograma: "
                             + "; ".join(p["mensagem"] for p in estado["pendencias"][:5]))
    cal = calendario_da_obra(banco, obra_id)
    c = banco.carregar_calendario(obra_id)
    rede = banco.carregar_rede(obra_id)
    dados = banco.carregar_obra(obra_id)
    tarefas = tarefas_da_obra(estado["atividades"], rede["dependencias"], banco.equipes_travadas(obra_id), cal.jornadas())
    funcoes = sorted({f for t in tarefas.values() for m in t.modos for f in m.equipe})
    custos = custos_efetivos(banco, obra_id, funcoes)
    faltando = [f for f, v in custos.items() if not v["custo_hora"]]
    if faltando:
        raise ErroCronograma("Informe o custo por hora de: " + ", ".join(faltando) + ".")
    prazo_lic = prazo_licitacao_meses(dados["obra"])
    inst = Instancia(
        calendario=cal, tarefas=tarefas, limite=data_limite(cal.inicio, prazo_meses),
        custo_hora={f: v["custo_hora"] for f, v in custos.items()},
        indiretos=indiretos_da_obra(dados["servicos"], rede["atividades"], prazo_lic),
        limite_rigidas=c["limite_rigidas"], max_por_funcao=c["max_por_funcao"], max_total=c["max_pessoas_total"],
    )
    contexto = {"estado": estado, "rede": rede, "equipe_padrao": {a["codigo"]: a["equipe_padrao"] for a in estado["atividades"]},
                "tempo_limite": c["tempo_limite"]}
    return inst, contexto


# --------------------------------------------------------------------------- períodos e equipe indireta


def periodos_indiretas(inst: Instancia, rede: dict[str, Any], res: dict[str, Any]) -> list[dict[str, Any]]:
    """Início e fim de cada atividade indireta a partir das atividades de referência."""
    por_cod = {a["codigo"]: a for a in res["atividades"]}
    inicio_obra = inst.calendario.inicio.isoformat()
    res_p = []
    for cod, a in rede["atividades"].items():
        if a["tipo"] != "indireta":
            continue
        de, ate = a.get("periodo_de") or "INICIO_OBRA", a.get("periodo_ate") or "FIM_OBRA"
        ini = inicio_obra if de == "INICIO_OBRA" else (por_cod.get(de) or {}).get("inicio")
        fim = res["termino"] if ate == "FIM_OBRA" else (por_cod.get(ate) or {}).get("termino")
        res_p.append({"codigo": cod, "nome": a.get("nome"), "de": de, "ate": ate, "inicio": ini, "termino": fim,
                      "total": a.get("total")})
    return res_p


def equipe_indireta_semanal(inst: Instancia, estado: dict[str, Any], periodos: list[dict[str, Any]], n_semanas: int
                            ) -> list[dict[str, Any]]:
    """Equipe indireta (etapa 4) por semana: fixa na obra toda ou no período da atividade indireta."""
    cal = inst.calendario
    per = {p["codigo"]: p for p in periodos}
    linhas: dict[str, list[float]] = defaultdict(lambda: [0.0] * n_semanas)
    for e in estado.get("equipe_indireta") or []:
        p = per.get(e["atividade"])
        if not p or not p["inicio"] or not p["termino"]:
            continue
        s0 = (segunda_da_semana(para_data(p["inicio"])) - cal.semana0).days // 7
        s1 = (segunda_da_semana(para_data(p["termino"])) - cal.semana0).days // 7
        for s in range(max(0, s0), min(n_semanas - 1, s1) + 1):
            linhas[e["funcao"]][s] += e["pessoas"]
    return [{"funcao": f, "pessoas": [round(v, 2) for v in serie]} for f, serie in linhas.items()]


# --------------------------------------------------------------------------- cenários


def calcular_cenario(banco: Banco, obra_id: int, prazo_meses: float, biblioteca: Biblioteca | None = None,
                     tempo_limite: float | None = None, estado: dict[str, Any] | None = None,
                     progresso: Callable[[dict[str, Any]], None] | None = None,
                     parar: threading.Event | None = None) -> dict[str, Any]:
    inst, ctx = montar_instancia(banco, obra_id, prazo_meses, biblioteca, estado)
    limite = tempo_limite if tempo_limite is not None else ctx["tempo_limite"]
    res = otimizar(inst, limite, ctx["equipe_padrao"], progresso, parar)
    res["prazo_meses"] = prazo_meses
    res["data_limite"] = inst.limite.isoformat()
    if res["situacao"] in VALIDAS:
        res["periodos_indiretas"] = periodos_indiretas(inst, ctx["rede"], res)
        n = max((len(v) for v in res["contratados"].values()), default=0)
        res["equipe_indireta"] = equipe_indireta_semanal(inst, ctx["estado"], res["periodos_indiretas"], n)
        res.pop("solucao", None)
    res["id"] = banco.gravar_cenario(obra_id, prazo_meses, inst.limite.isoformat(), res)
    return res


def calcular_cenarios(banco: Banco, obra_id: int, prazos: Iterable[float] | None = None,
                      biblioteca: Biblioteca | None = None, tempo_limite: float | None = None,
                      progresso: Callable[[dict[str, Any]], None] | None = None,
                      parar: threading.Event | None = None) -> dict[str, Any]:
    """Roda o otimizador para cada prazo (meses) e devolve a tabela comparativa."""
    estado = _estado_etapa4(banco, obra_id, biblioteca)
    if prazos is None:
        prazos = banco.carregar_calendario(obra_id)["prazos"] or prazos_padrao(
            prazo_licitacao_meses(banco.carregar_obra(obra_id)["obra"]))
    prazos = sorted({float(p) for p in prazos})
    if not prazos:
        raise ErroCronograma("Escolha pelo menos um prazo para calcular.")
    montar_instancia(banco, obra_id, prazos[-1], biblioteca, estado)  # valida antes de começar
    for i, p in enumerate(prazos):
        if parar is not None and parar.is_set():
            break
        if progresso:
            progresso({"cenario": i, "n": len(prazos), "prazo": p, "evento": "inicio"})
        calcular_cenario(banco, obra_id, p, biblioteca, tempo_limite, estado,
                         (lambda info, i=i, p=p: progresso({**info, "cenario": i, "n": len(prazos), "prazo": p}))
                         if progresso else None, parar)
    return comparacao(banco, obra_id)


def comparacao(banco: Banco, obra_id: int) -> dict[str, Any]:
    """Tabela comparativa dos cenários calculados (item 6 da especificação)."""
    obra = banco.carregar_obra(obra_id)["obra"]
    prazo_lic = prazo_licitacao_meses(obra)
    cenarios = banco.listar_cenarios(obra_id)
    referencia = next((c for c in cenarios if prazo_lic and abs(c["prazo_meses"] - prazo_lic) < 1e-6
                       and c["situacao"] in VALIDAS), None)
    validos = [c for c in cenarios if c["situacao"] in VALIDAS]
    mais_barato = min(validos, key=lambda c: c["custo_total"])["id"] if validos else None
    linhas = []
    for c in cenarios:
        det = c["detalhes"]
        linha = {
            "id": c["id"], "prazo_meses": c["prazo_meses"], "data_limite": c["data_limite"], "situacao": c["situacao"],
            "termino": c["termino"], "pico": c["pico"], "homem_semana": c["homem_semana"], "ociosidade": c["ociosidade"],
            "custo_mao_de_obra": c["custo_mao_de_obra"], "custo_indiretos": c["custo_indiretos"],
            "custo_total": c["custo_total"], "escolhido": c["escolhido"], "mais_barato": c["id"] == mais_barato,
            "calculado_em": c["calculado_em"], "segundos": c["segundos"], "mensagem": det.get("mensagem"),
            "menor_prazo": det.get("menor_prazo"), "limite_inferior": det.get("limite_inferior"),
            "diferenca": None, "diferenca_pct": None,
        }
        if referencia and c["situacao"] in VALIDAS:
            dif = referencia["custo_total"] - c["custo_total"]
            linha["diferenca"] = round(dif, 2)
            linha["diferenca_pct"] = round(100 * dif / referencia["custo_total"], 2) if referencia["custo_total"] else None
        linhas.append(linha)
    return {"cenarios": linhas, "prazo_licitacao": prazo_lic, "mais_barato": mais_barato,
            "referencia": referencia["id"] if referencia else None}


def escolher_cenario(banco: Banco, obra_id: int, cenario_id: int) -> None:
    c = banco.carregar_cenario(int(cenario_id))
    if c is None or c["obra_id"] != obra_id:
        raise ErroCronograma("Cenário não encontrado nesta obra.")
    if c["situacao"] not in VALIDAS:
        raise ErroCronograma("Este cenário não tem cronograma (prazo impossível ou sem solução).")
    banco.escolher_cenario(obra_id, c["id"])


def detalhe_cenario(banco: Banco, obra_id: int, cenario_id: int | None = None) -> dict[str, Any]:
    """Cronograma de um cenário (o escolhido, se não informar) com o que o Gantt e a equipe por semana precisam."""
    if cenario_id is None:
        escolhido = next((c for c in banco.listar_cenarios(obra_id) if c["escolhido"]), None)
        if escolhido is None:
            raise ErroCronograma("Nenhum cenário escolhido ainda.")
        cenario_id = escolhido["id"]
    c = banco.carregar_cenario(int(cenario_id))
    if c is None or c["obra_id"] != obra_id:
        raise ErroCronograma("Cenário não encontrado nesta obra.")
    rede = banco.carregar_rede(obra_id)
    ativ = rede["atividades"]
    for a in c["atividades"]:
        r = ativ.get(a["atividade"]) or {}
        a.update(codigo=a["atividade"], nome=r.get("nome"), etapa=r.get("etapa"), tipo=r.get("tipo"),
                 ordem=r.get("ordem_biblioteca", 0))
    execucao = banco.carregar_execucao(obra_id)
    for a in c["atividades"]:
        a["execucao"] = (execucao.get(a["codigo"]) or {}).get("execucao") or PROPRIA
    c["atividades"].sort(key=lambda a: (a["inicio"], a["ordem"]))
    det = c.pop("detalhes")
    c.update({k: det.get(k) for k in ("caminho_critico", "indiretos", "menor_prazo", "origem", "limite_inferior",
                                       "horas_pagas", "horas_ocupadas", "dias_uteis", "periodos_indiretas",
                                       "equipe_indireta", "mensagem")})
    semanas = sorted({e["semana"] for e in c["equipe_semana"]})
    funcoes: dict[str, dict[str, Any]] = {}
    for e in c["equipe_semana"]:
        f = funcoes.setdefault(e["funcao"], {"funcao": e["funcao"], "contratados": [0] * len(semanas),
                                             "horas_ocupadas": [0.0] * len(semanas), "horas_pagas": [0.0] * len(semanas)})
        k = semanas.index(e["semana"])
        f["contratados"][k] = e["contratados"]
        f["horas_ocupadas"][k] = e["horas_ocupadas"]
        f["horas_pagas"][k] = e["horas_pagas"] or 0.0
    for f in funcoes.values():
        serie = f["contratados"]
        ativas = [k for k, v in enumerate(serie) if v]
        f["entrada"] = semanas[ativas[0]] if ativas else None
        f["saida"] = semanas[ativas[-1]] if ativas else None
        f["pico"] = max(serie, default=0)
        f["semana_pico"] = semanas[serie.index(f["pico"])] if ativas else None
    c["semanas"] = semanas
    c["funcoes"] = sorted(funcoes.values(), key=lambda f: (f["entrada"] or "", -f["pico"]))
    c["total_semana"] = [sum(f["contratados"][k] for f in funcoes.values()) for k in range(len(semanas))]
    return c


def exportar_equipe_excel(banco: Banco, obra_id: int, cenario_id: int | None = None) -> bytes:
    """Tabela semana × função (contratados), com horas ocupadas e a equipe indireta, em .xlsx."""
    import openpyxl
    from openpyxl.styles import Font, PatternFill

    c = detalhe_cenario(banco, obra_id, cenario_id)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Contratados"
    negrito = Font(bold=True)
    ws.append([f"Cenário de {c['prazo_meses']:g} meses — término {c['termino']} — situação {c['situacao']}"])
    ws.append([])
    ws.append(["Função", "Entrada", "Pico", "Saída", *[date.fromisoformat(s).strftime("%d/%m/%Y") for s in c["semanas"]]])
    for cel in ws[3]:
        cel.font = negrito
    for f in c["funcoes"]:
        ws.append([f["funcao"], f["entrada"], f["pico"], f["saida"], *f["contratados"]])
    ws.append(["Total próprios", None, max(c["total_semana"], default=0), None, *c["total_semana"]])
    for cel in ws[ws.max_row]:
        cel.font = negrito
    if c.get("equipe_indireta"):
        ws.append([])
        ws.append(["Equipe indireta (etapa 4)"])
        ws[ws.max_row][0].font = negrito
        for e in c["equipe_indireta"]:
            ws.append([e["funcao"], None, None, None, *e["pessoas"][:len(c["semanas"])]])
    ws.column_dimensions["A"].width = 28
    ws2 = wb.create_sheet("Horas ocupadas")
    ws2.append(["Função", *[date.fromisoformat(s).strftime("%d/%m/%Y") for s in c["semanas"]]])
    for f in c["funcoes"]:
        ws2.append([f["funcao"], *f["horas_ocupadas"]])
    ws2.append([])
    ws2.append(["Horas pagas"])
    for f in c["funcoes"]:
        ws2.append([f["funcao"], *f["horas_pagas"]])
    ws2.column_dimensions["A"].width = 28
    ws3 = wb.create_sheet("Atividades")
    ws3.append(["Código", "Atividade", "Etapa", "Tipo", "Execução", "Início", "Término", "Duração", "Unidade", "Equipe",
                "Folga (dias úteis)", "Crítica"])
    for cel in ws3[1]:
        cel.font = negrito
    destaque = PatternFill("solid", fgColor="FDE2E1")
    for a in sorted(c["atividades"], key=lambda a: (a["inicio"], a["ordem"])):
        ws3.append([a["codigo"], a["nome"], a["etapa"], a["tipo"], a["execucao"], a["inicio"], a["termino"], a["duracao"],
                    a["unidade"], ", ".join(f"{n} {f}" for f, n in a["equipe"].items()), a["folga"],
                    "sim" if a["critica"] else ""])
        if a["critica"]:
            for cel in ws3[ws3.max_row]:
                cel.fill = destaque
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
