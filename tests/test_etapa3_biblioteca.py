"""Etapa 3 — carga e validação da biblioteca de atividades (Excel)."""
import pytest

from atividades.biblioteca import (
    ErroBiblioteca,
    carregar_biblioteca,
    interpretar_dependencias,
    salvar_atividade_na_biblioteca,
    Dependencia,
)
from atividades.grafo import achar_ciclo, ordem_topologica
from conftest import copiar_biblioteca, linha_da_atividade


def test_biblioteca_padrao_carrega(biblioteca):
    assert len(biblioteca.atividades) == 80
    assert len(biblioteca.regras) == 89
    assert "TOTAL" not in biblioteca.atividades
    fun05 = biblioteca.atividades["FUN-05"]
    assert fun05.depende_de == [Dependencia("FUN-04", 3, "II", "du")]
    assert biblioteca.atividades["QUA-03"].depende_de[0] == Dependencia("QUA-02", 28)
    assert biblioteca.atividades["EST-03"].duracao_fixa_dias == 28
    assert biblioteca.atividades["FUN-04"].tipo_producao == "concretagem"
    assert biblioteca.atividades["PRE-01"].equipe_max == 20  # vazio = 20
    assert fun05.tipo == "rigida"
    assert biblioteca.atividades["IND-03"].periodo_de == "TER-01"
    assert biblioteca.atividades["IND-03"].periodo_ate == "FUN-04"
    ter = biblioteca.atividades["TER-01"].depende_de
    assert [d.codigo for d in ter] == ["PRE-03", "PRE-04"]


def test_biblioteca_sem_ciclo(biblioteca):
    grafo = {c: [d.codigo for d in a.depende_de] for c, a in biblioteca.atividades.items()}
    assert achar_ciclo(grafo) is None
    ordem = ordem_topologica(grafo)
    assert len(ordem) == 80
    assert ordem.index("TES-01") < ordem.index("LIM-01")


def test_regras_lidas(biblioteca):
    r = {x.ordem: x for x in biblioteca.regras}
    assert r[6].natureza == "tempo" and r[6].atividade == "IND-06"
    assert r[67].termos_no_grupo == ["^QUADRA"]
    assert r[3].termos_na_descricao == ["LOCACAO DE CONTAINER", "LOCACAO DE BANHEIRO"]
    assert r[11].termos_na_descricao == []


@pytest.mark.parametrize(
    "texto, esperado",
    [
        ("FUN-04+3d", [Dependencia("FUN-04", 3)]),
        ("PRE-03, PRE-04", [Dependencia("PRE-03"), Dependencia("PRE-04")]),
        ("SPDA-01", [Dependencia("SPDA-01")]),
        (" pis-01 + 7D ", [Dependencia("PIS-01", 7)]),
        ("FUN-02:II+3du", [Dependencia("FUN-02", 3, "II", "du")]),
        ("FUN-02:TI+2du, QUA-02+28d", [Dependencia("FUN-02", 2, "TI", "du"), Dependencia("QUA-02", 28, "TI", "d")]),
        ("fun-02:ii", [Dependencia("FUN-02", 0, "II")]),
        (None, []),
    ],
)
def test_interpretar_dependencias(texto, esperado):
    deps, erros = interpretar_dependencias(texto)
    assert erros == [] and deps == esperado


@pytest.mark.parametrize("texto", ["FUN04", "FUN-04+3", "FUN-04+3 dias", "FUN-04-3d", "FUN-4", "FUN-04:IF+2d", "FUN-04:II+2h"])
def test_dependencia_formato_invalido(texto):
    _, erros = interpretar_dependencias(texto)
    assert erros


def _erros(tmp_path, alterar):
    caminho = copiar_biblioteca(tmp_path / "bib.xlsx", alterar)
    with pytest.raises(ErroBiblioteca) as exc:
        carregar_biblioteca(caminho)
    return exc.value.erros


