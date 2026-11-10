"""Abrir o app sem o CMD: caminho do banco, app já aberto, botão de fechar, log e avisos."""
from __future__ import annotations

import http.server
import json
import logging
import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path

import pytest
from werkzeug.serving import make_server

from armazenamento import Banco
from web import app as modulo_app
from web import atalho, inicio
from web.app import criar_app

RAIZ = Path(__file__).resolve().parent.parent


def porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def sem_log_no_projeto(tmp_path, monkeypatch):
    """Log em pasta temporária (e tira o handler no fim, para não vazar para os outros testes)."""
    monkeypatch.setattr(inicio, "PASTA_LOGS", tmp_path / "logs")
    yield tmp_path / "logs" / "app.log"
    raiz = logging.getLogger()
    for h in [h for h in raiz.handlers if getattr(h, "_cronograma", False)]:
        raiz.removeHandler(h)
        h.close()


@pytest.fixture
def avisos(monkeypatch):
    lista = []
    monkeypatch.setattr(modulo_app, "avisar", lambda texto, janela=True: lista.append((texto, janela)))
    monkeypatch.setattr(atalho, "avisar", lambda texto, janela=True: lista.append((texto, janela)))
    return lista


@pytest.fixture
def nosso_servidor(tmp_path):
    """O app rodando de verdade numa porta livre (como se já tivesse sido aberto pelo atalho)."""
    porta = porta_livre()
    srv = make_server("127.0.0.1", porta, criar_app(str(tmp_path / "aberto.sqlite3")), threaded=True)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield porta
    srv.shutdown()
    srv.server_close()


