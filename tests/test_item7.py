"""Item 7 — terceirizados na contagem de pessoas: nome e pessoas do terceirizado, contagem por semana, total na
obra, limite do canteiro com os terceirizados, diagnóstico, telas e exportação."""
import io

import openpyxl
import pytest

from armazenamento import Banco
from atividades import carregar_biblioteca
from conftest import BIBLIOTECA, copiar_biblioteca, preparar_obra
from cronograma import Calendario, Modo, Tarefa
from cronograma import obra as etapa5
from cronograma.agenda import contar_terceirizados, contratados_minimos, resumir
from cronograma.otimizador import IMPOSSIVEL, otimizar
from mao_de_obra import obra as etapa4
from mao_de_obra.calculo import (
    ORIGEM_BIBLIOTECA,
    ORIGEM_COMPOSICAO,
    ORIGEM_DIGITADO,
    ORIGEM_OUTRAS_OBRAS,
    SEM_ESTIMATIVA,
    terceirizado_da_atividade,
)
from test_etapa5_obra import INICIO, resolver_pendencias
from test_etapa5_redes import SEGUNDA, equipe, inst, rede
from web.app import criar_app

COLUNAS_ITEM7 = ("rotulo_terceirizado", "pessoas_terceirizado")
VALIDAS = ("otimo", "melhor_encontrado")
TEMPO = 12


def terc(dias, pessoas, rotulo="Telhado", deps=(), partes_max=1, origem="digitado"):
    return Tarefa(codigo="", modos=[Modo(dias_uteis=dias)], tipo="flexivel", deps=list(deps), execucao="terceirizada",
                  terceirizado={"rotulo": rotulo, "pessoas": pessoas, "origem": origem}, partes_max=partes_max)


def _ativ(estado, cod):
    return next(a for a in estado["atividades"] if a["codigo"] == cod)


# ------------------------------------------------------------------ biblioteca


def test_biblioteca_tem_21_colunas_e_as_duas_novas_no_fim():
    ws = openpyxl.load_workbook(BIBLIOTECA, read_only=True)["Atividades"]
    cab = next(ws.iter_rows(min_row=1, max_row=1, values_only=True))
    assert len(cab) == 21 and tuple(cab[-2:]) == COLUNAS_ITEM7


def test_colunas_novas_lidas_pelo_nome(tmp_path, biblioteca):
    a = biblioteca.atividades
    assert all(a[c].rotulo_terceirizado == "Eletricista" for c in ("ELE-01", "ELE-02", "ELE-04", "ELE-08", "SPDA-01",
                                                                  "TEL-01", "INC-01"))
    assert all(a[c].rotulo_terceirizado == "Bombeiro" for c in ("HID-01", "HID-02", "HID-04", "HID-05"))
    assert (a["COB-02"].rotulo_terceirizado, a["COB-02"].pessoas_terceirizado) == ("Telhado", 4)
    assert (a["PAV-02"].rotulo_terceirizado, a["PAV-02"].pessoas_terceirizado) == ("Asfalto", 8)
    assert a["IND-03"].rotulo_terceirizado is None and a["IND-03"].pessoas_terceirizado is None

    def embaralhar(wb):
        ws = wb["Atividades"]
        linhas = [list(r) for r in ws.iter_rows(values_only=True)]
        ordem = list(reversed(range(len(linhas[0]))))
        ws.delete_rows(1, ws.max_row)
        for l in linhas:
            ws.append([l[i] for i in ordem])
    b = carregar_biblioteca(copiar_biblioteca(tmp_path / "embaralhada.xlsx", embaralhar))
    for cod, x in biblioteca.atividades.items():
        y = b.atividades[cod]
        assert (y.rotulo_terceirizado, y.pessoas_terceirizado) == (x.rotulo_terceirizado, x.pessoas_terceirizado)


