"""Leitura do arquivo principal de teste (Concorrência 2/2024) — itens 11 da especificação."""
import pytest


def test_aba_planilha_escolhida(resultado):
    assert resultado["aba"] == "PLANILHA"
    assert resultado["motivo_aba"] == "nome"
    nomes = [a["nome"] for a in resultado["abas"]]
    assert "CRONOGRAMA" in nomes and "CPU" in nomes  # lista para troca de aba


def test_cabecalho_linha_10_colunas_b_a_k(resultado):
    assert resultado["linha_cabecalho"] == 10
    assert resultado["colunas"] == {
        "item": "B", "base": "C", "codigo": "D", "descricao": "E", "unidade": "F",
        "quantidade": "G", "preco_unit": "H", "preco_unit_bdi": "I", "total": "J", "total_bdi": "K",
    }
    assert resultado["colunas_faltando"] == []


def test_dados_gerais_da_obra(resultado):
    obra = resultado["obra"]
    assert obra["nome"].startswith("CONSTRUÇÃO DO CENTRO ESPORTIVO E PRAÇA DE LAZER")
    assert obra["prazo_valor"] == 12
    assert obra["prazo_unidade"] == "meses"
    assert obra["bdi"] == pytest.approx(0.2522)
    assert obra["desoneracao"] == "DESONERADA"
    assert obra["referencias"] == [
        "SINAPI OUTUBRO/2023", "SUDECAP JULHO/2023", "SETOP AGOSTO/2023", "DNIT JULHO/2023",
    ]
    assert obra["total_planilha"] == 4527898.72
    assert obra["total_bdi_planilha"] == 5669771.17
    assert obra["arquivo"] == "Concorrencia_2_2024_PLANILHA_ORCAMENTARIA_EDITAVEL.XLSX"
    assert obra["data_importacao"]


def test_quantidade_e_totais_dos_servicos(resultado):
    v = resultado["validacao"]
    assert len(resultado["servicos"]) == 374
    assert v["qtd_servicos"] == 374
    assert v["soma_servicos"] == 4527898.72
    assert v["soma_servicos_bdi"] == 5669771.17
    assert v["total_confere"] is True
    assert v["total_bdi_confere"] is True
    assert v["grupos_divergentes"] == 0
    assert v["ok"] is True
    assert resultado["resumo"] == "374 serviços lidos — total R$ 4.527.898,72 (confere com a planilha)"


def test_sem_alertas_de_erro(resultado):
    erros = [a for a in resultado["alertas"] if a["nivel"] != "info"]
    assert erros == []


def test_linhas_de_total_soltas_ignoradas(resultado):
    linhas = {s["linha_excel"] for s in resultado["servicos"]} | {g["linha_excel"] for g in resultado["grupos"]}
    assert not linhas & {11, 491, 492, 493, 494, 495, 497}
    infos = {a["linha"] for a in resultado["alertas"] if a["nivel"] == "info"}
    assert {493, 495} <= infos


def test_item_1_1_1_taxa(servicos_por_item):
    s = servicos_por_item["1.1.1"]
    assert s["codigo"] == "COMP-65"
    assert s["unidade"] == "%"
    assert s["quantidade"] == 0.05
    assert s["natureza"] == "taxa"
    assert s["item_grupo"] == "1.1"
    assert s["caminho_grupos"] == ["1", "1.1"]


def test_item_4_2_grupo_pai_4(servicos_por_item):
    s = servicos_por_item["4.2"]
    assert s["codigo"] == "ED-29802"
    assert s["item_grupo"] == "4"


def test_item_4_10_texto(servicos_por_item):
    assert "4.10" in servicos_por_item and "4.1" in servicos_por_item
    assert servicos_por_item["4.10"]["linha_excel"] != servicos_por_item["4.1"]["linha_excel"]
    assert servicos_por_item["4.10"]["codigo"] == "96616"
    assert all(isinstance(s["item"], str) for s in servicos_por_item.values())


