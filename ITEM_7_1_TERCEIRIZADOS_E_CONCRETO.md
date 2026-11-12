# Ajuste 7.1 — Terceirizados com equipe e produção reais, concreto de caminhão

Especificação para o Claude Code. Projeto `cronograma-obras`, item 7 pronto (commit `08cfd85`).

O relatório do item 7 e uma conferência das horas da planilha de teste mostraram quatro problemas. Esta rodada corrige os quatro. Decisões do engenheiro estão marcadas como **(decisão)**.

| Problema | Exemplo na planilha de teste |
|---|---|
| O otimizador infla a equipe e as máquinas dos terceirizados, porque o custo deles é fixo | Marmoraria com 26 pessoas em 4 dias, Piso de borracha com 16 em 1 dia |
| Horas de composição viram durações sem sentido nos terceirizados | Sinalização: 506 h para 63 m² de pintura de setas |
| Horas de produção de concreto somadas quando o concreto vem de caminhão | QUA-02 (piso da quadra, concreto **usinado**): 4.293 h para 876 m², com referência de concreto em betoneira e estimativa por custo somadas à composição |
| Funções que a empresa não tem viram funções próprias | 5 h de Serralheiro na URB-04, Montador na SIN-01 |

## Arquivos que acompanham esta especificação

| Arquivo | Onde colocar | O que mudou |
|---|---|---|
| `biblioteca_atividades.xlsx` | substituir `dados/biblioteca_atividades.xlsx` | Colunas novas `producao_terceirizado` e `prazo_entrega_dias`; ACA-01 passa a própria; COB-03 passa a terceirizada ("Calhas"); pessoas da COB-03 e da URB-03; Legenda. **23 colunas** (as duas últimas são as novas). |
| `funcoes.xlsx` | substituir `dados/funcoes.xlsx` | Serralheiro, Montador e Soldador com categoria nova `terceirizado` (item 4). |

Ler as colunas pelo nome; arquivos sem as colunas novas continuam valendo. Migração automática do banco. As obras salvas são de teste.

---

## 1. Terceirizado: o que conta é a instalação na obra

**(decisão)** Do terceirizado, o cronograma mostra só a **instalação na obra**. Fabricação e entrega fora da obra (estrutura metálica, serralheria, calhas, esquadrias, pedras) não ocupam o canteiro. O prazo de entrega fica guardado para o **lembrete de pedido de compra** de uma etapa futura e, por enquanto, não entra no cronograma.

### 1.1 Um modo só, sem escolha do otimizador
Terceirizada passa a ter **um modo**: pessoas fixas e duração fixa. O otimizador não escolhe mais o tamanho da equipe nem a quantidade de máquinas dela. Continua podendo dividir em partes (etapa 5.1).

### 1.2 Pessoas
Ordem: digitado na obra → padrão de outras obras → `pessoas_terceirizado` da biblioteca → `equipe_padrao` da atividade → sem estimativa (0, com aviso). **As horas da composição não definem mais a equipe.**

### 1.3 Duração da instalação
Ordem, com a origem mostrada como hoje:
1. **duração digitada** na obra;
2. **produção digitada** na obra, ou padrão de outras obras (já existe, etapa 5.1);
3. **`producao_terceirizado` da biblioteca** (nova);
4. **horas da composição ÷ (pessoas × horas por dia)**, arredondado para cima. Se houver horas de equipamento, usar o maior entre isso e horas de equipamento ÷ (máquinas da etapa 4 × horas por dia);
5. nenhuma: pendência na etapa 4, como hoje.

Formato da `producao_terceirizado` (o mesmo vale para o campo digitado na tela):
- `"<número> <UNIDADE>/dia"`: duração = teto(soma das quantidades dos serviços da atividade nessa unidade ÷ produção), mínimo 1 dia útil. Unidade comparada sem diferenciar maiúsculas. Se nenhum serviço tiver a unidade, cair para a opção seguinte e avisar.
- `"<número> dias"`: duração fixa em dias úteis.

