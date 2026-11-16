# Ajuste 7.2 — Horas das subcomposições e concreto de caminhão

Especificação para o Claude Code. Projeto `cronograma-obras`, ajuste 7.1 pronto (commit `8ccaeec`).

## Por que

No 7.1 ficou claro que o maior erro de horas vem das **subcomposições estimadas por custo**: subcomposições que aparecem dentro das composições da planilha, mas não estão no arquivo, no banco nem na referência. A estimativa transforma o custo delas em horas, e o custo de material vira hora de gente. Na planilha de teste, isso soma cerca de 3.700 h, e várias não fazem sentido:

| Subcomposição (QUA-02) | Estimado por custo | SINAPI real |
|---|---|---|
| 97090 Armação com tela Q-138 (2,42 kg/m²) | 914 h | 89 h |
| ED-50619 Polimento mecanizado | 290 h | 77 h (como 97097) |
| ED-48324 Transporte, lançamento e adensamento em radier | 276 h | 86 h (como 97096) |
| 98577 Tratamento de junta serrada (1,05 m/m²) | 1.044 h | **1.289 h** |

A junta serrada é mesmo trabalhosa no SINAPI (1,4 h de pedreiro e servente por metro). Por isso a QUA-02 fica em torno de **2.860 h** e não na faixa de 1.300 a 2.000 h que eu tinha posto no 7.1. **A faixa estava errada, não o app.**

**Padrão novo:** usar coeficientes reais em vez de estimar. Para código SINAPI, a referência pelo código. Para códigos de outras tabelas (SETOP "ED-...", ORSE, próprios), uma **referência pela descrição**, que liga a subcomposição a uma composição SINAPI equivalente. A estimativa por custo fica como último recurso e aparece numa lista para conferir.

## Arquivo que acompanha esta especificação

| Arquivo | Onde colocar | O que mudou |
|---|---|---|
| `produtividade_referencia.xlsx` | substituir `dados/produtividade_referencia.xlsx` | Aba `Referencias`: 9 composições SINAPI novas (98577, 98575, 97090, 97097, 97096, 90280, 87630, 103317, 103321). Aba nova **`Por descricao`** com 17 regras. Legenda atualizada. |

---

## 1. Referência pela descrição

### 1.1 Aba `Por descricao`
Colunas: `ordem`, `termos_na_descricao`, `unidade`, `mao_de_obra`, `horas_por_unidade`, `equivale_a`, `observacao`. Várias linhas com a mesma `ordem` formam uma regra (uma linha por mão de obra).

- A regra vale quando **todos** os termos separados por `&` aparecem **em qualquer parte** da descrição da subcomposição (sem diferenciar acentos e maiúsculas) **e** a unidade é a mesma. Diferente da `funcoes.xlsx`, o primeiro termo não precisa estar no começo.
- Usar a **primeira** regra que servir, pela `ordem`. As mais específicas vêm antes (ex.: `19X19X39` antes de `9X19X39`).
- `mao_de_obra` passa pela `funcoes.xlsx`, como na aba `Referencias` (ex.: ajudante de armador → Servente, operador de betoneira → Servente).
- `mao_de_obra = MATERIAL` com 0 h: a subcomposição é só material. Fica com 0 h e sai da estimativa (ex.: fornecimento de laje treliçada).
- Origem nova nas telas: `referencia_descricao`, mostrando a regra usada e o `equivale_a` (ex.: "como SINAPI 97096").

### 1.2 Ordem de busca das horas de uma subcomposição
composição no arquivo → banco de coeficientes → referência pelo código → **referência pela descrição** → estimativa por custo.

As subcomposições de concreto de caminhão (7.1) continuam com 0 h antes de tudo isso.

### 1.3 O usuário pode acrescentar regras
A aba é editável, como as outras. Ao carregar, validar: unidade preenchida, horas ≥ 0 e mão de obra reconhecida pela `funcoes.xlsx` ou igual a `MATERIAL`. Se algo estiver errado, mostrar um erro claro com a linha.

