"""Etapa 3: biblioteca de atividades, reconhecimento dos serviços e rede de atividades da obra.

Módulos independentes da interface:
- biblioteca: lê e valida o Excel da biblioteca (atividades e regras); grava alterações com backup.
- reconhecimento: liga serviços às atividades (memória → regras → ambíguo/sem regra).
- rede: escolhe as atividades da obra, herda dependências das que saem, liga ao fim, ordena.
- obra: aplica tudo a uma obra gravada no banco SQLite.
"""
from .biblioteca import Biblioteca, ErroBiblioteca, carregar_biblioteca, caminho_biblioteca
from .reconhecimento import ligar_servicos, reconhecer, resumo_ligacao
from .rede import ErroRede, montar_rede, sequencia

__all__ = [
    "Biblioteca", "ErroBiblioteca", "carregar_biblioteca", "caminho_biblioteca",
    "ligar_servicos", "reconhecer", "resumo_ligacao", "ErroRede", "montar_rede", "sequencia",
]
