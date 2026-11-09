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
from leitor_planilha import NATUREZAS, ErroLeitura, ler_planilha

PASTA_ESTATICA = Path(__file__).parent / "static"
CAMPOS_OBRA_EDITAVEIS = ("nome", "prazo_valor", "prazo_unidade", "bdi", "desoneracao", "referencias")
UNIDADES_PRAZO = ("dias", "semanas", "meses", "anos")


def criar_app(caminho_banco: str | None = None, pasta_uploads: str | None = None) -> Flask:
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
        return jsonify({"id": obra_id, "mensagem": f"Importação salva (obra nº {obra_id})."})

    @app.get("/api/importacoes")
    def listar():
        return jsonify(banco.listar_obras())

    @app.get("/api/importacoes/<int:obra_id>")
    def carregar(obra_id):
        dados = banco.carregar_obra(obra_id)
        return jsonify(dados) if dados else _erro("Importação não encontrada.", 404)

    return app


def main() -> None:
    porta = int(os.environ.get("PORTA", "5000"))
    app = criar_app()
    if os.environ.get("ABRIR_NAVEGADOR", "1") == "1":
        threading.Timer(1.0, lambda: webbrowser.open(f"http://127.0.0.1:{porta}")).start()
    app.run(host="127.0.0.1", port=porta, debug=False)


if __name__ == "__main__":
    main()
