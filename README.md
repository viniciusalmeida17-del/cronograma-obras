# Cronograma de obras — Etapa 2: leitor da planilha de licitação

Lê a planilha orçamentária da licitação (.xlsx), separa grupos e serviços, confere os totais
e mostra tudo numa tela de conferência antes de salvar. Especificação: `ETAPA_2_LEITOR_DE_PLANILHA.md`.

## Como rodar

```bash
pip install -r requirements.txt
python -m web.app          # abre http://127.0.0.1:5000 no navegador
python -m pytest           # testes automáticos
```

Variáveis opcionais: `PORTA` (padrão 5000), `CRONOGRAMA_BANCO` (padrão `cronograma.sqlite3`),
`ABRIR_NAVEGADOR=0` para não abrir o navegador sozinho.

## Estrutura

| Pasta | Conteúdo |
|---|---|
| `leitor_planilha/` | Leitura do Excel, **sem nenhuma dependência da interface**. `ler_planilha(caminho, aba=None, mapeamento=None, linha_cabecalho=None)` devolve um dicionário pronto para JSON. |
| `  texto.py` | Normalização (sem acento, maiúsculas), números em formato BR, item como texto, unidades. |
| `  colunas.py` | Acha a linha de cabeçalho (primeiras 30 linhas) e mapeia as colunas **pelo nome**. |
| `  dados_obra.py` | Nome da obra, prazo, BDI, desoneração e referências (acima do cabeçalho). |
| `  natureza.py` | Natureza preliminar pela unidade: produção / tempo / transporte / taxa. |
| `  validacao.py` | Total geral (tolerância R$ 1,00), total por grupo e quantidade × preço (R$ 0,05). |
| `  leitor.py` | Escolha da aba, classificação das linhas, hierarquia pelo prefixo do item. |
| `armazenamento/` | SQLite: tabelas `obras`, `grupos`, `servicos` (com `atividade_biblioteca`, `etapa_obra`, `local` vazios). |
| `web/` | Servidor Flask local + tela de conferência (HTML/JS puro, sem build). |
| `tests/` | Testes com o arquivo da Concorrência 2/2024 e o CSV esperado em `tests/dados/`. |

## Regras principais

- **Aba**: `PLANILHA` (sem diferenciar maiúsculas/acentos); senão, a primeira aba com cabeçalho; o usuário pode trocar.
- **Serviço**: tem código, unidade e quantidade > 0. **Grupo**: tem item e descrição, sem código.
  Linhas vazias/só zeros são puladas; linhas com valores sem item nem descrição (totais soltos) são ignoradas e listadas como informação.
- **Hierarquia**: grupo pai = maior prefixo do item que seja um grupo (`4.2` → `4`; `9.1.1.3` → `9.1.1`).
- **Item sempre texto** (`4.10` ≠ `4.1`). Se o item estiver gravado como número no Excel, usa o formato da célula e gera aviso.
- **Unidade**: maiúsculas, sem espaços. `unidade` guarda o texto da planilha; `unidade_normalizada` trata `M2/MÊS` = `M2XMÊS`.
- **Arredondamento**: reais com 2 casas, quantidades com 4.

## Fluxo na tela

1. Escolher o .xlsx → "Ler planilha".
2. Conferir aba e colunas (se faltar coluna obrigatória, a tela de mapeamento abre sozinha; "Ajustar colunas" abre a qualquer momento).
3. Conferir/editar dados da obra (o **prazo é obrigatório**), ver o aviso verde/vermelho e a lista de alertas (clique na linha para ir até ela).
4. Navegar na árvore de grupos, filtrar por grupo/natureza, buscar texto, corrigir a natureza de um serviço.
5. "Confirmar e salvar importação" grava no SQLite.
