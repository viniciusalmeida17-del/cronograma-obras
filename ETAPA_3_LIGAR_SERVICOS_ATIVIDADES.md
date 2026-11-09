# Etapa 3 — Ligar os serviços da planilha às atividades

Especificação para o Claude Code. Continua o projeto `cronograma-obras` (etapa 2 já pronta: leitor de planilha + banco SQLite + tela de conferência).

## Objetivo

Depois de importar a planilha, o app:
1. liga cada serviço a uma **atividade** da biblioteca (ex.: os 9 itens de fôrma, armação e lastro da fundação viram a atividade FUN-03);
2. mostra o que ligou sozinho e pergunta só o que não conseguiu decidir;
3. guarda as respostas do usuário para as próximas obras;
4. monta a **rede de atividades da obra**: quais atividades existem nela e a ordem entre elas.

Nesta etapa ainda **não há durações, equipes nem datas** (etapas 4 e 5). O resultado é a lista de atividades da obra, com os serviços e o custo de cada uma, e a sequência.

## Arquivos que acompanham esta especificação

| Arquivo | Onde colocar | Para quê |
|---|---|---|
| `biblioteca_atividades.xlsx` | `dados/biblioteca_atividades.xlsx` | Biblioteca padrão: 80 atividades (aba Atividades) e 89 regras de reconhecimento (aba Regras). A aba Legenda explica cada coluna. |
| `mapeamento_esperado_teste.csv` | `tests/` | Resultado esperado para os 374 serviços da planilha de teste (separado por `;`). |

A biblioteca fica em Excel de propósito: o usuário (engenheiro) vai editar no Excel. O app lê esse arquivo; não deixar a biblioteca escrita dentro do código.

## 1. Carregar e validar a biblioteca

Ler as abas `Atividades` e `Regras` (ignorar a linha TOTAL e as colunas `itens_na_planilha_teste` e `total_com_bdi_teste`, que são só de conferência).

**Atividades**: `codigo`, `etapa`, `atividade`, `depende_de`, `tipo`, `equipe_principal`, `observacao`, `periodo_de`, `periodo_ate`.
- `depende_de`: códigos separados por vírgula; cada um pode ter espera em dias corridos: `FUN-04+3d`.
- `tipo`: `rigida`, `flexivel`, `aguardar` ou `indireta`.
- `periodo_de` / `periodo_ate`: só para indiretas (`INICIO_OBRA`, `FIM_OBRA` ou um código de atividade).

**Regras**: `ordem`, `prioridade`, `atividade`, `termos_no_grupo`, `termos_na_descricao`, `natureza`.

Validações (mostrar erro claro, com a linha do Excel, e não seguir):
- código repetido; código citado em `depende_de`, em `periodo_*` ou numa regra que não existe;
- formato inválido em `depende_de` (aceitar só `XXX-00` ou `XXX-00+Nd`);
- tipo inválido;
- **ciclo** nas dependências (A depende de B, que depende de A), mostrando o caminho do ciclo.

## 2. Reconhecimento automático

Para cada serviço importado na etapa 2:

### 2.1 Preparação
- Normalizar textos: sem acento, maiúsculas.
- `grupos do item` = lista dos nomes dos grupos acima dele, do mais geral ao mais específico. Ex.: item `9.1.6.3` → [`INSTALAÇÕES ELÉTRICAS, TELECOMUNICAÇÕES E SPDA…`, `INSTALAÇÕES ELÉTRICAS - FORNECIMENTO…`, `ELETRODUTOS E ACESSÓRIOS…`], com profundidades 1, 2 e 3.

### 2.2 Memória (vem antes das regras)
Se o usuário já confirmou uma ligação para um serviço com **mesma base + mesmo código + mesmo nome de grupo imediato**, usar a mesma atividade (status `memoria`).

O grupo entra na chave porque o mesmo código vai para atividades diferentes conforme o grupo. Na planilha de teste, o lastro de concreto magro (SINAPI 96616) aparece na Fundação (→ FUN-03), na Contenção (→ CON-01) e na Quadra (→ QUA-01).

### 2.3 Regras
Uma regra **vale** para o serviço quando todas as condições preenchidas são verdadeiras (coluna vazia não restringe):
- `termos_no_grupo`: algum termo (separados por `|`) aparece em algum dos grupos do item. Termo começando com `^` precisa estar no **começo** do nome do grupo. Guardar a **profundidade** do grupo mais específico que casou.
- `termos_na_descricao`: algum termo aparece na descrição do serviço.
- `natureza`: igual à natureza do serviço (producao, tempo, transporte, taxa).

**Escolha** entre as regras que valem:
1. menor `prioridade` (1 é a mais específica);
2. empate → maior profundidade de grupo casado (subgrupo vence grupo);
3. ainda empatado entre **atividades diferentes** → status `ambiguo`, e o usuário escolhe entre elas;
4. nenhuma regra → status `sem_regra`, e o usuário escolhe na lista completa.

Guardar em cada serviço: `atividade_biblioteca`, `status_ligacao` (`automatico`, `memoria`, `confirmado`, `ambiguo`, `sem_regra`) e `regra_usada` (número da ordem).

Resultado esperado na planilha de teste: **374 serviços ligados automaticamente, 0 ambíguos, 0 sem regra**, exatamente como no `mapeamento_esperado_teste.csv`.

## 3. Tela de ligação

Abre depois da tela de conferência da etapa 2.

