"""Confere se há versão nova do app no GitHub e inicia a atualização (Windows: windows/atualizar.ps1 -Reabrir)."""
from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from .inicio import RAIZ

INTERVALO = 10 * 60          # segundos entre duas consultas ao GitHub
TEMPO_GIT = 20               # tempo máximo de cada comando git
SEM_JANELA = 0x08000000 if os.name == "nt" else 0   # CREATE_NO_WINDOW: sem piscar janela preta no pythonw

_cache: dict[str, Any] = {}
_trava = threading.Lock()


def _git(raiz: Path, *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=raiz, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=TEMPO_GIT, creationflags=SEM_JANELA,
                       env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"})
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip() or f"git {' '.join(args)} falhou")
    return r.stdout.strip()


def versao_atual(raiz: Path = RAIZ) -> str | None:
    try:
        return _git(raiz, "rev-parse", "--short", "HEAD")
    except Exception:  # noqa: BLE001 - sem git ou baixado como ZIP
        return None


def verificar(raiz: Path = RAIZ, forcar: bool = False) -> dict[str, Any]:
    """{"disponivel", "versao", "nova", "quantidade", "novidades", "motivo"}. Sem internet ou sem git: disponivel=False."""
    chave = str(raiz)
    with _trava:
        c = _cache.get(chave)
        if c and not forcar and time.monotonic() - c["quando"] < INTERVALO:
            return c["resultado"]
        resultado: dict[str, Any] = {"disponivel": False, "versao": None, "nova": None, "quantidade": 0,
                                     "novidades": [], "motivo": None}
        try:
            resultado["versao"] = _git(raiz, "rev-parse", "--short", "HEAD")
            _git(raiz, "fetch", "--quiet")
            n = int(_git(raiz, "rev-list", "--count", "HEAD..@{u}"))
            if n:
                resultado.update(disponivel=True, quantidade=n, nova=_git(raiz, "rev-parse", "--short", "@{u}"),
                                 novidades=_git(raiz, "log", "--format=%s", "HEAD..@{u}").splitlines()[:10])
        except Exception as exc:  # noqa: BLE001 - não atrapalha o uso do app
            resultado["motivo"] = str(exc)[:300]
            logging.getLogger("cronograma").info("Não foi possível conferir atualização: %s", resultado["motivo"])
        _cache[chave] = {"quando": time.monotonic(), "resultado": resultado}
        return resultado


def iniciar_atualizacao_windows(raiz: Path = RAIZ) -> None:
    """Roda windows/atualizar.ps1 -Reabrir separado do app: ele fecha o app, atualiza e abre de novo."""
    if os.name != "nt":
        raise NotImplementedError("A atualização pela tela só funciona no Windows. Use git pull e "
                                  "pip install -r requirements.txt.")
    ps1 = raiz / "windows" / "atualizar.ps1"
    subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", str(ps1),
         "-Reabrir"],
        cwd=raiz, creationflags=SEM_JANELA | 0x00000200,  # + CREATE_NEW_PROCESS_GROUP: continua após o app fechar
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True,
    )
    _cache.clear()
