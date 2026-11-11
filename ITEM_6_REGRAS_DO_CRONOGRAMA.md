# Item 6 — Regras do cronograma

Especificação para o Claude Code. Projeto `cronograma-obras`, Fase 1 do plano, itens 1, 2, 3 e 3.1 prontos (último commit `4df2a9e`).

Esta rodada **não cria tela nova grande**: ajusta as regras que montam o cronograma para ele ficar mais parecido com a obra real. São três partes: (1) tipos e esperas da biblioteca revistos por normas e cadernos de encargos, (2) troca de função por atividade e (3) continuidade de equipe, com um relatório que mostra o que está gerando ociosidade e quanto se ganha mudando.

## Arquivo que acompanha esta especificação

| Arquivo | Onde colocar | O que mudou |
|---|---|---|
| `biblioteca_atividades.xlsx` | substituir `dados/biblioteca_atividades.xlsx` | 9 atividades passaram de rígida para flexível (item 1.2); escoras com 21 dias (item 1.3); coluna nova `depende_de_norma` com os prazos de norma, usada só se a obra pedir (item 1.3); coluna nova `trocar_funcoes` (item 2), preenchida na PRE-01 e na PRE-02; coluna nova `fonte` (item 1.4); aba Legenda atualizada. **O arquivo novo tem 19 colunas** (as três últimas são `trocar_funcoes`, `fonte` e `depende_de_norma`). |

Ler as colunas **pelo nome do cabeçalho**, não pela posição. Uma biblioteca editada pelo usuário sem as colunas `trocar_funcoes`, `fonte` e `depende_de_norma` continua valendo (coluna vazia = sem troca, sem fonte, sem alternativa de norma).

Testes atuais que usam valores antigos da biblioteca (ex.: EST-03 com 28 dias, FUN-05 com `+3du`) devem ser **atualizados para os valores novos**, não afrouxados.

As obras salvas até agora são de teste: não precisam ser migradas nem reprocessadas. Cada obra continua guardando a própria cópia das atividades; a biblioteca nova vale para as próximas importações. Manter a migração automática do banco para os campos novos, como nas etapas anteriores.

---

## 1. Biblioteca revista: tipos, esperas e fonte

Nenhuma norma define "rígida" ou "flexível": isso é decisão de planejamento. O critério abaixo segue o princípio de folga do CPM (atividades fora do caminho principal podem flutuar dentro da folga). As **esperas** seguem a prática de obra por padrão, com os prazos de norma disponíveis como opção (item 1.3).

### 1.1 Critério (vale para a biblioteca e para a tela de sequência)
- **Rígida**: segura outro serviço ou tem motivo técnico para não esperar (vala aberta, estrutura e concretagem, cobertura que protege a obra, embutidos antes do chapisco, cura). Começa até 5 dias úteis depois de liberada (parâmetro da obra, já existe).
- **Flexível**: não libera nenhum outro serviço, ou só um serviço bem mais adiante, e não tem motivo técnico para ser imediata. Fica em qualquer semana entre o fim das anteriores e o início das que dependem dela (ou antes da LIM-01). O otimizador encaixa nas semanas com menos serviço.
- **Aguardar**: espera sem equipe (cura, testes), como hoje.

### 1.2 Tipos mudados (já feito no arquivo)

| Código | Atividade | Antes | Agora | Motivo |
|---|---|---|---|---|
| ELE-05 | Quadros, disjuntores e proteções | rígida | flexível | Montados a qualquer momento entre a fiação e os testes finais |
| ELE-06 | Tomadas, interruptores e luminárias | rígida | flexível | Só antes dos testes finais |
| HID-05 | Louças, metais, barras e chuveiros | rígida | flexível | Só antes dos testes finais |
| ESQ-02 | Portas de madeira e ferragens | rígida | flexível | Não libera outro serviço |
| PIN-03 | Pintura de metais e madeiras | rígida | flexível | Não libera outro serviço |
| EST-04 | Arquibancada e degraus | rígida | flexível | Só antes dos guarda-corpos (SER-02) |
| QUA-04 | Demarcação e equipamentos da quadra | rígida | flexível | Só antes da limpeza final |
| URB-02 | Acessibilidade (rampas e podotátil) | rígida | flexível | Não libera outro serviço |
| ACA-01 | Granito | rígida | flexível | Só antes das louças (HID-05) |

