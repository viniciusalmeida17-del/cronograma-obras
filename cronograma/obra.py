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

from .agenda import (
    CUSTO_TROCA_HORAS,
    DIAS_POR_MES,
    LIVRE,
    UMA_ENTRADA,
    Instancia,
    ItemIndireto,
    canteiro_conta_terceirizados,
    contar_terceirizados,
    dias_com_canteiro,
)
from .calendario import Calendario, data_limite, para_data, segunda_da_semana
from .modelo import (
    EQUIPE_MAX,
    MAQUINAS_MAX,
    OPERADOR,
    PROPRIA,
    RIGIDA,
    TERCEIRIZADA,
    Modo,
    modos_da_atividade,
    tarefas_da_obra,
)
from .otimizador import IMPOSSIVEL, MELHOR, OTIMO, menor_prazo, otimizar

_RE_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
VALIDAS = (OTIMO, MELHOR)
SEMANAS_POR_MES = 4.33
ENCARGOS_PADRAO = 80.0
# livres por padrão; o bombeiro (muitas vezes terceirizado) entra e sai conforme a frente de serviço
TRANSFERIVEIS_PADRAO = ("Servente", "Pedreiro", "Bombeiro", "Ajudante de bombeiro")
CRITERIOS = ("proporcional", "mensal", "fixo")
AVISO_REFERENCIA = "custos de mão de obra de referência da licitação, não os reais"


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


def custo_hora_do_salario(salario: float, encargos_pct: float, horas_semana: float) -> float:
    """Custo por hora = salário × (1 + encargos) ÷ horas pagas no mês (horas por semana × 4,33)."""
    return round(float(salario) * (1 + float(encargos_pct) / 100) / (float(horas_semana) * SEMANAS_POR_MES), 2)


def encargos_efetivos(banco: Banco, obra_id: int) -> float:
    cal = banco.carregar_calendario(obra_id)
    if cal.get("encargos") is not None:
        return float(cal["encargos"])
    padrao = banco.padrao("encargos")
    return float(padrao) if padrao is not None else ENCARGOS_PADRAO


def custos_efetivos(banco: Banco, obra_id: int, funcoes: Iterable[str]) -> dict[str, dict[str, Any]]:
    """Custo/h real por função.

    Ordem: salário desta obra → custo/h digitado nesta obra → salário da última obra → custo/h da última
    obra → composições da planilha (referência da licitação, não o custo real).
    """
    cal = banco.carregar_calendario(obra_id)
    horas_semana = banco.carregar_parametros(obra_id)["horas_semana"]
    encargos = encargos_efetivos(banco, obra_id)
    salarios_padrao = banco.padrao("salarios") or {}
    ultimos = banco.custos_hora_padrao()
    comp = custos_das_composicoes(banco, obra_id)
    res = {}
    for f in funcoes:
        sal = (cal.get("salarios") or {}).get(f)
        if sal:
            res[f] = {"custo_hora": custo_hora_do_salario(sal, encargos, horas_semana), "origem": "salario", "salario": sal}
        elif cal["custos_hora"].get(f) is not None:
            res[f] = {"custo_hora": cal["custos_hora"][f], "origem": "obra"}
        elif salarios_padrao.get(f):
            sal = salarios_padrao[f]
            res[f] = {"custo_hora": custo_hora_do_salario(sal, encargos, horas_semana), "origem": "salario_padrao",
                      "salario": sal}
        elif f in ultimos:
            res[f] = {"custo_hora": ultimos[f], "origem": "ultimo_usado"}
        elif f in comp:
            res[f] = {"custo_hora": comp[f]["custo_hora"], "origem": "composicoes"}
        elif f == OPERADOR and ("Pedreiro" in comp or comp):
            # sem linha de operador nas composições: usa o custo do pedreiro como referência
            ref = comp.get("Pedreiro") or max(comp.values(), key=lambda v: v["custo_hora"])
            res[f] = {"custo_hora": ref["custo_hora"], "origem": "composicoes_pedreiro"}
        else:
            res[f] = {"custo_hora": None, "origem": "faltando"}
        res[f]["composicoes"] = (comp.get(f) or {}).get("custo_hora")
        res[f]["referencia"] = res[f]["origem"] in ("composicoes", "composicoes_pedreiro", "faltando")
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
    """Prazo da licitação (cenário principal), −1, −2 e −3 meses. Nunca maiores que o prazo."""
    if not prazo:
        return []
    return sorted({round(float(prazo) - k, 2) for k in (3, 2, 1, 0) if prazo - k > 0})


def _prazos_validos(prazos: Iterable[float], prazo_lic: float | None) -> list[float]:
    """Prazos a calcular: os pedidos que não passam do prazo da licitação, sempre com o cenário principal."""
    lista = {round(float(p), 2) for p in prazos if not prazo_lic or float(p) <= prazo_lic + 1e-9}
    if prazo_lic:
        lista.add(round(float(prazo_lic), 2))
    return sorted(lista)


def prazo_licitacao_meses(obra: dict[str, Any]) -> float | None:
    v, u = obra.get("prazo_valor"), obra.get("prazo_unidade") or "meses"
    if not v:
        return None
    return {"meses": 1.0, "anos": 12.0, "semanas": 7 / DIAS_POR_MES, "dias": 1 / DIAS_POR_MES}.get(u, 1.0) * float(v)


def indiretos_planilha(servicos: list[dict[str, Any]], atividades: dict[str, dict[str, Any]],
                       prazo_licitacao: float | None, com_bdi: bool = False) -> list[dict[str, Any]]:
    """Itens das indiretas da planilha com o valor por mês (MÊS) ou fixo (o resto).

    Obra toda: valor ÷ prazo da licitação; entre atividades: valor ÷ quantidade (meses previstos).
    """
    itens = []
    for s_ in servicos:
        a = atividades.get(s_.get("atividade_biblioteca"))
        if not a or a["tipo"] != "indireta":
            continue
        total = (s_.get("total_bdi") if com_bdi else s_.get("total")) or 0.0
        de, ate = a.get("periodo_de") or "INICIO_OBRA", a.get("periodo_ate") or "FIM_OBRA"
        toda = de == "INICIO_OBRA" and ate == "FIM_OBRA"
        un = unidade_canonica(s_.get("unidade"))
        item = {"item": s_["item"], "descricao": f"{s_['item']} {s_.get('descricao') or ''}".strip(),
                "atividade": a["codigo"], "unidade": s_.get("unidade"), "total": round(total, 2), "de": de, "ate": ate,
                "valor_mes": None, "previsto_meses": None, "tipo": "fixo",
                "motivo": "não varia com o prazo nesta versão" if un == "M2/MES" else "custo fixo"}
        if un == "MES" and toda and prazo_licitacao:
            item.update(tipo="obra", valor_mes=round(total / prazo_licitacao, 2), previsto_meses=prazo_licitacao, motivo=None)
        elif un == "MES" and not toda and s_.get("quantidade"):
            item.update(tipo="periodo", valor_mes=round(total / s_["quantidade"], 2), previsto_meses=s_["quantidade"],
                        motivo=None)
        itens.append(item)
    return itens


def criterio_padrao(item: dict[str, Any]) -> str:
    return "fixo" if unidade_canonica(item.get("unidade")) == "%" else "proporcional"


