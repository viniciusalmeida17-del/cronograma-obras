"""Gerenciar importações: etapa atual, etapas que podem ser abertas, leitura salva, edição e exclusão de obras."""
from __future__ import annotations

import sqlite3

import pytest

from armazenamento import Banco
from atividades import obra as etapa3
from conftest import preparar_obra
from cronograma import obra as etapa5
from leitor_planilha import ler_planilha
from mao_de_obra import obra as etapa4
from test_etapa5_obra import INICIO, resolver_pendencias
from web import obras as gestao
from web.app import criar_app

# tabelas que pertencem à obra (apagadas junto) e as que são do app (ficam)
TABELAS_DA_OBRA = {
    "grupos": "obra_id", "servicos": "obra_id", "obra_atividades": "obra_id", "obra_dependencias": "obra_id",
    "obra_parametros": "obra_id", "atividade_execucao": "obra_id", "atividade_equipamento": "obra_id",
    "atividade_resumo": "obra_id", "obra_calendario": "obra_id", "cenarios": "obra_id",
}
TABELAS_DO_SERVICO = ("servico_mao_de_obra", "servico_equipamento", "servico_equipe_indireta",
                      "subcomposicoes_pendentes", "servico_custo_mao_de_obra")
TABELAS_DO_CENARIO = ("cenario_atividades", "cenario_equipe_semana")


def _atual(banco, obra):
    return gestao.etapas(banco, obra)["atual"]


def _contar(banco, obra):
    con = sqlite3.connect(banco.caminho)
    try:
        n = {t: con.execute(f"SELECT COUNT(*) FROM {t} WHERE {c} = ?", (obra,)).fetchone()[0]
             for t, c in TABELAS_DA_OBRA.items()}
        n["obras"] = con.execute("SELECT COUNT(*) FROM obras WHERE id = ?", (obra,)).fetchone()[0]
        for t in TABELAS_DO_SERVICO:
            n[t] = con.execute(f"SELECT COUNT(*) FROM {t} WHERE servico_id NOT IN (SELECT id FROM servicos)").fetchone()[0]
        for t in TABELAS_DO_CENARIO:
            n[t] = con.execute(f"SELECT COUNT(*) FROM {t} WHERE cenario_id NOT IN (SELECT id FROM cenarios)").fetchone()[0]
        return n
    finally:
        con.close()


@pytest.fixture(scope="module")
def obra_completa(tmp_path_factory, arquivo_teste, biblioteca):
    """Uma obra que passa por todas as etapas (vendo a etapa atual mudar) e uma segunda só importada."""
    banco = Banco(str(tmp_path_factory.mktemp("gestao") / "obras.sqlite3"))
    passos = []
    obra = banco.salvar_importacao(ler_planilha(arquivo_teste))
    banco.guardar_arquivo(obra, arquivo_teste)
    passos.append(_atual(banco, obra))
    etapa3.ligar_obra(banco, obra, biblioteca)
    passos.append(_atual(banco, obra))
    etapa3.montar_rede_obra(banco, obra, biblioteca)
    passos.append(_atual(banco, obra))
    etapa4.analisar_obra(banco, obra, biblioteca)
    resolver_pendencias(banco, obra, biblioteca)
    passos.append(_atual(banco, obra))
    etapa5.salvar_parametros_cronograma(banco, obra, {"data_inicio": INICIO})
    etapa5.calcular_cenarios(banco, obra, [12], biblioteca, tempo_limite=5)
    passos.append(_atual(banco, obra))
    cid = banco.listar_cenarios(obra)[0]["id"]
    etapa5.escolher_cenario(banco, obra, cid)
    passos.append(_atual(banco, obra))
    so_lida = banco.salvar_importacao(ler_planilha(arquivo_teste))
    return banco, obra, so_lida, passos


# ------------------------------------------------------------------ etapa atual e etapas que podem ser abertas


def test_etapa_atual_acompanha_a_obra(obra_completa):
    _, _, _, passos = obra_completa
    assert passos == ["leitura", "ligacao", "sequencia", "mao_de_obra", "cronograma", "escolhido"]


