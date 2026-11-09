"""Leitor da planilha orçamentária de licitação (.xlsx).

Uso básico:

    from leitor_planilha import ler_planilha
    resultado = ler_planilha("orcamento.xlsx")

O resultado é um dicionário (pronto para JSON) com: aba escolhida, colunas mapeadas,
dados da obra, grupos, serviços, alertas e validação dos totais.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Iterable

import openpyxl
from openpyxl.utils import column_index_from_string, get_column_letter

from .colunas import (
    CAMPOS,
    LINHAS_BUSCA_CABECALHO,
    OBRIGATORIOS,
    ROTULOS_CAMPOS,
    achar_cabecalho,
    mapear_colunas,
    pontuacao_cabecalho,
)
from .dados_obra import ler_dados_obra
from .natureza import NATUREZAS, classificar_natureza
from .texto import (
    arredondar_qtd,
    arredondar_reais,
    limpar_texto,
    normalizar,
    para_numero,
    texto_item,
    unidade_canonica,
    unidade_limpa,
)
from .validacao import validar

NOME_ABA_PADRAO = "PLANILHA"

# Campos que as próximas etapas vão preencher.
CAMPOS_FUTUROS_SERVICO = ("atividade_biblioteca", "etapa_obra", "local")


class ErroLeitura(Exception):
    """Erro que impede a leitura do arquivo (arquivo inválido, aba inexistente...)."""


# --------------------------------------------------------------------------- abas


def _ler_grade(ws, max_linhas: int | None = None) -> tuple[list[list[Any]], list[list[str | None]]]:
    """Lê a aba como lista de linhas (valores) e, em paralelo, os formatos numéricos."""
    valores: list[list[Any]] = []
    formatos: list[list[str | None]] = []
    for linha in ws.iter_rows(max_row=max_linhas):
        valores.append([getattr(c, "value", None) for c in linha])
        formatos.append([getattr(c, "number_format", None) for c in linha])
    return valores, formatos


def _abas_info(wb) -> list[dict[str, Any]]:
    info = []
    for nome in wb.sheetnames:
        ws = wb[nome]
        if getattr(ws, "max_row", None) is None:  # alguns tipos de aba (gráficos)
            info.append({"nome": nome, "tem_cabecalho": False})
            continue
        linhas = [list(r) for r in ws.iter_rows(max_row=LINHAS_BUSCA_CABECALHO, values_only=True)]
        info.append({"nome": nome, "tem_cabecalho": achar_cabecalho(linhas) is not None})
    return info


def escolher_aba(nomes: list[str], abas_info: list[dict[str, Any]]) -> tuple[str, str]:
    """Retorna (nome_da_aba, motivo)."""
    for nome in nomes:
        if normalizar(nome) == NOME_ABA_PADRAO:
            return nome, "nome"
    for info in abas_info:
        if info["tem_cabecalho"]:
            return info["nome"], "cabecalho"
    return nomes[0], "primeira"


# --------------------------------------------------------------------------- leitura


def ler_planilha(
    caminho: str | os.PathLike,
    aba: str | None = None,
    mapeamento: dict[str, str] | None = None,
    linha_cabecalho: int | None = None,
    nome_arquivo: str | None = None,
) -> dict[str, Any]:
    """Lê a planilha de licitação.

    :param aba: nome da aba; se None, escolhe automaticamente.
    :param mapeamento: campo -> letra da coluna (ex.: {"item": "B"}); sobrepõe o mapeamento automático.
    :param linha_cabecalho: número (1-based) da linha de cabeçalho; se None, procura automaticamente.
    """
    try:
        wb = openpyxl.load_workbook(caminho, read_only=True, data_only=True)
    except Exception as exc:  # arquivo corrompido, não é xlsx...
        raise ErroLeitura(f"Não foi possível abrir o arquivo como Excel (.xlsx): {exc}") from exc

    try:
        abas_info = _abas_info(wb)
        alertas: list[dict[str, Any]] = []

        if aba is not None:
            if aba not in wb.sheetnames:
                raise ErroLeitura(f"A aba '{aba}' não existe no arquivo.")
            motivo = "usuario"
        else:
            aba, motivo = escolher_aba(wb.sheetnames, abas_info)
            if motivo == "cabecalho":
                alertas.append(_alerta("aviso", None, f"Aba 'PLANILHA' não encontrada; sugerida a aba '{aba}', que tem cabeçalho de orçamento."))
            elif motivo == "primeira":
                alertas.append(_alerta("erro", None, "Nenhuma aba com cabeçalho de orçamento foi encontrada. Escolha a aba e as colunas manualmente."))

        grade, formatos = _ler_grade(wb[aba])
    finally:
        wb.close()

    resultado = _interpretar_grade(grade, formatos, mapeamento, linha_cabecalho, alertas)
    resultado.update(
        {
            "arquivo": nome_arquivo or os.path.basename(str(caminho)),
            "aba": aba,
            "motivo_aba": motivo,
            "abas": abas_info,
        }
    )
    resultado["obra"]["arquivo"] = resultado["arquivo"]
    resultado["obra"]["data_importacao"] = datetime.now().isoformat(timespec="seconds")
    return resultado


def _alerta(nivel: str, linha: int | None, mensagem: str, tipo: str = "geral") -> dict[str, Any]:
    return {"nivel": nivel, "linha": linha, "mensagem": mensagem, "tipo": tipo}


def _interpretar_grade(
    grade: list[list[Any]],
    formatos: list[list[str | None]],
    mapeamento: dict[str, str] | None,
    linha_cabecalho: int | None,
    alertas: list[dict[str, Any]],
) -> dict[str, Any]:
    # 1) linha de cabeçalho
    if linha_cabecalho is not None:
        idx_cab = linha_cabecalho - 1
        if not 0 <= idx_cab < len(grade):
            raise ErroLeitura(f"Linha de cabeçalho {linha_cabecalho} fora da aba.")
    else:
        idx_cab = achar_cabecalho(grade)

    if idx_cab is None:
        # sugere a linha que mais se parece com cabeçalho, para o usuário apontar as colunas
        candidatas = grade[:LINHAS_BUSCA_CABECALHO]
        idx_sugerida = max(range(len(candidatas)), key=lambda i: pontuacao_cabecalho(candidatas[i]), default=0)
        colunas_auto: dict[str, int] = mapear_colunas(grade[idx_sugerida]) if grade else {}
        alertas.append(_alerta("erro", None, f"Linha de cabeçalho não encontrada nas primeiras {LINHAS_BUSCA_CABECALHO} linhas.", "coluna"))
    else:
        idx_sugerida = idx_cab
        colunas_auto = mapear_colunas(grade[idx_cab])

    # 2) colunas: automático + correções do usuário
    colunas = dict(colunas_auto)
    for campo, letra in (mapeamento or {}).items():
        if campo not in CAMPOS:
            raise ErroLeitura(f"Campo desconhecido no mapeamento: {campo}")
        if letra:
            colunas[campo] = column_index_from_string(letra.strip().upper()) - 1
        else:
            colunas.pop(campo, None)

    faltando = [c for c in OBRIGATORIOS if c not in colunas]
    for campo in CAMPOS:
        if campo not in colunas:
            nivel = "erro" if campo in OBRIGATORIOS else "aviso"
            alertas.append(_alerta(nivel, (idx_sugerida + 1) if grade else None, f"Coluna '{ROTULOS_CAMPOS[campo]}' não encontrada no cabeçalho.", "coluna"))

    linha_cab_cells = grade[idx_sugerida] if grade else []
    cabecalhos = [
        {"letra": get_column_letter(i + 1), "texto": limpar_texto(v)}
        for i, v in enumerate(linha_cab_cells)
        if limpar_texto(v)
    ]

    base = {
        "linha_cabecalho": (idx_cab + 1) if idx_cab is not None else None,
        "linha_cabecalho_sugerida": idx_sugerida + 1,
        "colunas": {c: get_column_letter(i + 1) for c, i in sorted(colunas.items(), key=lambda x: x[1])},
        "cabecalhos": cabecalhos,
        "colunas_faltando": faltando,
        "alertas": alertas,
    }

    obra = ler_dados_obra(grade, idx_cab if idx_cab is not None else idx_sugerida)
    obra.update({"total_planilha": None, "total_bdi_planilha": None})

    if idx_cab is None or faltando:
        base.update({"obra": obra, "grupos": [], "servicos": [], "validacao": None, "resumo": "Leitura incompleta: aponte as colunas e a linha de cabeçalho."})
        if obra["prazo_valor"] is None:
            alertas.append(_alerta("erro", None, "Prazo de execução não encontrado. Preencha o prazo (obrigatório).", "obra"))
        return base

    # 3) linhas
    grupos, servicos, ignoradas = _classificar_linhas(grade, formatos, colunas, idx_cab, alertas)
    so_com_bdi = "total" not in colunas and "total_bdi" in colunas
    if so_com_bdi:
        # planilha só com preços com BDI: os sem BDI são calculados pelo BDI (um aviso só, no lugar dos de coluna)
        alertas[:] = [a for a in alertas if not (a["tipo"] == "coluna" and any(
            f"'{ROTULOS_CAMPOS[c]}'" in a["mensagem"] for c in ("preco_unit", "total")))]
        bdi = obra.get("bdi")
        if bdi is not None and bdi > -1:
            fator = 1 + float(bdi)
            for sv in servicos:
                sv["preco_unit"] = arredondar_reais(sv["preco_unit_bdi"] / fator) if sv["preco_unit_bdi"] is not None else None
                sv["total"] = arredondar_reais(sv["total_bdi"] / fator) if sv["total_bdi"] is not None else None
                sv["valores_sem_bdi"] = "calculado"
            pct = f"{100 * float(bdi):.2f}".replace(".", ",")
            alertas.append(_alerta("aviso", None, f"Planilha sem preços sem BDI; valores sem BDI calculados pelo BDI de {pct}%.",
                                   "coluna"))
        else:
            alertas.append(_alerta("aviso", None, "Planilha sem preços sem BDI e sem BDI informado; valores sem BDI "
                                   "não calculados (informe o BDI).", "coluna"))
    _montar_hierarquia(grupos, servicos, alertas)

    # 4) totais da planilha: linha logo abaixo do cabeçalho (ou linha de total solta no fim)
    tot, tot_bdi = _totais_planilha(grade, colunas, idx_cab, ignoradas)
    obra["total_planilha"] = tot
    obra["total_bdi_planilha"] = tot_bdi

    if obra["prazo_valor"] is None:
        alertas.append(_alerta("erro", None, "Prazo de execução não encontrado. Preencha o prazo (obrigatório).", "obra"))
    elif obra["prazo_unidade"] is None:
        alertas.append(_alerta("aviso", None, f"Unidade do prazo não identificada em '{obra['prazo_texto']}'. Confira.", "obra"))
    if obra["bdi"] is None:
        alertas.append(_alerta("aviso", None, "BDI não encontrado.", "obra"))
    if not obra["nome"]:
        alertas.append(_alerta("aviso", None, "Nome da obra não encontrado.", "obra"))

    validacao = validar(obra, grupos, servicos, alertas, so_com_bdi=so_com_bdi)
    if so_com_bdi:
        obra["total_planilha"] = validacao["soma_servicos"] if obra.get("bdi") is not None else None
        obra["sem_bdi_calculado"] = True

    base.update(
        {
            "obra": obra,
            "grupos": grupos,
            "servicos": servicos,
            "validacao": validacao,
            "resumo": validacao["resumo"],
        }
    )
    return base


def _valor(linha: list[Any], colunas: dict[str, int], campo: str) -> Any:
    idx = colunas.get(campo)
    if idx is None or idx >= len(linha):
        return None
    return linha[idx]


def _formato(formatos_linha: list[str | None], colunas: dict[str, int], campo: str) -> str | None:
    idx = colunas.get(campo)
    if idx is None or idx >= len(formatos_linha):
        return None
    return formatos_linha[idx]


def _classificar_linhas(grade, formatos, colunas, idx_cab, alertas):
    grupos: list[dict[str, Any]] = []
    servicos: list[dict[str, Any]] = []
    ignoradas: list[tuple[int, dict[str, Any]]] = []  # linhas só com valores (totais soltos)
    itens_vistos: dict[str, int] = {}

    for idx in range(idx_cab + 1, len(grade)):
        linha = grade[idx]
        fmts = formatos[idx] if idx < len(formatos) else []
        n_linha = idx + 1

        bruto_item = _valor(linha, colunas, "item")
        item = texto_item(bruto_item, _formato(fmts, colunas, "item"))
        if isinstance(bruto_item, float) and not bruto_item.is_integer():
            alertas.append(_alerta("aviso", n_linha, f"Item '{item}' está gravado como número no Excel; confira se as casas decimais estão corretas.", "linha"))
        descricao = limpar_texto(_valor(linha, colunas, "descricao"))
        codigo = limpar_texto(_valor(linha, colunas, "codigo"))
        base = limpar_texto(_valor(linha, colunas, "base"))
        unidade = unidade_limpa(_valor(linha, colunas, "unidade"))
        # Planilhas costumam ter 0 nas colunas de texto dos grupos: tratar "0" como vazio.
        if unidade == "0":
            unidade = None
        if codigo == "0":
            codigo = None
        quantidade = para_numero(_valor(linha, colunas, "quantidade"))
        valores = {
            c: para_numero(_valor(linha, colunas, c))
            for c in ("preco_unit", "preco_unit_bdi", "total", "total_bdi")
        }

        tem_texto = any([item, descricao, codigo, unidade, base])
        tem_valor = any(v for v in [quantidade, *valores.values()])
        if not tem_texto and not tem_valor:
            continue  # linha vazia ou só zeros

        if codigo and unidade and quantidade is not None and quantidade > 0:
            if item in itens_vistos:
                alertas.append(_alerta("aviso", n_linha, f"Item {item} repetido (já aparece na linha {itens_vistos[item]}).", "linha"))
            if item:
                itens_vistos.setdefault(item, n_linha)
            else:
                alertas.append(_alerta("aviso", n_linha, f"Serviço {codigo} sem número de item.", "linha"))
            natureza = classificar_natureza(unidade)
            servico = {
                "linha_excel": n_linha,
                "item": item,
                "item_grupo": None,
                "caminho_grupos": [],
                "base": base,
                "codigo": codigo,
                "descricao": descricao,
                "unidade": unidade,
                "unidade_normalizada": unidade_canonica(unidade),
                "quantidade": arredondar_qtd(quantidade),
                "preco_unit": arredondar_reais(valores["preco_unit"]),
                "preco_unit_bdi": arredondar_reais(valores["preco_unit_bdi"]),
                "total": arredondar_reais(valores["total"]),
                "total_bdi": arredondar_reais(valores["total_bdi"]),
                "natureza": natureza,
                "natureza_automatica": natureza,
            }
            for campo in CAMPOS_FUTUROS_SERVICO:
                servico[campo] = None
            servicos.append(servico)
        elif item and descricao and not codigo:
            if item in itens_vistos:
                alertas.append(_alerta("aviso", n_linha, f"Item {item} repetido (já aparece na linha {itens_vistos[item]}).", "linha"))
            itens_vistos.setdefault(item, n_linha)
            grupos.append(
                {
                    "linha_excel": n_linha,
                    "item": item,
                    "descricao": descricao,
                    "item_pai": None,
                    "nivel": None,
                    "total_planilha": arredondar_reais(valores["total"]),
                    "total_bdi_planilha": arredondar_reais(valores["total_bdi"]),
                    "soma_servicos": 0.0,
                    "soma_servicos_bdi": 0.0,
                    "qtd_servicos": 0,
                }
            )
        elif not item and not descricao and not codigo:
            ignoradas.append((idx, valores))
            if idx == idx_cab + 1:
                continue  # linha de totais logo abaixo do cabeçalho (esperada)
            alertas.append(_alerta("info", n_linha, "Linha com valores sem item nem descrição (total solto) — ignorada.", "linha"))
        else:
            motivos = []
            if codigo and not unidade:
                motivos.append("sem unidade")
            if codigo and (quantidade is None or quantidade <= 0):
                motivos.append("quantidade zero ou vazia")
            if not codigo and not item:
                motivos.append("sem número de item")
            if not codigo and item and not descricao:
                motivos.append("sem descrição")
            texto = ", ".join(motivos) or "formato não reconhecido"
            ident = item or codigo or (descricao or "")[:40]
            alertas.append(_alerta("aviso", n_linha, f"Linha '{ident}' ignorada: {texto}.", "linha"))

    return grupos, servicos, ignoradas


def _prefixos(item: str) -> Iterable[str]:
    partes = item.split(".")
    for n in range(len(partes) - 1, 0, -1):
        yield ".".join(partes[:n])


def _pai(item: str | None, por_item: dict[str, dict[str, Any]]) -> str | None:
    if not item:
        return None
    for prefixo in _prefixos(item):
        if prefixo in por_item:
            return prefixo
    return None


def _montar_hierarquia(grupos, servicos, alertas) -> None:
    por_item = {g["item"]: g for g in grupos}
    for g in grupos:
        g["item_pai"] = _pai(g["item"], por_item)
        if g["item_pai"] is None and "." in g["item"]:
            alertas.append(_alerta("aviso", g["linha_excel"], f"Grupo {g['item']} sem grupo pai na planilha.", "hierarquia"))

    def caminho(item_grupo: str | None) -> list[str]:
        cam = []
        while item_grupo is not None:
            cam.append(item_grupo)
            item_grupo = por_item[item_grupo]["item_pai"]
        return list(reversed(cam))

    for g in grupos:
        g["nivel"] = len(caminho(g["item"]))

    for s in servicos:
        s["item_grupo"] = _pai(s["item"], por_item)
        s["caminho_grupos"] = caminho(s["item_grupo"])
        if s["item_grupo"] is None:
            alertas.append(_alerta("aviso", s["linha_excel"], f"Serviço {s['item'] or s['codigo']} sem grupo (nenhum grupo com prefixo do item).", "hierarquia"))
        for gi in s["caminho_grupos"]:
            g = por_item[gi]
            g["qtd_servicos"] += 1
            g["soma_servicos"] += s["total"] or 0.0
            g["soma_servicos_bdi"] += s["total_bdi"] or 0.0

    for g in grupos:
        g["soma_servicos"] = round(g["soma_servicos"], 2)
        g["soma_servicos_bdi"] = round(g["soma_servicos_bdi"], 2)


def _totais_planilha(grade, colunas, idx_cab, ignoradas) -> tuple[float | None, float | None]:
    def ler(idx):
        linha = grade[idx]
        return (
            arredondar_reais(para_numero(_valor(linha, colunas, "total"))),
            arredondar_reais(para_numero(_valor(linha, colunas, "total_bdi"))),
        )

    if idx_cab + 1 < len(grade):
        linha = grade[idx_cab + 1]
        sem_item = not texto_item(_valor(linha, colunas, "item")) and not limpar_texto(_valor(linha, colunas, "descricao"))
        if sem_item:
            tot, tot_bdi = ler(idx_cab + 1)
            if tot or tot_bdi:
                return tot, tot_bdi
    # alternativa: última linha de total solta no fim da planilha
    for idx, valores in reversed(ignoradas):
        if valores.get("total") or valores.get("total_bdi"):
            return ler(idx)
    return None, None


__all__ = ["ler_planilha", "ErroLeitura", "escolher_aba", "NATUREZAS"]