def parametros_cronograma(banco: Banco, obra_id: int, biblioteca: Biblioteca | None = None) -> dict[str, Any]:
    estado = _estado_etapa4(banco, obra_id, biblioteca)
    cal = banco.carregar_calendario(obra_id)
    dados = banco.carregar_obra(obra_id)
    obra = dados["obra"]
    rede = banco.carregar_rede(obra_id)
    prazo = prazo_licitacao_meses(obra)
    funcoes = _funcoes_proprias(estado)
    if any(a["execucao"] == PROPRIA and a.get("horas_equipamento") for a in estado["atividades"]):
        funcoes.append(OPERADOR)
    p4 = banco.carregar_parametros(obra_id)
    travadas = banco.equipes_travadas(obra_id)
    execucao = banco.carregar_execucao(obra_id)
    atividades = [{"codigo": a["codigo"], "nome": a["nome"], "funcao_principal": a["funcao_principal"],
                   "execucao": a["execucao"], "equipe_padrao": a["equipe_padrao"], "equipe_max": a["equipe_max"],
                   "travada": travadas.get(a["codigo"]), "tem_equipamento": bool(a.get("horas_equipamento")),
                   "maquinas_max": (execucao.get(a["codigo"]) or {}).get("maquinas_max")}
                  for a in estado["atividades"] if a["funcao_principal"] or a.get("horas_equipamento")
                  if (a.get("duracao") or {}).get("tipo") == "calculada"]
    custos = custos_efetivos(banco, obra_id, funcoes)
    planilha = indiretos_planilha(dados["servicos"], rede["atividades"], prazo)
    reais = cal["indiretos_reais"]
    if reais is None:
        reais = banco.padrao("indiretos_reais") if banco.padrao("indiretos_reais") else None
    indiretos_ref = reais is None or (bool(reais) and all(x.get("planilha") for x in reais))
    if reais is None:
        reais = [{"descricao": i["descricao"], "valor_mes": i["valor_mes"], "de": i["de"], "ate": i["ate"]}
                 for i in planilha if i["valor_mes"]]
    terc_planilha = {a["codigo"]: a["total"] for a in estado["atividades"] if a["execucao"] == TERCEIRIZADA}
    terceirizados = [{"codigo": c, "nome": rede["atividades"].get(c, {}).get("nome"), "planilha": v,
                      "contratado": (cal["terceirizados"] or {}).get(c)} for c, v in terc_planilha.items()]
    criterios = [{**i, "criterio": (cal["criterios"] or {}).get(i["item"]) or criterio_padrao(i)} for i in planilha]
    avisos = []
    if any(v["referencia"] for v in custos.values()):
        avisos.append("Mão de obra: " + AVISO_REFERENCIA + " (informe os salários).")
    if indiretos_ref:
        avisos.append("Indiretos: valores da planilha, não os reais (edite a lista de indiretos reais).")
    if any(t["contratado"] is None for t in terceirizados):
        avisos.append("Terceirizados: valor da planilha sem BDI, não o contratado.")
    entradas = entradas_da_obra(cal, funcoes)
    tipo_troca, custo_troca, horas_troca = custo_troca_da_obra(cal)
    return {
        **cal,
        "prazos": _prazos_validos(cal["prazos"] or prazos_padrao(prazo), prazo),
        "prazo_licitacao": prazo,
        "dias_semana": p4["dias_semana"], "horas_semana": p4["horas_semana"], "mudancas_jornada": p4["mudancas_jornada"],
        "custos": custos,
        "encargos": encargos_efetivos(banco, obra_id),
        "salarios": cal.get("salarios") or {},
        "salarios_padrao": banco.padrao("salarios") or {},
        "funcoes": funcoes,
        "entradas": entradas,
        "transferiveis": [f for f, n in entradas.items() if n == LIVRE],
        "custo_troca_tipo": tipo_troca, "custo_troca": custo_troca, "custo_troca_horas": horas_troca,
        "contar_terceirizados": bool(cal["contar_terceirizados"]),
        "atividades_proprias": atividades,
        "codigos_sequencia": [c for c, a in sorted(rede["atividades"].items(), key=lambda x: x[1]["ordem_biblioteca"])
                              if a["tipo"] != "indireta"],
        "indiretos_reais": reais,
        "indiretos_referencia": indiretos_ref,
        "indiretos_planilha": planilha,
        "terceirizados": terceirizados,
        "criterios": criterios,
        "avisos": avisos,
        "pendencias_etapa4": estado["pendencias"],
        "obra": {k: obra.get(k) for k in ("id", "numero", "nome", "prazo_valor", "prazo_unidade")},
    }


def entradas_da_obra(cal: dict[str, Any], funcoes: Iterable[str]) -> dict[str, int]:
    """Entradas na obra por função: 0 = livre, N = até N entradas (1 = uma entrada, a regra de sempre).

    Padrão: livre para Servente, Pedreiro, Bombeiro e Ajudante de bombeiro, uma entrada para as outras. Obra com a opção antiga "pode sair e
    voltar": ligada = livre, desligada = uma entrada.
    """
    salvas = cal.get("entradas")
    if salvas is not None:
        padrao_livres = TRANSFERIVEIS_PADRAO
    elif cal.get("transferiveis") is not None:
        salvas, padrao_livres = {f: LIVRE for f in cal["transferiveis"]}, ()
    else:
        salvas, padrao_livres = {}, TRANSFERIVEIS_PADRAO
    res = {}
    for f in funcoes:
        if f in salvas and salvas[f] is not None:
            res[f] = int(salvas[f])
        else:
            res[f] = LIVRE if f in padrao_livres else UMA_ENTRADA
    return res


def custo_troca_da_obra(cal: dict[str, Any]) -> tuple[str, float, float]:
    """(tipo, R$ por pessoa, horas por pessoa) do custo de quem sai ou volta. Padrão: 8 horas da própria função."""
    tipo = cal.get("custo_troca_tipo")
    if tipo not in ("horas", "reais"):
        tipo = "reais" if (cal.get("custo_troca") or 0) > 0 else "horas"   # obra antiga com valor em reais
    horas = cal.get("custo_troca_horas")
    horas = CUSTO_TROCA_HORAS if horas is None else float(horas)
    return tipo, float(cal.get("custo_troca") or 0.0), horas


