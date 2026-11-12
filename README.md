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

### Atalhos do Windows (uma vez só, depois de criar o `.venv`)

Na pasta do projeto, rode:

```bat
powershell -ExecutionPolicy Bypass -File windows\criar_atalhos.ps1
```

Ele cria dois atalhos, na área de trabalho (a de verdade, mesmo se ela estiver no OneDrive) e no menu Iniciar:

- **Cronograma de Obras**: abre o app com dois cliques, sem janela preta (`windows\abrir.vbs` roda o
  `.venv\Scripts\pythonw.exe -m web.atalho`). Se o app já estiver aberto, só abre o navegador de novo.
- **Atualizar Cronograma de Obras**: fecha o app se estiver aberto, faz `git pull`, instala o `requirements.txt` no
  `.venv` e mostra numa janela se deu certo (com as novidades) ou qual foi o erro.

**Aviso de atualização:** ao abrir o app, ele confere no GitHub se há versão nova (no máximo a cada 10 minutos; sem
internet, nada aparece). Se houver, surge uma faixa no topo com as novidades e os botões **Atualizar agora** e
**Agora não** (esconde até fechar a aba). Atualizar agora roda o `windows\atualizar.ps1 -Reabrir`: o app fecha, atualiza,
abre de novo e a página recarrega sozinha; se der erro, aparece uma janela com o motivo e o app abre na versão anterior.

Para fechar o app, use o botão **Fechar o app** no topo de qualquer página. Se o app não conseguir abrir (falta o
`.venv`, faltam pacotes, a porta 5000 está ocupada por outro programa), aparece uma janela com o motivo. Erros ficam em
`logs\app.log` e o registro das atualizações em `logs\atualizacao.log` (a pasta `logs/` não vai para o git).
Se mudar a pasta do projeto de lugar, rode o `criar_atalhos.ps1` de novo.

### Pelo terminal (Windows)

```bat
.venv\Scripts\activate
python -m web.app
python -m pytest
```

O `web.app` abre http://127.0.0.1:5000 no navegador (feche pelo botão "Fechar o app" ou com Ctrl+C); o `pytest` roda
os testes (uns 2 minutos).

### Linux / macOS

```bash
python3.14 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m web.app
python -m pytest
```

O banco `cronograma.sqlite3` e a pasta `arquivos_obras/` ficam sempre na pasta do projeto, de onde quer que o app
seja aberto.

Variáveis opcionais: `PORTA` (padrão 5000), `CRONOGRAMA_BANCO` (padrão `cronograma.sqlite3` na pasta do projeto;
a pasta `arquivos_obras/` fica ao lado do banco),
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
| `  biblioteca.py` | Lê e valida o Excel da biblioteca (códigos, `depende_de`, `depende_de_norma`, `trocar_funcoes`, tipos, períodos, regras, ciclos); grava alterações com cópia de segurança em `dados/backup/`. |
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
| `  agenda.py` | Solução inicial (busca local), caminho crítico, folgas, equipe por semana (uma entrada, até N entradas ou livre), custo de saída e volta, relatório de continuidade, terceirizados por semana e total na obra, estimativa com o limite do canteiro, custos e a verificação de todas as restrições. |
| `  otimizador.py` | Modelo CP-SAT: início e modo de cada atividade, contratados por função e semana, sobe-e-desce, prazo, máximos (o do canteiro com os terceirizados, por dia). |
| `  obra.py` | Aplica a etapa 5 a uma obra do banco: parâmetros, custos por hora, indiretos por tempo, cenários, comparação, Excel. |
| `  sinapi.py` | (em `mao_de_obra/`) Importa a tabela analítica do SINAPI para o banco de coeficientes. |
| `dados/` | `biblioteca_atividades.xlsx` (biblioteca padrão), `funcoes.xlsx` (funções e aba Juntar funções), `produtividade_referencia.xlsx` (coeficientes SINAPI pesquisados) e `palavras_subcomposicao.txt` (palavras que indicam serviço), todos editáveis. |
| `armazenamento/` | SQLite: `obras`, `grupos`, `servicos` (com `atividade_biblioteca`, `status_ligacao`, `regra_usada`), `memoria_ligacoes`, `obra_atividades`, `obra_dependencias` as tabelas da etapa 4 (`armazenamento/banco_etapa4.py`) e as da etapa 5 (`armazenamento/banco_etapa5.py`: `obra_calendario`, `cenarios`, `cenario_atividades`, `cenario_equipe_semana`, `cenario_terceirizados_semana`, `custos_hora_padrao`; `pessoas_terceirizado_padrao` fica quando a obra é excluída). Bancos antigos são migrados sozinhos. Uma cópia do .xlsx de cada obra fica em `arquivos_obras/`, ao lado do banco. |
| `web/` | Servidor Flask local + telas (HTML/JS puro, sem build). `inicio.py`: caminhos, log, aviso em janela e "o app já está aberto?" (só biblioteca padrão); `atalho.py`: entrada do atalho do Windows; `atualizacao.py`: confere se há versão nova (git fetch) e inicia a atualização. |
| `windows/` | `criar_atalhos.ps1` (cria os atalhos), `abrir.vbs`, `atualizar.vbs` + `atualizar.ps1`, ícones (`gerar_icones.py` refaz os .ico). |
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