## 2. Estimativa por custo: último recurso, sempre à vista

- A regra continua a mesma (razão horas/custo dos serviços completos, com o limite de 3×).
- Na tela de mão de obra, lista nova **"Horas estimadas para conferir"**: cada subcomposição (ou serviço inteiro) estimada por custo, com item, descrição, unidade, custo, horas estimadas e atividade. Ordenar pelas horas, das maiores para as menores, com o botão **Digitar h/un** que já existe, na própria linha.
- No resumo da etapa 4: total de horas estimadas por custo e % das horas próprias. Aviso em amarelo se passar de **10%** das horas de uma atividade.

## 3. Concreto de caminhão (decisão do engenheiro)

O caminhão tem no mínimo 5 m³ e pode chegar a 10 m³. Em concretagem grande, a média é caminhão de 8 m³, com o máximo de caminhões que der no dia.

- **"Concreto de caminhão a partir de"**: padrão passa de 3 para **5 m³** por serviço (o caminhão mínimo). Abaixo disso, betoneira na obra.
- **Volume por caminhão**: padrão continua **8 m³**. Aceitar de 5 a 10 m³; fora disso, aviso.
- **Caminhões por dia**: padrão passa de 3 para **vazio = sem limite**. A concretagem fica limitada pela equipe de lançamento (horas de mão de obra), não pelo número de caminhões. O usuário pode digitar um máximo por obra (ex.: usina longe ou rua estreita), e aí volta a regra da etapa 5.1 (duração mínima pelo volume).
- Atualizar os textos de ajuda desses três parâmetros com essa explicação.

## 4. Testes automáticos

Novos, além de manter todos os atuais (atualizar os que usam valores antigos, sem afrouxar):
- **Referência pela descrição**: "TRANSPORTE, LANÇAMENTO E ADENSAMENTO DE CONCRETO EM RADIER" (M3) usa a regra do 97096; "ALVENARIA DE VEDAÇÃO COM BLOCO DE CONCRETO, ESP. 9CM" usa a de 9 cm e não a de 19 cm; unidade diferente não casa; "LAJE TRELIÇADA ... ENCHIMENTO EM EPS" fica com 0 h e fora da estimativa.
- **Ordem**: subcomposição com código na aba `Referencias` usa o código, mesmo que uma regra por descrição também sirva.
- **Validação**: regra com mão de obra desconhecida gera erro com a linha.
- **QUA-02 (15.2.2)**: entre **2.700 e 3.000 h**, com 98577 e 97090 pelo código e ED-50619 e ED-48324 pela descrição. Tirar a marca de falha esperada do teste do 7.1 e trocar a faixa.
- **Outras da planilha de teste**: EST-04 (ED-48202, 98575 e 90280), URB-01 (ED-48191), PIS-01 (87630 pelo código; 87745 e 87755 pela descrição) e CON-01 (40.16.02) sem horas estimadas por custo.
- **Lista para conferir**: mostra as estimativas que sobraram (ex.: tijolo maciço e reboco da HID-01, que não têm regra), ordenadas pelas horas.
- **Concreto**: serviço "feito em obra" com 4 m³ → betoneira; com 5 m³ → caminhão; caminhões por dia vazio → a duração da concretagem vem só da mão de obra; com 3 caminhões por dia digitados → volta o limite pelo volume.
- **Planilha de teste cabe em 12 meses** com os padrões.

## 5. Ao terminar

Rode a planilha de teste com os padrões e informe ao usuário:
- horas antes e depois por atividade afetada (QUA-02, EST-04, EST-01, URB-01, PIS-01, CON-01, HID-01) e o total de horas próprias;
- horas que ainda ficaram estimadas por custo (total e as 5 maiores);
- término, pico de próprios (com a semana), pico total na obra e ociosidade, **comparando com o 7.1** (término 31/10/2025, pico de próprios 64, pico total 68, ociosidade 21,45%).

Rode todos os testes, atualize o README, faça o commit e envie para o GitHub.
