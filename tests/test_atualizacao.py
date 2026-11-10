"""Aviso de atualização: confere no "GitHub" (um repositório local de origem) e o botão Atualizar agora."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from web import atualizacao
from web.app import criar_app

RAIZ = Path(__file__).resolve().parent.parent


def git(pasta, *args):
    return subprocess.run(["git", "-c", "user.name=Teste", "-c", "user.email=teste@exemplo.com",
                           "-c", "init.defaultBranch=main", *args],
                          cwd=pasta, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repos(tmp_path):
    """origem (o GitHub), a cópia do usuário e a cópia de quem publica as mudanças."""
    origem = tmp_path / "origem.git"
    git(tmp_path, "init", "--bare", str(origem))
    dev = tmp_path / "dev"
    git(tmp_path, "clone", str(origem), str(dev))
    (dev / "a.txt").write_text("1")
    git(dev, "add", ".")
    git(dev, "commit", "-m", "Primeira versão")
    git(dev, "push", "-u", "origin", "HEAD:main")
    usuario = tmp_path / "usuario"
    git(tmp_path, "clone", str(origem), str(usuario))
    atualizacao._cache.clear()
    yield dev, usuario
    atualizacao._cache.clear()


def publicar(dev, mensagem):
    (dev / "a.txt").write_text(mensagem)
    git(dev, "commit", "-am", mensagem)
    git(dev, "push", "origin", "HEAD:main")


def test_sem_atualizacao(repos):
    _, usuario = repos
    r = atualizacao.verificar(usuario)
    assert r["disponivel"] is False and r["quantidade"] == 0 and r["motivo"] is None
    assert r["versao"] == git(usuario, "rev-parse", "--short", "HEAD")


def test_com_atualizacao_lista_as_novidades(repos):
    dev, usuario = repos
    publicar(dev, "Ajudantes de eletricista e bombeiro")
    publicar(dev, "Botão Fechar o app")
    r = atualizacao.verificar(usuario)
    assert r["disponivel"] is True and r["quantidade"] == 2
    assert r["novidades"] == ["Botão Fechar o app", "Ajudantes de eletricista e bombeiro"]
    assert r["nova"] == git(dev, "rev-parse", "--short", "HEAD")
    # a cópia do usuário não muda só por conferir (git fetch, sem pull)
    assert (usuario / "a.txt").read_text() == "1"


def test_consulta_guardada_por_10_minutos(repos):
    dev, usuario = repos
    assert atualizacao.verificar(usuario)["disponivel"] is False
    publicar(dev, "Mudança nova")
    assert atualizacao.verificar(usuario)["disponivel"] is False      # ainda a consulta guardada
    assert atualizacao.verificar(usuario, forcar=True)["disponivel"] is True


def test_sem_git_ou_sem_internet_nao_atrapalha(tmp_path, repos):
    zip_baixado = tmp_path / "baixado_como_zip"
    zip_baixado.mkdir()
    r = atualizacao.verificar(zip_baixado)
    assert r["disponivel"] is False and r["motivo"]
    _, usuario = repos
    git(usuario, "remote", "set-url", "origin", str(tmp_path / "nao_existe.git"))   # "sem internet"
    r = atualizacao.verificar(usuario, forcar=True)
    assert r["disponivel"] is False and r["motivo"]
    assert atualizacao.versao_atual(zip_baixado) is None


def test_rota_atualizacao(tmp_path):
    app = criar_app(str(tmp_path / "b.sqlite3"))
    app.config["VERIFICAR_ATUALIZACAO"] = lambda: {"disponivel": True, "quantidade": 1, "novidades": ["X"], "versao": "abc"}
    assert app.test_client().get("/api/atualizacao").get_json()["novidades"] == ["X"]


def test_sobre_tem_a_versao(tmp_path):
    d = criar_app(str(tmp_path / "b.sqlite3")).test_client().get("/api/sobre").get_json()
    assert d["versao"] == atualizacao.versao_atual(RAIZ)


def test_rota_atualizar(tmp_path):
    iniciadas = []
    app = criar_app(str(tmp_path / "b.sqlite3"), ao_fechar=lambda: None)
    app.config["INICIAR_ATUALIZACAO"] = lambda: iniciadas.append(1)
    c = app.test_client()
    assert c.post("/api/atualizar").status_code == 403          # sem o cabeçalho (ex.: outro site)
    assert iniciadas == []
    r = c.post("/api/atualizar", headers={"X-Atualizar": "1"})
    assert r.status_code == 200 and iniciadas == [1]


def test_rota_atualizar_fora_do_app_ou_fora_do_windows(tmp_path):
    app = criar_app(str(tmp_path / "b.sqlite3"))                 # servidor que não foi aberto pelo app
    r = app.test_client().post("/api/atualizar", headers={"X-Atualizar": "1"})
    assert r.status_code == 409 and "atalho" in r.get_json()["erro"]

    app = criar_app(str(tmp_path / "c.sqlite3"), ao_fechar=lambda: None)

    def nao_windows():
        raise NotImplementedError("só no Windows")

    app.config["INICIAR_ATUALIZACAO"] = nao_windows
    r = app.test_client().post("/api/atualizar", headers={"X-Atualizar": "1"})
    assert r.status_code == 501 and "Windows" in r.get_json()["erro"]


@pytest.mark.skipif(__import__("os").name == "nt", reason="fora do Windows")
def test_iniciar_fora_do_windows():
    with pytest.raises(NotImplementedError):
        atualizacao.iniciar_atualizacao_windows()


def test_script_reabre_o_app_e_a_tela_oferece_atualizar():
    ps1 = (RAIZ / "windows" / "atualizar.ps1").read_text(encoding="utf-8-sig")
    assert "param([switch]$Reabrir)" in ps1 and "Abrir-App" in ps1 and "ABRIR_NAVEGADOR = '0'" in ps1
    js = (RAIZ / "web" / "static" / "topo.js").read_text(encoding="utf-8")
    assert "/api/atualizacao" in js and "Atualizar agora" in js and "Agora não" in js and "/api/atualizar" in js