- **Resumo no topo**: "374 serviços — 374 ligados automaticamente, 0 pendentes".
- **Pendentes primeiro**: ambíguos e sem regra, com a descrição completa, os grupos e as opções (no ambíguo, as atividades empatadas primeiro; depois a lista completa com busca).
- **Visão por atividade**: lista das atividades na ordem da etapa da obra; cada uma abre e mostra seus serviços, com a quantidade de itens e o total com BDI.
- **Trocar a atividade de um serviço** por uma lista com busca (código ou nome). Ao trocar, perguntar: "aplicar também aos outros N serviços com o mesmo código neste grupo?".
- Toda escolha ou troca feita pelo usuário vira status `confirmado` e é gravada na **memória** (item 2.2).
- Botão para confirmar e seguir.

## 4. Rede de atividades da obra

Depois da ligação, montar as atividades **desta obra**:

1. **Entram**: as atividades com pelo menos um serviço ligado, mais as de tipo `aguardar` e as sem custo da biblioteca (`EST-03`, `HID-03`, `TES-01`), mas só se as atividades das quais elas dependem estiverem na obra (TES-01 entra sempre).
2. **Saem**: as demais. Quando uma atividade sai, quem dependia dela **herda as dependências dela**, com as esperas. Exemplo: numa obra sem estacas (sem FUN-01), FUN-02 passa a depender de LOC-01.
3. **Sem sucessor**: toda atividade (fora as indiretas) que não for pré-requisito de nenhuma outra recebe a LIM-01 como sucessora, ou seja, precisa terminar antes da limpeza final.
4. **Indiretas** não entram na sequência; ficam guardadas com o período (`periodo_de` / `periodo_ate`) para a etapa de custos.

**Edição por obra**: o usuário pode mudar, só nesta obra, o `tipo` e o `depende_de` de uma atividade, e acrescentar ou remover dependências. Validar ciclo a cada mudança. Isso **não altera a biblioteca padrão**, a não ser que ele clique em "salvar também na biblioteca padrão", que grava no Excel. Fazer cópia de segurança do arquivo antes de gravar.

**Tela da sequência**: lista em ordem de execução possível (ordenação topológica), mostrando código, nome, tipo (com cor: rígida branca, flexível verde, aguardar amarela), depende de, quantidade de itens e total. Não precisa ser gráfico ainda; o Gantt vem na etapa 5.

## 5. Banco de dados

Acrescentar ao SQLite da etapa 2:
- `servicos`: preencher `atividade_biblioteca`; novos campos `status_ligacao`, `regra_usada`.
- `memoria_ligacoes`: base, código, grupo imediato normalizado, atividade, data.
- `obra_atividades`: obra, código, nome, tipo, total com BDI, total sem BDI, número de itens, periodo_de, periodo_ate.
- `obra_dependencias`: obra, atividade, depende_de, espera_dias.

A biblioteca padrão continua no Excel. A obra guarda sua própria cópia das atividades e dependências, para não mudar quando a biblioteca for editada depois.

## 6. Fora desta etapa

- Durações, produtividade e equipes (etapa 4).
- Datas, Gantt e encaixe das atividades flexíveis nas semanas mais vazias (etapa 5).
- Distribuição dos custos indiretos no tempo (etapa 6).
- Correções pendentes do leitor de planilha (ex.: planilhas sem colunas sem BDI). Serão feitas depois, todas juntas, numa especificação própria.

## 7. Testes automáticos

Com a planilha `Concorrencia_2_2024_PLANILHA_ORCAMENTARIA_EDITAVEL.XLSX` e a `biblioteca_atividades.xlsx`:

- biblioteca carrega sem erro: 80 atividades, 89 regras, sem ciclo;
- os 374 serviços batem com o `mapeamento_esperado_teste.csv` (item → atividade e número da regra), com 0 ambíguos e 0 sem regra;
- casos de contexto: `4.10` → FUN-03, `6.4` → CON-01, `15.2.3` → QUA-01 (mesmo serviço, grupos diferentes); `5.1.2` → EST-01 (e não IND-06, porque a regra do escoramento exige natureza `tempo`); `5.1.11` → IND-06; `9.1.8.1` → ELE-08; `13.14` → SER-03; `9.3.1.1` → SPDA-01;
- soma dos totais com BDI por atividade = R$ 5.669.771,17;
- rede da obra: 77 atividades com itens + EST-03, HID-03 e TES-01 = **80 atividades** (nesta obra todas entram); sem ciclo; LIM-01 é a última;
- **remoção com herança**: tirar FUN-01 de uma cópia da obra → FUN-02 passa a depender de LOC-01;
- **espera herdada**: tirar FUN-04 de uma cópia → FUN-05 passa a depender de FUN-03 (FUN-05 dependia de `FUN-04+3d` e FUN-04 dependia de FUN-03 sem espera: a espera de 3 dias é mantida, `FUN-03+3d`);
- **memória**: trocar `4.10` para outra atividade, reimportar a mesma planilha → `4.10` volta com status `memoria` e a atividade escolhida; `6.4` (mesmo código, outro grupo) continua em CON-01;
- **ambíguo**: criar uma biblioteca de teste com duas regras empatadas para o mesmo item → status `ambiguo`, com as duas opções;
- **validação**: biblioteca de teste com ciclo → erro mostrando o caminho; dependência para código inexistente → erro com a linha.

## Regra para herança de esperas (item 4.2)

Se B depende de `A+x` e A (que sai) depende de `C+y`, então B passa a depender de `C+(x+y)`.