def test_biblioteca_sem_as_colunas_novas_carrega(tmp_path):
    def tirar(wb):
        wb["Atividades"].delete_cols(20, 2)
    b = carregar_biblioteca(copiar_biblioteca(tmp_path / "antiga.xlsx", tirar))
    assert all(a.rotulo_terceirizado is None and a.pessoas_terceirizado is None for a in b.atividades.values())
    assert b.atividades["COB-02"].trocar_funcoes == carregar_biblioteca().atividades["COB-02"].trocar_funcoes


# ------------------------------------------------------------------ nome do terceirizado


def test_nome_vazio_usa_a_funcao_principal_e_depois_o_nome_da_atividade():
    sem = {"codigo": "X-01", "nome": "Serviço X", "equipe_principal": None, "rotulo_terceirizado": ""}
    assert terceirizado_da_atividade(sem, {}, None, {}, None, 8.8)["nome"] == "Serviço X (terceirizado)"
    calc = {"funcao_principal": "Pedreiro", "equipe": {"Pedreiro": 2}}
    t = terceirizado_da_atividade(sem, {}, calc, {"Pedreiro": 100.0}, {"tipo": "calculada", "dias": 6}, 8.8)
    assert t["rotulo"] == "Pedreiro" and t["nome"] == "Pedreiro (terceirizado)"
    com_lib = {**sem, "equipe_principal": "Pintor"}
    assert terceirizado_da_atividade(com_lib, {}, None, {}, None, 8.8)["rotulo"] == "Pintor"
    assert terceirizado_da_atividade({**sem, "rotulo_terceirizado": "Telhado"}, {}, calc, {}, None, 8.8)["rotulo"] == "Telhado"


def test_mesmo_nome_soma_no_mesmo_dia(biblioteca):
    """ELE-02 e ELE-04 terceirizadas, ambas 'Eletricista' na biblioteca, em paralelo: somam no dia."""
    rot = {c: biblioteca.atividades[c].rotulo_terceirizado for c in ("ELE-02", "ELE-04")}
    assert set(rot.values()) == {"Eletricista"}
    i = inst(rede(**{"ELE-02": terc(5, 3, rot["ELE-02"]), "ELE-04": terc(5, 2, rot["ELE-04"]),
                     "PED": equipe(5, Pedreiro=2)}))
    sol = {"ELE-02": i.entrada("ELE-02", 0, 0), "ELE-04": i.entrada("ELE-04", 0, 0), "PED": i.entrada("PED", 0, 0)}
    r = resumir(i, sol, contratados_minimos(i, sol))
    t = r["terceirizados"]
    assert [x["rotulo"] for x in t["rotulos"]] == ["Eletricista"]
    assert t["rotulos"][0]["serie"][0] == 5
    assert t["total_obra"][0] == 5 + 2
    semana = next(s for s in t["semanas"] if s["indice"] == 0)
    assert {a["codigo"]: a["pessoas"] for a in semana["atividades"]} == {"ELE-02": 3, "ELE-04": 2}


# ------------------------------------------------------------------ pessoas: prioridade e origem


ATIV = {"codigo": "MET-01", "nome": "Estrutura metálica", "rotulo_terceirizado": "Estrutura metálica",
        "pessoas_terceirizado": 6}
CALC = {"funcao_principal": "Montador", "equipe": {"Montador": 3, "Servente": 2}}
HORAS = {"Montador": 300.0, "Servente": 150.0}
CALCULADA = {"tipo": "calculada", "dias": 12, "unidade": "uteis"}


def test_pessoas_digitado_ganha_de_tudo():
    t = terceirizado_da_atividade(ATIV, {"pessoas_terceirizado": 9}, CALC, HORAS, CALCULADA, 8.8, 5)
    assert (t["pessoas"], t["origem"]) == (9, ORIGEM_DIGITADO)


