"""Classificação preliminar da natureza do serviço pela unidade."""
from __future__ import annotations

from .texto import unidade_canonica

PRODUCAO = "producao"
TEMPO = "tempo"
TRANSPORTE = "transporte"
TAXA = "taxa"

NATUREZAS = (PRODUCAO, TEMPO, TRANSPORTE, TAXA)

_UNIDADES_TEMPO = {"MES", "M2/MES"}


def classificar_natureza(unidade: str | None) -> str:
    u = unidade_canonica(unidade) or ""
    if u == "%":
        return TAXA
    if "XKM" in u:
        return TRANSPORTE
    if u in _UNIDADES_TEMPO or u.endswith("/MES") or u.endswith("XMES"):
        return TEMPO
    return PRODUCAO
