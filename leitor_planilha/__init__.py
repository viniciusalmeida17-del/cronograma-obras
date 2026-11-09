"""Leitura da planilha orçamentária de licitação (Etapa 2).

Módulo independente da interface: recebe um .xlsx e devolve um dicionário com
obra, grupos, serviços, alertas e validação.
"""
from .colunas import CAMPOS, OBRIGATORIOS, ROTULOS_CAMPOS
from .leitor import ErroLeitura, ler_planilha
from .natureza import NATUREZAS, classificar_natureza
from .validacao import formatar_reais, validar

__all__ = [
    "CAMPOS",
    "OBRIGATORIOS",
    "ROTULOS_CAMPOS",
    "ErroLeitura",
    "ler_planilha",
    "NATUREZAS",
    "classificar_natureza",
    "formatar_reais",
    "validar",
]
