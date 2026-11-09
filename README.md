# Cronograma de obras

App local para montar o cronograma de uma obra a partir da planilha orçamentária da licitação.

| Etapa | O que faz | Especificação |
|---|---|---|
| 2 | Lê a planilha (.xlsx), separa grupos e serviços, confere os totais, tela de conferência | `ETAPA_2_LEITOR_DE_PLANILHA.md` |
| 3 | Liga cada serviço a uma atividade da biblioteca, guarda as escolhas do usuário, monta a rede de atividades da obra | `ETAPA_3_LIGAR_SERVICOS_ATIVIDADES.md` |

## Como rodar

```bash
pip install -r requirements.txt
python -m web.app          # abre http://127.0.0.1:5000 no navegador
python -m pytest           # testes automáticos
```

Variáveis opcionais: `PORTA` (padrão 5000), `CRONOGRAMA_BANCO` (padrão `cronograma.sqlite3`),
`CRONOGRAMA_BIBLIOTECA` (padrão `dados/biblioteca_atividades.xlsx`), `ABRIR_NAVEGADOR=0` para não abrir o navegador sozinho.

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
| `atividades/` | Etapa 3, também sem dependência da interface. |
| `  biblioteca.py` | Lê e valida o Excel da biblioteca (códigos, `depende_de`, tipos, períodos, regras, ciclos); grava alterações com cópia de segurança em `dados/backup/`. |
| `  reconhecimento.py` | Liga serviços às atividades: memória → regras (prioridade, profundidade do grupo) → `ambiguo` / `sem_regra`. |
| `  rede.py` | Atividades da obra, herança de dependências (com soma das esperas), ligação à LIM-01, ordem topológica, edição por obra. |
| `  obra.py` | Aplica a etapa 3 a uma obra gravada no banco (usado pela tela e pelos testes). |
| `dados/` | `biblioteca_atividades.xlsx`: biblioteca padrão, editada pelo engenheiro no Excel. |
| `armazenamento/` | SQLite: `obras`, `grupos`, `servicos` (com `atividade_biblioteca`, `status_ligacao`, `regra_usada`), `memoria_ligacoes`, `obra_atividades`, `obra_dependencias`. Bancos da etapa 2 são migrados sozinhos. |
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

## Etapa 3 — ligação e rede

1. Depois de salvar a importação, o link "Seguir para a ligação" abre a tela de ligação.
2. O app liga cada serviço: primeiro pela **memória** (mesma base + código + nome do grupo imediato já confirmados antes),
   depois pelas **regras** da biblioteca. O que não decidir fica em **Pendentes** (ambíguo: atividades empatadas primeiro; sem regra: lista completa com busca).
3. "Trocar" muda a atividade de um serviço; se houver outros com o mesmo código no mesmo grupo, o app pergunta se aplica a eles também.
   Toda escolha vira `confirmado` e vai para a memória.
4. "Confirmar e seguir" monta a rede da obra:
   - entram as atividades com serviço, as sem custo (tipo `aguardar` ou sem nenhuma regra na biblioteca: EST-03, HID-03, TES-01) se as atividades das quais dependem estiverem na obra, e sempre TES-01 e LIM-01;
   - quem dependia de uma atividade que saiu herda as dependências dela, somando as esperas (`A+x` e `A → C+y` vira `C+(x+y)`);
   - atividades sem sucessor passam a ser pré-requisito da LIM-01;
   - indiretas ficam fora da sequência, com o período guardado.
5. Na tela da sequência dá para mudar tipo e dependências só nesta obra (com checagem de ciclo), ou marcar
   "salvar também na biblioteca padrão" (grava no Excel, com cópia de segurança antes).