def test_ciclo_mostra_caminho(tmp_path):
    def alterar(wb):
        ws = wb["Atividades"]
        ws.cell(linha_da_atividade(ws, "PRE-01"), 4).value = "PRE-03"  # PRE-03 → PRE-02 → PRE-01 → PRE-03

    erros = _erros(tmp_path, alterar)
    ciclo = [e for e in erros if "Ciclo" in e["mensagem"]]
    assert len(ciclo) == 1
    msg = ciclo[0]["mensagem"]
    for cod in ("PRE-01", "PRE-02", "PRE-03"):
        assert cod in msg
    assert "→" in msg
    assert ciclo[0]["linha"] is not None


def test_dependencia_inexistente_com_linha(tmp_path):
    def alterar(wb):
        ws = wb["Atividades"]
        ws.cell(linha_da_atividade(ws, "FUN-02"), 4).value = "FUN-01, XYZ-99"

    erros = _erros(tmp_path, alterar)
    assert {"aba": "Atividades", "linha": 15, "mensagem": "FUN-02 depende de XYZ-99, que não existe."} in erros


def test_codigo_repetido(tmp_path):
    def alterar(wb):
        ws = wb["Atividades"]
        ws.cell(linha_da_atividade(ws, "FUN-02"), 1).value = "FUN-01"

    erros = _erros(tmp_path, alterar)
    assert any("FUN-01 repetido" in e["mensagem"] and e["linha"] == 15 for e in erros)


def test_formato_e_tipo_invalidos(tmp_path):
    def alterar(wb):
        ws = wb["Atividades"]
        ws.cell(linha_da_atividade(ws, "FUN-05"), 4).value = "FUN-04 + 3 dias"
        ws.cell(linha_da_atividade(ws, "FUN-03"), 5).value = "urgente"

    erros = _erros(tmp_path, alterar)
    assert any("formato inválido" in e["mensagem"] and e["linha"] == 18 for e in erros)
    assert any("tipo 'urgente' inválido" in e["mensagem"] and e["linha"] == 16 for e in erros)


def test_periodo_e_regra_com_codigo_inexistente(tmp_path):
    def alterar(wb):
        ws = wb["Atividades"]
        ws.cell(linha_da_atividade(ws, "IND-03"), 8).value = "TER-99"
        wb["Regras"]["C2"].value = "IND-99"

    erros = _erros(tmp_path, alterar)
    assert any("periodo_de 'TER-99'" in e["mensagem"] and e["linha"] == 4 for e in erros)
    assert any(e["aba"] == "Regras" and e["linha"] == 2 and "IND-99" in e["mensagem"] for e in erros)


def test_arquivo_inexistente(tmp_path):
    with pytest.raises(ErroBiblioteca):
        carregar_biblioteca(tmp_path / "nao_existe.xlsx")


def test_salvar_na_biblioteca_com_backup(tmp_path):
    caminho = copiar_biblioteca(tmp_path / "bib.xlsx")
    backup = salvar_atividade_na_biblioteca("FUN-05", "flexivel", [Dependencia("FUN-04", 5)], caminho)
    assert backup.exists() and backup.parent.name == "backup"
    assert carregar_biblioteca(backup).atividades["FUN-05"].tipo == "rigida"  # cópia é a versão anterior
    nova = carregar_biblioteca(caminho)
    assert nova.atividades["FUN-05"].tipo == "flexivel"
    assert nova.atividades["FUN-05"].depende_de == [Dependencia("FUN-04", 5)]
    assert len(nova.atividades) == 80 and len(nova.regras) == 89


def test_salvar_na_biblioteca_recusa_ciclo(tmp_path):
    caminho = copiar_biblioteca(tmp_path / "bib.xlsx")
    with pytest.raises(ErroBiblioteca) as exc:
        salvar_atividade_na_biblioteca("LOC-01", "rigida", [Dependencia("FUN-02")], caminho)
    assert "Ciclo" in str(exc.value)
    assert carregar_biblioteca(caminho).atividades["LOC-01"].depende_de == [Dependencia("TER-01", 10, "II", "du")]
    assert not (tmp_path / "backup").exists()
