"""Funções de normalização e limpeza de texto/números vindos do Excel."""
from __future__ import annotations

import re
import unicodedata
from typing import Any


def sem_acento(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalizar(valor: Any) -> str:
    """Texto para comparação: sem acento, maiúsculo, espaços/quebras de linha colapsados."""
    if valor is None:
        return ""
    texto = sem_acento(str(valor)).upper()
    return re.sub(r"\s+", " ", texto).strip()


def limpar_texto(valor: Any) -> str | None:
    """Texto para exibição/armazenamento: só tira espaços do início e do fim."""
    if valor is None:
        return None
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    texto = str(valor).strip()
    return texto or None


def para_numero(valor: Any) -> float | None:
    """Converte célula em número. Aceita textos no formato brasileiro ("1.234,56", "25,22%")."""
    if valor is None or isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor).strip().replace("R$", "").replace(" ", "")
    if not texto:
        return None
    porcentagem = texto.endswith("%")
    texto = texto.rstrip("%")
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        numero = float(texto)
    except ValueError:
        return None
    return numero / 100 if porcentagem else numero


def arredondar_reais(valor: float | None) -> float | None:
    return None if valor is None else round(valor + 0.0, 2)


def arredondar_qtd(valor: float | None) -> float | None:
    return None if valor is None else round(valor + 0.0, 4)


def texto_item(valor: Any, formato_numero: str | None = None) -> str | None:
    """Número do item sempre como texto ("4.10" nunca vira "4.1").

    Se a célula estiver como número no Excel, usa o formato da célula para recuperar
    as casas decimais exibidas (ex.: 4.1 com formato "0.00" -> "4.10").
    """
    if valor is None or isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        return str(valor)
    if isinstance(valor, float):
        if valor.is_integer():
            return str(int(valor))
        casas = _casas_decimais_formato(formato_numero)
        return f"{valor:.{casas}f}" if casas else repr(valor)
    texto = str(valor).strip().rstrip(".").strip()
    texto = re.sub(r"\s+", "", texto)
    return texto or None


def _casas_decimais_formato(formato: str | None) -> int:
    if not formato or formato == "General":
        return 0
    m = re.search(r"\.(0+)", formato)
    return len(m.group(1)) if m else 0


def unidade_limpa(valor: Any) -> str | None:
    texto = limpar_texto(valor)
    if texto is None:
        return None
    return re.sub(r"\s+", "", texto).upper()


_EQUIVALENCIAS_UNIDADE = {
    "M²": "M2",
    "M³": "M3",
    "M2XMES": "M2/MES",
    "M2/MES": "M2/MES",
    "MES": "MES",
    "MESES": "MES",
}


def unidade_canonica(unidade: str | None) -> str | None:
    """Forma canônica para comparação de unidades (M2XMÊS == M2/MÊS, M² == M2...)."""
    if not unidade:
        return None
    u = unidade.upper().replace("²", "2").replace("³", "3")
    u = sem_acento(u).replace(" ", "")
    return _EQUIVALENCIAS_UNIDADE.get(u, u)
