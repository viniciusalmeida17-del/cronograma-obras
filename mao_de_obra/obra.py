"""Etapa 4 aplicada a uma obra gravada no banco: análise das composições, parâmetros, execução e resumo."""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Iterable

from armazenamento import Banco
from atividades.biblioteca import Biblioteca

from .analise import COMPOSICAO, ESTIMADO, MANUAL, Analisador, chave_codigo, mapa_codigo_item
from .calculo import EQUIPE_MAX, EQUIPE_PADRAO, EXECUCOES, INDIRETA, PERGUNTAR, calcular_obra
from .composicoes import ler_composicoes
from .funcoes import TabelaFuncoes, carregar_funcoes, carregar_palavras_subcomposicao


class ErroMaoDeObra(Exception):
    pass


CAMPOS_NOVOS = ("execucao_padrao", "equipe_padrao", "equipe_max", "duracao_fixa_dias")


def _obra(banco: Banco, obra_id: int) -> dict[str, Any]:
    dados = banco.carregar_obra(obra_id)
    if dados is None:
        raise ErroMaoDeObra(f"Obra {obra_id} não encontrada.")
    return dados


def atividades_da_obra(banco: Banco, obra_id: int, biblioteca: Biblioteca | None = None) -> dict[str, dict[str, Any]]:
    """Cópia das atividades da obra (etapa 3). Campos da etapa 4 vazios (obra antiga) vêm da biblioteca."""
    rede = banco.carregar_rede(obra_id)
    if rede is None:
        raise ErroMaoDeObra("A rede de atividades desta obra ainda não foi montada (etapa 3).")
    atividades = rede["atividades"]
    for cod, a in atividades.items():
        lib = biblioteca.atividades.get(cod) if biblioteca else None
        for campo in CAMPOS_NOVOS:
            if a.get(campo) is None and lib is not None:
                a[campo] = getattr(lib, campo)
        a["execucao_padrao"] = a.get("execucao_padrao") or "propria"
        a["equipe_padrao"] = a.get("equipe_padrao") or EQUIPE_PADRAO
        a["equipe_max"] = a.get("equipe_max") or EQUIPE_MAX
    return atividades


def analisar_obra(
    banco: Banco,
    obra_id: int,
    biblioteca: Biblioteca | None = None,
    funcoes: TabelaFuncoes | None = None,
    palavras: list[str] | None = None,
) -> dict[str, Any]:
    """Lê as composições do arquivo da obra, calcula as horas por serviço e grava. Alimenta o banco de coeficientes."""
    arquivo = banco.arquivo_da_obra(obra_id)
    if arquivo is None:
        raise ErroMaoDeObra("O arquivo da planilha desta obra não está guardado. Envie o .xlsx novamente.")
    dados = _obra(banco, obra_id)
    atividades = atividades_da_obra(banco, obra_id, biblioteca)
    funcoes = funcoes or carregar_funcoes()
    palavras = palavras if palavras is not None else carregar_palavras_subcomposicao()

    lidas = ler_composicoes(arquivo, dados["obra"].get("aba"))
    servicos = dados["servicos"]
    analisador = Analisador(lidas.composicoes, funcoes, palavras, mapa_codigo_item(servicos), banco.consulta_coeficientes())
    manuais = banco.horas_manuais(obra_id)
    analises = {s["id"]: analisador.analisar_servico(s, manuais.get(s["id"])) for s in servicos}
    banco.gravar_analises(obra_id, analises)
    banco.gravar_custos_mao_de_obra(analises)
    banco.gravar_abas_composicoes(obra_id, lidas.resumo_abas())

    # banco de coeficientes: horas lidas das composições desta planilha, por base + código
    for s in servicos:
        a = analises[s["id"]]
        if a["origem"] == MANUAL or not a.get("composicao") or not s.get("codigo"):
            continue
        horas: dict[str, float] = defaultdict(float)
        for h in a["horas"]:
            if h["origem"] != ESTIMADO:
                horas[h["funcao"]] += h["horas_un"]
        if horas:
            banco.gravar_coeficientes(s.get("base"), s["codigo"], dict(horas), "planilha", obra_id, s.get("descricao"))

    banco.iniciar_execucao(obra_id, {
        c: (a["execucao_padrao"] if a["execucao_padrao"] in EXECUCOES else None)
        for c, a in atividades.items() if a["tipo"] != INDIRETA
    })
    estado = estado_mao_de_obra(banco, obra_id, biblioteca)
    estado["alertas_composicoes"] = lidas.alertas
    return estado