### 1.3 Esperas: prática (padrão) ou norma (opção por obra)

Na obra real, chapisco, emboço, cerâmica, piso e pintura **não seguem** os prazos de norma. Por isso o padrão continua sendo o de antes (prática de obra) e os prazos de norma ficam guardados numa coluna nova, `depende_de_norma`, para quando a fiscalização exigir.

**Parâmetro novo da obra: "Prazos de espera"**, com duas opções:
- **Prática** (padrão): usa o `depende_de`, como hoje.
- **Norma**: nas atividades com `depende_de_norma` preenchido, usa esse valor no lugar do `depende_de`. Nas outras, nada muda.

Ao trocar a opção, remontar a rede da obra (com herança, como na etapa 3), validar ciclo e recalcular. Na tela de sequência, quando a obra estiver em "Norma", marcar as atividades que mudaram. A edição por obra do `depende_de` (etapa 3) vale para a opção que estiver ativa.

| Código | `depende_de` (prática, padrão) | `depende_de_norma` | Base da norma |
|---|---|---|---|
| REV-01 (chapisco) | `ELE-02:II+5du, HID-02:II+5du, EST-03` | `ELE-02:II+5du, HID-02:II+5du, ALV-02:II+14d, EST-02:II+28d` | NBR 7200: base de concreto com 28 dias e alvenaria com 14 dias |
| REV-02 (emboço) | `REV-01:II+3du, HID-03` | `REV-01:II+3d, HID-03, COB-02` | NBR 7200 / SUDECAP cap. 14: chapisco com 3 dias e cobertura concluída |
| REV-03 (cerâmica de parede) | `REV-02:II+10du` | `REV-02:II+14d` | NBR 13755: emboço com 14 dias |
| PIS-02 (piso cerâmico) | `PIS-01:II+5du, REV-03:II+5du` | `PIS-01:II+14d, REV-03:II+5du` | NBR 13753: contrapiso com 14 dias |
| PIN-01 (selador) | `REV-02:II+20du, REV-03` | `REV-02:II+30d, REV-03` | SUDECAP cap. 17: 30 dias de cura |
| PIN-04 (pintura de pisos) | `PEX-02` | `PEX-02+28d` | Fichas técnicas: concreto com 28 dias |

Mudanças que valem nas duas opções (já no `depende_de`):

| Código | Antes | Agora | Base |
|---|---|---|---|
| EST-03 (retirada das escoras) | 28 dias | 21 dias | Retirada total aos 21 dias (caderno ORSE); NBR 14931/15696: conforme plano de escoramento |
| FUN-05 (reaterro) | `FUN-04:II+3du` | `FUN-04:II+3d` | Retirada das fôrmas laterais com no mínimo 3 dias |

Com "Norma", a dependência REV-02 → COB-02 pode alongar a obra (o telhado espera a estrutura metálica). Isso é esperado: se não couber no prazo, mostrar o diagnóstico (etapa 5.1).

### 1.4 Coluna `fonte`
Texto informativo com a origem do tipo e das esperas: `[Norma]`, `[Caderno]`, `[Fabricante]`, `[Planejamento]` ou `[Prática]` (convenção de obra, sem norma específica). O app **não usa no cálculo**. Mostrar ao passar o mouse sobre a atividade na tela de sequência, junto com o critério do tipo (texto da aba Legenda).

## 2. Trocar função por atividade

Na obra real, alguns serviços do início pedem, na composição, pintor ou eletricista, mas são feitos por pedreiro e servente (ligação elétrica provisória, extensão, pintura de tapume). Isso hoje obriga o app a contratar pintor e eletricista no primeiro mês e deixá-los parados até o acabamento, por causa da regra de não demitir.