def test_lista_tem_etapa_atual_e_botoes(obra_completa):
    banco, obra, so_lida, _ = obra_completa
    lista = {o["id"]: o for o in gestao.listar(banco)}
    assert lista[obra]["atual_rotulo"] == "Cenário escolhido"
    assert all(e["ativa"] for e in lista[obra]["etapas"])
    assert lista[so_lida]["atual_rotulo"] == "Leitura"
    etapas = {e["chave"]: e for e in lista[so_lida]["etapas"]}
    assert [e["chave"] for e in lista[so_lida]["etapas"]] == ["leitura", "ligacao", "sequencia", "mao_de_obra", "cronograma"]
    assert etapas["leitura"]["ativa"] and etapas["ligacao"]["ativa"]
    for chave in ("sequencia", "mao_de_obra", "cronograma"):
        assert not etapas[chave]["ativa"] and "sequência primeiro" in etapas[chave]["motivo"]
    assert etapas["mao_de_obra"]["url"] == "/mao-de-obra"


@pytest.mark.parametrize("situacao, atual, desativadas", [
    ({}, "Leitura", {"sequencia", "mao_de_obra", "cronograma"}),
    ({"tem_ligacao": True}, "Ligação", {"sequencia", "mao_de_obra", "cronograma"}),
    ({"tem_ligacao": True, "tem_rede": True}, "Sequência", {"cronograma"}),
    ({"tem_ligacao": True, "tem_rede": True, "tem_mao_de_obra": True}, "Mão de obra", set()),
    ({"tem_ligacao": True, "tem_rede": True, "tem_mao_de_obra": True, "tem_cenarios": True}, "Cronograma calculado", set()),
    ({"tem_ligacao": True, "tem_rede": True, "tem_mao_de_obra": True, "tem_cenarios": True, "tem_escolhido": True},
     "Cenário escolhido", set()),
])
def test_regras_das_etapas(situacao, atual, desativadas):
    base = {"tem_ligacao": False, "tem_rede": False, "tem_mao_de_obra": False, "tem_cenarios": False, "tem_escolhido": False}
    r = gestao.etapas_da_obra({**base, **situacao})
    assert r["atual_rotulo"] == atual
    assert {e["chave"] for e in r["etapas"] if not e["ativa"]} == desativadas
    for e in r["etapas"]:
        assert (e["motivo"] is None) == e["ativa"]
    if situacao.get("tem_rede") and not situacao.get("tem_mao_de_obra"):
        assert next(e for e in r["etapas"] if e["chave"] == "cronograma")["motivo"] == "Calcule a mão de obra primeiro."


# ------------------------------------------------------------------ leitura salva e edição


def test_leitura_salva_sem_reenviar_a_planilha(obra_completa, arquivo_teste):
    banco, obra, _, _ = obra_completa
    d = gestao.leitura_salva(banco, obra)
    lida = ler_planilha(arquivo_teste)
    assert d["salva"] and d["obra_id"] == obra
    assert len(d["servicos"]) == len(lida["servicos"]) and len(d["grupos"]) == len(lida["grupos"])
    assert d["validacao"]["soma_servicos"] == pytest.approx(lida["validacao"]["soma_servicos"])
    assert d["validacao"]["ok"] == lida["validacao"]["ok"]
    por_item = {g["item"]: g for g in d["grupos"]}
    lidos = {g["item"]: g for g in lida["grupos"]}
    assert all(por_item[i]["nivel"] == lidos[i]["nivel"] and por_item[i]["qtd_servicos"] == lidos[i]["qtd_servicos"]
               for i in lidos)
    s = d["servicos"][0]
    assert s["caminho_grupos"] and "divergencia" in s and s["natureza_automatica"] == s["natureza"]


def test_editar_nome_prazo_e_bdi(tmp_path, arquivo_teste):
    banco = Banco(str(tmp_path / "b.sqlite3"))
    obra = banco.salvar_importacao(ler_planilha(arquivo_teste))
    d = gestao.editar_obra(banco, obra, {"nome": "  Ginásio Teste ", "prazo_valor": "10", "prazo_unidade": "meses",
                                         "bdi": 0.2, "referencias": ["SINAPI 01/2025", " "], "arquivo": "ignorado"})
    o = banco.carregar_obra(obra)["obra"]
    assert (o["nome"], o["prazo_valor"], o["prazo_unidade"], o["bdi"]) == ("Ginásio Teste", 10.0, "meses", 0.2)
    assert o["referencias"] == ["SINAPI 01/2025"] and o["arquivo"] != "ignorado"
    assert d["obra"]["nome"] == "Ginásio Teste"
    for errado in ({"prazo_valor": 0}, {"prazo_valor": "x"}, {"prazo_unidade": "quinzenas"}, {"bdi": 25}):
        with pytest.raises(gestao.ErroObras):
            gestao.editar_obra(banco, obra, errado)
    with pytest.raises(gestao.ErroObras):
        gestao.editar_obra(banco, 999, {"nome": "x"})