def test_9_1_e_grupo(resultado, servicos_por_item):
    grupos = {g["item"]: g for g in resultado["grupos"]}
    assert "9" in grupos and "9.1" in grupos and "9.1.1" in grupos
    assert "9.1" not in servicos_por_item
    assert grupos["9.1"]["item_pai"] == "9"
    assert grupos["9.1.1"]["item_pai"] == "9.1"
    assert servicos_por_item["9.1.1.1"]["item_grupo"] == "9.1.1"
    assert servicos_por_item["9.1.1.1"]["caminho_grupos"] == ["9", "9.1", "9.1.1"]


def test_grupos_de_nivel_1_sem_pai(resultado):
    grupos = {g["item"]: g for g in resultado["grupos"]}
    assert grupos["1"]["item_pai"] is None and grupos["1"]["nivel"] == 1
    assert grupos["1.2"]["item_pai"] == "1" and grupos["1.2"]["descricao"] == "SERVIÇOS PRELIMINARES"


def test_1_2_2_unidade_sem_espaco(servicos_por_item):
    assert servicos_por_item["1.2.2"]["unidade"] == "UN"


def test_descricao_sem_espacos_nas_pontas(resultado):
    for s in resultado["servicos"]:
        assert s["descricao"] == s["descricao"].strip()


def test_contagem_natureza(resultado):
    assert resultado["validacao"]["por_natureza"] == {"producao": 359, "tempo": 9, "transporte": 5, "taxa": 1}


def test_m2_mes_equivalentes(servicos_por_item):
    a, b = servicos_por_item["1.4.1"], servicos_por_item["5.1.11"]
    assert {a["unidade"], b["unidade"]} == {"M2/MÊS", "M2XMÊS"}
    assert a["unidade_normalizada"] == b["unidade_normalizada"]
    assert a["natureza"] == b["natureza"] == "tempo"


def test_valores_arredondados(resultado):
    for s in resultado["servicos"]:
        for campo in ("preco_unit", "preco_unit_bdi", "total", "total_bdi"):
            assert s[campo] == round(s[campo], 2)
        assert s["quantidade"] == round(s["quantidade"], 4)


def test_campos_previstos_para_proximas_etapas(resultado):
    for s in resultado["servicos"]:
        assert s["atividade_biblioteca"] is None
        assert s["etapa_obra"] is None
        assert s["local"] is None


def test_soma_dos_grupos_confere(resultado):
    grupos = {g["item"]: g for g in resultado["grupos"]}
    assert grupos["1"]["total_planilha"] == 900439.63
    assert grupos["1"]["soma_servicos"] == pytest.approx(900439.63, abs=1)
    assert grupos["1"]["confere"] is True
    assert grupos["1.1"]["total_planilha"] == 0
    assert grupos["1.1"]["confere"] is None  # grupo sem total: não compara


# ---------------------------------------------------------------- comparação com o CSV


def _caminho_descricoes(resultado, servico):
    grupos = {g["item"]: g for g in resultado["grupos"]}
    descricoes = [grupos[i]["descricao"] for i in servico["caminho_grupos"]]
    return descricoes[0], " > ".join(descricoes[1:])


def test_csv_tem_374_servicos(esperados):
    assert len(esperados) == 374


def test_cada_linha_do_csv_bate(resultado, esperados):
    por_linha = {s["linha_excel"]: s for s in resultado["servicos"]}
    assert set(por_linha) == {int(e["linha"]) for e in esperados}
    diferencas = []
    for e in esperados:
        s = por_linha[int(e["linha"])]
        grupo, subgrupo = _caminho_descricoes(resultado, s)
        obtido = {
            "item": s["item"], "grupo": grupo, "subgrupo": subgrupo, "base": s["base"] or "",
            "codigo": s["codigo"], "descricao": s["descricao"], "unidade": s["unidade"],
            "natureza": s["natureza"],
        }
        for campo, valor in obtido.items():
            if valor != e[campo]:
                diferencas.append((e["linha"], campo, e[campo], valor))
        for campo in ("quantidade", "preco_unit", "preco_unit_bdi", "total", "total_bdi"):
            if s[campo] != pytest.approx(float(e[campo]), abs=1e-6):
                diferencas.append((e["linha"], campo, e[campo], s[campo]))
    assert diferencas == []