### Coluna `trocar_funcoes` (biblioteca)
- Formato: `Função de origem > Função de destino`, separados por ponto e vírgula. Ex.: `Pintor > Servente; Eletricista > Pedreiro`.
- Comparação sem acento, sem diferenciar maiúsculas e ignorando espaços extras.
- As duas funções têm que ser funções da empresa (resultado da `funcoes.xlsx`). Se não forem, mostrar erro claro na importação da biblioteca, indicando a atividade e o texto.
- Já preenchido no arquivo:
  - **PRE-01**: `Eletricista > Pedreiro; Ajudante de eletricista > Servente; Bombeiro > Pedreiro; Ajudante de bombeiro > Servente; Pintor > Servente`
  - **PRE-02**: `Pintor > Servente; Eletricista > Pedreiro; Ajudante de eletricista > Servente`
- O encarregado continua na administração local (indireta); não entra aqui.

### Como aplicar
1. Ordem do cálculo de horas: composição → `funcoes.xlsx` → **`trocar_funcoes` da atividade** → juntar funções (aba "Juntar funções") → equipes e duração.
2. As horas **não mudam**, só a função. Se a função de destino já existe na atividade, as horas somam.
3. Se a função principal da atividade for trocada, a de destino passa a ser a principal para `equipe_padrao` e `equipe_max`.
4. Vale só para atividades **próprias**. Em terceirizada, ignorar.

### Edição por obra
- Na tela de mão de obra da atividade, mostrar as trocas aplicadas (ex.: "Pintor → Servente: 32 h").
- O usuário pode mudar as trocas **só nesta obra**, como já faz com o tipo e o `depende_de`, com o botão "salvar também na biblioteca padrão" (com cópia de segurança do Excel antes de gravar, como já existe).
- Recalcular horas, equipes e duração da atividade ao mudar.

## 3. Continuidade de equipe

O engenheiro prefere que a mesma equipe fique na obra sem sair e voltar, porque isso gera desgaste e custo. O eletricista, por exemplo, idealmente entra e faz tudo de uma vez. A exceção é obra por etapas ou por ambientes.

### 3.1 Entradas na obra por função
Substituir a opção atual "pode sair e voltar" (tela de parâmetros) por **"entradas na obra"**, por função:
- **Uma entrada** (padrão para todas, menos Servente e Pedreiro): é a regra de hoje. Sobe até o pico e depois só desce.
- **Até N entradas** (N escolhido pelo usuário, ex.: 2 para o eletricista em obra por etapas): a função pode sair da obra e voltar até N − 1 vezes. Dentro de cada entrada vale o sobe-e-desce. Cada ausência dura pelo menos o mínimo de semanas (parâmetro que já existe, padrão 2).
- **Livre** (padrão para Servente e Pedreiro): é o "pode sair e voltar" de hoje, sem limite de entradas. Cada redução dura pelo menos o mínimo de semanas.

Converter as obras com a opção antiga: ligado = Livre; desligado = Uma entrada.

### 3.2 Custo de saída e volta
- O parâmetro "custo por pessoa que sai ou entra" (hoje padrão R$ 0) passa a ter padrão de **8 horas da própria função** por pessoa que sai ou volta (custo por hora real ou de referência, o que estiver valendo). O usuário pode mudar para um valor em reais ou zerar.
- Entra no custo real do cenário, como linha separada no resumo: "custo de saída e volta de equipe".

### 3.3 Relatório de continuidade (no resumo do cenário)
Tabela por função:

| Coluna | O que é |
|---|---|
| Entrada / saída | primeira e última semana com a função contratada |
| Entradas | quantas vezes entrou na obra |
| Semanas na obra | semanas com pelo menos 1 contratado |
| Semanas sem serviço | semanas com gente contratada e nenhuma hora de serviço da função |
| Horas paradas e custo | como na ociosidade por função |
| Quem puxa a entrada | atividade que obriga a função a entrar mais cedo, com as horas dela e quantas semanas a função fica parada depois |
| Quem segura a saída | atividade que obriga a função a ficar até mais tarde, idem |

Ex.: "Eletricista entra na semana 3 por causa da ELE-01 (24 h) e fica 9 semanas sem serviço até a ELE-02."

