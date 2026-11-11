"""Etapa 3 — rede de atividades da obra."""
import pytest

from atividades.biblioteca import Dependencia
from atividades.grafo import achar_ciclo
from atividades.rede import (
    ErroRede,
    dependencias_de,
    editar_atividade,
    indiretas,
    montar_rede,
    sequencia,
)


@pytest.fixture(scope="module")
def rede(biblioteca, servicos_ligados):
    return montar_rede(biblioteca, servicos_ligados)


def _grafo(rede):
    g = {c: [] for c, a in rede["atividades"].items() if a["tipo"] != "indireta"}
    for d in rede["dependencias"]:
        g[d["atividade"]].append(d["depende_de"])
    return g


def test_80_atividades_na_obra(rede, biblioteca):
    assert len(rede["atividades"]) == 80
    assert set(rede["atividades"]) == set(biblioteca.atividades)
    com_itens = [a for a in rede["atividades"].values() if a["n_itens"] > 0]
    assert len(com_itens) == 77
    sem_custo = {c for c, a in rede["atividades"].items() if a["n_itens"] == 0}
    assert sem_custo == {"EST-03", "HID-03", "TES-01"}


def test_totais_da_rede(rede):
    ativs = rede["atividades"].values()
    assert round(sum(a["total_bdi"] for a in ativs), 2) == 5669771.17
    assert round(sum(a["total"] for a in ativs), 2) == 4527898.72
    assert sum(a["n_itens"] for a in ativs) == 374
    assert rede["atividades"]["FUN-03"]["n_itens"] == 9


def test_sem_ciclo_e_lim01_por_ultimo(rede):
    assert achar_ciclo(_grafo(rede)) is None
    seq = sequencia(rede)
    assert seq[-1]["codigo"] == "LIM-01"
    assert seq[0]["codigo"] == "PRE-01"
    assert len(seq) == 74  # 80 - 6 indiretas
    posicao = {a["codigo"]: a["posicao"] for a in seq}
    for d in rede["dependencias"]:
        assert posicao[d["depende_de"]] < posicao[d["atividade"]]


def test_indiretas_fora_da_sequencia(rede):
    ind = {a["codigo"]: a for a in indiretas(rede)}
    assert set(ind) == {"IND-01", "IND-02", "IND-03", "IND-04", "IND-05", "IND-06"}
    assert (ind["IND-03"]["periodo_de"], ind["IND-03"]["periodo_ate"]) == ("TER-01", "FUN-04")
    assert (ind["IND-01"]["periodo_de"], ind["IND-01"]["periodo_ate"]) == ("INICIO_OBRA", "FIM_OBRA")
    assert not any(d["atividade"].startswith("IND") or d["depende_de"].startswith("IND") for d in rede["dependencias"])


def test_toda_atividade_tem_sucessor_ou_liga_ao_fim(rede):
    g = _grafo(rede)
    com_sucessor = {d for deps in g.values() for d in deps}
    assert set(g) - com_sucessor == {"LIM-01"}
    fim = {d["depende_de"] for d in rede["dependencias"] if d["origem"] == "fim"}
    assert "SER-03" in fim and "QUA-04" in fim and "TES-01" not in fim
    assert all(d["atividade"] == "LIM-01" for d in rede["dependencias"] if d["origem"] == "fim")


def test_dependencias_da_biblioteca_com_espera(rede):
    assert dependencias_de(rede, "FUN-05") == [Dependencia("FUN-04", 3, "II", "d")]
    assert set(map(str, dependencias_de(rede, "QUA-03"))) == {"QUA-02+28d", "COB-02"}
    assert set(map(str, dependencias_de(rede, "PIN-01"))) == {"REV-02:II+20du", "REV-03"}
    # só a REV-01 espera a cura (EST-03); o resto segue em paralelo
    assert {d["atividade"] for d in rede["dependencias"] if d["depende_de"] == "EST-03"} == {"REV-01"}


def test_remocao_com_heranca_fun01(biblioteca, servicos_ligados):
    servicos = [s for s in servicos_ligados if s["atividade_biblioteca"] != "FUN-01"]
    r = montar_rede(biblioteca, servicos)
    assert "FUN-01" not in r["atividades"]
    assert dependencias_de(r, "FUN-02") == [Dependencia("LOC-01", 4, "II", "du")]  # II+2du + II+2du
    origem = {d["origem"] for d in r["dependencias"] if d["atividade"] == "FUN-02"}
    assert origem == {"herdada"}
    assert len(r["atividades"]) == 79


def test_espera_herdada_fun04(biblioteca, servicos_ligados):
    servicos = [s for s in servicos_ligados if s["atividade_biblioteca"] != "FUN-04"]
    r = montar_rede(biblioteca, servicos)
    assert "FUN-04" not in r["atividades"]
    assert dependencias_de(r, "FUN-05") == [Dependencia("FUN-03", 8, "II", "du")]
    assert dependencias_de(r, "EST-01") == [Dependencia("FUN-03", 10, "II", "du")]
    assert achar_ciclo(_grafo(r)) is None


def test_espera_soma_em_cadeia(biblioteca, servicos_ligados):
    """B depende de A+x e A (sai) depende de C+y → B depende de C+(x+y)."""
    tirar = {"REV-02"}  # REV-02 depende de REV-01:II+3du; REV-03 depende de REV-02:II+10du
    r = montar_rede(biblioteca, [s for s in servicos_ligados if s["atividade_biblioteca"] not in tirar])
    assert Dependencia("REV-01", 13, "II", "du") in dependencias_de(r, "REV-03")