## Obras salvas

- **Número da obra**: o nº que aparece nas telas (lista, confirmação de exclusão, barra de etapas, títulos, mensagens,
  nome do Excel exportado) é a **ordem de importação entre as obras que existem**: a mais antiga é a 1. Ao excluir, as
  que sobram são renumeradas. O id interno do banco não muda e é o que vai nos links (`?obra=`) e na API.
- As telas mostram só o nome da etapa no topo (Leitura, Ligação, Sequência, Mão de obra, Cronograma), sem numeração.
- **Lista na tela inicial** (sempre aberta): nº, nome, arquivo, data, total e **Etapa atual**: Leitura, Ligação,
  Sequência, Mão de obra, Cronograma calculado ou Cenário escolhido (a mais avançada a que a obra chegou).
- **Abrir qualquer etapa** pelos botões de cada obra. As que ainda não podem ser abertas ficam desativadas, com o motivo
  ao passar o mouse: Sequência e Mão de obra pedem a sequência montada; Cronograma pede a mão de obra calculada.
- **Barra de etapas** (Leitura › Ligação › Sequência › Mão de obra › Cronograma) abaixo do topo de todas as telas da obra,
  com o nome da obra, a tela atual destacada e a mesma regra de desativar (`web/static/etapas.js`).
- **Leitura de uma obra salva** (`/?obra=N`): mostra os dados lidos sem enviar a planilha de novo e deixa alterar nome,
  prazo, BDI, desoneração e referências (`POST /api/obras/N/dados`). Os serviços não mudam: para trocá-los, importe de novo.
- **Excluir**: botão em cada obra ou caixas de seleção + "Excluir selecionadas", com confirmação na própria página
  listando as obras. Apaga a obra e tudo dela (serviços, ligações, rede, mão de obra, cronograma, cenários) e a cópia da
  planilha em `arquivos_obras/`; **a memória das ligações e o banco de coeficientes ficam**, então uma nova importação da
  mesma planilha já vem com as ligações confirmadas pela memória. Obra com o cálculo do cronograma rodando não pode ser
  excluída. API: `POST /api/obras/excluir` com `{"ids": [...]}` ou `DELETE /api/obras/N`.
- Regras em `web/obras.py` (etapa atual, etapas disponíveis, leitura salva, edição e exclusão).

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
  esperas somam (unidades diferentes → dias úteis, 7 corridos ≈ 5 úteis). EST-03 = 21 dias corridos (item 6); só a REV-01 espera a cura.
- **Concretagem** (`tipo_producao = concretagem`): duração ≥ teto(m³ da atividade ÷ (m³ por caminhão × caminhões por dia));
  parâmetros da obra (padrão 8 m³ e 3 caminhões).
- **Equipes e máquinas**: `equipe_max` vazio = 20; o otimizador testa 1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 20. Máquinas de cada
  equipamento de 1 até o máximo (padrão 6, por obra e por atividade); em atividade própria cada máquina traz 1 Operador/Motorista.
- **Funções da empresa** (`funcoes.xlsx`): Servente, Pedreiro, Pedreiro de acabamento, Carpinteiro, Armador, Bombeiro,
  Ajudante de bombeiro, Eletricista, Ajudante de eletricista, Pintor (+ Operador/Motorista). Termos com `&` exigem as
  duas palavras (ex.: `AUXILIAR&ELETRICISTA`); os outros ajudantes viram Servente. Aba **Juntar funções**: Carpinteiro e
  Armador → Pedreiro é possível, mas desligado por padrão (liga por obra na tela de mão de obra).
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
- **Ociosidade**: sem contar feriados (coluna à parte), total e por função, com as 3 maiores causas. Entradas na obra
  por função: veja o item 6.
  Terceirizadas podem ser feitas em até 3 partes de ≥ 5 dias úteis.
