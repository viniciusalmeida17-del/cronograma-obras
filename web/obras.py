"""Gerenciar as obras salvas: etapa atual, quais etapas podem ser abertas, leitura salva, edição e exclusão."""
from __future__ import annotations

from contextlib import closing
from pathlib import Path
from typing import Any, Iterable

from armazenamento import Banco
from leitor_planilha.leitor import _montar_hierarquia
from leitor_planilha.validacao import validar

# etapas que se abrem pela barra do topo / pelos botões da lista (chave, rótulo, endereço)
ETAPAS = (
    ("leitura", "Leitura", "/"),
    ("ligacao", "Ligação", "/ligacao"),
    ("sequencia", "Sequência", "/sequencia"),
    ("mao_de_obra", "Mão de obra", "/mao-de-obra"),
    ("cronograma", "Cronograma", "/cronograma"),
)

# etapa atual (a mais avançada a que a obra chegou)
ATUAIS = (
    ("escolhido", "Cenário escolhido"),
    ("cronograma", "Cronograma calculado"),
    ("mao_de_obra", "Mão de obra"),
    ("sequencia", "Sequência"),
    ("ligacao", "Ligação"),
    ("leitura", "Leitura"),
)

CAMPOS_EDITAVEIS = ("nome", "prazo_valor", "prazo_unidade", "bdi", "desoneracao", "referencias")
UNIDADES_PRAZO = ("dias", "semanas", "meses", "anos")


class ErroObras(Exception):
    def __init__(self, mensagem: str, status: int = 400):
        super().__init__(mensagem)
        self.status = status


_SITUACAO = """
    SELECT o.id,
        EXISTS (SELECT 1 FROM servicos s WHERE s.obra_id = o.id AND s.status_ligacao IS NOT NULL) AS tem_ligacao,
        EXISTS (SELECT 1 FROM obra_atividades a WHERE a.obra_id = o.id) AS tem_rede,
        EXISTS (SELECT 1 FROM atividade_resumo r WHERE r.obra_id = o.id) AS tem_mao_de_obra,
        EXISTS (SELECT 1 FROM cenarios c WHERE c.obra_id = o.id) AS tem_cenarios,
        EXISTS (SELECT 1 FROM cenarios c WHERE c.obra_id = o.id AND c.escolhido = 1) AS tem_escolhido
    FROM obras o
"""


def situacoes(banco: Banco, ids: Iterable[int] | None = None) -> dict[int, dict[str, bool]]:
    """Até onde cada obra chegou (consulta só a existência de dados de cada etapa)."""
    with closing(banco._conectar()) as con:
        linhas = con.execute(_SITUACAO).fetchall()
    filtro = set(ids) if ids is not None else None
    return {r["id"]: {k: bool(r[k]) for k in r.keys() if k != "id"}
            for r in linhas if filtro is None or r["id"] in filtro}


def etapas_da_obra(situacao: dict[str, bool]) -> dict[str, Any]:
    """{"atual": chave, "atual_rotulo", "etapas": [{chave, rotulo, url, ativa, motivo}]}"""
    feito = {
        "escolhido": situacao["tem_escolhido"],
        "cronograma": situacao["tem_cenarios"],
        "mao_de_obra": situacao["tem_mao_de_obra"],
        "sequencia": situacao["tem_rede"],
        "ligacao": situacao["tem_ligacao"],
        "leitura": True,
    }
    atual, rotulo = next((c, r) for c, r in ATUAIS if feito[c])
    motivos = {
        "leitura": None,
        "ligacao": None,
        "sequencia": None if situacao["tem_rede"] else "Termine a ligação e monte a sequência primeiro (na tela de Ligação).",
        "mao_de_obra": None if situacao["tem_rede"] else "Monte a sequência primeiro (termine a ligação e monte a rede).",
        "cronograma": (None if situacao["tem_mao_de_obra"] else
                       "Calcule a mão de obra primeiro." if situacao["tem_rede"] else "Monte a sequência primeiro."),
    }
    etapas = [{"chave": c, "rotulo": r, "url": u, "ativa": motivos[c] is None, "motivo": motivos[c]}
              for c, r, u in ETAPAS]
    return {"atual": atual, "atual_rotulo": rotulo, "etapas": etapas}


def listar(banco: Banco) -> list[dict[str, Any]]:
    obras = banco.listar_obras()
    sit = situacoes(banco)
    for o in obras:
        o.update(etapas_da_obra(sit[o["id"]]))
    return obras


def etapas(banco: Banco, obra_id: int) -> dict[str, Any]:
    dados = banco.carregar_obra(obra_id)
    if dados is None:
        raise ErroObras("Obra não encontrada.", 404)
    o = dados["obra"]
    return {"obra": {"id": obra_id, "nome": o.get("nome"), "arquivo": o.get("arquivo")},
            **etapas_da_obra(situacoes(banco, [obra_id])[obra_id])}