def estado_mao_de_obra(banco: Banco, obra_id: int, biblioteca: Biblioteca | None = None) -> dict[str, Any]:
    """Recalcula estimativas, durações e resumo (rápido; não relê o Excel) e grava o resumo por atividade."""
    dados = _obra(banco, obra_id)
    analises = banco.carregar_analises(obra_id)
    if not analises:
        raise ErroMaoDeObra("A mão de obra desta obra ainda não foi calculada.")
    atividades = atividades_da_obra(banco, obra_id, biblioteca)
    execucao = banco.carregar_execucao(obra_id)
    parametros = banco.carregar_parametros(obra_id)
    obra = dados["obra"]
    resultado = calcular_obra(dados["servicos"], analises, atividades, execucao, parametros,
                              (obra.get("prazo_valor"), obra.get("prazo_unidade")))
    banco.gravar_estimativas(analises)
    banco.gravar_resumo_atividades(obra_id, resultado["atividades"])

    # equipe indireta separada em "toda a obra" e "por período"
    por_servico_ativ = {s["id"]: s.get("atividade_biblioteca") for s in dados["servicos"]}
    equipe = []
    for sid, a in analises.items():
        cod = por_servico_ativ.get(sid)
        ativ = atividades.get(cod) or {}
        for funcao, q in a["indireta"].items():
            toda = (ativ.get("periodo_de") in (None, "INICIO_OBRA")) and (ativ.get("periodo_ate") in (None, "FIM_OBRA"))
            equipe.append({"funcao": funcao, "pessoas": round(q, 4), "atividade": cod, "nome_atividade": ativ.get("nome"),
                           "periodo_de": ativ.get("periodo_de"), "periodo_ate": ativ.get("periodo_ate"), "toda_obra": toda})
    resultado["equipe_indireta"] = equipe
    fixa: dict[str, float] = defaultdict(float)
    for e in equipe:
        if e["toda_obra"]:
            fixa[e["funcao"]] += e["pessoas"]
    resultado["equipe_fixa"] = [{"funcao": f, "pessoas": round(q, 4)} for f, q in fixa.items()]

    # detalhes por serviço para a tela
    servicos = []
    for s in dados["servicos"]:
        a = analises.get(s["id"])
        if not a:
            continue
        servicos.append({
            "id": s["id"], "item": s["item"], "linha_excel": s["linha_excel"], "base": s["base"], "codigo": s["codigo"],
            "descricao": s["descricao"], "unidade": s["unidade"], "quantidade": s["quantidade"], "total": s["total"],
            "atividade": s.get("atividade_biblioteca"), "origem": a["origem"],
            "horas": [{**h, "horas_total": round(h["horas_un"] * (s["quantidade"] or 0), 4)} for h in a["horas"]],
            "equipamentos": a["equipamentos"], "pendentes": a["pendentes"], "indireta": a["indireta"],
            "estimativa": a.get("estimativa"),
        })
    resultado["servicos"] = servicos
    resultado["obra"] = {k: obra.get(k) for k in ("id", "nome", "arquivo", "prazo_valor", "prazo_unidade", "composicoes_abas")}
    resultado["abas_composicoes"] = _json(obra.get("composicoes_abas"))
    resultado["funcoes_conhecidas"] = sorted({h["funcao"] for a in analises.values() for h in a["horas"]}
                                             | {f for a in resultado["atividades"] for f in a["horas_brutas"]})
    resultado["pode_seguir"] = not resultado["pendencias"]
    return resultado


