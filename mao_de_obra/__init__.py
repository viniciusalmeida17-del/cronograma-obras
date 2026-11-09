"""Etapa 4: mão de obra e duração das atividades.

Módulos sem dependência da interface:
- funcoes: tabela de funções (dados/funcoes.xlsx) e classificação das linhas das composições.
- composicoes: leitura das composições (formato A por disciplina; formato B da aba CPU).
- analise: horas por função e de equipamento por serviço, com expansão de subcomposições.
- calculo: estimativas, duração com a equipe padrão, resumo da obra (funções puras).
- obra: aplica a etapa 4 a uma obra gravada no banco.
"""
from .calculo import calcular_duracao, calcular_obra
from .composicoes import ler_composicoes
from .funcoes import carregar_funcoes, carregar_palavras_subcomposicao

__all__ = ["calcular_duracao", "calcular_obra", "ler_composicoes", "carregar_funcoes", "carregar_palavras_subcomposicao"]