### 3.4 Sugestões calculadas
Para as **3 funções com maior custo de horas paradas**, testar de verdade e mostrar o ganho (R$ e pontos de ociosidade) de cada alternativa que se aplica à atividade que puxa a entrada ou segura a saída:
- tornar a atividade flexível (se for rígida);
- trocar a função dela (ex.: `Eletricista > Pedreiro`), só como sugestão para o usuário decidir;
- terceirizar a atividade (se a execução for `perguntar`);
- permitir 2 entradas para a função.

Cada teste recalcula o cenário com só aquela mudança, com tempo limite próprio (padrão 20 s, parâmetro). Mostrar só as que melhoram, ordenadas pelo ganho, com botão **Aplicar nesta obra** (que grava a mudança na obra e recalcula). Rodar as sugestões num botão separado ("Procurar melhorias"), para não deixar lento o cálculo normal.

## 4. Outros ajustes
- Na tela de sequência, coluna "trocas de função" (resumida) ao lado do tipo.
- Atualizar o README com o que mudou e a Legenda da biblioteca (já atualizada no arquivo).

## 5. Testes automáticos

Novos, além de manter todos os atuais:
- **Biblioteca nova**: 19 colunas lidas pelo nome; biblioteca antiga sem as colunas novas continua carregando; rede sem ciclo nas duas opções de prazo.
- **Tipos**: as 9 atividades da tabela do item 1.2 vêm como flexíveis.
- **Prazos de espera**: em "Prática" (padrão), a rede da planilha de teste usa o `depende_de` (REV-02 não depende de COB-02; EST-03 com 21 dias). Em "Norma", usa o `depende_de_norma` nas 6 atividades da tabela (REV-02 depende de COB-02; PIS-02 começa ≥ 14 dias corridos depois do início do contrapiso). Trocar de volta para "Prática" restaura a rede. Uma edição manual do `depende_de` na obra continua valendo depois de trocar a opção.
- **Leitura de trocas**: `" pintor >servente ;Eletricista > Pedreiro"` vira duas trocas; função inexistente gera erro com a atividade e o texto.
- **PRE-01 e PRE-02 na planilha de teste**: nenhuma hora de Eletricista, Ajudante de eletricista, Bombeiro, Ajudante de bombeiro ou Pintor; total de horas da atividade igual ao de antes da troca.
- **Ordem com juntar**: troca `Pintor > Carpinteiro` com "juntar Carpinteiro → Pedreiro" ligado → as horas vão para Pedreiro.
- **Terceirizada**: troca em atividade terceirizada é ignorada.
- **Entradas**: rede pequena com uma função e um vale de 6 semanas sem serviço:
  - Uma entrada → não sai no vale;
  - Até 2 entradas → sai no vale e volta;
  - vale de 1 semana com mínimo de 2 → não sai;
  - três vales com até 2 entradas → sai em um só.
- **Conversão**: obra com "pode sair e voltar" ligado vira Livre; desligado vira Uma entrada.
- **Custo de saída e volta**: com padrão de 8 h, aparece no custo do cenário e é zero quando ninguém sai.
- **Relatório**: rede em que uma atividade curta do Eletricista no começo gera um vale → "quem puxa a entrada" aponta essa atividade e as semanas sem serviço estão certas.
- **Sugestões**: no mesmo caso, a sugestão de tornar flexível ou trocar a função aparece com ganho calculado maior que zero; "Aplicar nesta obra" grava e recalcula.
- **Planilha de teste continua cabendo em 12 meses** com os padrões. Com "Norma", não é obrigatório caber: mostrar o diagnóstico e relatar.

## 6. Ao terminar
Rode a planilha de teste com os padrões e informe ao usuário, **antes e depois** desta rodada: término, menor prazo possível, pico de pessoas, ociosidade total e por função e a semana em que Eletricista e Pintor entram na obra. Rode também com "Prazos de espera: Norma" e informe o término e o menor prazo possível nessa opção. É referência para o teste manual, não teste automático.

Rode todos os testes, atualize o README, faça o commit e envie para o GitHub.
