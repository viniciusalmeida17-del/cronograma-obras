"""Interface web local (Flask).

Executar:  python -m web.app   (abre em http://127.0.0.1:5000)
No Windows também pelo atalho "Cronograma de Obras" (windows/criar_atalhos.ps1), sem janela preta.
"""
from __future__ import annotations

import logging
import os
import sys
import tempfile
import threading
import time
import uuid
import webbrowser
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, request, send_from_directory
from werkzeug.serving import make_server

from armazenamento import Banco
from atividades import ErroBiblioteca, carregar_biblioteca
from atividades import obra as etapa3
from cronograma import obra as etapa5
from leitor_planilha import NATUREZAS, ErroLeitura, ler_planilha
from mao_de_obra import obra as etapa4
from mao_de_obra.funcoes import ErroFuncoes

from . import atualizacao
from . import obras as gestao
from .inicio import (HOST, NOME_APP, NOSSO, OUTRO, RAIZ, avisar, caminho_banco_padrao, configurar_log, porta_padrao,
                     preparar_saidas, verificar_porta)

PASTA_ESTATICA = Path(__file__).parent / "static"
CAMPOS_OBRA_EDITAVEIS = ("nome", "prazo_valor", "prazo_unidade", "bdi", "desoneracao", "referencias")
UNIDADES_PRAZO = ("dias", "semanas", "meses", "anos")


