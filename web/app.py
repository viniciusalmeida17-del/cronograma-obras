"""Interface web local (Flask) da Etapa 2 — leitura e conferência da planilha.

Executar:  python -m web.app   (abre em http://127.0.0.1:5000)
"""
from __future__ import annotations

import os
import tempfile
import threading
import uuid
import webbrowser
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request, send_from_directory

from armazenamento import Banco
from atividades import ErroBiblioteca, carregar_biblioteca
from atividades import obra as etapa3
from leitor_planilha import NATUREZAS, ErroLeitura, ler_planilha
from mao_de_obra import obra as etapa4
from mao_de_obra.funcoes import ErroFuncoes

PASTA_ESTATICA = Path(__file__).parent / "static"
CAMPOS_OBRA_EDITAVEIS = ("nome", "prazo_valor", "prazo_unidade", "bdi", "desoneracao", "referencias")
UNIDADES_PRAZO = ("dias", "semanas", "meses", "anos")


def criar_app(
    caminho_banco: str | None = None, pasta_uploads: str | None = None, caminho_biblioteca: str | None = None
) -> Flask:
    app = Flask(__name__, static_folder=None)
    app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024
    banco = Banco(caminho_banco or os.environ.get("CRONOGRAMA_BANCO", "cronograma.sqlite3"))
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
        return jsonify({"id": obra_id, "mensagem": f"Importação salva (obra nº {obra_id})."})

    @app.get("/api/importacoes")
    def listar():
        return jsonify(banco.listar_obras())

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
        campos = {k: dados[k] for k in ("rendimento", "equipe_padrao", "duracao_manual", "maquinas") if k in dados}
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

    return app


def main() -> None:
    porta = int(os.environ.get("PORTA", "5000"))
    app = criar_app()
    if os.environ.get("ABRIR_NAVEGADOR", "1") == "1":
        threading.Timer(1.0, lambda: webbrowser.open(f"http://127.0.0.1:{porta}")).start()
    app.run(host="127.0.0.1", port=porta, debug=False)


if __name__ == "__main__":
    main()