def _real(valor: Any, nome: str, minimo: float, maximo: float) -> float | None:
    if valor in (None, ""):
        return None
    try:
        v = float(str(valor).replace(",", "."))
    except ValueError:
        raise ErroCronograma(f"Valor inválido para {nome}.")
    if not minimo <= v <= maximo:
        raise ErroCronograma(f"Valor fora da faixa para {nome}.")
    return v


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
    if "transferiveis" in dados and "entradas" not in dados:   # opção antiga: marcada = livre
        livres = {str(f) for f in (dados["transferiveis"] or [])}
        atuais = c.get("entradas") or {}
        c["entradas"] = {**{f: UMA_ENTRADA for f in TRANSFERIVEIS_PADRAO},
                         **{f: (UMA_ENTRADA if n == LIVRE else n) for f, n in atuais.items()}, **{f: LIVRE for f in livres}}
        c["transferiveis"] = sorted(livres)
    if "entradas" in dados:
        entradas = dict(c.get("entradas") or {})
        for f, v in (dados["entradas"] or {}).items():
            if v in (None, ""):
                entradas.pop(str(f), None)
                continue
            if str(v).lower() == "livre":
                v = LIVRE
            entradas[str(f)] = _inteiro(v, f"o número de entradas de {f} (0 = livre)", 0, 20)
        c["entradas"] = entradas
    if "custo_troca_tipo" in dados:
        if dados["custo_troca_tipo"] not in ("horas", "reais"):
            raise ErroCronograma("Custo de quem sai ou volta: use horas da função ou um valor em reais.")
        c["custo_troca_tipo"] = dados["custo_troca_tipo"]
    if "custo_troca_horas" in dados:
        c["custo_troca_horas"] = _real(dados["custo_troca_horas"], "as horas por pessoa que sai ou volta", 0, 1000) or 0.0
    if "min_semanas_reducao" in dados:
        c["min_semanas_reducao"] = _inteiro(dados["min_semanas_reducao"], "a duração mínima de uma redução (semanas)", 1, 12)
    if "custo_troca" in dados:
        c["custo_troca"] = _real(dados["custo_troca"], "o custo por pessoa que sai ou volta", 0, 100000) or 0.0
    if "maquinas_max" in dados:
        c["maquinas_max"] = _inteiro(dados["maquinas_max"], "o máximo de máquinas por equipamento", 1, 50)
    if "dividir_terceirizadas" in dados:
        c["dividir_terceirizadas"] = 1 if dados["dividir_terceirizadas"] else 0
    if "contar_terceirizados" in dados:
        c["contar_terceirizados"] = 1 if dados["contar_terceirizados"] else 0
    if "encargos" in dados:
        c["encargos"] = _real(dados["encargos"], "o percentual de encargos", 0, 300)
        if c["encargos"] is not None:
            banco.lembrar_padrao("encargos", c["encargos"])
    if "salarios" in dados:
        salarios = {}
        for f, v in (dados["salarios"] or {}).items():
            x = _real(v, f"o salário de {f}", 0.01, 1000000)
            if x is not None:
                salarios[f] = x
        c["salarios"] = salarios
        banco.lembrar_padrao("salarios", {**(banco.padrao("salarios") or {}), **salarios})
    if "indiretos_reais" in dados:
        if dados["indiretos_reais"] in (None, "planilha"):
            # volta aos valores da planilha (referência), ignorando os da última obra
            obra_ = banco.carregar_obra(obra_id)
            planilha = indiretos_planilha(obra_["servicos"], banco.carregar_rede(obra_id)["atividades"],
                                          prazo_licitacao_meses(obra_["obra"]))
            c["indiretos_reais"] = [{"descricao": i["descricao"], "valor_mes": i["valor_mes"], "de": i["de"], "ate": i["ate"],
                                     "planilha": True} for i in planilha if i["valor_mes"]]
        else:
            lista = []
            for it in dados["indiretos_reais"]:
                desc = str(it.get("descricao") or "").strip()
                if not desc:
                    continue
                valor = _real(it.get("valor_mes"), f"o valor por mês de '{desc}'", 0, 100000000) or 0.0
                de = (it.get("de") or "INICIO_OBRA").strip().upper()
                ate = (it.get("ate") or "FIM_OBRA").strip().upper()
                item = {"descricao": desc, "valor_mes": valor, "de": de, "ate": ate}
                antigo = next((x for x in (c.get("indiretos_reais") or []) if x.get("planilha")
                               and x["descricao"] == desc and x["valor_mes"] == valor), None)
                if antigo:
                    item["planilha"] = True
                lista.append(item)
            c["indiretos_reais"] = lista
            if not all(x.get("planilha") for x in lista):
                banco.lembrar_padrao("indiretos_reais", [{k: v for k, v in x.items() if k != "planilha"} for x in lista])
    if "terceirizados" in dados:
        terc = {}
        for cod, v in (dados["terceirizados"] or {}).items():
            x = _real(v, f"o valor contratado de {cod}", 0, 1000000000)
            if x is not None:
                terc[cod] = x
        c["terceirizados"] = terc
    if "criterios" in dados:
        crit = {}
        for item, v in (dados["criterios"] or {}).items():
            if v not in CRITERIOS:
                raise ErroCronograma(f"Critério de pagamento inválido para o item {item}: use {', '.join(CRITERIOS)}.")
            crit[str(item)] = v
        c["criterios"] = crit
    if "prazos" in dados:
        prazo_lic = prazo_licitacao_meses(banco.carregar_obra(obra_id)["obra"])
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
            if prazo_lic and v > prazo_lic + 1e-9:
                raise ErroCronograma(f"Prazo de {v:g} meses maior que o da licitação ({prazo_lic:g}): os cenários são "
                                     "só iguais ou menores que o prazo da licitação.")
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


def definir_limites(banco: Banco, obra_id: int, codigo: str, equipe_max: Any = None, maquinas_max: Any = None,
                    biblioteca: Biblioteca | None = None) -> None:
    """Equipe máxima (pessoas da função principal) e máximo de máquinas de cada equipamento de uma atividade."""
    rede = banco.carregar_rede(obra_id)
    if rede is None or codigo not in rede["atividades"] or rede["atividades"][codigo]["tipo"] == "indireta":
        raise ErroCronograma(f"Atividade {codigo} não está na sequência desta obra.")
    if equipe_max not in (None, ""):
        n = _inteiro(equipe_max, "a equipe máxima", 1, 200)
        banco.atualizar_atividade_obra(obra_id, codigo, equipe_max=n)
    if maquinas_max is not None:
        banco.atualizar_execucao(obra_id, codigo, maquinas_max=_inteiro(maquinas_max, "o máximo de máquinas", 1, 50, True))


def aplicar_sugestao(banco: Banco, obra_id: int, acao: dict[str, Any], biblioteca: Biblioteca | None = None) -> None:
    """Aplica uma sugestão do diagnóstico de prazo."""
    tipo, cod, valor = acao.get("tipo"), acao.get("atividade"), acao.get("valor")
    if tipo == "equipe_max":
        definir_limites(banco, obra_id, cod, equipe_max=valor, biblioteca=biblioteca)
    elif tipo == "maquinas_max":
        definir_limites(banco, obra_id, cod, maquinas_max=valor, biblioteca=biblioteca)
    elif tipo == "destravar":
        banco.travar_equipe(obra_id, cod, None)
    elif tipo == "max_pessoas_total":
        salvar_parametros_cronograma(banco, obra_id, {"max_pessoas_total": valor})
    elif tipo == "duracao":
        try:
            etapa4.definir_atividade(banco, obra_id, cod, duracao_manual=valor, biblioteca=biblioteca)
        except etapa4.ErroMaoDeObra as exc:
            raise ErroCronograma(str(exc))
    else:
        raise ErroCronograma("Sugestão desconhecida.")


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
    """Itens das indiretas da planilha como custo por tempo (valores sem BDI)."""
    return [ItemIndireto(descricao=i["descricao"], atividade=i["atividade"], tipo=i["tipo"],
                         custo_mes=i["valor_mes"] or 0.0, custo_total=i["total"], de=i["de"], ate=i["ate"],
                         unidade=i["unidade"], previsto_meses=i["previsto_meses"], motivo=i["motivo"])
            for i in indiretos_planilha(servicos, atividades, prazo_licitacao)]


def _itens_reais(lista: list[dict[str, Any]]) -> list[ItemIndireto]:
    itens = []
    for i in lista:
        de, ate = i.get("de") or "INICIO_OBRA", i.get("ate") or "FIM_OBRA"
        tipo = "obra" if (de, ate) == ("INICIO_OBRA", "FIM_OBRA") else "periodo"
        itens.append(ItemIndireto(descricao=i["descricao"], atividade=None, tipo=tipo, custo_mes=float(i["valor_mes"] or 0),
                                  de=de, ate=ate))
    return itens


