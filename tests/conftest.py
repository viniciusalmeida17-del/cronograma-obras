import csv
import sys
from pathlib import Path

import openpyxl
import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from leitor_planilha import ler_planilha  # noqa: E402

DADOS = Path(__file__).parent / "dados"
ARQUIVO_TESTE = DADOS / "Concorrencia_2_2024_PLANILHA_ORCAMENTARIA_EDITAVEL.XLSX"
CSV_ESPERADO = DADOS / "itens_extraidos_teste.csv"


@pytest.fixture(scope="session")
def arquivo_teste() -> Path:
    return ARQUIVO_TESTE


@pytest.fixture(scope="session")
def resultado(arquivo_teste):
    return ler_planilha(arquivo_teste)


@pytest.fixture(scope="session")
def servicos_por_item(resultado):
    return {s["item"]: s for s in resultado["servicos"]}


@pytest.fixture(scope="session")
def esperados():
    with open(CSV_ESPERADO, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter=";"))


@pytest.fixture(scope="session")
def valores_planilha(arquivo_teste):
    """Valores (já calculados) da aba PLANILHA original, como lista de linhas."""
    wb = openpyxl.load_workbook(arquivo_teste, data_only=True, read_only=True)
    linhas = [list(r) for r in wb["PLANILHA"].iter_rows(values_only=True)]
    wb.close()
    return linhas


def gravar_copia(
    destino: Path,
    linhas: list[list],
    nome_aba: str = "PLANILHA",
    abas_antes: tuple[str, ...] = (),
) -> Path:
    """Grava as linhas numa planilha nova (só valores), com abas extras antes."""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for nome in abas_antes:
        ws = wb.create_sheet(nome)
        ws.append(["CRONOGRAMA FÍSICO-FINANCEIRO"])
        ws.append(["ITEM", "DESCRIÇÃO", "MÊS 1", "MÊS 2"])
    ws = wb.create_sheet(nome_aba)
    for linha in linhas:
        ws.append(list(linha))
    wb.save(destino)
    return destino


# ------------------------------------------------------------------ etapa 3

BIBLIOTECA = RAIZ / "dados" / "biblioteca_atividades.xlsx"
CSV_MAPEAMENTO = Path(__file__).parent / "mapeamento_esperado_teste.csv"


@pytest.fixture(scope="session")
def biblioteca():
    from atividades import carregar_biblioteca

    return carregar_biblioteca(BIBLIOTECA)


@pytest.fixture(scope="session")
def servicos_ligados(resultado, biblioteca):
    """Serviços da planilha de teste já ligados às atividades (cópias)."""
    from atividades import ligar_servicos

    servicos = [dict(s) for s in resultado["servicos"]]
    for s, l in zip(servicos, ligar_servicos(servicos, resultado["grupos"], biblioteca)):
        s.update(l)
    return servicos


@pytest.fixture(scope="session")
def mapeamento_esperado():
    with open(CSV_MAPEAMENTO, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter=";"))


def copiar_biblioteca(destino: Path, alterar=None) -> Path:
    """Copia a biblioteca padrão; `alterar(wb)` pode mudar o conteúdo antes de salvar."""
    wb = openpyxl.load_workbook(BIBLIOTECA)
    if alterar:
        alterar(wb)
    wb.save(destino)
    return destino


def linha_da_atividade(ws, codigo: str) -> int:
    for linha in range(2, ws.max_row + 1):
        if ws.cell(linha, 1).value == codigo:
            return linha
    raise KeyError(codigo)