def test_pessoas_composicao_ganha_de_outras_obras_e_biblioteca():
    t = terceirizado_da_atividade(ATIV, {}, CALC, HORAS, CALCULADA, 8.8, 5)
    assert (t["pessoas"], t["origem"], t["por_modo"]) == (5, ORIGEM_COMPOSICAO, True)
    assert t["detalhe"] == {"Montador": 3, "Servente": 2}


def test_pessoas_outras_obras_ganha_da_biblioteca():
    t = terceirizado_da_atividade(ATIV, {}, None, {}, {"tipo": "manual", "dias": 40}, 8.8, 5)
    assert (t["pessoas"], t["origem"]) == (5, ORIGEM_OUTRAS_OBRAS)


def test_pessoas_biblioteca_e_sem_estimativa():
    t = terceirizado_da_atividade(ATIV, {}, None, {}, {"tipo": "manual", "dias": 40}, 8.8, None)
    assert (t["pessoas"], t["origem"]) == (6, ORIGEM_BIBLIOTECA)
    t = terceirizado_da_atividade({**ATIV, "pessoas_terceirizado": None}, {}, None, {}, {"tipo": "manual", "dias": 40},
                                  8.8, None)
    assert (t["pessoas"], t["origem"]) == (0, SEM_ESTIMATIVA)
    assert t["aviso"] == "sem estimativa de pessoas: digite na mão de obra"


def test_composicao_com_duracao_digitada():
    """176 h em 10 dias úteis de 8,8 h → 2 pessoas."""
    t = terceirizado_da_atividade(ATIV, {}, {"funcao_principal": "Montador", "equipe": {"Montador": 2}},
                                  {"Montador": 176.0}, {"tipo": "manual", "dias": 10}, 8.8, 5)
    assert (t["pessoas"], t["origem"], t["por_modo"]) == (2, ORIGEM_COMPOSICAO, False)


# ------------------------------------------------------------------ contagem por semana


def _pos(cod, rotulo, pessoas, dias, origem="digitado"):
    return {"codigo": cod, "nome": cod, "rotulo": rotulo, "pessoas": pessoas, "origem": origem, "dias": dias}


def test_contagem_semanal_vale_o_maior_dia_nao_a_soma():
    cal = Calendario(SEGUNDA)   # segunda-feira: dias 0..4 são a semana 0
    t = contar_terceirizados(cal, [_pos("SER-01", "Serralheria", 3, [(0, 2)]), _pos("SER-02", "Serralheria", 4, [(3, 2)])],
                             [0])
    assert t["rotulos"][0]["serie"] == [4]
    assert t["homem_semana_terceirizado"] == 4


def test_terceirizada_em_partes_zera_no_intervalo():
    cal = Calendario(SEGUNDA)
    t = contar_terceirizados(cal, [_pos("COB-02", "Telhado", 4, [(0, 5), (15, 5)])], [2, 2, 2, 2])
    assert t["rotulos"][0]["serie"] == [4, 0, 0, 4]
    assert t["total_obra"] == [6, 2, 2, 6]


def test_terceirizada_dividida_pelo_otimizador_conta_so_nas_partes():
    i = inst(rede(A=equipe(10), T=terc(10, 3, partes_max=3)))
    sol = {"A": i.entrada("A", 0, 0), "T": i.entrada("T", 0, 0, [(0, 5), (15, 5)])}
    r = resumir(i, sol, contratados_minimos(i, sol))
    assert r["terceirizados"]["rotulos"][0]["serie"] == [3, 0, 0, 3]


def test_total_na_obra_e_pico_total():
    cal = Calendario(SEGUNDA)
    t = contar_terceirizados(cal, [_pos("A", "Telhado", 4, [(5, 5)]), _pos("B", "Asfalto", 8, [(10, 3)])], [6, 5, 2])
    assert t["total_obra"] == [6, 9, 10]
    assert (t["pico_total"], t["semana_pico_total"]) == (10, "2025-08-18")
    assert (t["pico_proprios"], t["semana_pico_proprios"]) == (6, "2025-08-04")
    assert [r["rotulo"] for r in t["rotulos"]] == ["Asfalto", "Telhado"]   # maior pico primeiro