- **Gantt**: escala dia/semana/mês, etapas que abrem e fecham (barra-resumo), linhas de hoje e da data limite, setas de
  dependência (II tracejada), só o caminho crítico, terceirizadas em partes.
- **Leitor**: planilha só com preços com BDI é aceita; os sem BDI são calculados pelo BDI (um aviso só).

## Item 6 — regras do cronograma

Especificação em `ITEM_6_REGRAS_DO_CRONOGRAMA.md`. As obras salvas antes continuam com a própria cópia das atividades;
a biblioteca nova vale para as próximas importações (o banco ganha as colunas novas sozinho).

- **Biblioteca** (`dados/biblioteca_atividades.xlsx`, 19 colunas no item 6 (21 com as do item 7 e 23 com as do ajuste 7.1), lidas pelo nome do cabeçalho; uma biblioteca sem as
  colunas novas continua valendo):
  - 9 atividades passaram a **flexíveis** (ELE-05, ELE-06, HID-05, ESQ-02, PIN-03, EST-04, QUA-04, URB-02, ACA-01).
    Critério: rígida = segura outro serviço ou tem motivo técnico para não esperar; flexível = não libera nenhum
    serviço (ou só um bem adiante) e o otimizador encaixa nas semanas com menos serviço; aguardar = espera sem equipe.
  - EST-03 (retirada das escoras) com **21 dias**; FUN-05 com `FUN-04:II+3d` (fôrmas laterais, dias corridos).
  - `fonte`: origem do tipo e das esperas (`[Norma]`, `[Caderno]`, `[Fabricante]`, `[Planejamento]`, `[Prática]`).
    Só informativa: aparece ao passar o mouse na tela de sequência, com o critério do tipo (aba Legenda).
  - `depende_de_norma`: esperas de norma (NBR 7200, 13753, 13755, SUDECAP) na REV-01, REV-02, REV-03, PIS-02,
    PIN-01 e PIN-04. Ciclo nas dependências de norma também é erro da biblioteca.
  - `trocar_funcoes`: `Função de origem > Função de destino; …` (sem acento, maiúsculas ou espaços extras). As duas
    têm que ser funções da `funcoes.xlsx`; senão a biblioteca mostra o erro com a atividade e o texto.
- **Prazos de espera** (tela de Sequência, por obra): **Prática** (padrão, `depende_de`) ou **Norma** (usa
  `depende_de_norma` onde houver). As dependências das duas opções (com a herança) ficam guardadas ao montar a rede;
  trocar a opção troca só essas atividades (marcadas "norma"), valida ciclo e grava. Uma atividade com `depende_de`
  editado nesta obra fica igual nas duas opções. Com Norma a obra pode ficar mais longa (REV-02 espera a COB-02);
  se não couber no prazo, aparece o diagnóstico.
- **Trocar função por atividade**: ordem do cálculo de horas = composição → `funcoes.xlsx` → `trocar_funcoes` →
  juntar funções → equipes e duração. As horas não mudam, só a função (somam se o destino já existe); se a função
  principal for trocada, a de destino vira a principal. Só em atividade **própria** (terceirizada ignora). PRE-01 e
  PRE-02 já vêm com as trocas de eletricista, bombeiro e pintor para pedreiro e servente. Na tela de mão de obra
  (detalhe da atividade) aparecem as trocas aplicadas ("Pintor → Servente: 245 h") e dá para mudar só nesta obra,
  com "salvar também na biblioteca padrão" (cópia de segurança antes). A tela de sequência mostra a coluna "Trocas de função".
- **Entradas na obra** (parâmetros do cronograma, por função; substitui "pode sair e voltar"):
  **uma entrada** (padrão, menos Servente, Pedreiro, Bombeiro e Ajudante de bombeiro) = sobe até o pico e depois só desce;
  **até N entradas** = sai e volta até N − 1 vezes, sobe-e-desce dentro de cada entrada, cada ausência com pelo menos
  a ausência mínima (padrão 2 semanas); **livre** (padrão Servente, Pedreiro, Bombeiro e Ajudante de bombeiro) = sai e volta sem limite.
  Obras com a opção antiga: ligada = livre, desligada = uma entrada.
- **Custo de saída e volta**: padrão **8 horas da própria função** por pessoa que sai ou volta (ou um valor em R$, ou zero).
  Conta as pessoas que saem e voltam (aumentos além do pico), 2 movimentos cada; é zero quando ninguém sai. Entra no
  custo real do cenário como linha separada ("Custo de saída e volta de equipe").
