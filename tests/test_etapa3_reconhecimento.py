"""Etapa 3 — reconhecimento automático dos serviços."""
from collections import Counter

import pytest

from atividades import carregar_biblioteca, ligar_servicos, resumo_ligacao
from atividades.reconhecimento import chave_memoria, grupos_do_item
from conftest import copiar_biblioteca


@pytest.fixture(scope="module")
def por_item(servicos_ligados):
    return {s["item"]: s for s in servicos_ligados}


def test_374_automaticos_sem_pendencias(servicos_ligados):
    r = resumo_ligacao(servicos_ligados)
    assert r["total"] == 374
    assert r["por_status"]["automatico"] == 374
    assert r["por_status"]["ambiguo"] == 0
    assert r["por_status"]["sem_regra"] == 0
    assert r["texto"] == "374 serviços — 374 ligados automaticamente, 0 pendentes"


def test_bate_com_mapeamento_esperado(servicos_ligados, mapeamento_esperado):
    assert len(mapeamento_esperado) == 374
    por_linha = {s["linha_excel"]: s for s in servicos_ligados}
    diferencas = []
    for e in mapeamento_esperado:
        s = por_linha[int(e["linha"])]
        obtido = (s["item"], s["atividade_biblioteca"], s["regra_usada"])
        esperado = (e["item"], e["atividade"], int(e["regra"]))
        if obtido != esperado:
            diferencas.append((e["linha"], esperado, obtido))
    assert diferencas == []


@pytest.mark.parametrize(
    "item, atividade",
    [
        ("4.10", "FUN-03"),
        ("6.4", "CON-01"),
        ("15.2.3", "QUA-01"),
        ("5.1.2", "EST-01"),
        ("5.1.11", "IND-06"),
        ("9.1.8.1", "ELE-08"),
        ("13.14", "SER-03"),
        ("9.3.1.1", "SPDA-01"),
    ],
)
def test_casos_de_contexto(por_item, item, atividade):
    assert por_item[item]["atividade_biblioteca"] == atividade


def test_mesmo_servico_em_grupos_diferentes(por_item):
    lastros = [por_item[i] for i in ("4.10", "6.4", "15.2.3")]
    assert {s["codigo"] for s in lastros} == {"96616"}
    assert [s["atividade_biblioteca"] for s in lastros] == ["FUN-03", "CON-01", "QUA-01"]


def test_escoramento_exige_natureza_tempo(por_item):
    assert por_item["5.1.2"]["natureza"] != "tempo"
    assert "ESCORAMENTO" in por_item["5.1.2"]["descricao"]
    assert por_item["5.1.11"]["natureza"] == "tempo"
    assert por_item["5.1.11"]["regra_usada"] == 6


def test_grupos_do_item(resultado, por_item):
    nomes = grupos_do_item(por_item["9.1.6.3"]["item_grupo"], resultado["grupos"])
    assert len(nomes) == 3
    assert nomes[0].startswith("INSTALAÇÕES ELÉTRICAS, TELECOMUNICAÇÕES E SPDA")
    assert nomes[2].startswith("ELETRODUTOS E ACESSÓRIOS")
    assert por_item["9.1.6.3"]["grupo_imediato"] == nomes[2]


def test_total_por_atividade_fecha(servicos_ligados, mapeamento_esperado):
    soma = Counter()
    for s in servicos_ligados:
        soma[s["atividade_biblioteca"]] += s["total_bdi"]
    assert round(sum(soma.values()), 2) == 5669771.17
    esperado = Counter()
    for e in mapeamento_esperado:
        esperado[e["atividade"]] += float(e["total_bdi"])
    assert {k: round(v, 2) for k, v in soma.items()} == {k: round(v, 2) for k, v in esperado.items()}
    assert len(soma) == 77


