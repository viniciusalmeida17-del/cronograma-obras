# Cronograma de obras

App local para montar o cronograma de uma obra a partir da planilha orçamentária da licitação.

| Etapa | O que faz | Especificação |
|---|---|---|
| 2 | Lê a planilha (.xlsx), separa grupos e serviços, confere os totais, tela de conferência | `ETAPA_2_LEITOR_DE_PLANILHA.md` |
| 3 | Liga cada serviço a uma atividade da biblioteca, guarda as escolhas do usuário, monta a rede de atividades da obra | `ETAPA_3_LIGAR_SERVICOS_ATIVIDADES.md` |
| 4 | Horas por função e de equipamento a partir das composições, própria × terceirizada, duração com a equipe padrão, resumo da obra | `ETAPA_4_MAO_DE_OBRA_E_DURACAO.md` |

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
| `mao_de_obra/` | Etapa 4, sem dependência da interface. |
| `  funcoes.py` | Tabela de funções (`dados/funcoes.xlsx`) e classificação das linhas: mão de obra, equipamento (CHP/CHI), subcomposição. |
| `  composicoes.py` | Lê as composições: formato A (abas por disciplina) e formato B (aba CPU, só para itens sem o A). |
| `  analise.py` | Horas por unidade de cada serviço, expandindo subcomposições que são itens da planilha e usando o banco de coeficientes. |
| `  calculo.py` | Estimativas (custo × razão horas/custo), duração com a equipe padrão, resumo por função, cobertura, pendências. |
| `  obra.py` | Aplica a etapa 4 a uma obra gravada no banco. |
| `dados/` | `biblioteca_atividades.xlsx` (biblioteca padrão), `funcoes.xlsx` (funções) e `palavras_subcomposicao.txt` (palavras que indicam serviço), todos editáveis. |
| `armazenamento/` | SQLite: `obras`, `grupos`, `servicos` (com `atividade_biblioteca`, `status_ligacao`, `regra_usada`), `memoria_ligacoes`, `obra_atividades`, `obra_dependencias` e as tabelas da etapa 4 (`armazenamento/banco_etapa4.py`). Bancos antigos são migrados sozinhos. Uma cópia do .xlsx de cada obra fica em `arquivos_obras/`, ao lado do banco. |
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

## Etapa 4 — mão de obra e duração

1. Na tela da sequência, "Seguir para mão de obra e duração". O app lê as composições do arquivo da obra
   (formato A nas abas por disciplina; formato B da aba CPU para o que faltar) e mostra em quais abas achou.
2. **Horas por serviço** (origem registrada):
   - `composicao`: linhas de mão de obra reconhecidas pela `funcoes.xlsx` (primeiro termo no começo da descrição),
     mais as subcomposições que são itens da planilha, expandidas em profundidade (horas × coeficiente);
   - `banco`: banco de coeficientes, alimentado por toda planilha importada e pelo que o usuário digita;
     serve para planilhas futuras sem composições;
   - `estimado` (amarelo): o que sobrou (subcomposição pendente ou serviço sem composição) =
     custo × (horas ÷ custo dos serviços completos da mesma atividade → etapa → obra);
   - `manual`: horas por unidade digitadas no serviço; vão para o banco;
   - `sem_mao_de_obra`: só material ou equipamento.
   Subcomposição pendente = insumo sem composição cuja descrição tem uma palavra de `dados/palavras_subcomposicao.txt`
   (palavra inteira, ignorando o trecho depois de " PARA " e atributos como "APLICAÇÃO:"). Dá para digitar as horas dela,
   que valem para todo serviço que a usa, nesta e nas próximas obras.
3. **Parâmetros da obra**: horas/semana (44), dias/semana (5 ou 6), rendimento (90%: horas ÷ 0,9) e mudanças de jornada
   (guardadas para a etapa 5).
4. **Própria × terceirizada**: valor inicial da coluna `execucao_padrao`; as `perguntar` precisam de resposta
   (com "aplicar à etapa inteira"). Terceirizada continua com horas para a duração, mas sai do resumo por função.
5. **Duração** (dias úteis, para cima): função principal com `equipe_padrao` pessoas; as outras na proporção
   (mínimo 1); maior entre funções e equipamentos (horas ÷ (máquinas × horas/dia); 1 máquina de cada por padrão,
   editável por equipamento em cada atividade, de 1 a 20). `duracao_fixa_dias` = dias corridos.
   Sem horas (ex.: terceirizada sem composição) = duração digitada, pendência obrigatória antes da etapa 5.
6. **Resumo**: equipe indireta (fixa durante toda a obra e por período), horas ajustadas por função com a média
   de pessoas no prazo da licitação, cobertura por origem e lista de pendências.