def test_custo_e_ociosidade_nao_mudam_com_a_contagem():
    def mk(com):
        tt = terc(5, 4) if com else Tarefa(codigo="", modos=[Modo(dias_uteis=5)], tipo="flexivel", execucao="terceirizada",
                                           partes_max=1)
        return rede(A=equipe(10, Pedreiro=3), T=tt, B=equipe(5, deps=[("A", 0), ("T", 0)], Servente=2))
    r1, r2 = otimizar(inst(mk(True), limite_dias=40), 10), otimizar(inst(mk(False), limite_dias=40), 10)
    assert r1["situacao"] == r2["situacao"] == "otimo"
    for k in ("custo_total", "custo_mao_de_obra", "custo_indiretos", "ociosidade", "pico", "termino"):
        assert r1[k] == r2[k], k
    assert r1["pico_total"] >= max(r1["pico"], 4) and r2["pico_total"] == r2["pico"]
    assert r2["terceirizados"]["rotulos"] == []


# ------------------------------------------------------------------ limite do canteiro


def _rede_canteiro():
    return rede(A=equipe(10, Pedreiro=8), T=terc(5, 4), Z=equipe(1, deps=[("A", 0), ("T", 0)], Pedreiro=1))


def _paralelas(r):
    a = {x["codigo"]: x for x in r["atividades"]}
    return not (a["T"]["termino"] < a["A"]["inicio"] or a["A"]["termino"] < a["T"]["inicio"])


def test_limite_do_canteiro_conta_terceirizados():
    ligado = otimizar(inst(_rede_canteiro(), limite_dias=40, max_total=10), 10)
    assert ligado["situacao"] in VALIDAS and ligado["violacoes"] == []
    assert not _paralelas(ligado) and max(ligado["terceirizados"]["total_obra"]) <= 10
    desligado = otimizar(inst(_rede_canteiro(), limite_dias=40, max_total=10, contar_terceirizados=False), 10)
    assert desligado["situacao"] in VALIDAS and _paralelas(desligado)
    assert desligado["pico_total"] == 12


def test_sem_maximo_o_resultado_e_o_de_antes():
    com = otimizar(inst(_rede_canteiro(), limite_dias=40), 10)
    sem_contar = otimizar(inst(_rede_canteiro(), limite_dias=40, contar_terceirizados=False), 10)
    for k in ("termino", "custo_total", "pico", "ociosidade"):
        assert com[k] == sem_contar[k]


def test_verificar_acusa_canteiro_estourado():
    from cronograma.agenda import verificar
    i = inst(_rede_canteiro(), limite_dias=40, max_total=10)
    sol = {"A": i.entrada("A", 0, 0), "T": i.entrada("T", 0, 0)}
    sol["Z"] = i.entrada("Z", 0, 10)
    erros = verificar(i, sol, contratados_minimos(i, sol))
    assert any("pessoas no canteiro com os terceirizados" in e for e in erros)


def test_diagnostico_sugere_aumentar_o_maximo_do_canteiro():
    t = rede(A=equipe(10, Pedreiro=8), T=terc(10, 4), Z=equipe(1, deps=[("A", 0), ("T", 0)], Pedreiro=1))
    i = inst(t, limite_dias=15, max_total=10)
    assert otimizar(i, 10)["situacao"] == IMPOSSIVEL
    d = etapa5.diagnostico(i, {"estado": {"atividades": []}})
    s = next(x for x in d["sugestoes"] if x["acao"]["tipo"] == "max_pessoas_total")
    assert s["acao"]["valor"] == 12 and s["ganho"] == 10
    assert "de 10 para 12 reduz 10 dias úteis" in s["texto"]
    assert d["canteiro"]["dias_uteis"] > d["canteiro"]["sem_limite"]


