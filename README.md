# Cronograma de obras

App local para montar o cronograma de uma obra a partir da planilha orçamentária da licitação.

| Etapa | O que faz | Especificação |
|---|---|---|
| 2 | Lê a planilha (.xlsx), separa grupos e serviços, confere os totais, tela de conferência | `ETAPA_2_LEITOR_DE_PLANILHA.md` |
| 3 | Liga cada serviço a uma atividade da biblioteca, guarda as escolhas do usuário, monta a rede de atividades da obra | `ETAPA_3_LIGAR_SERVICOS_ATIVIDADES.md` |
| 4 | Horas por função e de equipamento a partir das composições, própria × terceirizada, duração com a equipe padrão, resumo da obra | `ETAPA_4_MAO_DE_OBRA_E_DURACAO.md` |
| 5 | Cronograma com datas (otimizador OR-Tools), equipe por semana sem demitir e recontratar, comparação de prazos | `ETAPA_5_CRONOGRAMA_E_EQUIPES.md` |
| 5.1 | Correções: elos início-início, concretagem, equipes até 20 e máquinas, funções da empresa, custo real × receita, diagnóstico de prazo, ociosidade, referências e SINAPI, Gantt, planilha sem preços sem BDI | `ETAPA_5_1_CORRECOES.md` |

## Como rodar

O otimizador da etapa 5 usa o **OR-Tools**, que tem pacote para Python **3.10 a 3.14**, mas **ainda não para o 3.15**.
Por isso o projeto roda num ambiente virtual com Python 3.14.

### Windows (uma vez só, na pasta do projeto)

```bat
py install 3.14
py -3.14 -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
```

(Se o `py install` não existir no seu computador, instale o Python 3.14 pelo site python.org e use os mesmos comandos a partir do `py -3.14 -m venv .venv`.)

### No dia a dia (Windows)

```bat
.venv\Scripts\activate
python -m web.app
python -m pytest
```

O `web.app` abre http://127.0.0.1:5000 no navegador; o `pytest` roda os testes (uns 2 minutos).

### Linux / macOS