def test_memoria_vem_antes_das_regras(resultado, biblioteca, por_item):
    s = por_item["4.10"]
    memoria = {chave_memoria(s["base"], s["codigo"], s["grupo_imediato"]): "FUN-04"}
    ligs = ligar_servicos(resultado["servicos"], resultado["grupos"], biblioteca, memoria)
    por = {x["item"]: l for x, l in zip(resultado["servicos"], ligs)}
    assert por["4.10"]["atividade_biblioteca"] == "FUN-04" and por["4.10"]["status_ligacao"] == "memoria"
    assert por["6.4"]["atividade_biblioteca"] == "CON-01" and por["6.4"]["status_ligacao"] == "automatico"


def test_confirmado_e_mantido(resultado, biblioteca):
    servicos = [dict(s) for s in resultado["servicos"]]
    alvo = next(s for s in servicos if s["item"] == "4.10")
    alvo.update(atividade_biblioteca="EST-01", status_ligacao="confirmado")
    ligs = ligar_servicos(servicos, resultado["grupos"], biblioteca)
    l = ligs[servicos.index(alvo)]
    assert (l["atividade_biblioteca"], l["status_ligacao"]) == ("EST-01", "confirmado")


def test_regras_empatadas_dao_ambiguo(tmp_path, resultado):
    """Duas regras de mesma prioridade, mesma profundidade e atividades diferentes."""
    def alterar(wb):
        ws = wb["Regras"]
        ws.append([90, 1, "FUN-04", "FUNDACAO", "LASTRO DE CONCRETO MAGRO", None])
        ws.append([91, 1, "FUN-03", "FUNDACAO", "LASTRO DE CONCRETO MAGRO", None])

    bib = carregar_biblioteca(copiar_biblioteca(tmp_path / "bib.xlsx", alterar))
    ligs = ligar_servicos(resultado["servicos"], resultado["grupos"], bib)
    por = {x["item"]: l for x, l in zip(resultado["servicos"], ligs)}
    assert por["4.10"]["status_ligacao"] == "ambiguo"
    assert por["4.10"]["atividade_biblioteca"] is None
    assert por["4.10"]["candidatas"] == ["FUN-04", "FUN-03"]
    assert por["6.4"]["status_ligacao"] == "automatico"  # Contenção não é afetada
    assert resumo_ligacao(ligs)["pendentes"] == 1


def test_sem_regra(tmp_path, resultado):
    def alterar(wb):
        ws = wb["Regras"]
        for linha in range(2, ws.max_row + 1):
            if ws.cell(linha, 3).value == "LIM-01":
                ws.delete_rows(linha)
                break

    bib = carregar_biblioteca(copiar_biblioteca(tmp_path / "bib.xlsx", alterar))
    ligs = ligar_servicos(resultado["servicos"], resultado["grupos"], bib)
    por = {x["item"]: l for x, l in zip(resultado["servicos"], ligs)}
    assert por["23.1"]["status_ligacao"] == "sem_regra"
    assert por["23.1"]["candidatas"] == []


def test_mesma_prioridade_subgrupo_vence_grupo(tmp_path, resultado):
    """Empate de prioridade: a regra que casa num grupo mais profundo vence."""
    def alterar(wb):
        ws = wb["Regras"]
        ws.append([90, 1, "TEL-01", "INSTALACOES ELETRICAS, TELECOM", "CABO DE COBRE", None])  # profundidade 1
        ws.append([91, 1, "ELE-04", "CONDUTORES ISOLACAO", "CABO DE COBRE", None])              # profundidade 3

    bib = carregar_biblioteca(copiar_biblioteca(tmp_path / "bib.xlsx", alterar))
    ligs = ligar_servicos(resultado["servicos"], resultado["grupos"], bib)
    por = {x["item"]: l for x, l in zip(resultado["servicos"], ligs)}
    assert por["9.1.1.1"]["atividade_biblioteca"] == "ELE-04"
    assert por["9.1.1.1"]["regra_usada"] == 91