# ------------------------------------------------------------------ obra de teste


@pytest.fixture(scope="module")
def obra7(tmp_path_factory, arquivo_teste, biblioteca):
    banco = Banco(str(tmp_path_factory.mktemp("item7") / "obra.sqlite3"))
    obra = preparar_obra(banco, arquivo_teste, biblioteca)
    etapa4.analisar_obra(banco, obra, biblioteca)
    resolver_pendencias(banco, obra, biblioteca)
    etapa5.salvar_parametros_cronograma(banco, obra, {"data_inicio": INICIO})
    cmp = etapa5.calcular_cenarios(banco, obra, [12], biblioteca, TEMPO)
    return banco, obra, cmp


def test_terceirizadas_da_obra_tem_nome_e_origem(obra7, biblioteca):
    banco, obra, _ = obra7
    est = etapa4.estado_mao_de_obra(banco, obra, biblioteca)
    terc = {a["codigo"]: a["terceirizado"] for a in est["atividades"] if a["execucao"] == "terceirizada"}
    assert terc["COB-02"]["nome"] == "Telhado (terceirizado)"
    assert terc["MET-01"]["origem"] == ORIGEM_BIBLIOTECA and terc["MET-01"]["pessoas"] == 6
    assert terc["SER-01"]["rotulo"] == terc["SER-02"]["rotulo"] == "Serralheria"
    assert all(t["origem"] in (ORIGEM_DIGITADO, ORIGEM_COMPOSICAO, ORIGEM_OUTRAS_OBRAS, ORIGEM_BIBLIOTECA, SEM_ESTIMATIVA)
               for t in terc.values())
    assert all(a["terceirizado"] is None for a in est["atividades"] if a["execucao"] == "propria")


def test_planilha_de_teste_cabe_em_12_meses_com_os_padroes(obra7, biblioteca):
    banco, obra, cmp = obra7
    c = cmp["cenarios"][0]
    assert banco.carregar_calendario(obra)["max_pessoas_total"] is None
    assert c["situacao"] in VALIDAS and c["pico_total"] >= c["pico"]
    det = etapa5.detalhe_cenario(banco, obra, c["id"])
    assert det["terceirizados"] and det["pico_total"] == c["pico_total"]
    assert det["total_obra"] == [p + t for p, t in zip(det["total_semana"], det["total_terceirizados"])]
    assert max(det["total_obra"]) == det["pico_total"]
    assert det["semanas"][det["total_obra"].index(det["pico_total"])] == det["semana_pico_total"]
    assert det["resumo_terceirizados"]["homem_semana_terceirizado"] == sum(det["total_terceirizados"])
    cob = next(a for a in det["atividades"] if a["codigo"] == "COB-02")
    assert cob["terceirizado"]["nome"] == "Telhado (terceirizado)" and cob["terceirizado"]["pessoas"] > 0