```bash
python3.14 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m web.app
python -m pytest
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
| `cronograma/` | Etapa 5, sem dependência da interface. |
| `  calendario.py` | Dias úteis (5 ou 6 por semana), feriados nacionais fixos e móveis (Páscoa), feriados locais, jornada por semana. |
| `  modelo.py` | Tarefas e modos (1 até `equipe_max` da função principal; as outras na proporção; modos sem ganho de prazo são retirados). |
| `  agenda.py` | Solução inicial (busca local), caminho crítico, folgas, equipe por semana, custos e a verificação de todas as restrições. |
| `  otimizador.py` | Modelo CP-SAT: início e modo de cada atividade, contratados por função e semana, sobe-e-desce, prazo, máximos. |
| `  obra.py` | Aplica a etapa 5 a uma obra do banco: parâmetros, custos por hora, indiretos por tempo, cenários, comparação, Excel. |
| `  sinapi.py` | (em `mao_de_obra/`) Importa a tabela analítica do SINAPI para o banco de coeficientes. |
| `dados/` | `biblioteca_atividades.xlsx` (biblioteca padrão), `funcoes.xlsx` (funções e aba Juntar funções), `produtividade_referencia.xlsx` (coeficientes SINAPI pesquisados) e `palavras_subcomposicao.txt` (palavras que indicam serviço), todos editáveis. |
| `armazenamento/` | SQLite: `obras`, `grupos`, `servicos` (com `atividade_biblioteca`, `status_ligacao`, `regra_usada`), `memoria_ligacoes`, `obra_atividades`, `obra_dependencias` as tabelas da etapa 4 (`armazenamento/banco_etapa4.py`) e as da etapa 5 (`armazenamento/banco_etapa5.py`: `obra_calendario`, `cenarios`, `cenario_atividades`, `cenario_equipe_semana`, `custos_hora_padrao`). Bancos antigos são migrados sozinhos. Uma cópia do .xlsx de cada obra fica em `arquivos_obras/`, ao lado do banco. |
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

## Etapa 5 — cronograma, equipes e prazos

1. Na tela de mão de obra (sem pendências), "Seguir para o cronograma".
2. **Parâmetros**: data de início (obrigatória), feriados locais, limite das rígidas (5 dias úteis), tempo limite por cenário (60 s),
   máximo de pessoas no canteiro e por função (opcionais), custo por hora de cada função e equipes travadas.
   - Custo por hora inicial = média, ponderada pelas horas, do preço das linhas de mão de obra das composições; quando a função
     tem linhas "com encargos complementares", só elas entram (Pedreiro R$ 24,43 na planilha de teste). O valor salvo vale
     para a obra e vira o padrão da próxima.
3. **Calendário**: esperas (`+3d`) e `duracao_fixa_dias` em dias corridos; durações com equipe em dias úteis; B começa no primeiro
   dia útil depois de término de A + espera. Jornada da semana de início vale para a atividade inteira.
4. **Otimizador** (OR-Tools CP-SAT), por cenário:
   - decide o início e o tamanho da equipe de cada atividade própria e os contratados de cada função por semana;
   - dependências, rígidas até o limite depois de liberadas, "aguardar" logo que liberada, capacidade diária ≤ contratados da
     semana, cada função sobe até um pico e depois só desce (não demite e recontrata), prazo e máximos;
   - minimiza mão de obra paga (contratados × horas da semana × custo/h, inclusive as horas paradas) + indiretos por tempo,
     com desempate por terminar mais cedo;
   - parte de uma solução inicial (equipe padrão ou mínima, aumentando a do caminho crítico até caber, e depois troca de modos
     enquanto o custo cair); mostra se a solução é ótima ou a melhor encontrada no tempo.
   - Prazo impossível: informa o menor prazo com a equipe máxima e o caminho crítico.
5. **Indiretos por tempo**: itens em MÊS. Obra toda = valor ÷ prazo da licitação por mês; entre atividades = valor ÷ quantidade
   por mês; custo = R$/mês × duração real do período. M2/MÊS, % e o resto ficam fixos ("não varia com o prazo nesta versão").
6. **Cenários**: padrão prazo − 3, − 2, − 1 e o próprio (meses); tabela comparativa; o mais barato fica destacado e o escolhido
   vira o cronograma da obra. Gantt (cores por tipo, caminho crítico, folga, faixas das indiretas), equipe por semana (gráfico com
   a parte parada hachurada, tabela semana × função com entrada, pico e saída, equipe indireta à parte, exportação para Excel)
   e resumo.

## Etapa 5.1 — correções

- **Dependências** (`depende_de`): `CÓDIGO[:TIPO][+ESPERA]`. `TI` término-início (padrão) ou `II` início-início;
  `+Nd` dias corridos, `+Ndu` dias úteis. `A:II+N`: B começa N depois do início de A e **não termina antes** do
  término de A + N. Formato antigo (`FUN-04+3d`) continua aceito. Na herança, fica o tipo do elo de quem fica e as
  esperas somam (unidades diferentes → dias úteis, 7 corridos ≈ 5 úteis). EST-03 = 28 dias corridos; só a REV-01 espera a cura.
- **Concretagem** (`tipo_producao = concretagem`): duração ≥ teto(m³ da atividade ÷ (m³ por caminhão × caminhões por dia));
  parâmetros da obra (padrão 8 m³ e 3 caminhões).
- **Equipes e máquinas**: `equipe_max` vazio = 20; o otimizador testa 1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 20. Máquinas de cada
  equipamento de 1 até o máximo (padrão 6, por obra e por atividade); em atividade própria cada máquina traz 1 Operador/Motorista.
- **Funções da empresa** (`funcoes.xlsx`): Servente, Pedreiro, Pedreiro de acabamento, Carpinteiro, Armador, Bombeiro,
  Ajudante de bombeiro, Eletricista, Ajudante de eletricista, Pintor (+ Operador/Motorista). Termos com `&` exigem as
  duas palavras (ex.: `AUXILIAR&ELETRICISTA`); os outros ajudantes viram Servente. Aba **Juntar funções**: Carpinteiro e
  Armador → Pedreiro é possível, mas desligado por padrão (liga por obra na tela de mão de obra).
- **Obras salvas acompanham a `funcoes.xlsx`**: cada obra guarda a assinatura da tabela usada; quando a tabela muda, a obra
  é reprocessada ao ser aberta. Se o "juntar" da obra era só o padrão antigo, passa a seguir o novo; escolha diferente
  do padrão é mantida. Os cenários já calculados não mudam: recalcule na tela de cronograma.
- **Horas**: composição → banco de coeficientes → **referência** (`produtividade_referencia.xlsx`) → estimado.
  Estimativa acima de 3 × a média da atividade é limitada e marcada em vermelho. Tela **Importar SINAPI**
  (tabela analítica da CAIXA, colunas pelo cabeçalho ou mapeamento manual). Terceirizadas: **produção por dia** calcula
  a duração e vira padrão para as próximas obras.
- **Prazo da licitação**: é o cenário principal e sempre é calculado; cenários só iguais ou menores. Se não couber:
  diagnóstico com o menor prazo, o caminho crítico (duração, equipe e máquinas usadas/máximas) e sugestões com o ganho
  calculado, com botão "aplicar e recalcular".
- **Custo real × receita**: salário + encargos (padrão 80%) por função, indiretos reais por mês e valor contratado dos
  terceirizados (padrões lembrados para a próxima obra; enquanto não preencher, aviso "referência da licitação").
  Critério de pagamento das indiretas: proporcional (padrão), mensal ou fixo. A tabela mostra receita e custo que
  variam com o prazo, o **resultado** e a diferença para o principal (só a parte que varia com o prazo).
- **Ociosidade**: sem contar feriados (coluna à parte), total e por função, com as 3 maiores causas. Funções que
  **podem sair e voltar** (padrão Servente e Pedreiro) não seguem o sobe-e-desce, mas cada redução dura ≥ 2 semanas.
  Terceirizadas podem ser feitas em até 3 partes de ≥ 5 dias úteis.
- **Gantt**: escala dia/semana/mês, etapas que abrem e fecham (barra-resumo), linhas de hoje e da data limite, setas de
  dependência (II tracejada), só o caminho crítico, terceirizadas em partes.
- **Leitor**: planilha só com preços com BDI é aceita; os sem BDI são calculados pelo BDI (um aviso só).
