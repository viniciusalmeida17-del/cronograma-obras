"""Ligação automática dos serviços da planilha às atividades da biblioteca."""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from leitor_planilha.texto import normalizar

from .biblioteca import Biblioteca, Regra

AUTOMATICO = "automatico"
MEMORIA = "memoria"
CONFIRMADO = "confirmado"
AMBIGUO = "ambiguo"
SEM_REGRA = "sem_regra"
STATUS = (AUTOMATICO, MEMORIA, CONFIRMADO, AMBIGUO, SEM_REGRA)
PENDENTES = (AMBIGUO, SEM_REGRA)


def grupos_do_item(item_grupo: str | None, grupos: Iterable[Mapping[str, Any]]) -> list[str]:
    """Nomes dos grupos acima do serviço, do mais geral ao mais específico."""
    por_item = {g["item"]: g for g in grupos}
    nomes: list[str] = []
    atual = item_grupo
    while atual is not None and atual in por_item:
        nomes.append(por_item[atual]["descricao"])
        atual = por_item[atual].get("item_pai")
    return list(reversed(nomes))


def chave_memoria(base: str | None, codigo: str | None, grupo_imediato: str | None) -> tuple[str, str, str]:
    """Chave da memória: mesma base + mesmo código + mesmo nome do grupo imediato."""
    return normalizar(base), normalizar(codigo), normalizar(grupo_imediato)


def _casa_termo(termo: str, texto: str) -> bool:
    if termo.startswith("^"):
        return texto.startswith(termo[1:])
    return termo in texto


def avaliar_regra(regra: Regra, grupos_norm: list[str], descricao_norm: str, natureza: str | None) -> int | None:
    """Retorna a profundidade do grupo casado (0 se a regra não olha grupo) ou None se a regra não vale."""
    if regra.natureza and regra.natureza != natureza:
        return None
    if regra.termos_na_descricao and not any(_casa_termo(t, descricao_norm) for t in regra.termos_na_descricao):
        return None
    if not regra.termos_no_grupo:
        return 0
    profundidade = None
    for nivel, nome in enumerate(grupos_norm, start=1):
        if any(_casa_termo(t, nome) for t in regra.termos_no_grupo):
            profundidade = nivel  # fica com o mais específico
    return profundidade


def reconhecer(
    descricao: str | None,
    grupos: list[str],
    natureza: str | None,
    biblioteca: Biblioteca,
) -> dict[str, Any]:
    """Aplica as regras a um serviço.

    Retorna {atividade, status, regra_usada, candidatas, regras_validas}.
    """
    grupos_norm = [normalizar(g) for g in grupos]
    desc_norm = normalizar(descricao)
    validas: list[tuple[int, int, Regra]] = []  # (prioridade, -profundidade, regra)
    for regra in biblioteca.regras:
        prof = avaliar_regra(regra, grupos_norm, desc_norm, natureza)
        if prof is not None:
            validas.append((regra.prioridade, -prof, regra))

    if not validas:
        return {"atividade": None, "status": SEM_REGRA, "regra_usada": None, "candidatas": [], "regras_validas": []}

    melhor = min((p, d) for p, d, _ in validas)
    empatadas = sorted((r for p, d, r in validas if (p, d) == melhor), key=lambda r: r.ordem)
    atividades = list(dict.fromkeys(r.atividade for r in empatadas))
    regras_validas = [r.ordem for _, _, r in sorted(validas, key=lambda x: (x[0], x[1], x[2].ordem))]
    if len(atividades) > 1:
        return {"atividade": None, "status": AMBIGUO, "regra_usada": None, "candidatas": atividades,
                "regras_validas": regras_validas}
    return {"atividade": atividades[0], "status": AUTOMATICO, "regra_usada": empatadas[0].ordem,
            "candidatas": [], "regras_validas": regras_validas}


def ligar_servicos(
    servicos: list[dict[str, Any]],
    grupos: list[Mapping[str, Any]],
    biblioteca: Biblioteca,
    memoria: Mapping[tuple[str, str, str], str] | None = None,
    manter_confirmados: bool = True,
) -> list[dict[str, Any]]:
    """Liga cada serviço a uma atividade. Não altera a lista de entrada.

    Cada serviço precisa de: item_grupo, base, codigo, descricao, natureza.
    Ordem: confirmação anterior do usuário (se manter_confirmados) → memória → regras.
    Retorna, para cada serviço (na mesma ordem), um dict com
    atividade_biblioteca, status_ligacao, regra_usada, candidatas, grupos e grupo_imediato.
    """
    memoria = memoria or {}
    resultado = []
    for s in servicos:
        nomes = grupos_do_item(s.get("item_grupo"), grupos)
        imediato = nomes[-1] if nomes else None
        base_info = {"grupos": nomes, "grupo_imediato": imediato, "candidatas": []}

        if manter_confirmados and s.get("status_ligacao") == CONFIRMADO and s.get("atividade_biblioteca"):
            resultado.append({**base_info, "atividade_biblioteca": s["atividade_biblioteca"],
                              "status_ligacao": CONFIRMADO, "regra_usada": None})
            continue

        lembrada = memoria.get(chave_memoria(s.get("base"), s.get("codigo"), imediato))
        if lembrada and lembrada in biblioteca.atividades:
            resultado.append({**base_info, "atividade_biblioteca": lembrada, "status_ligacao": MEMORIA, "regra_usada": None})
            continue

        r = reconhecer(s.get("descricao"), nomes, s.get("natureza"), biblioteca)
        resultado.append({**base_info, "atividade_biblioteca": r["atividade"], "status_ligacao": r["status"],
                          "regra_usada": r["regra_usada"], "candidatas": r["candidatas"]})
    return resultado


def resumo_ligacao(ligacoes: list[Mapping[str, Any]]) -> dict[str, Any]:
    cont = {st: 0 for st in STATUS}
    for l in ligacoes:
        cont[l["status_ligacao"]] = cont.get(l["status_ligacao"], 0) + 1
    total = len(ligacoes)
    pendentes = cont[AMBIGUO] + cont[SEM_REGRA]
    partes = [f"{cont[AUTOMATICO]} ligados automaticamente"]
    if cont[MEMORIA]:
        partes.append(f"{cont[MEMORIA]} pela memória")
    if cont[CONFIRMADO]:
        partes.append(f"{cont[CONFIRMADO]} confirmados")
    partes.append(f"{pendentes} pendentes")
    return {"total": total, "pendentes": pendentes, "por_status": cont,
            "texto": f"{total} serviços — " + ", ".join(partes)}
