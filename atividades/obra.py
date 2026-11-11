"""Etapa 3 aplicada a uma obra gravada no banco: ligação, memória e rede."""
from __future__ import annotations

from typing import Any, Iterable

from armazenamento import Banco

from .biblioteca import (
    CRITERIOS_TIPO,
    PRAZOS_ESPERA,
    Biblioteca,
    ErroBiblioteca,
    salvar_atividade_na_biblioteca,
)
from .reconhecimento import (
    CONFIRMADO,
    PENDENTES,
    chave_memoria,
    grupos_do_item,
    ligar_servicos,
    reconhecer,
    resumo_ligacao,
)
from .rede import (
    INDIRETA,
    ErroRede,
    alternativas_de_prazo,
    aplicar_prazos,
    usa_norma,
    dependencias_de,
    editar_atividade,
    indiretas,
    montar_rede,
    sequencia,
    totais_por_atividade,
)


class ErroObra(Exception):
    pass


def _obra(banco: Banco, obra_id: int) -> dict[str, Any]:
    dados = banco.carregar_obra(obra_id)
    if dados is None:
        raise ErroObra("Obra não encontrada.")
    return dados


def ligar_obra(banco: Banco, obra_id: int, biblioteca: Biblioteca, refazer: bool = False) -> dict[str, Any]:
    """Liga os serviços da obra às atividades (memória → regras) e grava.

    Serviços já ligados não são mexidos, a não ser com refazer=True (as escolhas
    confirmadas pelo usuário são sempre mantidas).
    """
    dados = _obra(banco, obra_id)
    servicos = dados["servicos"]
    a_ligar = [s for s in servicos if refazer or not s.get("status_ligacao")]
    if a_ligar:
        ligacoes = ligar_servicos(a_ligar, dados["grupos"], biblioteca, banco.carregar_memoria())
        banco.gravar_ligacoes(obra_id, [{"id": s["id"], **l} for s, l in zip(a_ligar, ligacoes)])
    return estado_ligacao(banco, obra_id, biblioteca)


def estado_ligacao(banco: Banco, obra_id: int, biblioteca: Biblioteca) -> dict[str, Any]:
    """Tudo o que a tela de ligação precisa."""
    dados = _obra(banco, obra_id)
    servicos = dados["servicos"]
    for s in servicos:
        s["grupos"] = grupos_do_item(s.get("item_grupo"), dados["grupos"])
        s["candidatas"] = []
        if s["status_ligacao"] in PENDENTES:
            s["candidatas"] = reconhecer(s["descricao"], s["grupos"], s["natureza"], biblioteca)["candidatas"]
    totais = totais_por_atividade(servicos)
    atividades = []
    for a in biblioteca.lista_atividades():
        t = totais.get(a["codigo"], {"n_itens": 0, "total": 0.0, "total_bdi": 0.0})
        atividades.append({**a, **t})
    return {
        "obra": dados["obra"],
        "servicos": servicos,
        "atividades": atividades,
        "resumo": resumo_ligacao(servicos),
        "total_bdi": round(sum(s["total_bdi"] or 0 for s in servicos), 2),
    }


def servicos_semelhantes(servicos: list[dict[str, Any]], servico: dict[str, Any]) -> list[dict[str, Any]]:
    """Outros serviços com o mesmo código (e base) no mesmo grupo."""
    return [
        s for s in servicos
        if s["id"] != servico["id"] and s.get("codigo") == servico.get("codigo")
        and s.get("base") == servico.get("base") and s.get("item_grupo") == servico.get("item_grupo")
    ]


def confirmar_ligacao(
    banco: Banco, obra_id: int, servico_ids: Iterable[int], atividade: str, biblioteca: Biblioteca
) -> dict[str, Any]:
    """Escolha/troca feita pelo usuário: status 'confirmado' e gravação na memória."""
    atividade = atividade.upper()
    if atividade not in biblioteca.atividades:
        raise ErroObra(f"Atividade {atividade} não existe na biblioteca.")
    dados = _obra(banco, obra_id)
    por_id = {s["id"]: s for s in dados["servicos"]}
    ids = [int(i) for i in servico_ids]
    faltando = [i for i in ids if i not in por_id]
    if faltando or not ids:
        raise ErroObra(f"Serviço(s) não encontrado(s) nesta obra: {faltando or 'nenhum informado'}")
    banco.gravar_ligacoes(obra_id, [
        {"id": i, "atividade_biblioteca": atividade, "status_ligacao": CONFIRMADO, "regra_usada": None} for i in ids
    ])
    chaves = []
    for i in ids:
        s = por_id[i]
        nomes = grupos_do_item(s.get("item_grupo"), dados["grupos"])
        chaves.append(chave_memoria(s.get("base"), s.get("codigo"), nomes[-1] if nomes else None))
    banco.gravar_memoria(chaves, atividade)
    return estado_ligacao(banco, obra_id, biblioteca)


# --------------------------------------------------------------------------- rede


def montar_rede_obra(banco: Banco, obra_id: int, biblioteca: Biblioteca) -> dict[str, Any]:
    """Monta a rede a partir das ligações (sem pendências) e grava a cópia da obra."""
    dados = _obra(banco, obra_id)
    pendentes = [s for s in dados["servicos"] if not s.get("atividade_biblioteca") or s.get("status_ligacao") in PENDENTES]
    if pendentes:
        raise ErroObra(f"Há {len(pendentes)} serviço(s) sem atividade. Resolva as pendências antes de seguir.")
    try:
        rede = montar_rede(biblioteca, dados["servicos"], prazos=banco.prazos_espera(obra_id))
    except ErroRede as exc:
        raise ErroObra(str(exc)) from exc
    banco.salvar_rede(obra_id, rede)
    return estado_rede(banco, obra_id, biblioteca)