def criar_app(
    caminho_banco: str | None = None, pasta_uploads: str | None = None, caminho_biblioteca: str | None = None,
    ao_fechar: Any = None,
) -> Flask:
    app = Flask(__name__, static_folder=None)
    app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024
    app.config["CAMINHO_BANCO"] = caminho_banco or caminho_banco_padrao()
    app.config["AO_FECHAR"] = ao_fechar  # main() põe aqui o desligamento do servidor
    app.config["VERIFICAR_ATUALIZACAO"] = atualizacao.verificar
    app.config["INICIAR_ATUALIZACAO"] = atualizacao.iniciar_atualizacao_windows
    versao: dict[str, Any] = {}
    banco = Banco(app.config["CAMINHO_BANCO"])
    uploads = Path(pasta_uploads or tempfile.mkdtemp(prefix="cronograma_uploads_"))
    uploads.mkdir(parents=True, exist_ok=True)
    leituras: dict[str, dict[str, Any]] = {}  # token -> arquivo e opções da última leitura

    def _ler(token: str) -> dict[str, Any]:
        info = leituras[token]
        resultado = ler_planilha(info["caminho"], nome_arquivo=info["nome"], **info["opcoes"])
        resultado["token"] = token
        return resultado

    def _erro(msg: str, status: int = 400):
        return jsonify({"erro": msg}), status

    @app.get("/api/sobre")
    def sobre():
        # usado para saber se o app já está aberto nesta porta (clicar no atalho de novo só abre o navegador)
        if "valor" not in versao:
            versao["valor"] = atualizacao.versao_atual()
        return jsonify({"app": NOME_APP, "pasta": str(RAIZ), "pid": os.getpid(), "versao": versao["valor"]})

    @app.get("/api/atualizacao")
    def conferir_atualizacao():
        # consulta o GitHub (git fetch) no máximo a cada 10 minutos; sem internet, só diz que não há
        return jsonify(app.config["VERIFICAR_ATUALIZACAO"]())

    @app.post("/api/atualizar")
    def atualizar():
        if request.headers.get("X-Atualizar") != "1":
            return _erro("Pedido inválido.", 403)
        if app.config.get("AO_FECHAR") is None:
            return _erro("Para atualizar pela tela, abra o app pelo atalho Cronograma de Obras "
                         "(ou use o atalho Atualizar Cronograma de Obras).", 409)
        try:
            app.config["INICIAR_ATUALIZACAO"]()
        except NotImplementedError as exc:
            return _erro(str(exc), 501)
        except Exception as exc:  # noqa: BLE001
            logging.getLogger("cronograma").exception("Falha ao iniciar a atualização")
            return _erro(f"Não foi possível iniciar a atualização: {exc}", 500)
        logging.getLogger("cronograma").info("Atualização pedida pela tela")
        return jsonify({"ok": True})

    @app.post("/api/fechar")
    def fechar():
        # cabeçalho próprio: outro site aberto no navegador não consegue mandar (o navegador exige permissão antes)
        if request.headers.get("X-Fechar") != "1":
            return _erro("Pedido inválido.", 403)
        desligar = app.config.get("AO_FECHAR")
        if desligar is None:
            return _erro("Este servidor não foi aberto pelo app (python -m web.app ou atalho); feche-o por onde foi aberto.", 409)
        logging.getLogger("cronograma").info("Fechado pelo botão da tela")
        threading.Timer(0.3, desligar).start()  # responde antes de desligar
        return jsonify({"ok": True})

    @app.get("/")
    def index():
        return send_from_directory(PASTA_ESTATICA, "index.html")

    @app.get("/ligacao")
    def pagina_ligacao():
        return send_from_directory(PASTA_ESTATICA, "ligacao.html")

    @app.get("/sequencia")
    def pagina_sequencia():
        return send_from_directory(PASTA_ESTATICA, "sequencia.html")

    @app.get("/mao-de-obra")
    def pagina_mao_de_obra():
        return send_from_directory(PASTA_ESTATICA, "mao_de_obra.html")

    @app.get("/cronograma")
    def pagina_cronograma():
        return send_from_directory(PASTA_ESTATICA, "cronograma.html")

    @app.get("/sinapi")
    def pagina_sinapi():
        return send_from_directory(PASTA_ESTATICA, "sinapi.html")

    @app.get("/static/<path:arquivo>")
    def estatico(arquivo):
        return send_from_directory(PASTA_ESTATICA, arquivo)

    @app.post("/api/leitura")
    def nova_leitura():
        arquivo = request.files.get("arquivo")
        if arquivo is None or not arquivo.filename:
            return _erro("Envie o arquivo .xlsx da planilha.")
        if not arquivo.filename.lower().endswith((".xlsx", ".xlsm")):
            return _erro("Formato não suportado: envie um arquivo .xlsx.")
        token = uuid.uuid4().hex
        caminho = uploads / f"{token}.xlsx"
        arquivo.save(caminho)
        leituras[token] = {"caminho": str(caminho), "nome": arquivo.filename, "opcoes": {}}
        try:
            return jsonify(_ler(token))
        except ErroLeitura as exc:
            leituras.pop(token, None)
            return _erro(str(exc))

    @app.post("/api/leitura/<token>")
    def reler(token):
        """Lê de novo com outra aba e/ou mapeamento manual de colunas."""
        if token not in leituras:
            return _erro("Leitura não encontrada; envie o arquivo novamente.", 404)
        dados = request.get_json(silent=True) or {}
        opcoes: dict[str, Any] = {}
        if dados.get("aba"):
            opcoes["aba"] = dados["aba"]
        if dados.get("mapeamento"):
            opcoes["mapeamento"] = {k: v for k, v in dados["mapeamento"].items()}
        if dados.get("linha_cabecalho"):
            try:
                opcoes["linha_cabecalho"] = int(dados["linha_cabecalho"])
            except (TypeError, ValueError):
                return _erro("Linha de cabeçalho inválida.")
        anteriores = leituras[token]["opcoes"]
        leituras[token]["opcoes"] = opcoes
        try:
            return jsonify(_ler(token))
        except ErroLeitura as exc:
            leituras[token]["opcoes"] = anteriores
            return _erro(str(exc))

    @app.post("/api/importacoes")
    def confirmar():
        dados = request.get_json(silent=True) or {}
        token = dados.get("token")
        if token not in leituras:
            return _erro("Leitura não encontrada; envie o arquivo novamente.", 404)
        resultado = _ler(token)
        if resultado["colunas_faltando"] or not resultado["servicos"]:
            return _erro("A leitura está incompleta: nenhum serviço foi lido.")

        obra = resultado["obra"]
        for campo, valor in (dados.get("obra") or {}).items():
            if campo not in CAMPOS_OBRA_EDITAVEIS:
                continue
            if campo in ("prazo_valor", "bdi"):
                if valor in (None, ""):
                    valor = None
                else:
                    try:
                        valor = float(valor)
                    except (TypeError, ValueError):
                        return _erro(f"Valor inválido para {campo}.")
            if campo == "prazo_unidade" and valor not in UNIDADES_PRAZO:
                return _erro("Unidade de prazo inválida.")
            if campo == "referencias" and not isinstance(valor, list):
                return _erro("Referências devem ser uma lista.")
            obra[campo] = valor
        if not obra.get("prazo_valor") or obra["prazo_valor"] <= 0:
            return _erro("Informe o prazo da obra (obrigatório para as próximas etapas).")
        if not obra.get("prazo_unidade"):
            return _erro("Informe a unidade do prazo.")

        naturezas = dados.get("naturezas") or {}
        por_linha = {s["linha_excel"]: s for s in resultado["servicos"]}
        for linha, natureza in naturezas.items():
            if natureza not in NATUREZAS:
                return _erro(f"Natureza inválida: {natureza}")
            servico = por_linha.get(int(linha))
            if servico is not None:
                servico["natureza"] = natureza

        obra_id = banco.salvar_importacao(resultado)
        banco.guardar_arquivo(obra_id, leituras[token]["caminho"])  # etapa 4 lê as composições dele
        return jsonify({"id": obra_id, "numero": banco.numero_obra(obra_id),
                        "mensagem": f"Importação salva (obra nº {banco.numero_obra(obra_id)})."})

    @app.get("/api/importacoes")
    def listar():
        # obras salvas com a etapa atual e quais etapas já podem ser abertas
        return jsonify(gestao.listar(banco))

    @app.get("/api/importacoes/<int:obra_id>")
    def carregar(obra_id):
        dados = banco.carregar_obra(obra_id)
        return jsonify(dados) if dados else _erro("Importação não encontrada.", 404)

    # ------------------------------------------------------------------ etapa 3

    def _biblioteca():
        return carregar_biblioteca(caminho_biblioteca)

    @app.errorhandler(ErroBiblioteca)
    def erro_biblioteca(exc):
        return jsonify({"erro": "A biblioteca de atividades tem erros. Corrija o Excel e recarregue a página.",
                        "erros_biblioteca": exc.erros}), 422

    @app.errorhandler(etapa3.ErroObra)
    def erro_obra(exc):
        return jsonify({"erro": str(exc)}), 400

    @app.get("/api/biblioteca")
    def biblioteca():
        b = _biblioteca()
        return jsonify({"caminho": b.caminho, "atividades": b.lista_atividades(), "qtd_regras": len(b.regras)})

    @app.get("/api/obras/<int:obra_id>/ligacao")
    def ligacao(obra_id):
        return jsonify(etapa3.ligar_obra(banco, obra_id, _biblioteca()))

    @app.post("/api/obras/<int:obra_id>/ligacao/refazer")
    def refazer_ligacao(obra_id):
        return jsonify(etapa3.ligar_obra(banco, obra_id, _biblioteca(), refazer=True))

    @app.post("/api/obras/<int:obra_id>/ligacao")
    def trocar_ligacao(obra_id):
        dados = request.get_json(silent=True) or {}
        if not dados.get("atividade") or not dados.get("servicos"):
            return _erro("Informe a atividade e os serviços.")
        return jsonify(etapa3.confirmar_ligacao(banco, obra_id, dados["servicos"], dados["atividade"], _biblioteca()))

    @app.post("/api/obras/<int:obra_id>/rede")
    def montar_rede(obra_id):
        return jsonify(etapa3.montar_rede_obra(banco, obra_id, _biblioteca()))

    @app.get("/api/obras/<int:obra_id>/rede")
    def rede(obra_id):
        return jsonify(etapa3.estado_rede(banco, obra_id))

    @app.post("/api/obras/<int:obra_id>/rede/<codigo>")
    def editar_rede(obra_id, codigo):
        dados = request.get_json(silent=True) or {}
        return jsonify(etapa3.editar_atividade_obra(
            banco, obra_id, codigo,
            tipo=dados.get("tipo"),
            depende_de=dados.get("depende_de"),
            salvar_na_biblioteca=bool(dados.get("salvar_biblioteca")),
            caminho_biblioteca=caminho_biblioteca,
        ))

    # ------------------------------------------------------------------ etapa 4

    def _biblioteca_opcional():
        try:
            return _biblioteca()
        except ErroBiblioteca:
            return None  # a obra já tem a cópia das atividades; a biblioteca só completa campos

    @app.errorhandler(etapa4.ErroMaoDeObra)
    def erro_mao_de_obra(exc):
        precisa_arquivo = "arquivo da planilha" in str(exc)
        return jsonify({"erro": str(exc), "precisa_arquivo": precisa_arquivo}), 409 if precisa_arquivo else 400

    @app.errorhandler(ErroFuncoes)
    def erro_funcoes(exc):
        return jsonify({"erro": "A tabela de funções (dados/funcoes.xlsx) tem erros: " + str(exc)}), 422

    def _estado(obra_id):
        return jsonify(etapa4.estado_mao_de_obra(banco, obra_id, _biblioteca_opcional()))

    @app.get("/api/obras/<int:obra_id>/mao-de-obra")
    def mao_de_obra(obra_id):
        if not banco.carregar_analises(obra_id):
            return jsonify(etapa4.analisar_obra(banco, obra_id, _biblioteca_opcional()))
        return _estado(obra_id)

    @app.post("/api/obras/<int:obra_id>/mao-de-obra/analisar")
    def reanalisar(obra_id):
        return jsonify(etapa4.analisar_obra(banco, obra_id, _biblioteca_opcional()))

    @app.post("/api/obras/<int:obra_id>/arquivo")
    def anexar_arquivo(obra_id):
        arquivo = request.files.get("arquivo")
        if arquivo is None or not arquivo.filename.lower().endswith((".xlsx", ".xlsm")):
            return _erro("Envie o arquivo .xlsx da planilha desta obra.")
        temporario = uploads / f"obra_{obra_id}_{uuid.uuid4().hex}.xlsx"
        arquivo.save(temporario)
        banco.guardar_arquivo(obra_id, temporario)
        return jsonify(etapa4.analisar_obra(banco, obra_id, _biblioteca_opcional()))

    @app.post("/api/obras/<int:obra_id>/parametros")
    def parametros(obra_id):
        etapa4.salvar_parametros(banco, obra_id, request.get_json(silent=True) or {})
        return _estado(obra_id)

    @app.post("/api/obras/<int:obra_id>/execucao")
    def execucao(obra_id):
        dados = request.get_json(silent=True) or {}
        etapa4.definir_execucao(banco, obra_id, dados.get("atividades") or [], dados.get("execucao"), _biblioteca_opcional())
        return _estado(obra_id)

    @app.post("/api/obras/<int:obra_id>/atividade/<codigo>")
    def atividade_obra(obra_id, codigo):
        dados = request.get_json(silent=True) or {}
        campos = {k: dados[k] for k in ("rendimento", "equipe_padrao", "duracao_manual", "maquinas", "producao_dia")
                  if k in dados}
        try:
            etapa4.definir_atividade(banco, obra_id, codigo, biblioteca=_biblioteca_opcional(), **campos)
        except ValueError:
            return _erro("Valor inválido.")
        return _estado(obra_id)

    @app.post("/api/obras/<int:obra_id>/servico/<int:servico_id>/horas")
    def horas_servico(obra_id, servico_id):
        dados = request.get_json(silent=True) or {}
        return jsonify(etapa4.definir_horas_servico(banco, obra_id, servico_id, dados.get("horas") or {}, _biblioteca_opcional()))

    @app.post("/api/obras/<int:obra_id>/subcomposicao")
    def horas_subcomposicao(obra_id):
        dados = request.get_json(silent=True) or {}
        return jsonify(etapa4.definir_horas_subcomposicao(banco, obra_id, dados.get("codigo"), dados.get("horas") or {},
                                                          dados.get("descricao"), _biblioteca_opcional()))

    # ------------------------------------------------------------------ SINAPI (etapa 5.1)

    sinapi_arquivos: dict[str, str] = {}

    @app.post("/api/sinapi")
    def importar_sinapi():
        """Recebe a tabela analítica (multipart 'arquivo') ou reprocessa um envio anterior com o mapeamento."""
        from mao_de_obra.sinapi import ErroSinapi

        arquivo = request.files.get("arquivo")
        if arquivo is not None:
            if not arquivo.filename.lower().endswith((".xlsx", ".xlsm")):
                return _erro("Envie a planilha .xlsx de composições analíticas do SINAPI.")
            token = uuid.uuid4().hex
            caminho = uploads / f"sinapi_{token}.xlsx"
            arquivo.save(caminho)
            sinapi_arquivos[token] = str(caminho)
            dados = request.form
            mapeamento = None
        else:
            dados = request.get_json(silent=True) or {}
            token = dados.get("token")
            if token not in sinapi_arquivos:
                return _erro("Envie o arquivo do SINAPI de novo.")
            mapeamento = {k: int(v) for k, v in (dados.get("mapeamento") or {}).items() if v not in (None, "")}
        try:
            res = etapa4.importar_sinapi(banco, sinapi_arquivos[token], mapeamento or None, dados.get("aba") or None,
                                         int(dados["linha_cabecalho"]) if dados.get("linha_cabecalho") else None,
                                         biblioteca=_biblioteca_opcional())
        except ErroSinapi as exc:
            return _erro(str(exc))
        res["token"] = token
        return jsonify(res)

    # ------------------------------------------------------------------ etapa 5

    calculos: dict[int, dict[str, Any]] = {}  # obra -> cálculo de cenários em andamento (ou o último)
    trava_calculos = threading.Lock()

    @app.errorhandler(etapa5.ErroCronograma)
    def erro_cronograma(exc):
        return jsonify({"erro": str(exc)}), 400

    @app.get("/api/obras/<int:obra_id>/cronograma/parametros")
    def cronograma_parametros(obra_id):
        return jsonify(etapa5.parametros_cronograma(banco, obra_id, _biblioteca_opcional()))

    @app.post("/api/obras/<int:obra_id>/cronograma/parametros")
    def salvar_cronograma_parametros(obra_id):
        etapa5.salvar_parametros_cronograma(banco, obra_id, request.get_json(silent=True) or {})
        return jsonify(etapa5.parametros_cronograma(banco, obra_id, _biblioteca_opcional()))

    @app.post("/api/obras/<int:obra_id>/cronograma/travar")
    def travar_equipe(obra_id):
        dados = request.get_json(silent=True) or {}
        etapa5.travar_equipe(banco, obra_id, str(dados.get("atividade") or ""), dados.get("pessoas"), _biblioteca_opcional())
        return jsonify(etapa5.parametros_cronograma(banco, obra_id, _biblioteca_opcional()))

    def _estado_calculo(obra_id: int) -> dict[str, Any]:
        c = calculos.get(obra_id)
        if not c:
            return {"rodando": False}
        info = {k: v for k, v in c.items() if k not in ("thread", "parar", "inicio_cenario")}
        if c["rodando"] and c.get("n"):
            parcial = min(0.99, (time.monotonic() - c["inicio_cenario"]) / max(1.0, c["tempo_limite"]))
            info["progresso"] = round((c["cenario"] + parcial) / c["n"], 3)
        return info

    @app.post("/api/obras/<int:obra_id>/cronograma/calcular")
    def calcular_cenarios(obra_id):
        dados = request.get_json(silent=True) or {}
        with trava_calculos:
            if (calculos.get(obra_id) or {}).get("rodando"):
                return _erro("Já há um cálculo em andamento para esta obra.", 409)
            if "prazos" in dados or "tempo_limite" in dados:
                etapa5.salvar_parametros_cronograma(banco, obra_id, {k: dados[k] for k in ("prazos", "tempo_limite") if k in dados})
            biblioteca = _biblioteca_opcional()
            params = banco.carregar_calendario(obra_id)
            prazos = params["prazos"] or etapa5.prazos_padrao(etapa5.prazo_licitacao_meses(banco.carregar_obra(obra_id)["obra"]))
            # valida antes de abrir a thread (erros voltam na hora)
            etapa5.montar_instancia(banco, obra_id, max(prazos) if prazos else 1, biblioteca)
            parar = threading.Event()
            estado = {"rodando": True, "cenario": 0, "n": len(prazos), "prazo": None, "tempo_limite": params["tempo_limite"],
                      "inicio_cenario": time.monotonic(), "solucoes": 0, "melhor": None, "erro": None, "progresso": 0.0,
                      "parar": parar}

            def progresso(info: dict[str, Any]) -> None:
                if info.get("evento") == "inicio":
                    estado.update(cenario=info["cenario"], prazo=info["prazo"], inicio_cenario=time.monotonic(),
                                  solucoes=0, melhor=None)
                else:
                    estado.update(solucoes=info.get("solucoes", 0), melhor=info.get("melhor"))

            def rodar() -> None:
                try:
                    etapa5.calcular_cenarios(banco, obra_id, prazos, biblioteca, progresso=progresso, parar=parar)
                except Exception as exc:  # noqa: BLE001 - mostrado na tela
                    logging.getLogger("cronograma").exception("Erro no cálculo dos cenários da obra %s", obra_id)
                    estado["erro"] = str(exc)
                finally:
                    estado.update(rodando=False, progresso=1.0)

            estado["thread"] = threading.Thread(target=rodar, daemon=True)
            calculos[obra_id] = estado
            estado["thread"].start()
        return jsonify(_estado_calculo(obra_id))

    @app.post("/api/obras/<int:obra_id>/cronograma/limites")
    def limites_atividade(obra_id):
        dados = request.get_json(silent=True) or {}
        etapa5.definir_limites(banco, obra_id, str(dados.get("atividade") or ""), dados.get("equipe_max"),
                               dados.get("maquinas_max"), _biblioteca_opcional())
        return jsonify(etapa5.parametros_cronograma(banco, obra_id, _biblioteca_opcional()))

    @app.post("/api/obras/<int:obra_id>/cronograma/sugestao")
    def aplicar_sugestao(obra_id):
        dados = request.get_json(silent=True) or {}
        etapa5.aplicar_sugestao(banco, obra_id, dados.get("acao") or {}, _biblioteca_opcional())
        return jsonify(etapa5.parametros_cronograma(banco, obra_id, _biblioteca_opcional()))

    @app.get("/api/obras/<int:obra_id>/cronograma/calculo")
    def estado_calculo(obra_id):
        return jsonify(_estado_calculo(obra_id))

    @app.post("/api/obras/<int:obra_id>/cronograma/parar")
    def parar_calculo(obra_id):
        c = calculos.get(obra_id)
        if c and c.get("rodando"):
            c["parar"].set()
        return jsonify(_estado_calculo(obra_id))

    @app.get("/api/obras/<int:obra_id>/cenarios")
    def cenarios(obra_id):
        return jsonify(etapa5.comparacao(banco, obra_id))

    @app.post("/api/obras/<int:obra_id>/cenarios/<int:cenario_id>/escolher")
    def escolher_cenario(obra_id, cenario_id):
        etapa5.escolher_cenario(banco, obra_id, cenario_id)
        return jsonify(etapa5.comparacao(banco, obra_id))

    @app.get("/api/obras/<int:obra_id>/cenarios/<cenario>")
    def cenario(obra_id, cenario):
        return jsonify(etapa5.detalhe_cenario(banco, obra_id, None if cenario == "escolhido" else int(cenario)))

    @app.get("/api/obras/<int:obra_id>/cenarios/<cenario>/excel")
    def cenario_excel(obra_id, cenario):
        cid = None if cenario == "escolhido" else int(cenario)
        dados = etapa5.exportar_equipe_excel(banco, obra_id, cid)
        return Response(dados, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition":
                                 f'attachment; filename="equipe_por_semana_obra_{banco.numero_obra(obra_id)}.xlsx"'})

    # ------------------------------------------------------------------ gerenciar obras salvas

    @app.errorhandler(gestao.ErroObras)
    def erro_obras(exc):
        return jsonify({"erro": str(exc)}), exc.status

    @app.get("/api/obras/<int:obra_id>/etapas")
    def etapas_obra(obra_id):
        return jsonify(gestao.etapas(banco, obra_id))

    @app.get("/api/obras/<int:obra_id>/leitura")
    def leitura_salva(obra_id):
        return jsonify(gestao.leitura_salva(banco, obra_id))

    @app.post("/api/obras/<int:obra_id>/dados")
    def editar_obra(obra_id):
        return jsonify(gestao.editar_obra(banco, obra_id, request.get_json(silent=True) or {}))

    def _excluir(ids):
        with trava_calculos:
            rodando = [i for i, c in calculos.items() if c.get("rodando")]
            r = gestao.excluir(banco, ids, rodando)
            for i in r["excluidas"]:
                calculos.pop(i, None)
        logging.getLogger("cronograma").info("Obras excluídas: %s", r["excluidas"])
        return jsonify(r)

    @app.post("/api/obras/excluir")
    def excluir_obras():
        return _excluir((request.get_json(silent=True) or {}).get("ids") or [])

    @app.delete("/api/obras/<int:obra_id>")
    def excluir_obra(obra_id):
        return _excluir([obra_id])

    return app