# ------------------------------------------------------------------ exclusão


@pytest.fixture
def banco_com_duas_obras(tmp_path, arquivo_teste, biblioteca):
    banco = Banco(str(tmp_path / "b.sqlite3"))
    a = preparar_obra(banco, arquivo_teste, biblioteca)
    # o usuário confirma as ligações da obra a: elas vão para a memória
    por_atividade: dict[str, list[int]] = {}
    for s in banco.carregar_obra(a)["servicos"]:
        if s["atividade_biblioteca"]:
            por_atividade.setdefault(s["atividade_biblioteca"], []).append(s["id"])
    for atividade, ids in por_atividade.items():
        etapa3.confirmar_ligacao(banco, a, ids, atividade, biblioteca)
    etapa4.analisar_obra(banco, a, biblioteca)
    b = preparar_obra(banco, arquivo_teste, biblioteca)
    return banco, a, b


def test_excluir_apaga_tudo_da_obra_e_o_arquivo(banco_com_duas_obras):
    banco, a, b = banco_com_duas_obras
    arquivo = banco.arquivo_da_obra(a)
    assert arquivo.exists()
    antes = _contar(banco, a)
    assert antes["servicos"] and antes["obra_atividades"] and antes["atividade_resumo"]
    memoria = banco.carregar_memoria()
    with sqlite3.connect(banco.caminho) as con:
        coef = con.execute("SELECT COUNT(*) FROM banco_coeficientes").fetchone()[0]
    assert memoria and coef

    r = gestao.excluir(banco, [a])
    assert r["excluidas"] == [a] and str(arquivo.resolve()) in r["arquivos_apagados"]
    assert not arquivo.exists()
    assert all(v == 0 for v in _contar(banco, a).values()), _contar(banco, a)
    # memória das ligações e banco de coeficientes ficam
    assert banco.carregar_memoria() == memoria
    with sqlite3.connect(banco.caminho) as con:
        assert con.execute("SELECT COUNT(*) FROM banco_coeficientes").fetchone()[0] == coef
    # a outra obra continua inteira, com o arquivo
    assert banco.carregar_obra(b) and banco.arquivo_da_obra(b).exists()
    assert [o["id"] for o in gestao.listar(banco)] == [b]


def test_nova_importacao_usa_a_memoria_de_obra_excluida(banco_com_duas_obras, arquivo_teste, biblioteca):
    banco, a, b = banco_com_duas_obras
    gestao.excluir(banco, [a, b])
    assert gestao.listar(banco) == []
    nova = preparar_obra(banco, arquivo_teste, biblioteca)
    servicos = banco.carregar_obra(nova)["servicos"]
    pela_memoria = [s for s in servicos if s["status_ligacao"] == "memoria"]
    assert len(pela_memoria) > 0.5 * len(servicos)


def test_excluir_varias_e_validacoes(banco_com_duas_obras):
    banco, a, b = banco_com_duas_obras
    with pytest.raises(gestao.ErroObras) as e:
        gestao.excluir(banco, [])
    assert e.value.status == 400
    with pytest.raises(gestao.ErroObras) as e:
        gestao.excluir(banco, [a, 999])
    assert e.value.status == 404 and banco.carregar_obra(a)  # nada apagado
    with pytest.raises(gestao.ErroObras) as e:
        gestao.excluir(banco, [a, b], rodando=[b])
    assert e.value.status == 409 and "rodando" in str(e.value)
    assert banco.carregar_obra(a) and banco.carregar_obra(b)  # nada apagado
    assert gestao.excluir(banco, [b, a])["excluidas"] == [a, b]
    assert gestao.listar(banco) == []


def test_arquivo_fora_de_arquivos_obras_nao_e_apagado(tmp_path, arquivo_teste):
    banco = Banco(str(tmp_path / "b.sqlite3"))
    obra = banco.salvar_importacao(ler_planilha(arquivo_teste))
    fora = tmp_path / "importante.xlsx"
    fora.write_bytes(b"x")
    with sqlite3.connect(banco.caminho) as con:
        con.execute("UPDATE obras SET arquivo_salvo = ? WHERE id = ?", (str(fora), obra))
    gestao.excluir(banco, [obra])
    assert fora.exists()