def _json(texto: Any) -> Any:
    import json
    try:
        return json.loads(texto) if texto else []
    except ValueError:
        return []


# --------------------------------------------------------------------------- edições do usuário

_RE_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def salvar_parametros(banco: Banco, obra_id: int, dados: dict[str, Any]) -> None:
    atual = banco.carregar_parametros(obra_id)
    p = {**atual, **{k: v for k, v in dados.items() if k in atual}}
    try:
        p["horas_semana"] = float(p["horas_semana"])
        p["dias_semana"] = int(p["dias_semana"])
        p["rendimento"] = float(p["rendimento"])
    except (TypeError, ValueError):
        raise ErroMaoDeObra("Parâmetros inválidos.")
    if p["rendimento"] > 1.5:
        p["rendimento"] /= 100  # aceita "90" como 90%
    if not 0 < p["horas_semana"] <= 80:
        raise ErroMaoDeObra("Horas por semana devem estar entre 1 e 80.")
    if p["dias_semana"] not in (5, 6):
        raise ErroMaoDeObra("Dias de trabalho por semana: 5 (segunda a sexta) ou 6 (com sábado).")
    if not 0.3 <= p["rendimento"] <= 1.5:
        raise ErroMaoDeObra("Rendimento deve estar entre 30% e 150%.")
    mudancas = []
    for m in p.get("mudancas_jornada") or []:
        data, horas = str(m.get("a_partir_de") or "").strip(), m.get("horas_semana")
        if not _RE_DATA.match(data):
            raise ErroMaoDeObra(f"Data inválida na mudança de jornada: '{data}' (use AAAA-MM-DD).")
        try:
            horas = float(horas)
        except (TypeError, ValueError):
            raise ErroMaoDeObra(f"Horas inválidas na mudança de jornada de {data}.")
        if not 0 < horas <= 80:
            raise ErroMaoDeObra(f"Horas por semana inválidas na mudança de jornada de {data}.")
        mudancas.append({"a_partir_de": data, "horas_semana": horas})
    p["mudancas_jornada"] = sorted(mudancas, key=lambda m: m["a_partir_de"])
    banco.salvar_parametros(obra_id, p)


def definir_execucao(banco: Banco, obra_id: int, codigos: Iterable[str], execucao: str,
                     biblioteca: Biblioteca | None = None) -> None:
    if execucao not in EXECUCOES:
        raise ErroMaoDeObra("Execução deve ser 'propria' ou 'terceirizada'.")
    atividades = atividades_da_obra(banco, obra_id, biblioteca)
    for c in codigos:
        if c not in atividades or atividades[c]["tipo"] == INDIRETA:
            raise ErroMaoDeObra(f"Atividade {c} não está na sequência desta obra.")
        banco.atualizar_execucao(obra_id, c, execucao=execucao)


_NADA = object()
MAQUINAS_MAX = 20