- **Continuidade de equipe** (Resumo do cenário): por função, entrada e saída, quantas entradas, semanas na obra, semanas
  sem serviço, horas e custo parados, **quem puxa a entrada** e **quem segura a saída** (ex.: "Eletricista entra na
  semana 3 por causa da ELE-01 (24 h) e fica 9 semanas sem serviço até a ELE-02").
- **Procurar melhorias** (botão no Resumo, em segundo plano): para as 3 funções com maior custo de horas paradas, testa
  na atividade que puxa a entrada ou segura a saída tornar flexível (se rígida), trocar a função (ex.: `Eletricista >
  Pedreiro`, só sugestão), terceirizar (se a execução é "perguntar"; conta o terceirizado com a mesma mão de obra) e
  permitir 2 entradas (Operador/Motorista não é trocado: vem com a máquina; a LIM-01 não vira flexível). O cenário é
  recalculado com o mesmo tempo (base justa) e cada teste parte desse cronograma, só com aquela mudança (20 s cada). Mostra só as que melhoram,
  pelo ganho em R$ e em pontos de ociosidade, com **Aplicar nesta obra** (grava e recalcula o cenário).

## Item 7 — terceirizados na contagem de pessoas

Especificação em `ITEM_7_TERCEIRIZADOS_NA_CONTAGEM.md`. A equipe por semana passa a contar também os terceirizados,
**identificados pelo serviço** (ex.: "Eletricista (terceirizado): 3", "Telhado (terceirizado): 4"), para dimensionar
o canteiro e as áreas de vivência. **Não muda custo nem ociosidade**: o terceirizado é contrato fechado e a contagem é
informativa. A única regra nova do otimizador é o limite do canteiro.

- **Biblioteca** (21 colunas, lidas pelo nome; sem as colunas novas continua valendo):
  - `rotulo_terceirizado`: o nome que aparece como `<nome> (terceirizado)`. Atividades com o mesmo nome são da mesma
    empresa e somam na semana (ELE-* e SPDA/TEL/INC "Eletricista", HID "Bombeiro", SER-01/02/03 "Serralheria"…).
    Vazio = função principal da atividade; sem função, o nome da atividade. A IND-03 (topografia) é indireta e fica fora.
  - `pessoas_terceirizado`: estimativa de prática para quando não há horas na composição (TER-01 5, FUN-01 4, MET-01 6,
    COB-02 4, QUA-03 4, EXA-01 2, SER 3, ESQ-01 2, ACA-01 2, PEX-04 3, PAV-02 8, SIN-01 3).
- **Pessoas do terceirizado**, por atividade terceirizada (as que vêm terceirizadas, as "perguntar" escolhidas e as do
  "Procurar melhorias"), nesta ordem:
  1. **digitado** nesta obra (tela de mão de obra, detalhe da atividade);
  2. **composição**: a equipe do modo escolhido pelo otimizador (soma das funções); com a duração digitada (ou pela
     produção por dia), teto(horas ÷ (dias úteis × horas por dia)) por função;
  3. **outras obras**: o último valor digitado para a atividade em outra obra (fica quando a obra é excluída);
  4. **biblioteca** (`pessoas_terceirizado`);
  5. **sem estimativa**: conta 0, com o aviso "sem estimativa de pessoas: digite na mão de obra" na atividade e no resumo.
  A origem aparece sempre. Terceirizada dividida em partes conta só nos dias das partes.
- **Contagem por semana**: para cada nome, o **maior** número de pessoas num dia útil da semana (soma das atividades
  com o mesmo nome naquele dia). **Total na obra** = próprios contratados + terceirizados. Fica gravada com o cenário
  (`cenario_terceirizados_semana`), e mudar o nome ou as pessoas na mão de obra refaz só a contagem dos cenários já
  calculados (sem rodar o otimizador; com o limite do canteiro contando terceirizados, a tela avisa para recalcular).
- **Telas**: equipe por semana com os terceirizados empilhados acima dos próprios (listrados, contorno tracejado),
  botão "Mostrar terceirizados", linha do total na obra e dica com as atividades e pessoas de cada uma; tabela
  semana × função com as linhas `<nome> (terceirizado)` e **Total na obra** (também no Excel exportado). Resumo:
  pico de próprios, **pico total na obra** (com a semana), pico por terceirizado, homem-semana terceirizado e as
  atividades sem estimativa. Comparação de cenários: coluna "Pico total na obra". Gantt: "Telhado (terceirizado): 4
  pessoas (origem)" na dica da barra. Mão de obra: campos "nome do terceirizado" (com "salvar também na biblioteca
  padrão", cópia de segurança antes) e "pessoas do terceirizado".
- **Limite do canteiro**: "contar terceirizados no limite do canteiro" (parâmetros do cronograma, **ligado por
  padrão**): em cada dia útil, próprios contratados na semana + terceirizados em andamento no dia ≤ máximo de pessoas
  no canteiro; nas terceirizadas com horas, a equipe escolhida pelo otimizador entra na conta. Com o máximo vazio, nada
  muda. O diagnóstico de prazo sugere "aumentar o máximo de pessoas no canteiro de X para Y reduz N dias úteis"
  quando esse limite segura o prazo (estimativa com as atividades o mais cedo possível sem passar do máximo).

## Ajuste 7.1 — terceirizados com equipe e produção reais, concreto de caminhão

Especificação em `ITEM_7_1_TERCEIRIZADOS_E_CONCRETO.md`.

- **Terceirizado = instalação na obra.** Fabricação e entrega fora da obra não ocupam o canteiro. A terceirizada
  tem **um modo só** (pessoas e duração fixas): o otimizador não escolhe mais a equipe nem as máquinas dela (antes
  ele inflava, porque o custo do terceirizado é fixo). Continua podendo ser dividida em partes.
  - **Pessoas**: digitado na obra → padrão de outras obras → `pessoas_terceirizado` da biblioteca → `equipe_padrao`
    da atividade → sem estimativa (0, com aviso). As horas da composição não definem mais a equipe.
  - **Duração da instalação**: digitada → produção digitada (ou padrão de outras obras) → `producao_terceirizado`
    da biblioteca → horas da composição ÷ (pessoas × horas por dia) (ou horas de equipamento ÷ máquinas, o maior)
    → pendência. A produção é `"150 M2/dia"` (duração = teto(soma das quantidades nessa unidade ÷ produção),
    mínimo 1) ou `"2 dias"`; se nenhum serviço da atividade estiver na unidade, cai para a opção seguinte com aviso.
    O mesmo formato vale no campo da tela (só o número = unidade principal da atividade).
  - **Prazo de entrega** (`prazo_entrega_dias`, dias corridos): mostrado e editável por obra, guardado para o lembrete
    de pedido de compra (etapa futura). Não muda o cronograma.
  - Biblioteca: ACA-01 (granito) passa a **própria** (as pedras são compradas e o pedreiro instala); COB-03 (calhas)
    passa a **terceirizada** ("Calhas").
  - Tela de mão de obra, aba Própria × terceirizada: lista **"Terceirizadas para conferir"** (nome, pessoas, produção
    ou duração, origem de cada uma e prazo de entrega), editável na própria lista; o que for digitado vira padrão das
    próximas obras. Mudar pessoas ou produção muda a duração: a tela avisa para recalcular o cenário.
  - Diagnóstico de prazo: terceirizada no caminho crítico gera "aumentar as pessoas do terceirizado X de A para B
    reduz N dias" (duração na proporção, produção × B ÷ A), calculado de verdade; **Aplicar e recalcular** grava
    pessoas e produção como digitados na obra.
- **Concreto de caminhão** (parâmetro da etapa 4 "concreto de caminhão a partir de", padrão **3 m³** por serviço, o
  valor fica como padrão das próximas obras): serviço com USINADO ou BOMBEADO na descrição, ou com volume de concreto
  ≥ o parâmetro (a quantidade, se em M3; senão quantidade × coeficiente da subcomposição de concreto), não tem horas de
  **produção do concreto**: as subcomposições de concreto (descrição começando com "CONCRETO", em m³) ficam com 0 h
  nas origens banco, referência e estimado, e fora da estimativa por custo. Ficam lançamento, adensamento e
  acabamento. O serviço aparece marcado "concreto de caminhão: produção do concreto sem horas". Abaixo do volume,
  continua como betoneira. Mudar o parâmetro relê as composições.
- **Funções que a empresa não tem**: na `funcoes.xlsx`, SERRALHEIRO, MONTADOR e SOLDADOR têm `categoria =
  terceirizado`. Em atividade **própria**, essas horas não entram na equipe própria, na duração nem no custo (aviso
  "N h de Serralheiro são de terceirizado e não entram na equipe própria"); essas funções saem das listas de funções
  da empresa (parâmetros, equipe por semana).
- Testes: `tests/test_item71.py`. A QUA-02 continua acima de 2.000 h depois da regra do concreto (estimativas por
  custo de junta serrada, armação, polimento e lançamento): o teste da faixa 1.300–2.000 h está marcado como
  falha esperada, com o motivo, para o engenheiro decidir.