def main(argv: list[str] | None = None) -> int:
    """Abre o servidor e o navegador. Se o app já estiver aberto nesta porta, só abre o navegador.

    --atalho: aberto pelo atalho do Windows (pythonw): problemas aparecem numa janela em vez do terminal.
    """
    argv = sys.argv[1:] if argv is None else argv
    janela = "--atalho" in argv
    preparar_saidas()
    configurar_log()
    log = logging.getLogger("cronograma")
    porta = porta_padrao()
    url = f"http://{HOST}:{porta}"
    abrir_navegador = os.environ.get("ABRIR_NAVEGADOR", "1") == "1"

    situacao = verificar_porta(porta)
    if situacao == NOSSO:
        log.info("O app já está aberto em %s: só abre o navegador", url)
        print(f"O Cronograma de obras já está aberto em {url}.")
        if abrir_navegador:
            webbrowser.open(url)
        return 0
    if situacao == OUTRO:
        avisar(f"A porta {porta} está sendo usada por outro programa, então o app não pode abrir.\n\n"
               "Feche o outro programa (ou reinicie o computador) e tente de novo.", janela)
        return 1

    try:
        servidor = make_server(HOST, porta, criar_app(), threaded=True)
    except Exception as exc:  # noqa: BLE001
        log.exception("Falha ao iniciar")
        avisar(f"O app não conseguiu iniciar:\n\n{exc}\n\nDetalhes em logs\\app.log.", janela)
        return 1
    servidor.app.config["AO_FECHAR"] = lambda: threading.Thread(target=servidor.shutdown, daemon=True).start()
    log.info("App aberto em %s (banco %s)", url, servidor.app.config["CAMINHO_BANCO"])
    if abrir_navegador:
        threading.Timer(1.0, webbrowser.open, [url]).start()
    print(f"Cronograma de obras em {url}  (feche pelo botão \"Fechar o app\" ou com Ctrl+C)")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        servidor.server_close()
        log.info("App fechado")
    return 0


if __name__ == "__main__":
    sys.exit(main())
