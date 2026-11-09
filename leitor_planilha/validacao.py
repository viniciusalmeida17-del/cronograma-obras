"""Validação dos totais lidos contra os totais da própria planilha."""
from __future__ import annotations

from collections import Counter
from typing import Any

from .natureza import NATUREZAS

TOLERANCIA_TOTAL = 1.00  # R$ — total geral e totais de grupo
TOLERANCIA_SERVICO = 0.05  # R$ — quantidade × preço unitário


def formatar_reais(valor: float | None) -> str:
    if valor is None:
        return "—"
    texto = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


def _alerta(nivel, linha, mensagem, tipo):
    return {"nivel": nivel, "linha": linha, "mensagem": mensagem, "tipo": tipo}


def validar(obra: dict[str, Any], grupos: list[dict], servicos: list[dict], alertas: list[dict],
            so_com_bdi: bool = False) -> dict[str, Any]:
    """Confere totais e quantidade × preço. `so_com_bdi`: a planilha não tem as colunas sem BDI (calculadas);
    a validação usa só as colunas com BDI."""
    soma = round(sum(s["total"] or 0.0 for s in servicos), 2)
    soma_bdi = round(sum(s["total_bdi"] or 0.0 for s in servicos), 2)

    def comparar(lido, planilha):
        if planilha is None:
            return None, None
        dif = round(lido - planilha, 2)
        return abs(dif) <= TOLERANCIA_TOTAL, dif

    confere, dif = comparar(soma, obra.get("total_planilha"))
    confere_bdi, dif_bdi = comparar(soma_bdi, obra.get("total_bdi_planilha"))

    if so_com_bdi:
        confere, dif = None, None
        if confere_bdi is None:
            alertas.append(_alerta("aviso", None, "Total geral com BDI da planilha não encontrado; não foi possível conferir.", "total"))
    elif confere is None:
        alertas.append(_alerta("aviso", None, "Total geral da planilha não encontrado; não foi possível conferir.", "total"))
    elif not confere:
        alertas.append(_alerta("erro", None, f"Soma dos serviços ({formatar_reais(soma)}) difere do total da planilha ({formatar_reais(obra['total_planilha'])}) em {formatar_reais(dif)}.", "total"))
    if confere_bdi is False:
        alertas.append(_alerta("erro", None, f"Soma dos serviços com BDI ({formatar_reais(soma_bdi)}) difere do total da planilha ({formatar_reais(obra['total_bdi_planilha'])}) em {formatar_reais(dif_bdi)}.", "total"))

    # Grupos: só quando o grupo tem total preenchido e > 0.
    grupos_divergentes = 0
    for g in grupos:
        g["confere"] = None
        for campo_plan, campo_soma, rotulo in (
            ("total_planilha", "soma_servicos", ""),
            ("total_bdi_planilha", "soma_servicos_bdi", " com BDI"),
        ):
            if so_com_bdi and campo_plan == "total_planilha":
                continue
            plan = g[campo_plan]
            if not plan or plan <= 0:
                continue
            dif_g = round(g[campo_soma] - plan, 2)
            ok = abs(dif_g) <= TOLERANCIA_TOTAL
            g["confere"] = ok if g["confere"] is None else (g["confere"] and ok)
            if not ok:
                alertas.append(_alerta("erro", g["linha_excel"], f"Grupo {g['item']}: soma dos serviços{rotulo} {formatar_reais(g[campo_soma])} ≠ total do grupo {formatar_reais(plan)} (diferença {formatar_reais(dif_g)}).", "total"))
        if g["confere"] is False:
            grupos_divergentes += 1

    # Serviços: quantidade × preço unitário ≈ total.
    servicos_divergentes = 0
    unit, tot = ("preco_unit_bdi", "total_bdi") if so_com_bdi else ("preco_unit", "total")
    for s in servicos:
        s["divergencia"] = None
        if s["quantidade"] is None or s[unit] is None or s[tot] is None:
            alertas.append(_alerta("aviso", s["linha_excel"], f"Serviço {s['item']}: preço unitário ou total vazio.", "servico"))
            continue
        calculado = round(s["quantidade"] * s[unit], 2)
        dif_s = round(s[tot] - calculado, 2)
        if abs(dif_s) > TOLERANCIA_SERVICO:
            s["divergencia"] = dif_s
            servicos_divergentes += 1
            alertas.append(_alerta("aviso", s["linha_excel"], f"Serviço {s['item']}: quantidade × preço unitário = {formatar_reais(calculado)}, mas o total é {formatar_reais(s[tot])} (diferença {formatar_reais(dif_s)}).", "servico"))

    contagem = Counter(s["natureza"] for s in servicos)
    por_natureza = {n: contagem.get(n, 0) for n in NATUREZAS}

    n = len(servicos)
    if so_com_bdi:
        situacao = ("com BDI confere com a planilha" if confere_bdi else "total com BDI não encontrado"
                    if confere_bdi is None else f"com BDI NÃO confere: {formatar_reais(obra['total_bdi_planilha'])}")
    elif confere:
        situacao = "confere com a planilha"
    elif confere is None:
        situacao = "total da planilha não encontrado"
    else:
        situacao = f"NÃO confere com a planilha: {formatar_reais(obra['total_planilha'])}"
    resumo = f"{n} serviços lidos — total {formatar_reais(soma)} ({situacao})"
    if so_com_bdi:
        resumo = f"{n} serviços lidos — total com BDI {formatar_reais(soma_bdi)} ({situacao})"

    ok = (bool(confere_bdi) if so_com_bdi else (bool(confere) and confere_bdi is not False)) \
        and grupos_divergentes == 0 and n > 0
    return {
        "ok": ok,
        "qtd_servicos": n,
        "qtd_grupos": len(grupos),
        "soma_servicos": soma,
        "soma_servicos_bdi": soma_bdi,
        "total_confere": confere,
        "total_bdi_confere": confere_bdi,
        "diferenca_total": dif,
        "diferenca_total_bdi": dif_bdi,
        "grupos_divergentes": grupos_divergentes,
        "servicos_divergentes": servicos_divergentes,
        "por_natureza": por_natureza,
        "resumo": resumo,
    }
