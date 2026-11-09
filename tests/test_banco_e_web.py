"""Gravação no SQLite e fluxo completo pela interface web (Flask)."""
import io
import sqlite3

import pytest

from armazenamento import Banco
from web.app import criar_app


def test_salvar_e_carregar(tmp_path, resultado):
    banco = Banco(str(tmp_path / "teste.sqlite3"))
    obra_id = banco.salvar_importacao(resultado)
    dados = banco.carregar_obra(obra_id)

    assert dados["obra"]["prazo_valor"] == 12
    assert dados["obra"]["bdi"] == pytest.approx(0.2522)
    assert dados["obra"]["referencias"][0] == "SINAPI OUTUBRO/2023"
    assert dados["obra"]["arquivo"] == "Concorrencia_2_2024_PLANILHA_ORCAMENTARIA_EDITAVEL.XLSX"
    assert len(dados["servicos"]) == 374
    assert len(dados["grupos"]) == len(resultado["grupos"])

    s = {x["item"]: x for x in dados["servicos"]}
    assert s["4.10"]["item"] == "4.10" and s["4.2"]["item_grupo"] == "4"
    assert s["1.1.1"]["natureza"] == "taxa"
    assert set(("atividade_biblioteca", "etapa_obra", "local")) <= set(s["1.1.1"])
    assert round(sum(x["total"] for x in dados["servicos"]), 2) == 4527898.72

    assert banco.listar_obras()[0]["qtd_servicos"] == 374
    banco.excluir_obra(obra_id)
    assert banco.carregar_obra(obra_id) is None
    con = sqlite3.connect(tmp_path / "teste.sqlite3")
    assert con.execute("SELECT COUNT(*) FROM servicos").fetchone()[0] == 0


def test_prazo_obrigatorio_no_banco(tmp_path, resultado):
    import copy

    sem_prazo = copy.deepcopy(resultado)
    sem_prazo["obra"]["prazo_valor"] = None
    with pytest.raises(ValueError):
        Banco(str(tmp_path / "b.sqlite3")).salvar_importacao(sem_prazo)


@pytest.fixture()
def cliente(tmp_path):
    app = criar_app(str(tmp_path / "web.sqlite3"), str(tmp_path / "uploads"))
    app.testing = True
    return app.test_client()


def _enviar(cliente, arquivo_teste):
    with open(arquivo_teste, "rb") as f:
        conteudo = f.read()
    return cliente.post(
        "/api/leitura",
        data={"arquivo": (io.BytesIO(conteudo), arquivo_teste.name)},
        content_type="multipart/form-data",
    )


def test_pagina_inicial(cliente):
    r = cliente.get("/")
    assert r.status_code == 200 and b"Leitura da Planilha" in r.data
    assert cliente.get("/static/app.js").status_code == 200


def test_fluxo_completo(cliente, arquivo_teste):
    r = _enviar(cliente, arquivo_teste)
    assert r.status_code == 200
    dados = r.get_json()
    assert dados["aba"] == "PLANILHA" and len(dados["servicos"]) == 374
    token = dados["token"]

    # troca de aba e volta
    r = cliente.post(f"/api/leitura/{token}", json={"aba": "CRONOGRAMA"})
    assert r.status_code == 200 and r.get_json()["servicos"] == []
    r = cliente.post(f"/api/leitura/{token}", json={"aba": "PLANILHA"})
    assert len(r.get_json()["servicos"]) == 374

    # confirmação com edição do prazo e da natureza de um serviço
    linha_container = next(s["linha_excel"] for s in dados["servicos"] if s["item"] == "1.2.2")
    r = cliente.post(
        "/api/importacoes",
        json={
            "token": token,
            "obra": {"nome": "Obra editada", "prazo_valor": 360, "prazo_unidade": "dias", "bdi": 0.25},
            "naturezas": {str(linha_container): "taxa"},
        },
    )
    assert r.status_code == 200, r.get_json()
    obra_id = r.get_json()["id"]

    salvo = cliente.get(f"/api/importacoes/{obra_id}").get_json()
    assert salvo["obra"]["nome"] == "Obra editada"
    assert salvo["obra"]["prazo_valor"] == 360 and salvo["obra"]["prazo_unidade"] == "dias"
    assert salvo["obra"]["bdi"] == 0.25
    assert next(s for s in salvo["servicos"] if s["item"] == "1.2.2")["natureza"] == "taxa"
    assert cliente.get("/api/importacoes").get_json()[0]["id"] == obra_id


def test_confirmar_sem_prazo_recusa(cliente, arquivo_teste):
    token = _enviar(cliente, arquivo_teste).get_json()["token"]
    r = cliente.post("/api/importacoes", json={"token": token, "obra": {"prazo_valor": ""}})
    assert r.status_code == 400 and "prazo" in r.get_json()["erro"].lower()


def test_natureza_invalida_recusa(cliente, arquivo_teste):
    token = _enviar(cliente, arquivo_teste).get_json()["token"]
    r = cliente.post("/api/importacoes", json={"token": token, "naturezas": {"15": "xyz"}})
    assert r.status_code == 400


def test_envio_invalido(cliente):
    r = cliente.post("/api/leitura", data={}, content_type="multipart/form-data")
    assert r.status_code == 400
    r = cliente.post(
        "/api/leitura", data={"arquivo": (io.BytesIO(b"x"), "planilha.pdf")}, content_type="multipart/form-data"
    )
    assert r.status_code == 400