def receitas_da_obra(servicos: list[dict[str, Any]], atividades: dict[str, dict[str, Any]],
                     prazo_licitacao: float | None, criterios: dict[str, str]) -> list[ItemIndireto]:
    """Receita que varia com o prazo: indiretas com critério 'mensal' (valor com BDI por mês × duração)."""
    itens = []
    for i in indiretos_planilha(servicos, atividades, prazo_licitacao, com_bdi=True):
        crit = criterios.get(i["item"]) or criterio_padrao(i)
        if crit != "mensal":
            continue
        if not i["valor_mes"]:
            meses = prazo_licitacao or 1.0
            valor_mes, tipo = i["total"] / meses, "obra"
        else:
            valor_mes, tipo = i["valor_mes"], i["tipo"]
        itens.append(ItemIndireto(descricao=i["descricao"], atividade=i["atividade"], tipo=tipo, custo_mes=valor_mes,
                                  custo_total=i["total"], de=i["de"], ate=i["ate"], unidade=i["unidade"],
                                  previsto_meses=i["previsto_meses"]))
    return itens


def montar_instancia(banco: Banco, obra_id: int, prazo_meses: float, biblioteca: Biblioteca | None = None,
                     estado: dict[str, Any] | None = None) -> tuple[Instancia, dict[str, Any]]:
    estado = estado or _estado_etapa4(banco, obra_id, biblioteca)
    if estado["pendencias"]:
        raise ErroCronograma("Resolva as pendências da mão de obra antes do cronograma: "
                             + "; ".join(p["mensagem"] for p in estado["pendencias"][:5]))
    cal = calendario_da_obra(banco, obra_id)
    params = parametros_cronograma(banco, obra_id, biblioteca)
    c = banco.carregar_calendario(obra_id)
    rede = banco.carregar_rede(obra_id)
    dados = banco.carregar_obra(obra_id)
    execucao = banco.carregar_execucao(obra_id)
    maq_padrao = c.get("maquinas_max") or MAQUINAS_MAX
    maq = {cod: (execucao.get(cod) or {}).get("maquinas_max") or maq_padrao for cod in rede["atividades"]}
    travadas = banco.equipes_travadas(obra_id)
    tarefas = tarefas_da_obra(estado["atividades"], rede["dependencias"], travadas, cal.jornadas(), maq,
                              bool(c.get("dividir_terceirizadas", 1)))
    funcoes = sorted({f for t in tarefas.values() if t.propria for m in t.modos for f in m.equipe})
    custos = custos_efetivos(banco, obra_id, funcoes)
    faltando = [f for f, v in custos.items() if not v["custo_hora"]]
    if faltando:
        raise ErroCronograma("Informe o salário (ou o custo por hora) de: " + ", ".join(faltando) + ".")
    prazo_lic = prazo_licitacao_meses(dados["obra"])
    inst = Instancia(
        calendario=cal, tarefas=tarefas, limite=data_limite(cal.inicio, prazo_meses),
        custo_hora={f: v["custo_hora"] for f, v in custos.items()},
        indiretos=_itens_reais(params["indiretos_reais"]),
        limite_rigidas=c["limite_rigidas"], max_por_funcao=c["max_por_funcao"], max_total=c["max_pessoas_total"],
        entradas=dict(params["entradas"]), min_semanas_reducao=c.get("min_semanas_reducao") or 2,
        custo_troca=params["custo_troca"] if params["custo_troca_tipo"] == "reais" else 0.0,
        custo_troca_horas=params["custo_troca_horas"] if params["custo_troca_tipo"] == "horas" else 0.0,
        receitas=receitas_da_obra(dados["servicos"], rede["atividades"], prazo_lic, c.get("criterios") or {}),
        contar_terceirizados=params["contar_terceirizados"],
    )
    terc = {t["codigo"]: (t["contratado"] if t["contratado"] is not None else t["planilha"])
            for t in params["terceirizados"]}
    contexto = {"estado": estado, "rede": rede, "equipe_padrao": {a["codigo"]: a["equipe_padrao"] for a in estado["atividades"]},
                "tempo_limite": c["tempo_limite"], "avisos": params["avisos"], "travadas": travadas, "maquinas_max": maq,
                "custo_terceirizados": round(sum(v or 0 for v in terc.values()), 2)}
    return inst, contexto


# --------------------------------------------------------------------------- diagnóstico de prazo


def _menor_fim(inst: Instancia) -> int:
    sol = menor_prazo(inst)["solucao"]
    return inst.calendario.ultimo_util_ate(inst.fim_da_obra(sol)) + 1


def diagnostico(inst: Instancia, ctx: dict[str, Any]) -> dict[str, Any]:
    """Por que não cabe: menor prazo com os limites atuais, caminho crítico e sugestões com o ganho calculado."""
    cal = inst.calendario
    mp = menor_prazo(inst)
    sol = mp["solucao"]
    base = mp["dias_uteis"]
    por_cod = {a["codigo"]: a for a in ctx["estado"]["atividades"]}
    cadeia = []
    for cod in mp["caminho_critico"]:
        t = inst.tarefas[cod]
        a = sol[cod]
        m = t.modos[a["modo"]]
        principal = t.funcao_principal
        cadeia.append({
            "codigo": cod, "nome": t.nome, "execucao": t.execucao, "duracao": a["duracao"],
            "unidade": "corridos" if m.corridos else "uteis",
            "inicio": cal.data(a["inicio"]).isoformat(), "termino": cal.data_do_offset(a["fim"]).isoformat(),
            "equipe": dict(m.equipe), "equipe_principal": m.equipe.get(principal) if principal else None,
            "equipe_max": t.equipe_max if m.horas else None, "maquinas": dict(m.maquinas),
            "maquinas_max": t.maquinas_max if m.horas_equipamento else None, "travada": t.travada,
            "limitante": m.limitante(cal.horas_dia(a["inicio"])),
        })
    sugestoes = []

    def testar(cod: str, modos: list[Modo]) -> int:
        original = inst.tarefas[cod].modos
        inst.tarefas[cod].modos = modos
        try:
            return base - _menor_fim(inst)
        finally:
            inst.tarefas[cod].modos = original

    jornadas = cal.jornadas()
    for item in cadeia:
        cod = item["codigo"]
        t = inst.tarefas[cod]
        a4 = por_cod.get(cod) or {}
        nome = f"{cod} ({t.nome})" if t.nome else cod
        if t.travada:
            ganho = testar(cod, modos_da_atividade(a4, None, jornadas, t.maquinas_max))
            if ganho > 0:
                sugestoes.append({"texto": f"destravar a equipe da {nome} (hoje travada em {t.travada}) reduz {ganho} dias úteis",
                                  "ganho": ganho, "acao": {"tipo": "destravar", "atividade": cod}})
        if item["equipe_max"] and item["equipe_principal"] == item["equipe_max"] and item["limitante"] == "mao_de_obra":
            novo = max(30, int(item["equipe_max"] * 1.5))
            ganho = testar(cod, modos_da_atividade(a4, t.travada, jornadas, t.maquinas_max, equipe_max=novo))
            if ganho > 0:
                sugestoes.append({"texto": f"aumentar a equipe máxima da {nome} de {item['equipe_max']} para {novo} "
                                           f"reduz {ganho} dias úteis",
                                  "ganho": ganho, "acao": {"tipo": "equipe_max", "atividade": cod, "valor": novo}})
        if item["maquinas_max"] and item["maquinas"] and max(item["maquinas"].values()) >= item["maquinas_max"]:
            novo = item["maquinas_max"] + 4
            ganho = testar(cod, modos_da_atividade(a4, t.travada, jornadas, novo))
            if ganho > 0:
                equip = max(item["maquinas"], key=lambda e: (t.modos[0].horas_equipamento.get(e, 0), e))
                sugestoes.append({"texto": f"{nome} com até {novo} máquinas de cada equipamento (ex.: {equip[:50]}) "
                                           f"reduz {ganho} dias úteis",
                                  "ganho": ganho, "acao": {"tipo": "maquinas_max", "atividade": cod, "valor": novo}})
        m0 = t.modos[0]
        if len(t.modos) == 1 and m0.dias_uteis and not m0.horas and item["duracao"] > 2:
            nova = max(1, int(item["duracao"] * 0.75))
            ganho = testar(cod, modos_da_atividade(a4, t.travada, jornadas, t.maquinas_max, dias_uteis=nova))
            if ganho > 0:
                quem = "terceirizada" if t.execucao == TERCEIRIZADA else "duração digitada"
                sugestoes.append({"texto": f"rever a duração da {nome} ({quem}): de {item['duracao']} para {nova} dias "
                                           f"úteis reduz {ganho} dias úteis",
                                  "ganho": ganho, "acao": {"tipo": "duracao", "atividade": cod, "valor": nova}})
    canteiro = None
    if inst.max_total is not None:
        # limite do canteiro (próprios + terceirizados, se a opção estiver ligada) segurando o prazo?
        x = inst.max_total
        com_limite = dias_com_canteiro(inst, x)
        if com_limite > base:
            canteiro = {"maximo": x, "dias_uteis": com_limite, "sem_limite": base}
            alvo = max(inst.horizonte, base)
            y = x
            for passo in (1, 2, 3, 4, 5, 6, 8, 10, 15, 20, 30, 40, 60, 100, 200):
                y = x + passo
                if dias_com_canteiro(inst, y) <= alvo:
                    break
            ganho = com_limite - dias_com_canteiro(inst, y)
            if ganho > 0:
                quem = "próprios + terceirizados" if canteiro_conta_terceirizados(inst) else "próprios"
                sugestoes.append({"texto": f"aumentar o máximo de pessoas no canteiro ({quem}) de {x} para {y} "
                                           f"reduz {ganho} dias úteis",
                                  "ganho": ganho, "acao": {"tipo": "max_pessoas_total", "valor": y}})
                canteiro.update(sugerido=y, ganho=ganho)
            base = max(base, com_limite)
    sugestoes.sort(key=lambda x: -x["ganho"])
    return {"menor_prazo": {k: v for k, v in mp.items() if k != "solucao"}, "caminho_critico": cadeia,
            "sugestoes": sugestoes[:10], "dias_uteis_limite": inst.horizonte, "canteiro": canteiro,
            "faltam_dias_uteis": max(0, base - inst.horizonte)}


