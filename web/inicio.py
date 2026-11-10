"""Partes da abertura do app que não dependem do Flask: caminhos, log, aviso em janela e "o app já está aberto?".

Só usa a biblioteca padrão, para funcionar mesmo quando faltam pacotes no .venv (o aviso explica o que fazer).
"""
from __future__ import annotations

import json
import logging
import os
import socket
import sys
import urllib.request
from logging.handlers import RotatingFileHandler
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent   # pasta do projeto
PASTA_LOGS = RAIZ / "logs"
NOME_APP = "cronograma-obras"
TITULO = "Cronograma de Obras"
HOST = "127.0.0.1"

LIVRE, NOSSO, OUTRO = "livre", "nosso", "outro"


def caminho_banco_padrao() -> str:
    """CRONOGRAMA_BANCO, se definida; senão cronograma.sqlite3 na pasta do projeto (não na pasta de onde se abriu)."""
    return os.environ.get("CRONOGRAMA_BANCO") or str(RAIZ / "cronograma.sqlite3")


def porta_padrao() -> int:
    return int(os.environ.get("PORTA", "5000"))


def preparar_saidas() -> None:
    """Com pythonw não há console: sys.stdout/sys.stderr são None e um print derrubaria o app."""
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")


def configurar_log(pasta: Path | None = None) -> Path:
    """Erros e avisos vão para logs/app.log (até 1 MB, guarda 3 anteriores)."""
    pasta = Path(pasta or PASTA_LOGS)
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = pasta / "app.log"
    raiz = logging.getLogger()
    for h in [h for h in raiz.handlers if getattr(h, "_cronograma", False)]:
        raiz.removeHandler(h)
        h.close()
    handler = RotatingFileHandler(arquivo, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))
    handler._cronograma = True  # type: ignore[attr-defined]
    raiz.addHandler(handler)
    if raiz.level == logging.NOTSET or raiz.level > logging.INFO:
        raiz.setLevel(logging.INFO)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)  # sem uma linha por requisição
    return arquivo


def avisar(texto: str, janela: bool = True) -> None:
    """Grava no log e mostra o motivo: janela no Windows (aberto pelo atalho) ou texto no terminal."""
    logging.getLogger("cronograma").error(texto)
    if janela and os.name == "nt":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, texto, TITULO, 0x10 | 0x40000)  # ícone de erro, por cima
            return
        except Exception:  # noqa: BLE001
            pass
    if sys.stderr is not None:
        print(texto, file=sys.stderr)


def verificar_porta(porta: int, host: str = HOST, espera: float = 1.5) -> str:
    """'livre'; 'nosso' (este app já está aberto nessa porta) ou 'outro' (a porta é de outro programa)."""
    try:
        with socket.create_connection((host, porta), timeout=espera):
            pass
    except OSError:
        return LIVRE
    try:
        with urllib.request.urlopen(f"http://{host}:{porta}/api/sobre", timeout=espera) as r:
            if json.loads(r.read().decode("utf-8")).get("app") == NOME_APP:
                return NOSSO
    except Exception:  # noqa: BLE001 - qualquer resposta que não seja a nossa
        pass
    return OUTRO