# ------------------------------------------------------------------ leitura de uma obra salva


def leitura_salva(banco: Banco, obra_id: int) -> dict[str, Any]:
    """Os dados lidos da planilha, no mesmo formato da leitura nova (para a tela de Leitura), sem reler o Excel."""
    dados = banco.carregar_obra(obra_id)
    if dados is None:
        raise ErroObras("Obra não encontrada.", 404)
    obra = dados["obra"]
    grupos = [{**g, "nivel": None, "soma_servicos": 0.0, "soma_servicos_bdi": 0.0, "qtd_servicos": 0}
              for g in dados["grupos"]]
    servicos = [{**s, "natureza_automatica": s["natureza"]} for s in dados["servicos"]]
    alertas: list[dict[str, Any]] = []
    _montar_hierarquia(grupos, servicos, alertas)
    validacao = validar(obra, grupos, servicos, alertas)
    return {
        "obra_id": obra_id, "salva": True, "arquivo": obra.get("arquivo"), "aba": obra.get("aba"),
        "data_importacao": obra.get("data_importacao"),
        "obra": obra, "grupos": grupos, "servicos": servicos, "validacao": validacao, "resumo": validacao["resumo"],
        "alertas": [a for a in alertas if a["tipo"] in ("geral", "servico", "grupo", "total")],
        **etapas_da_obra(situacoes(banco, [obra_id])[obra_id]),
    }


def editar_obra(banco: Banco, obra_id: int, dados: dict[str, Any]) -> dict[str, Any]:
    """Altera nome, prazo, BDI, desoneração e referências de uma obra salva."""
    if banco.carregar_obra(obra_id) is None:
        raise ErroObras("Obra não encontrada.", 404)
    novos: dict[str, Any] = {}
    for campo, valor in dados.items():
        if campo not in CAMPOS_EDITAVEIS:
            continue
        if campo in ("prazo_valor", "bdi"):
            if valor in (None, ""):
                valor = None
            else:
                try:
                    valor = float(valor)
                except (TypeError, ValueError):
                    raise ErroObras(f"Valor inválido para {'prazo' if campo == 'prazo_valor' else 'BDI'}.")
        if campo == "prazo_unidade" and valor not in UNIDADES_PRAZO:
            raise ErroObras("Unidade de prazo inválida.")
        if campo == "referencias":
            if not isinstance(valor, list):
                raise ErroObras("Referências devem ser uma lista.")
            valor = [str(v).strip() for v in valor if str(v).strip()]
        if campo in ("nome", "desoneracao") and valor is not None:
            valor = str(valor).strip() or None
        novos[campo] = valor
    if "prazo_valor" in novos and not (novos["prazo_valor"] and novos["prazo_valor"] > 0):
        raise ErroObras("Informe o prazo da obra (obrigatório para as próximas etapas).")
    if "bdi" in novos and novos["bdi"] is not None and not 0 <= novos["bdi"] < 5:
        raise ErroObras("BDI inválido (use, por exemplo, 25 para 25%).")
    banco.atualizar_obra(obra_id, novos)
    return leitura_salva(banco, obra_id)


# ------------------------------------------------------------------ exclusão


def excluir(banco: Banco, ids: Iterable[Any], rodando: Iterable[int] = ()) -> dict[str, Any]:
    """Apaga as obras e tudo delas (e a cópia da planilha). A memória das ligações e o banco de coeficientes ficam.

    `rodando`: obras com cálculo do cronograma em andamento (não podem ser excluídas; nada é apagado).
    """
    try:
        ids = sorted({int(i) for i in ids})
    except (TypeError, ValueError):
        raise ErroObras("Lista de obras inválida.")
    if not ids:
        raise ErroObras("Escolha pelo menos uma obra para excluir.")
    obras = {o["id"]: o for o in banco.listar_obras()}
    faltando = [i for i in ids if i not in obras]
    if faltando:
        raise ErroObras(f"Obra(s) não encontrada(s): {', '.join(map(str, faltando))}.", 404)
    ocupadas = [i for i in ids if i in set(rodando)]
    if ocupadas:
        nomes = "; ".join(f"nº {i} ({(obras[i]['nome'] or 'sem nome')[:60]})" for i in ocupadas)
        raise ErroObras(f"O cálculo do cronograma está rodando: {nomes}. Pare o cálculo ou espere terminar antes de excluir.",
                        409)
    arquivos = banco.excluir_obras(ids)
    apagados = []
    for caminho in arquivos:
        try:
            Path(caminho).unlink()
            apagados.append(str(caminho))
        except FileNotFoundError:
            pass
    return {"excluidas": ids, "nomes": [obras[i]["nome"] for i in ids], "arquivos_apagados": apagados}