Valores da biblioteca (estimativa de prática, para conferir):

| Atividade | Produção | Duração na planilha de teste | Pessoas | Entrega (dias) |
|---|---|---|---|---|
| TER-01 Terraplenagem | 800 M3/dia | 22 | 5 | — |
| FUN-01 Estacas | 5 M3/dia | 4 | 4 | — |
| MET-01 Estrutura metálica (montagem) | 1000 KG/dia | 11 | 6 | 30 |
| COB-02 Telhado | 150 M2/dia | 10 | 4 | — |
| COB-03 Calhas | 1 dias | 1 | 2 | 10 |
| QUA-03 Piso de PU | 60 M2/dia | 13 | 4 | — |
| EXA-01 Exaustão | 5 dias | 5 | 2 | 20 |
| SER-01 Janelas, portas e portões | 20 M2/dia | 7 | 3 | 20 |
| SER-02 Guarda-corpos e corrimãos | 40 M/dia | 14 | 3 | 20 |
| SER-03 Gradil | 50 M/dia | 4 | 3 | 15 |
| ESQ-01 Esquadrias de alumínio | 15 M2/dia | 2 | 2 | 20 |
| PEX-04 Piso de borracha | 50 M2/dia | 4 | 3 | — |
| PAV-02 Asfalto | 2 dias | 2 | 8 | — |
| SIN-01 Sinalização | 2 dias | 2 | 3 | — |
| URB-03 Playground (se terceirizado) | 3 UN/dia | 5 | 3 | 30 |

As durações digitadas no teste (`DURACOES_TERCEIRIZADAS` em `tests/test_etapa5_obra.py`, ex.: MET-01 = 40) eram um apoio da etapa 5.1 e passam a vir da biblioteca: **tirar do teste** as que a biblioteca agora cobre.

### 1.4 Mudanças de execução na biblioteca
- **ACA-01 (granito) passa a própria (decisão):** as pedras são compradas do fornecedor, e o pedreiro instala. Entram as horas da composição, como em qualquer própria. Prazo de entrega de 15 dias guardado.
- **COB-03 (calhas) passa a terceirizada (decisão):** a calha é montada fora e o terceirizado vem instalar. Nome "Calhas".

### 1.5 Prazo de entrega
- Coluna `prazo_entrega_dias` (dias corridos): mostrar e permitir editar por obra na tela de mão de obra, com o aviso "usado no lembrete de compra (etapa futura)". Não muda o cronograma.

### 1.6 Telas
- Na mão de obra, lista **"Terceirizadas para conferir"**: atividade, nome, pessoas, produção ou duração, origem de cada uma e prazo de entrega, editáveis na própria lista. O que for digitado vira padrão das próximas obras (como hoje).
- Mudar pessoas ou produção muda a duração: avisar que é preciso recalcular o cenário.

### 1.7 Diagnóstico de prazo
Quando uma terceirizada estiver no caminho crítico, sugerir "aumentar as pessoas do terceirizado X de A para B reduz N dias", com a duração reduzida na proporção (produção × B ÷ A). Calcular de verdade, com **Aplicar e recalcular** (grava pessoas e produção como digitados na obra).

## 2. Concreto de caminhão

**(decisão)** Volume grande de concreto vem de caminhão (usinado), mesmo que a composição diga "feito em obra".

- Parâmetro novo da etapa 4, com padrão salvo: **"concreto de caminhão a partir de"** (m³ por serviço), padrão **3 m³**.
- Volume de concreto do serviço: a quantidade, se a unidade for M3; senão, quantidade × coeficiente da subcomposição de concreto (m³ por unidade).
- **Serviço com concreto de caminhão** (descrição com USINADO ou BOMBEADO, ou volume ≥ o parâmetro): a **produção do concreto não tem horas**. Ou seja, subcomposições de concreto (preparo em betoneira, concreto usinado) ficam com 0 h nas origens `banco`, `referencia` e `estimado`, e não entram na estimativa por custo. Ficam as horas de lançamento, adensamento e acabamento da própria composição.
- Marcar o serviço na tela de mão de obra: "concreto de caminhão: produção do concreto sem horas".
- Serviço abaixo do volume continua como hoje (betoneira na obra).