@pytest.fixture
def outro_programa(tmp_path):
    """Um servidor HTTP qualquer (não é o nosso) ocupando uma porta."""
    porta = porta_livre()

    class Silencioso(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", porta), Silencioso)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield porta
    srv.shutdown()
    srv.server_close()


# ------------------------------------------------------------------ banco sempre na pasta do projeto


def test_banco_padrao_na_pasta_do_projeto(tmp_path, monkeypatch):
    monkeypatch.delenv("CRONOGRAMA_BANCO", raising=False)
    monkeypatch.chdir(tmp_path)  # abrir de outra pasta não muda nada
    assert Path(inicio.caminho_banco_padrao()) == RAIZ / "cronograma.sqlite3"


def test_criar_app_usa_a_pasta_do_projeto_nao_a_pasta_atual(tmp_path, monkeypatch):
    projeto, outra = tmp_path / "projeto", tmp_path / "outra_pasta"
    projeto.mkdir()
    outra.mkdir()
    monkeypatch.delenv("CRONOGRAMA_BANCO", raising=False)
    monkeypatch.setattr(inicio, "RAIZ", projeto)
    monkeypatch.chdir(outra)
    app = criar_app()
    assert Path(app.config["CAMINHO_BANCO"]) == projeto / "cronograma.sqlite3"
    assert (projeto / "cronograma.sqlite3").exists() and not (outra / "cronograma.sqlite3").exists()
    assert Banco(app.config["CAMINHO_BANCO"]).pasta_arquivos == projeto / "arquivos_obras"


def test_variavel_cronograma_banco_continua_valendo(tmp_path, monkeypatch):
    caminho = tmp_path / "meu_banco.sqlite3"
    monkeypatch.setenv("CRONOGRAMA_BANCO", str(caminho))
    assert inicio.caminho_banco_padrao() == str(caminho)
    app = criar_app()
    assert app.config["CAMINHO_BANCO"] == str(caminho) and caminho.exists()


# ------------------------------------------------------------------ app já aberto


def test_verificar_porta(nosso_servidor, outro_programa):
    assert inicio.verificar_porta(porta_livre()) == inicio.LIVRE
    assert inicio.verificar_porta(nosso_servidor) == inicio.NOSSO
    assert inicio.verificar_porta(outro_programa) == inicio.OUTRO


def test_rota_sobre(tmp_path):
    c = criar_app(str(tmp_path / "b.sqlite3")).test_client()
    d = c.get("/api/sobre").get_json()
    assert d["app"] == "cronograma-obras" and Path(d["pasta"]) == RAIZ


def test_clicar_de_novo_so_abre_o_navegador(nosso_servidor, monkeypatch, sem_log_no_projeto, avisos):
    abertos = []
    monkeypatch.setenv("PORTA", str(nosso_servidor))
    monkeypatch.setenv("ABRIR_NAVEGADOR", "1")
    monkeypatch.setattr(modulo_app.webbrowser, "open", lambda url: abertos.append(url))
    monkeypatch.setattr(modulo_app, "make_server", lambda *a, **k: pytest.fail("subiu outro servidor"))
    assert modulo_app.main(["--atalho"]) == 0
    assert abertos == [f"http://127.0.0.1:{nosso_servidor}"]
    assert avisos == []
    assert "já está aberto" in sem_log_no_projeto.read_text(encoding="utf-8")


def test_porta_de_outro_programa_avisa(outro_programa, monkeypatch, sem_log_no_projeto, avisos):
    monkeypatch.setenv("PORTA", str(outro_programa))
    monkeypatch.setattr(modulo_app, "make_server", lambda *a, **k: pytest.fail("tentou subir o servidor"))
    assert modulo_app.main(["--atalho"]) == 1
    (texto, janela), = avisos
    assert f"porta {outro_programa}" in texto and "outro programa" in texto and janela is True
    # pelo terminal (python -m web.app) o aviso não é em janela
    avisos.clear()
    assert modulo_app.main([]) == 1
    assert avisos[0][1] is False


def test_falha_ao_iniciar_avisa_e_registra(tmp_path, monkeypatch, sem_log_no_projeto, avisos):
    monkeypatch.setenv("PORTA", str(porta_livre()))
    monkeypatch.setenv("CRONOGRAMA_BANCO", str(tmp_path / "b.sqlite3"))

    def falha(*a, **k):
        raise OSError("acesso negado à porta")

    monkeypatch.setattr(modulo_app, "make_server", falha)
    assert modulo_app.main(["--atalho"]) == 1
    assert "acesso negado à porta" in avisos[0][0]
    assert "acesso negado à porta" in sem_log_no_projeto.read_text(encoding="utf-8")


# ------------------------------------------------------------------ fechar o app


def test_rota_fechar(tmp_path):
    chamadas = []
    c = criar_app(str(tmp_path / "b.sqlite3"), ao_fechar=lambda: chamadas.append(1)).test_client()
    assert c.post("/api/fechar").status_code == 403          # sem o cabeçalho (ex.: outro site)
    assert chamadas == []
    r = c.post("/api/fechar", headers={"X-Fechar": "1"})
    assert r.status_code == 200 and r.get_json() == {"ok": True}
    for _ in range(50):
        if chamadas:
            break
        time.sleep(0.05)
    assert chamadas == [1]


def test_rota_fechar_sem_servidor_do_app(tmp_path):
    c = criar_app(str(tmp_path / "b.sqlite3")).test_client()
    r = c.post("/api/fechar", headers={"X-Fechar": "1"})
    assert r.status_code == 409 and "não foi aberto pelo app" in r.get_json()["erro"]


def test_main_abre_e_o_botao_fecha(tmp_path, monkeypatch, sem_log_no_projeto, avisos):
    porta = porta_livre()
    monkeypatch.setenv("PORTA", str(porta))
    monkeypatch.setenv("ABRIR_NAVEGADOR", "0")
    monkeypatch.setenv("CRONOGRAMA_BANCO", str(tmp_path / "b.sqlite3"))
    resultado = []
    t = threading.Thread(target=lambda: resultado.append(modulo_app.main([])), daemon=True)
    t.start()
    for _ in range(100):
        if inicio.verificar_porta(porta) == inicio.NOSSO:
            break
        time.sleep(0.05)
    else:
        pytest.fail("o app não abriu")
    pedido = urllib.request.Request(f"http://127.0.0.1:{porta}/api/fechar", method="POST", headers={"X-Fechar": "1"})
    with urllib.request.urlopen(pedido, timeout=5) as r:
        assert json.loads(r.read()) == {"ok": True}
    t.join(timeout=10)
    assert not t.is_alive() and resultado == [0]
    assert inicio.verificar_porta(porta) == inicio.LIVRE
    log = sem_log_no_projeto.read_text(encoding="utf-8")
    assert "App aberto" in log and "Fechado pelo botão" in log and "App fechado" in log


def test_todas_as_paginas_tem_o_botao_fechar():
    paginas = sorted((RAIZ / "web" / "static").glob("*.html"))
    assert len(paginas) >= 6
    for p in paginas:
        assert '<script src="/static/topo.js"></script>' in p.read_text(encoding="utf-8"), p.name
    assert "Fechar o app" in (RAIZ / "web" / "static" / "topo.js").read_text(encoding="utf-8")


# ------------------------------------------------------------------ log e atalho


def test_erro_de_rota_vai_para_o_log(tmp_path, sem_log_no_projeto):
    inicio.configurar_log()
    app = criar_app(str(tmp_path / "b.sqlite3"))

    @app.get("/explode")
    def explode():
        raise RuntimeError("falha de teste 123")

    assert app.test_client().get("/explode").status_code == 500
    texto = sem_log_no_projeto.read_text(encoding="utf-8")
    assert "falha de teste 123" in texto and "Traceback" in texto


def test_log_fora_do_git():
    assert "logs/" in (RAIZ / ".gitignore").read_text(encoding="utf-8").split()


def test_atalho_sem_pacotes_mostra_aviso(monkeypatch, sem_log_no_projeto, avisos):
    monkeypatch.setitem(sys.modules, "web.app", None)  # simula import falhando (ex.: Flask não instalado)
    assert atalho.main() == 1
    (texto, _), = avisos
    assert "faltam pacotes" in texto and "requirements.txt" in texto
    assert "Falha ao carregar o app" in sem_log_no_projeto.read_text(encoding="utf-8")


def test_atalho_chama_o_app_em_modo_janela(monkeypatch, sem_log_no_projeto):
    recebido = []
    monkeypatch.setattr(modulo_app, "main", lambda argv=None: recebido.append(argv) or 0)
    assert atalho.main() == 0
    assert recebido == [["--atalho"]]


def test_scripts_do_windows():
    pasta = RAIZ / "windows"
    for nome in ("abrir.vbs", "atualizar.vbs"):
        bruto = (pasta / nome).read_bytes()
        assert bruto.startswith(b"\xff\xfe"), nome  # UTF-16 (o Windows Script Host lê acentos assim)
        texto = bruto.decode("utf-16")
        assert "\r\n" in texto
    abrir = (pasta / "abrir.vbs").read_bytes().decode("utf-16")
    assert r".venv\Scripts\pythonw.exe" in abrir and "-m web.atalho" in abrir and ", 0, False" in abrir
    for nome in ("criar_atalhos.ps1", "atualizar.ps1"):
        assert (pasta / nome).read_bytes().startswith(b"\xef\xbb\xbf"), nome  # BOM: acentos no PowerShell 5
    criar = (pasta / "criar_atalhos.ps1").read_text(encoding="utf-8-sig")
    assert "GetFolderPath('Desktop')" in criar and "GetFolderPath('Programs')" in criar and "WScript.Shell" in criar
    assert "Cronograma de Obras" in criar and "Atualizar Cronograma de Obras" in criar
    atualizar = (pasta / "atualizar.ps1").read_text(encoding="utf-8-sig")
    assert "'pull'" in atualizar and "requirements.txt" in atualizar and "/api/fechar" in atualizar
    for ico in ("cronograma.ico", "atualizar.ico"):
        assert (pasta / ico).read_bytes()[:4] == b"\x00\x00\x01\x00"