def test_sem_custo_so_entra_com_dependencias(biblioteca, servicos_ligados):
    servicos = [s for s in servicos_ligados if s["atividade_biblioteca"] != "HID-02"]
    r = montar_rede(biblioteca, servicos)
    assert "HID-02" not in r["atividades"] and "HID-03" not in r["atividades"]
    assert "TES-01" in r["atividades"] and "EST-03" in r["atividades"]
    # REV-01 dependia de HID-02:II+5du, que dependia de ALV-02:II+5du → ALV-02:II+10du
    assert Dependencia("ALV-02", 10, "II", "du") in dependencias_de(r, "REV-01")
    # REV-02 dependia de HID-03 (TI) → HID-02 (TI) → ALV-02:II+5du; o elo de quem fica é TI
    assert Dependencia("ALV-02", 5, "TI", "du") in dependencias_de(r, "REV-02")


def test_tes01_entra_sempre(biblioteca, servicos_ligados):
    servicos = [s for s in servicos_ligados if not s["atividade_biblioteca"].startswith(("ELE", "HID"))]
    r = montar_rede(biblioteca, servicos)
    assert "TES-01" in r["atividades"]
    assert sequencia(r)[-1]["codigo"] == "LIM-01"


def test_editar_tipo_e_dependencias_so_na_obra(rede, biblioteca):
    nova = editar_atividade(rede, "SER-03", tipo="rigida", depende_de="PEX-02, URB-01+2d")
    assert nova["atividades"]["SER-03"]["tipo"] == "rigida"
    assert nova["atividades"]["SER-03"]["editada"] is True
    assert set(map(str, dependencias_de(nova, "SER-03"))) == {"PEX-02", "URB-01+2d"}
    # a rede original e a biblioteca não mudam
    assert rede["atividades"]["SER-03"]["tipo"] == "flexivel"
    assert dependencias_de(rede, "SER-03") == [Dependencia("LOC-01")]
    assert biblioteca.atividades["SER-03"].tipo == "flexivel"
    assert sequencia(nova)[-1]["codigo"] == "LIM-01"


def test_remover_dependencia_refaz_ligacao_ao_fim(rede):
    # SIN-01 só é pré-requisito da LIM-01 ("fim"). Se ESQ-01 passar a depender dela,
    # SIN-01 ganha sucessor e sai da lista do fim.
    assert any(d["depende_de"] == "SIN-01" and d["origem"] == "fim" for d in rede["dependencias"])
    nova = editar_atividade(rede, "ESQ-01", depende_de="PIS-02, SIN-01")
    assert not any(d["depende_de"] == "SIN-01" and d["origem"] == "fim" for d in nova["dependencias"])
    # tirando todas as dependências de EXA-01, PIN-01 continua com sucessor (PIN-02): não vai para o fim
    nova = editar_atividade(rede, "EXA-01", depende_de="")
    assert dependencias_de(nova, "EXA-01") == []
    assert not any(d["depende_de"] == "PIN-01" and d["origem"] == "fim" for d in nova["dependencias"])


def test_editar_recusa_ciclo(rede):
    with pytest.raises(ErroRede) as exc:
        editar_atividade(rede, "LOC-01", depende_de="FUN-02")
    assert "Ciclo" in str(exc.value) and "LOC-01" in str(exc.value) and "FUN-02" in str(exc.value)


@pytest.mark.parametrize(
    "codigo, kwargs",
    [
        ("XYZ-01", {"tipo": "rigida"}),
        ("FUN-02", {"tipo": "urgente"}),
        ("FUN-02", {"tipo": "indireta"}),
        ("FUN-02", {"depende_de": "FUN-02"}),
        ("FUN-02", {"depende_de": "ZZZ-01"}),
        ("FUN-02", {"depende_de": "IND-01"}),
        ("FUN-02", {"depende_de": "FUN 01"}),
    ],
)
def test_editar_recusa_invalidos(rede, codigo, kwargs):
    with pytest.raises(ErroRede):
        editar_atividade(rede, codigo, **kwargs)


def test_heranca_tira_fun03(biblioteca, servicos_ligados):
    """Tirar a FUN-03: FUN-04 (FUN-03:II+5du) herda FUN-02:II+3du → FUN-02:II+8du."""
    r = montar_rede(biblioteca, [s for s in servicos_ligados if s["atividade_biblioteca"] != "FUN-03"])
    assert dependencias_de(r, "FUN-04") == [Dependencia("FUN-02", 8, "II", "du")]
    assert str(dependencias_de(r, "FUN-04")[0]) == "FUN-02:II+8du"


def test_heranca_converte_unidades():
    from atividades.biblioteca import Dependencia as D
    from atividades.rede import somar_elos

    assert somar_elos(D("A", 3, "II", "du"), D("C", 7, "TI", "d"), "C") == D("C", 8, "II", "du")  # 7d → 5du
    assert somar_elos(D("A", 3), D("C", 4), "C") == D("C", 7)
    assert somar_elos(D("A", 0), D("C", 2, "II", "du"), "C") == D("C", 2, "TI", "du")