# ------------------------------------------------------------------ rotas


@pytest.fixture
def cliente(tmp_path, arquivo_teste, biblioteca):
    app = criar_app(str(tmp_path / "web.sqlite3"))
    banco = Banco(app.config["CAMINHO_BANCO"])
    a = preparar_obra(banco, arquivo_teste, biblioteca)
    b = banco.salvar_importacao(ler_planilha(arquivo_teste))
    return app, app.test_client(), banco, a, b


def test_rotas_lista_etapas_leitura_e_edicao(cliente):
    app, c, banco, a, b = cliente
    lista = c.get("/api/importacoes").get_json()
    assert {o["id"]: o["atual"] for o in lista} == {a: "sequencia", b: "leitura"}
    e = c.get(f"/api/obras/{a}/etapas").get_json()
    assert e["obra"]["id"] == a and e["atual_rotulo"] == "Sequência"
    assert c.get("/api/obras/999/etapas").status_code == 404
    d = c.get(f"/api/obras/{b}/leitura").get_json()
    assert d["salva"] and d["servicos"]
    r = c.post(f"/api/obras/{b}/dados", json={"nome": "Novo nome", "prazo_valor": 8, "prazo_unidade": "meses"})
    assert r.status_code == 200 and r.get_json()["obra"]["nome"] == "Novo nome"
    assert c.post(f"/api/obras/{b}/dados", json={"prazo_valor": -1}).status_code == 400


def test_rota_excluir(cliente):
    app, c, banco, a, b = cliente
    assert c.post("/api/obras/excluir", json={"ids": []}).status_code == 400
    r = c.delete(f"/api/obras/{b}")
    assert r.status_code == 200 and r.get_json()["excluidas"] == [b]
    assert c.delete(f"/api/obras/{b}").status_code == 404
    r = c.post("/api/obras/excluir", json={"ids": [a]})
    assert r.status_code == 200 and c.get("/api/importacoes").get_json() == []


def test_rota_excluir_com_calculo_rodando(cliente, monkeypatch):
    """Com o cálculo do cronograma rodando, a obra não pode ser excluída."""
    import threading

    app, c, banco, a, b = cliente
    liberar, comecou = threading.Event(), threading.Event()

    def calcular_devagar(*args, parar=None, **kwargs):
        comecou.set()
        liberar.wait(10)
        return {}

    etapa4.analisar_obra(banco, a)
    resolver_pendencias(banco, a, None)
    etapa5.salvar_parametros_cronograma(banco, a, {"data_inicio": INICIO, "prazos": [12]})
    monkeypatch.setattr(etapa5, "calcular_cenarios", calcular_devagar)
    assert c.post(f"/api/obras/{a}/cronograma/calcular", json={"prazos": "12"}).status_code == 200
    assert comecou.wait(10)
    try:
        r = c.post("/api/obras/excluir", json={"ids": [a, b]})
        assert r.status_code == 409 and "rodando" in r.get_json()["erro"]
        assert banco.carregar_obra(a) and banco.carregar_obra(b)   # nenhuma apagada
    finally:
        liberar.set()
    for _ in range(100):
        if not c.get(f"/api/obras/{a}/cronograma/calculo").get_json().get("rodando"):
            break
        threading.Event().wait(0.05)
    assert c.post("/api/obras/excluir", json={"ids": [a]}).status_code == 200


def test_paginas_tem_a_barra_de_etapas():
    from pathlib import Path

    estatico = Path(__file__).resolve().parent.parent / "web" / "static"
    for pagina in ("index", "ligacao", "sequencia", "mao_de_obra", "cronograma"):
        assert '<script src="/static/etapas.js"></script>' in (estatico / f"{pagina}.html").read_text(encoding="utf-8")
    js = (estatico / "etapas.js").read_text(encoding="utf-8")
    assert "/api/obras/" in js and "desativada" in js and "motivo" in js
    index = (estatico / "index.html").read_text(encoding="utf-8")
    assert '<details id="salvas"' not in index and 'id="tabela-obras"' in index
    app_js = (estatico / "app.js").read_text(encoding="utf-8")
    assert "confirm(" not in app_js.split("async function salvarObraSalva")[1]   # exclusão sem o confirm do navegador