Antes de mudar, **listar no relatório** as subcomposições do item 15.2.2 (QUA-02) e do 15.1.5 (PEX-02), com a origem e as horas de cada uma, para o engenheiro ver o que saiu. Se depois da regra a QUA-02 ficar acima de 2.000 h, relatar o motivo (sem mudar o teste para passar).

## 3. Horas sem sentido nas terceirizadas

Já resolvido pelo item 1.3: a produção da biblioteca vale mais que as horas. As horas da composição ficam só como último recurso e no detalhe do tooltip.

## 4. Funções que a empresa não tem (Serralheiro, Montador)

**(decisão)** Serralheiro e Montador são sempre terceirizados (fabricam fora e vêm instalar).

- Na `funcoes.xlsx`, as regras de SERRALHEIRO, MONTADOR e SOLDADOR têm `categoria = terceirizado`.
- Em atividade **própria**, horas de função `terceirizado` **não entram** na equipe própria, na duração nem no custo de mão de obra própria. A atividade mostra o aviso "N h de Serralheiro são de terceirizado e não entram na equipe própria".
- Em atividade terceirizada não muda nada (a equipe vem do item 1.2).
- Essas funções saem da lista de funções da empresa nas telas de parâmetros e de equipe por semana.

## 5. Testes automáticos

Novos, além de manter todos os atuais (atualizar os que usam os valores antigos, sem afrouxar):
- **Arquivos**: biblioteca com 23 colunas; ACA-01 própria; COB-03 terceirizada "Calhas"; funções Serralheiro, Montador e Soldador com categoria `terceirizado`.
- **Um modo**: terceirizada com horas tem um modo só; o otimizador não muda pessoas nem máquinas dela.
- **Pessoas**: digitado > outras obras > biblioteca > equipe_padrao > sem estimativa.
- **Duração**: digitada > produção digitada/outras obras > produção da biblioteca > horas ÷ pessoas; `"150 M2/dia"` com 1.453,56 m² → 10 dias; `"2 dias"` → 2; unidade inexistente na atividade → cai para a opção seguinte, com aviso.
- **Planilha de teste**: PEX-04 com 3 pessoas e 4 dias; SIN-01 com 2 dias; MET-01 com 11 dias; nenhuma terceirizada com mais pessoas que a biblioteca.
- **Concreto de caminhão**: serviço USINADO → subcomposição de concreto com 0 h e fora da estimativa; serviço "feito em obra" com 155 m³ → igual; serviço com 2 m³ "feito em obra" → horas de betoneira mantidas; parâmetro mudado para 200 m³ → o de 155 m³ volta a ter horas de betoneira.
- **QUA-02**: horas totais caem para perto das da composição (ordem de 1.300 a 2.000 h).
- **Serralheiro em própria**: URB-04 sem Serralheiro na equipe própria, com o aviso; total de horas próprias da atividade sem essas horas.
- **Diagnóstico**: terceirizada no caminho crítico gera a sugestão de mais pessoas com o ganho calculado; Aplicar grava e recalcula.
- **Prazo de entrega**: lido, editável por obra e sem efeito nas datas.
- **Planilha de teste cabe em 12 meses** com os padrões.

## 6. Ao terminar

Rode a planilha de teste com os padrões e informe ao usuário:
- término, pico de próprios (com a semana), pico total na obra (com a semana) e ociosidade total, **comparando com o item 7** (término 02/01/2026, pico de próprios 52, pico total 73);
- horas da QUA-02 e da PEX-02 antes e depois, com a lista das subcomposições do item 2;
- tabela das terceirizadas: pessoas, duração e origem de cada uma.

Rode todos os testes, atualize o README, faça o commit e envie para o GitHub.