def test_digitar_pessoas_recalcula_so_a_contagem_e_vira_padrao(obra7, biblioteca, arquivo_teste, tmp_path):
    banco, obra, cmp = obra7
    cid = cmp["cenarios"][0]["id"]
    antes = etapa5.detalhe_cenario(banco, obra, cid)
    caminho = copiar_biblioteca(tmp_path / "bib.xlsx")
    cli = criar_app(banco.caminho, str(tmp_path / "up"), str(caminho)).test_client()
    r = cli.post(f"/api/obras/{obra}/atividade/MET-01/terceirizado",
                 json={"pessoas_terceirizado": 5, "rotulo_terceirizado": "Metálica", "salvar_biblioteca": True})
    assert r.status_code == 200, r.get_json()
    j = r.get_json()
    t = _ativ(j, "MET-01")["terceirizado"]
    assert (t["pessoas"], t["origem"], t["nome"]) == (5, ORIGEM_DIGITADO, "Metálica (terceirizado)")
    assert j["contagem"]["recontados"] == 1 and not j["contagem"]["precisa_recalcular"]
    assert carregar_biblioteca(caminho).atividades["MET-01"].rotulo_terceirizado == "Metálica"
    depois = etapa5.detalhe_cenario(banco, obra, cid)
    assert depois["calculado_em"] == antes["calculado_em"] and depois["termino"] == antes["termino"]
    assert depois["custo_total"] == antes["custo_total"] and depois["ociosidade"] == antes["ociosidade"]
    met = next(x for x in depois["terceirizados"] if x["rotulo"] == "Metálica")
    assert met["pico"] == 5
    assert not any(x["rotulo"] == "Estrutura metálica" for x in depois["terceirizados"])
    # padrão das próximas obras: obra nova vem com 5 (outras obras); excluir a primeira não apaga
    assert banco.pessoas_terceirizado_padrao()["MET-01"] == 5
    obra2 = preparar_obra(banco, arquivo_teste, biblioteca)
    etapa4.analisar_obra(banco, obra2, biblioteca)
    resolver_pendencias(banco, obra2, biblioteca)
    banco.excluir_obras([obra])
    t2 = _ativ(etapa4.estado_mao_de_obra(banco, obra2, biblioteca), "MET-01")["terceirizado"]
    assert (t2["pessoas"], t2["origem"]) == (5, ORIGEM_OUTRAS_OBRAS)
    assert banco.pessoas_terceirizado_padrao()["MET-01"] == 5


def test_exportacao_tem_terceirizados_e_total(tmp_path, arquivo_teste, biblioteca):
    banco = Banco(str(tmp_path / "exp.sqlite3"))
    obra = preparar_obra(banco, arquivo_teste, biblioteca)
    etapa4.analisar_obra(banco, obra, biblioteca)
    resolver_pendencias(banco, obra, biblioteca)
    etapa5.salvar_parametros_cronograma(banco, obra, {"data_inicio": INICIO})
    c = etapa5.calcular_cenario(banco, obra, 12, biblioteca, 6)
    assert c["situacao"] in VALIDAS
    det = etapa5.detalhe_cenario(banco, obra, c["id"])
    wb = openpyxl.load_workbook(io.BytesIO(etapa5.exportar_equipe_excel(banco, obra, c["id"])))
    linhas = {r[0]: r for r in wb["Contratados"].iter_rows(values_only=True) if r and r[0]}
    for t in det["terceirizados"]:
        assert t["nome"] in linhas and list(linhas[t["nome"]][4:4 + len(det["semanas"])]) == t["pessoas"]
    assert list(linhas["Total na obra"][4:4 + len(det["semanas"])]) == det["total_obra"]
    assert "Terceirizado" in [c.value for c in wb["Atividades"][1]]
    cmp = etapa5.comparacao(banco, obra)
    assert cmp["cenarios"][0]["pico_total"] == det["pico_total"]


def test_parametro_contar_terceirizados_ligado_por_padrao(tmp_path, arquivo_teste, biblioteca):
    banco = Banco(str(tmp_path / "p.sqlite3"))
    obra = preparar_obra(banco, arquivo_teste, biblioteca)
    etapa4.analisar_obra(banco, obra, biblioteca)
    resolver_pendencias(banco, obra, biblioteca)
    assert etapa5.parametros_cronograma(banco, obra, biblioteca)["contar_terceirizados"] is True
    etapa5.salvar_parametros_cronograma(banco, obra, {"contar_terceirizados": False, "data_inicio": INICIO})
    assert etapa5.parametros_cronograma(banco, obra, biblioteca)["contar_terceirizados"] is False
    inst_, _ = etapa5.montar_instancia(banco, obra, 12, biblioteca)
    assert inst_.contar_terceirizados is False
    etapa5.aplicar_sugestao(banco, obra, {"tipo": "max_pessoas_total", "valor": 80}, biblioteca)
    assert banco.carregar_calendario(obra)["max_pessoas_total"] == 80