def definir_prazos_espera(banco: Banco, obra_id: int, prazos: str, biblioteca: Biblioteca | None = None
                          ) -> dict[str, Any]:
    """Prazos de espera da obra: "pratica" (depende_de, padrão) ou "norma" (depende_de_norma onde houver).

    Troca as dependências das atividades que mudam (com herança, guardadas ao montar a rede), mantém as editadas
    nesta obra, valida ciclo e grava. Sem rede montada, só grava a opção (vale ao montar).
    """
    if prazos not in PRAZOS_ESPERA:
        raise ErroObra("Prazos de espera: use 'pratica' ou 'norma'.")
    _obra(banco, obra_id)
    rede = banco.carregar_rede(obra_id)
    if rede is not None:
        if not any(a.get("deps_prazos") for a in rede["atividades"].values()) and biblioteca is not None:
            # rede montada antes do item 6: calcula as alternativas com a biblioteca atual
            seq = {c for c, a in rede["atividades"].items() if a["tipo"] != INDIRETA and c in biblioteca.atividades}
            ordem = {c: a["ordem_biblioteca"] for c, a in rede["atividades"].items()}
            for cod, alt in alternativas_de_prazo(biblioteca, seq, ordem).items():
                rede["atividades"][cod]["deps_prazos"] = alt
        try:
            rede = aplicar_prazos(rede, prazos)
        except ErroRede as exc:
            raise ErroObra(f"Com os prazos de {'norma' if prazos == 'norma' else 'prática'}: {exc}") from exc
        banco.salvar_rede(obra_id, rede)
    banco.gravar_prazos_espera(obra_id, prazos)
    return estado_rede(banco, obra_id, biblioteca) if rede is not None else {"prazos_espera": prazos}


def estado_rede(banco: Banco, obra_id: int, biblioteca: Biblioteca | None = None) -> dict[str, Any]:
    rede = banco.carregar_rede(obra_id)
    if rede is None:
        raise ErroObra("A rede desta obra ainda não foi montada.")
    prazos = banco.prazos_espera(obra_id)
    seq = sequencia(rede)
    if biblioteca is None:
        try:
            from .biblioteca import carregar_biblioteca

            biblioteca = carregar_biblioteca(funcoes=None)
        except ErroBiblioteca:
            pass
    legenda = (biblioteca.legenda if biblioteca else {}) or {}
    for a in seq:
        a["usa_norma"] = usa_norma(a, prazos)
        a["tem_norma"] = bool(a.get("deps_prazos"))
        a["criterio_tipo"] = legenda.get(a["tipo"]) or CRITERIOS_TIPO.get(a["tipo"])
        if a.get("deps_prazos"):
            a["depende_de_pratica"] = _texto_deps(a["deps_prazos"]["pratica"])
            a["depende_de_norma"] = _texto_deps(a["deps_prazos"]["norma"])
    ind = indiretas(rede)
    todas = list(rede["atividades"].values())
    return {
        "obra": _obra(banco, obra_id)["obra"],
        "prazos_espera": prazos,
        "atividades_norma": [a["codigo"] for a in seq if a["usa_norma"]],
        "sequencia": seq,
        "indiretas": ind,
        "resumo": {
            "atividades": len(todas),
            "na_sequencia": len(seq),
            "indiretas": len(ind),
            "itens": sum(a["n_itens"] for a in todas),
            "total": round(sum(a["total"] for a in todas), 2),
            "total_bdi": round(sum(a["total_bdi"] for a in todas), 2),
        },
    }


def _texto_deps(deps: list[dict[str, Any]]) -> str:
    from .rede import dict_para_dep
    from .biblioteca import formatar_dependencias

    return formatar_dependencias([dict_para_dep(d) for d in deps])


def editar_atividade_obra(
    banco: Banco,
    obra_id: int,
    codigo: str,
    tipo: str | None = None,
    depende_de: str | None = None,
    salvar_na_biblioteca: bool = False,
    caminho_biblioteca: str | None = None,
) -> dict[str, Any]:
    """Edita tipo/dependências só nesta obra; opcionalmente grava também no Excel da biblioteca."""
    rede = banco.carregar_rede(obra_id)
    if rede is None:
        raise ErroObra("A rede desta obra ainda não foi montada.")
    try:
        nova = editar_atividade(rede, codigo, tipo=tipo, depende_de=depende_de)
    except ErroRede as exc:
        raise ErroObra(str(exc)) from exc
    backup = None
    if salvar_na_biblioteca:
        codigo = codigo.upper()
        # Só grava as dependências se o usuário as editou; senão as herdadas desta obra iriam para a biblioteca.
        deps = dependencias_de(nova, codigo, incluir_fim=False) if depende_de is not None else None
        try:
            backup = salvar_atividade_na_biblioteca(codigo, nova["atividades"][codigo]["tipo"], deps, caminho_biblioteca)
        except ErroBiblioteca as exc:
            raise ErroObra("Não foi possível gravar na biblioteca: " + "; ".join(e["mensagem"] for e in exc.erros)) from exc
    banco.salvar_rede(obra_id, nova)
    estado = estado_rede(banco, obra_id)
    estado["backup_biblioteca"] = str(backup) if backup else None
    return estado