# --------------------------------------------------------------------------- continuidade: procurar melhorias

TEMPO_MELHORIAS = 20      # segundos por alternativa testada
FUNCOES_MELHORIAS = 3     # as funções com maior custo de horas paradas


def _destino_troca(funcao: str, funcoes_empresa: list[str], juntar_possivel: dict[str, str]) -> str | None:
    """Quem poderia fazer o serviço da função: a da aba Juntar funções; senão Servente (ajudantes) ou Pedreiro."""
    from leitor_planilha.texto import normalizar

    if juntar_possivel.get(funcao) and juntar_possivel[funcao] != funcao:
        return juntar_possivel[funcao]
    n = normalizar(funcao)
    destino = "Servente" if n.startswith(("AJUDANTE", "AUXILIAR", "SERVENTE")) else "Pedreiro"
    return destino if destino in funcoes_empresa and destino != funcao else None


def candidatas_melhoria(inst: Instancia, atividades: dict[str, dict[str, Any]], continuidade: list[dict[str, Any]],
                        funcoes_empresa: list[str], juntar_possivel: dict[str, str]) -> list[dict[str, Any]]:
    """Alternativas a testar para as 3 funções com maior custo de horas paradas, na atividade que puxa a entrada
    e na que segura a saída: tornar flexível (se rígida), trocar a função, terceirizar (se a execução é
    'perguntar') e permitir 2 entradas (se a função tem uma entrada só)."""
    vistas, res = set(), []

    def add(c: dict[str, Any]) -> None:
        chave = (c["tipo"], c.get("atividade"), c.get("funcao") if c["tipo"] in ("trocar", "entradas") else None)
        if chave not in vistas:
            vistas.add(chave)
            res.append(c)

    linhas = [l for l in continuidade if (l.get("custo_horas_paradas") or 0) > 0][:FUNCOES_MELHORIAS]
    for l in linhas:
        f = l["funcao"]
        for papel in ("puxa_entrada", "segura_saida"):
            u = l.get(papel)
            if not u or u["codigo"] not in inst.tarefas:
                continue
            cod = u["codigo"]
            t = inst.tarefas[cod]
            a4 = atividades.get(cod) or {}
            base = {"atividade": cod, "nome": t.nome, "funcao": f, "papel": papel}
            if t.tipo == RIGIDA and cod != inst.final:
                add({**base, "tipo": "flexivel"})
            destino = _destino_troca(f, funcoes_empresa, juntar_possivel)
            if destino and f != OPERADOR and t.propria and any(m.equipe.get(f) for m in t.modos):
                add({**base, "tipo": "trocar", "destino": destino})
            if t.propria and a4.get("execucao_padrao") == "perguntar":
                add({**base, "tipo": "terceirizar"})
        if inst.entradas_de(f) == UMA_ENTRADA:
            add({"tipo": "entradas", "funcao": f, "valor": 2, "atividade": None})
    return res


def instancia_com(inst: Instancia, c: dict[str, Any], juntar: dict[str, str] | None = None,
                  custo_hora_de: Callable[[str], float | None] | None = None, dividir_terceirizadas: bool = True
                  ) -> tuple[Instancia, float, str]:
    """Cópia da instância com só uma mudança. Devolve (instância, custo extra fora da mão de obra própria, texto)."""
    import copy
    import dataclasses

    from mao_de_obra.calculo import destino_final

    from .modelo import FLEXIVEL, PARTES_MAX

    tarefas = copy.deepcopy(inst.tarefas)
    entradas = dict(inst.entradas)
    custo_hora = dict(inst.custo_hora)
    extra = 0.0
    cod = c.get("atividade")
    nome = f"{cod} ({c.get('nome')})" if c.get("nome") else cod
    if c["tipo"] == "flexivel":
        tarefas[cod].tipo = FLEXIVEL
        texto = f"Tornar a {nome} flexível"
    elif c["tipo"] == "entradas":
        entradas[c["funcao"]] = int(c["valor"])
        texto = f"Permitir {c['valor']} entradas na obra para {c['funcao']}"
    elif c["tipo"] == "trocar":
        f = c["funcao"]
        dest = destino_final(c["destino"], [], juntar or {})
        t = tarefas[cod]
        for m in t.modos:   # mesmas horas e pessoas, na função de destino (a duração não muda)
            if m.equipe.get(f):
                m.equipe[dest] = m.equipe.get(dest, 0) + m.equipe.pop(f)
            if f in m.horas:
                m.horas[dest] = m.horas.get(dest, 0.0) + m.horas.pop(f)
        if t.funcao_principal == f:
            t.funcao_principal = dest
        if dest not in custo_hora:
            custo_hora[dest] = (custo_hora_de(dest) if custo_hora_de else None) or 0.0
        texto = (f"Trocar {f} por {c['destino']} na {nome} ({f} > {c['destino']}; é só sugestão: "
                 "confira se a equipe faz o serviço)")
    elif c["tipo"] == "terceirizar":
        t = tarefas[cod]
        m0 = inst.tarefas[cod].modos[0]
        horas = dict(m0.horas) if m0.horas else {
            f: q * inst.duracao(cod, 0, 0) * inst.calendario.horas_dia(0) for f, q in m0.equipe.items()}
        extra = sum(h * inst.custo_hora.get(f, 0.0) for f, h in horas.items())
        t.execucao = TERCEIRIZADA
        t.travada = None
        t.terceirizado = {"rotulo": t.funcao_principal or t.nome or cod, "pessoas": sum(m0.equipe.values()),
                          "origem": "composição", "por_modo": True, "detalhe": dict(m0.equipe)}
        t.partes_max = PARTES_MAX if dividir_terceirizadas else 1
        texto = (f"Terceirizar a {nome} (considerando que o terceirizado cobra a mesma mão de obra: "
                 f"{sum(horas.values()):.0f} h = {_reais(extra)})")
    else:
        raise ErroCronograma("Sugestão desconhecida.")
    nova = dataclasses.replace(inst, tarefas=tarefas, entradas=entradas, custo_hora=custo_hora, transferiveis=set())
    return nova, extra, texto