def definir_atividade(banco: Banco, obra_id: int, codigo: str, rendimento: Any = _NADA, equipe_padrao: Any = _NADA,
                      duracao_manual: Any = _NADA, biblioteca: Biblioteca | None = None,
                      maquinas: dict[str, Any] | None = None) -> None:
    """Rendimento específico, equipe padrão, duração manual (None limpa) e máquinas por equipamento da atividade."""
    atividades = atividades_da_obra(banco, obra_id, biblioteca)
    if codigo not in atividades or atividades[codigo]["tipo"] == INDIRETA:
        raise ErroMaoDeObra(f"Atividade {codigo} não está na sequência desta obra.")
    campos: dict[str, Any] = {}
    if rendimento is not _NADA:
        if rendimento in (None, ""):
            campos["rendimento"] = None
        else:
            r = float(rendimento)
            r = r / 100 if r > 1.5 else r
            if not 0.3 <= r <= 1.5:
                raise ErroMaoDeObra("Rendimento deve estar entre 30% e 150%.")
            campos["rendimento"] = r
    if equipe_padrao is not _NADA:
        if equipe_padrao in (None, ""):
            campos["equipe_padrao"] = None
        else:
            e = int(equipe_padrao)
            maximo = atividades[codigo]["equipe_max"]
            if not 1 <= e <= maximo:
                raise ErroMaoDeObra(f"Equipe padrão de {codigo} deve estar entre 1 e {maximo} (equipe máxima).")
            campos["equipe_padrao"] = e
    if duracao_manual is not _NADA:
        if duracao_manual in (None, ""):
            campos["duracao_manual"] = None
        else:
            d = float(duracao_manual)
            if d <= 0 or d != int(d):
                raise ErroMaoDeObra("A duração deve ser um número inteiro de dias úteis, maior que zero.")
            campos["duracao_manual"] = int(d)
    quantidades: dict[str, int] = {}
    for equip, n in (maquinas or {}).items():
        try:
            v = float(n) if n not in (None, "") else 1.0
        except (TypeError, ValueError):
            raise ErroMaoDeObra(f"Quantidade de máquinas inválida para {equip}.")
        if v != int(v) or not 1 <= v <= MAQUINAS_MAX:
            raise ErroMaoDeObra(f"Quantidade de máquinas de {equip} deve ser um número inteiro entre 1 e {MAQUINAS_MAX}.")
        quantidades[str(equip)] = int(v)
    banco.atualizar_execucao(obra_id, codigo, **campos)
    if quantidades:
        banco.gravar_maquinas(obra_id, codigo, quantidades)


def _validar_horas(horas: dict[str, Any]) -> dict[str, float]:
    limpas = {}
    for f, h in (horas or {}).items():
        f = str(f).strip()
        if not f or h in (None, ""):
            continue
        try:
            v = float(str(h).replace(",", "."))
        except ValueError:
            raise ErroMaoDeObra(f"Horas inválidas para {f}.")
        if v < 0:
            raise ErroMaoDeObra(f"Horas negativas para {f}.")
        if v > 0:
            limpas[f] = v
    return limpas


def definir_horas_servico(banco: Banco, obra_id: int, servico_id: int, horas: dict[str, Any],
                          biblioteca: Biblioteca | None = None) -> dict[str, Any]:
    """Horas por unidade digitadas pelo usuário (substituem as outras origens e vão para o banco). Vazio = desfaz."""
    dados = _obra(banco, obra_id)
    servico = next((s for s in dados["servicos"] if s["id"] == int(servico_id)), None)
    if servico is None:
        raise ErroMaoDeObra("Serviço não encontrado nesta obra.")
    limpas = _validar_horas(horas)
    banco.gravar_horas_manuais(servico["id"], limpas)
    if limpas and servico.get("codigo"):
        banco.gravar_coeficientes(servico.get("base"), servico["codigo"], limpas, "manual", obra_id, servico.get("descricao"))
    return analisar_obra(banco, obra_id, biblioteca)


def definir_horas_subcomposicao(banco: Banco, obra_id: int, codigo: str, horas: dict[str, Any],
                                descricao: str | None = None, biblioteca: Biblioteca | None = None) -> dict[str, Any]:
    """Horas por unidade de uma subcomposição pendente: vão para o banco (manual) e a obra é recalculada."""
    if not chave_codigo(codigo):
        raise ErroMaoDeObra("Subcomposição sem código: digite as horas no serviço.")
    limpas = _validar_horas(horas)
    if not limpas:
        raise ErroMaoDeObra("Informe as horas de pelo menos uma função.")
    banco.gravar_coeficientes("", codigo, limpas, "manual", obra_id, descricao)
    return analisar_obra(banco, obra_id, biblioteca)
