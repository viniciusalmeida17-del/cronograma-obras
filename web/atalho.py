"""Ponto de entrada do atalho do Windows: windows/abrir.vbs roda  .venv\\Scripts\\pythonw.exe -m web.atalho

Sem janela preta. Se faltar pacote no .venv ou o app não conseguir abrir, mostra uma janela com o motivo
e grava em logs/app.log.
"""
from __future__ import annotations

import logging
import sys

from web.inicio import avisar, configurar_log, preparar_saidas


def main() -> int:
    preparar_saidas()
    configurar_log()
    try:
        from web.app import main as principal
    except Exception as exc:  # noqa: BLE001
        logging.getLogger("cronograma").exception("Falha ao carregar o app")
        avisar("O app não conseguiu iniciar: faltam pacotes no ambiente do Python (.venv).\n\n"
               f"Detalhe: {exc}\n\n"
               "Use o atalho \"Atualizar Cronograma de Obras\" ou, na pasta do projeto:\n"
               ".venv\\Scripts\\python -m pip install -r requirements.txt")
        return 1
    try:
        return principal(["--atalho"])
    except Exception as exc:  # noqa: BLE001
        logging.getLogger("cronograma").exception("Erro inesperado")
        avisar(f"O app parou por um erro inesperado:\n\n{exc}\n\nDetalhes em logs\\app.log.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