def _reais(v: float) -> str:
    return "R$ " + f"{v:,.0f}".replace(",", ".")


def testar_melhorias(inst: Instancia, candidatas: list[dict[str, Any]], base_custo: float, base_ocio: float,
                     tempo: float, equipe_padrao: dict[str, int] | None = None, juntar: dict[str, str] | None = None,
                     custo_hora_de: Callable[[str], float | None] | None = None, dividir_terceirizadas: bool = True,
                     progresso: Callable[[dict[str, Any]], None] | None = None, parar: threading.Event | None = None,
                     prazo: float | None = None, solucao_base: dict[str, Any] | None = None,
                     ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Recalcula o cenário com cada mudança (só ela) e devolve (as que melhoram, ordenadas pelo ganho; todas).

    `solucao_base`: cronograma do cenário atual, ponto de partida de cada teste (continua valendo com a mudança),
    para o ganho não ser ruído do tempo limite.
    """
    sugestoes, testadas = [], []
    for k, cand in enumerate(candidatas):
        if parar is not None and parar.is_set():
            break
        if progresso:
            progresso({"evento": "inicio", "cenario": k, "n": len(candidatas), "prazo": prazo})
        alt, extra, texto = instancia_com(inst, cand, juntar, custo_hora_de, dividir_terceirizadas)
        res = otimizar(alt, tempo, equipe_padrao, parar=parar, solucoes_extra=[solucao_base] if solucao_base else None)
        item = {**cand, "texto": texto, "situacao": res["situacao"]}
        if res["situacao"] in VALIDAS:
            custo = res["custo_total"] + extra
            item.update(custo_total=round(custo, 2), ociosidade=res["ociosidade"], custo_extra=round(extra, 2),
                        ganho=round(base_custo - custo, 2), ganho_ociosidade=round(base_ocio - res["ociosidade"], 2),
                        termino=res["termino"], pico=res["pico"])
            if item["ganho"] > 1:
                sugestoes.append(item)
        testadas.append(item)
    sugestoes.sort(key=lambda x: -x["ganho"])
    return sugestoes, testadas


def procurar_melhorias(banco: Banco, obra_id: int, cenario_id: int | None = None, biblioteca: Biblioteca | None = None,
                       tempo: float | None = None, progresso: Callable[[dict[str, Any]], None] | None = None,
                       parar: threading.Event | None = None) -> dict[str, Any]:
    """Para as 3 funções com maior custo de horas paradas, testa (recalculando o cenário com só aquela mudança)
    tornar flexível, trocar a função, terceirizar e permitir 2 entradas. Mostra só as que melhoram."""
    import time

    from mao_de_obra.funcoes import carregar_funcoes

    if cenario_id is None:
        escolhido = next((c for c in banco.listar_cenarios(obra_id) if c["escolhido"]), None)
        if escolhido is None:
            raise ErroCronograma("Escolha um cenário antes de procurar melhorias.")
        cenario_id = escolhido["id"]
    c = banco.carregar_cenario(int(cenario_id))
    if c is None or c["obra_id"] != obra_id:
        raise ErroCronograma("Cenário não encontrado nesta obra.")
    if c["situacao"] not in VALIDAS:
        raise ErroCronograma("Este cenário não tem cronograma.")
    continuidade = c["detalhes"].get("continuidade")
    if continuidade is None:
        raise ErroCronograma("Recalcule o cronograma antes de procurar melhorias (o cálculo é de uma versão anterior).")
    tempo = float(tempo if tempo is not None else TEMPO_MELHORIAS)
    estado = _estado_etapa4(banco, obra_id, biblioteca)
    inst, ctx = montar_instancia(banco, obra_id, c["prazo_meses"], biblioteca, estado)
    tabela = carregar_funcoes()
    candidatas = candidatas_melhoria(inst, {a["codigo"]: a for a in estado["atividades"]}, continuidade,
                                     tabela.funcoes(), tabela.juntar_possivel)
    inicio = time.monotonic()
    # o cenário atual recalculado com o mesmo tempo: base justa e ponto de partida das alternativas
    if progresso:
        progresso({"evento": "inicio", "cenario": 0, "n": len(candidatas) + 1, "prazo": c["prazo_meses"]})
    base = otimizar(inst, tempo, ctx["equipe_padrao"], parar=parar)
    base_custo, base_ocio, solucao_base = c["custo_total"], c["ociosidade"], None
    if base["situacao"] in VALIDAS:
        solucao_base = base.get("solucao")
        base_custo, base_ocio = base["custo_total"], base["ociosidade"]

    def prog(info: dict[str, Any]) -> None:
        if progresso:
            progresso({**info, "cenario": info["cenario"] + 1, "n": len(candidatas) + 1})

    sugestoes, testadas = testar_melhorias(
        inst, candidatas, base_custo, base_ocio, tempo, ctx["equipe_padrao"],
        (estado.get("juntar") or {}).get("obra") or {},
        lambda f: custos_efetivos(banco, obra_id, [f])[f]["custo_hora"],
        bool(banco.carregar_calendario(obra_id).get("dividir_terceirizadas", 1)), prog, parar, c["prazo_meses"],
        solucao_base)
    resultado = {"cenario_id": c["id"], "prazo_meses": c["prazo_meses"],
                 "base": {"custo_total": base_custo, "ociosidade": base_ocio},
                 "sugestoes": sugestoes, "testadas": testadas, "tempo_por_teste": tempo,
                 "segundos": round(time.monotonic() - inicio, 1), "interrompido": bool(parar is not None and parar.is_set())}
    banco.gravar_melhorias(c["id"], resultado)
    return resultado


def aplicar_melhoria(banco: Banco, obra_id: int, acao: dict[str, Any], biblioteca: Biblioteca | None = None) -> None:
    """Grava na obra a mudança de uma sugestão do "Procurar melhorias" (o cenário é recalculado depois)."""
    from atividades import obra as etapa3

    tipo, cod, f = acao.get("tipo"), acao.get("atividade"), acao.get("funcao")
    try:
        if tipo == "flexivel":
            etapa3.editar_atividade_obra(banco, obra_id, cod, tipo="flexivel")
        elif tipo == "entradas":
            salvar_parametros_cronograma(banco, obra_id, {"entradas": {f: int(acao.get("valor") or 2)}})
        elif tipo == "trocar":
            atual = (banco.carregar_rede(obra_id)["atividades"].get(cod) or {}).get("trocar_funcoes") or ""
            novo = "; ".join(x for x in (atual, f"{f} > {acao.get('destino')}") if x)
            etapa4.definir_trocas(banco, obra_id, cod, novo, biblioteca=biblioteca)
        elif tipo == "terceirizar":
            etapa4.definir_execucao(banco, obra_id, [cod], TERCEIRIZADA, biblioteca)
        else:
            raise ErroCronograma("Sugestão desconhecida.")
    except (etapa4.ErroMaoDeObra, etapa3.ErroObra) as exc:
        raise ErroCronograma(str(exc))


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
                     parar: threading.Event | None = None,
                     solucoes_extra: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    inst, ctx = montar_instancia(banco, obra_id, prazo_meses, biblioteca, estado)
    limite = tempo_limite if tempo_limite is not None else ctx["tempo_limite"]
    res = otimizar(inst, limite, ctx["equipe_padrao"], progresso, parar, solucoes_extra=solucoes_extra)
    res["prazo_meses"] = prazo_meses
    res["data_limite"] = inst.limite.isoformat()
    res["entradas"] = {f: inst.entradas_de(f) for f in inst.funcoes}
    res["avisos_custos"] = ctx["avisos"]
    res["custo_terceirizados"] = ctx["custo_terceirizados"]
    if res["situacao"] not in VALIDAS:
        res["diagnostico"] = diagnostico(inst, ctx)
    if res["situacao"] in VALIDAS:
        res["periodos_indiretas"] = periodos_indiretas(inst, ctx["rede"], res)
        n = max((len(v) for v in res["contratados"].values()), default=0)
        res["equipe_indireta"] = equipe_indireta_semanal(inst, ctx["estado"], res["periodos_indiretas"], n)
    res["id"] = banco.gravar_cenario(obra_id, prazo_meses, inst.limite.isoformat(), res)
    return res


def calcular_cenarios(banco: Banco, obra_id: int, prazos: Iterable[float] | None = None,
                      biblioteca: Biblioteca | None = None, tempo_limite: float | None = None,
                      progresso: Callable[[dict[str, Any]], None] | None = None,
                      parar: threading.Event | None = None) -> dict[str, Any]:
    """Roda o otimizador para cada prazo (meses) e devolve a tabela comparativa."""
    estado = _estado_etapa4(banco, obra_id, biblioteca)
    prazo_lic = prazo_licitacao_meses(banco.carregar_obra(obra_id)["obra"])
    if prazos is None:
        prazos = banco.carregar_calendario(obra_id)["prazos"] or prazos_padrao(prazo_lic)
    prazos = _prazos_validos(prazos, prazo_lic)
    if not prazos:
        raise ErroCronograma("Escolha pelo menos um prazo para calcular.")
    montar_instancia(banco, obra_id, prazos[-1], biblioteca, estado)  # valida antes de começar
    solucoes: list[dict[str, Any]] = []
    for i, p in enumerate(prazos):
        if parar is not None and parar.is_set():
            break
        if progresso:
            progresso({"cenario": i, "n": len(prazos), "prazo": p, "evento": "inicio"})
        res = calcular_cenario(banco, obra_id, p, biblioteca, tempo_limite, estado,
                               (lambda info, i=i, p=p: progresso({**info, "cenario": i, "n": len(prazos), "prazo": p}))
                               if progresso else None, parar, solucoes)
        if res.get("solucao"):
            solucoes.append(res["solucao"])  # vale também para os prazos maiores
    return comparacao(banco, obra_id)


def comparacao(banco: Banco, obra_id: int) -> dict[str, Any]:
    """Tabela comparativa: receita e custo real que variam com o prazo, resultado e diferença para o principal."""
    obra = banco.carregar_obra(obra_id)["obra"]
    prazo_lic = prazo_licitacao_meses(obra)
    cenarios = [c for c in banco.listar_cenarios(obra_id)
                if not prazo_lic or c["prazo_meses"] <= prazo_lic + 1e-9]
    principal = next((c for c in cenarios if prazo_lic and abs(c["prazo_meses"] - prazo_lic) < 1e-6), None)
    validos = [c for c in cenarios if c["situacao"] in VALIDAS]

    def resultado(c: dict[str, Any]) -> float:
        if c.get("resultado") is not None:
            return c["resultado"]
        return (c.get("receita_variavel") or 0.0) - (c["custo_total"] or 0.0)

    melhor = max(validos, key=resultado)["id"] if validos else None
    linhas = []
    for c in cenarios:
        det = c["detalhes"]
        linha = {
            "id": c["id"], "prazo_meses": c["prazo_meses"], "data_limite": c["data_limite"], "situacao": c["situacao"],
            "principal": principal is not None and c["id"] == principal["id"],
            "termino": c["termino"], "pico": c["pico"], "homem_semana": c["homem_semana"], "ociosidade": c["ociosidade"],
            "pico_total": c.get("pico_total"), "semana_pico_total": c.get("semana_pico_total"),
            "custo_mao_de_obra": c["custo_mao_de_obra"], "custo_indiretos": c["custo_indiretos"],
            "custo_saida_volta": c.get("custo_saida_volta"),
            "custo_total": c["custo_total"], "receita_variavel": c.get("receita_variavel"),
            "resultado": resultado(c) if c["situacao"] in VALIDAS else None,
            "escolhido": c["escolhido"], "mais_barato": c["id"] == melhor, "melhor_resultado": c["id"] == melhor,
            "calculado_em": c["calculado_em"], "segundos": c["segundos"], "mensagem": det.get("mensagem"),
            "menor_prazo": det.get("menor_prazo"), "limite_inferior": det.get("limite_inferior"),
            "diagnostico": det.get("diagnostico"), "avisos_custos": det.get("avisos_custos") or [],
            "diferenca": None, "diferenca_pct": None,
        }
        if principal and principal["situacao"] in VALIDAS and c["situacao"] in VALIDAS:
            dif = resultado(c) - resultado(principal)
            linha["diferenca"] = round(dif, 2)
            base = abs(resultado(principal))
            linha["diferenca_pct"] = round(100 * dif / base, 2) if base else None
        linhas.append(linha)
    return {"cenarios": linhas, "prazo_licitacao": prazo_lic, "mais_barato": melhor, "melhor_resultado": melhor,
            "referencia": principal["id"] if principal else None,
            "principal": principal["id"] if principal else None,
            "avisos_custos": next((l["avisos_custos"] for l in linhas if l["avisos_custos"]), [])}


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
                                       "equipe_indireta", "mensagem", "receitas", "horas_feriado", "ociosidade_funcao",
                                       "causas_ociosidade", "diagnostico", "avisos_custos", "custo_terceirizados",
                                       "continuidade", "saida_volta_funcao", "entradas", "melhorias")})
    if c.get("receita_variavel") is None:
        c["receita_variavel"] = det.get("receita_variavel")
    if c.get("resultado") is None and c.get("custo_total") is not None:
        c["resultado"] = (c.get("receita_variavel") or 0.0) - c["custo_total"]
    rede_deps: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for d in rede["dependencias"]:
        rede_deps[d["atividade"]].append({"depende_de": d["depende_de"], "tipo": d.get("tipo") or "TI",
                                          "espera": d.get("espera_dias") or 0, "unidade": d.get("unidade") or "d"})
    for a in c["atividades"]:
        a["dependencias"] = rede_deps.get(a["codigo"], [])
    terc_semanas = c.pop("terceirizados_semana", None) or []
    semanas = sorted({e["semana"] for e in c["equipe_semana"]} | {t["semana"] for t in terc_semanas})
    funcoes: dict[str, dict[str, Any]] = {}
    for e in c["equipe_semana"]:
        f = funcoes.setdefault(e["funcao"], {"funcao": e["funcao"], "contratados": [0] * len(semanas),
                                             "horas_ocupadas": [0.0] * len(semanas), "horas_pagas": [0.0] * len(semanas),
                                             "horas_feriado": [0.0] * len(semanas)})
        k = semanas.index(e["semana"])
        f["contratados"][k] = e["contratados"]
        f["horas_ocupadas"][k] = e["horas_ocupadas"]
        f["horas_pagas"][k] = e["horas_pagas"] or 0.0
        f["horas_feriado"][k] = e.get("horas_feriado") or 0.0
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
    # terceirizados (item 7): uma linha por nome, depois das funções próprias, e o total na obra
    resumo_t = det.get("terceirizados") or {}
    linhas_t: dict[str, dict[str, Any]] = {}
    for t in terc_semanas:
        lt = linhas_t.setdefault(t["rotulo"], {"rotulo": t["rotulo"], "nome": f"{t['rotulo']} (terceirizado)",
                                               "pessoas": [0] * len(semanas), "atividades": [[] for _ in semanas]})
        k = semanas.index(t["semana"])
        lt["pessoas"][k] = t["pessoas"]
        lt["atividades"][k] = t["atividades"]
    ordem_t = {r["rotulo"]: n for n, r in enumerate(resumo_t.get("rotulos") or [])}
    for lt in linhas_t.values():
        lt["pico"] = max(lt["pessoas"], default=0)
        lt["semana_pico"] = semanas[lt["pessoas"].index(lt["pico"])] if lt["pico"] else None
        lt["homem_semana"] = sum(lt["pessoas"])
    c["terceirizados"] = sorted(linhas_t.values(), key=lambda x: (ordem_t.get(x["rotulo"], 999), -x["pico"], x["rotulo"]))
    c["total_terceirizados"] = [sum(lt["pessoas"][k] for lt in linhas_t.values()) for k in range(len(semanas))]
    c["total_obra"] = [c["total_semana"][k] + c["total_terceirizados"][k] for k in range(len(semanas))]
    c["pico_proprios"] = max(c["total_semana"], default=0)
    c["semana_pico_proprios"] = semanas[c["total_semana"].index(c["pico_proprios"])] if c["pico_proprios"] else None
    if c.get("pico_total") is None and resumo_t:
        c["pico_total"], c["semana_pico_total"] = resumo_t.get("pico_total"), resumo_t.get("semana_pico_total")
    c["resumo_terceirizados"] = {k: resumo_t.get(k) for k in ("pico_terceirizados", "homem_semana_terceirizado",
                                                             "sem_estimativa", "rotulos")} if resumo_t else None
    if c["resumo_terceirizados"] and c["resumo_terceirizados"].get("rotulos"):
        c["resumo_terceirizados"]["rotulos"] = [{k: v for k, v in r.items() if k != "serie"}
                                               for r in c["resumo_terceirizados"]["rotulos"]]
    return c


def recontar_terceirizados(banco: Banco, obra_id: int, biblioteca: Biblioteca | None = None) -> dict[str, Any]:
    """Refaz só a contagem dos terceirizados dos cenários calculados (nome ou pessoas mudaram), com as posições
    já calculadas. Diz se é preciso rodar o otimizador de novo (limite do canteiro com os terceirizados)."""
    estado = _estado_etapa4(banco, obra_id, biblioteca)
    info = {a["codigo"]: a.get("terceirizado") for a in estado["atividades"]}
    nomes = {a["codigo"]: a.get("nome") for a in estado["atividades"]}
    try:
        cal = calendario_da_obra(banco, obra_id)
    except ErroCronograma:
        return {"recontados": 0, "precisa_recalcular": False}
    n = 0
    for resumo in banco.listar_cenarios(obra_id):
        if resumo["situacao"] not in VALIDAS:
            continue
        c = banco.carregar_cenario(resumo["id"])
        posicoes, novos = [], {}
        for a in c["atividades"]:
            cod = a["atividade"]
            t = info.get(cod)
            if not t:
                novos[cod] = None
                continue
            antigo = a.get("terceirizado") or {}
            pessoas = t["pessoas"]
            detalhe = dict(t.get("detalhe") or {})
            if t.get("por_modo") and antigo.get("equipe_modo"):
                detalhe = dict(antigo["equipe_modo"])
                pessoas = sum(detalhe.values())
            ini = cal.indice_util(cal.offset_de(para_data(a["inicio"])))
            if a.get("partes"):
                dias = [(cal.indice_util(cal.offset_de(para_data(p["inicio"]))), p["duracao"]) for p in a["partes"]]
            else:
                ult = cal.ultimo_util_ate(cal.offset_de(para_data(a["termino"])))
                dias = [(ini, max(1, ult - ini + 1))]
            novos[cod] = {**t, "pessoas": pessoas, "detalhe": detalhe, "equipe_modo": antigo.get("equipe_modo") or {}}
            posicoes.append({"codigo": cod, "nome": nomes.get(cod), "rotulo": t["rotulo"], "pessoas": pessoas,
                             "origem": t["origem"], "detalhe": detalhe, "por_modo": bool(t.get("por_modo")), "dias": dias})
        proprios: dict[int, int] = defaultdict(int)
        for e in c["equipe_semana"]:
            proprios[(para_data(e["semana"]) - cal.semana0).days // 7] += e["contratados"]
        serie = [proprios.get(w, 0) for w in range(max(proprios, default=-1) + 1)]
        banco.regravar_terceirizados(c["id"], novos, contar_terceirizados(cal, posicoes, serie))
        n += 1
    cal_obra = banco.carregar_calendario(obra_id)
    return {"recontados": n,
            "precisa_recalcular": bool(cal_obra.get("max_pessoas_total") and cal_obra.get("contar_terceirizados", 1))}


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
    if c.get("terceirizados"):
        for t in c["terceirizados"]:
            ativas = [k for k, v in enumerate(t["pessoas"]) if v]
            ws.append([t["nome"], c["semanas"][ativas[0]] if ativas else None, t["pico"],
                       c["semanas"][ativas[-1]] if ativas else None, *t["pessoas"]])
        ws.append(["Total na obra", None, max(c["total_obra"], default=0), None, *c["total_obra"]])
        for cel in ws[ws.max_row]:
            cel.font = negrito
    if c.get("equipe_indireta"):
        ws.append([])
        ws.append(["Equipe indireta (da mão de obra)"])
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
                "Folga (dias úteis)", "Crítica", "Terceirizado", "Pessoas do terceirizado", "Origem"])
    for cel in ws3[1]:
        cel.font = negrito
    destaque = PatternFill("solid", fgColor="FDE2E1")
    for a in sorted(c["atividades"], key=lambda a: (a["inicio"], a["ordem"])):
        ws3.append([a["codigo"], a["nome"], a["etapa"], a["tipo"], a["execucao"], a["inicio"], a["termino"], a["duracao"],
                    a["unidade"], ", ".join(f"{n} {f}" for f, n in a["equipe"].items()), a["folga"],
                    "sim" if a["critica"] else "", *((a["terceirizado"]["nome"] if a["terceirizado"].get("nome")
                                                      else f"{a['terceirizado']['rotulo']} (terceirizado)",
                                                      a["terceirizado"]["pessoas"], a["terceirizado"]["origem"])
                                                     if a.get("terceirizado") else ())])
        if a["critica"]:
            for cel in ws3[ws3.max_row]:
                cel.fill = destaque
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
