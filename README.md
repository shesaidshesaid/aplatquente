# aplatquente – Automação APLAT (P-18) – Trabalho a Quente

Automação em Python, baseada em Selenium + Microsoft Edge, para **gerar o plano de Trabalho a Quente** e **preencher automaticamente** os principais formulários do APLAT (P-18):

- Questionário PT
- EPI adicional necessário e proteções
- Análise Ambiental
- APN-1
- Aba EPI

O objetivo é reduzir o trabalho manual e padronizar as respostas, respeitando regras fixas e gatilhos derivados da **Descrição da Etapa** e das **Características do trabalho**.

> **Aviso:** este projeto é feito para uso em ambiente corporativo específico (APLAT / P-18, Petrobras).  
> Ajustes de XPaths, textos e regras podem ser necessários em outras unidades ou após alterações no sistema.

---

## Visão Geral

O fluxo do script principal (`aplatquente.py`) é:

1. **Login no APLAT**
   - Abre o Microsoft Edge com `msedgedriver.exe`.
   - Tenta login automático (`attempt_auto_login`), podendo usar `--use-keyring` para senha.
   - Aguarda o `document.readyState == 'complete'`.

2. **Pesquisa e abertura das etapas**
   - Para cada número de etapa informado em `--valor`, executa `perform_search`:
     - Preenche a data (`--data`).
     - Preenche o número da etapa.
     - Clica em “Pesquisar”.
     - Abre o resultado encontrado.

3. **Validação de “Trabalho a Quente”**
   - Vai para a aba **Dados da Etapa**.
   - Lê o combo **Tipo de Trabalho**.
   - Só continua se o texto for “Trabalho a Quente” (senão, ignora a etapa).

4. **Coleta de contexto**
   - Lê a **Descrição da Etapa**.
   - Lê as **Características do trabalho** (campo próprio ou fieldset específico).
   - Normaliza texto (upper case, sem acentos, espaçamento limpado).

5. **Geração de plano**
   - A partir da descrição + características, monta um **contexto** com diversos flags:
     - `tem_chama`, `tem_oxicorte`, `tem_solda`, `tem_altura`, `tem_acesso_cordas`, `tem_sobre_o_mar`, `tem_trat_mec`, `tem_hidrojato`, `tem_espaco_confinado`, `tem_pressurizado`, `tem_partes_moveis`, etc.
   - Usa esse contexto para montar:
     - Plano de **EPI adicional (rádios)**.
     - Plano de **EPIs por categoria** (Vestimentas, Óculos, Luvas, Proteção Respiratória).
     - Mapa de respostas para **Questionário PT** (Sim / Não / NA).
     - Mapa de **APN-1** (Q001–Q020 com Sim/Não).
     - Regra fixa para **Análise Ambiental** (tudo “Não” para Trabalho a Quente).
   - Imprime um **relatório detalhado do plano esperado** no console.

6. **Preenchimento automático**
   - Abre, em sequência:
     - Aba **Questionário PT** → `preencher_questionario_pt`
     - Aba **EPI** (EPI adicional necessário e proteções) → `preencher_epi_adicional`
     - Aba **Análise Ambiental** → `preencher_analise_ambiental`
     - Aba **APN-1** → `preencher_apn1`
     - Aba **EPI** (tabela de EPIs por categoria) → `processar_aba_epi`
   - Cada formulário é preenchido com base no plano gerado.

7. **Confirmação da etapa**
   - No final, executa um único **“Confirmar”** no rodapé da etapa, usando `clicar_botao_confirmar_rodape`.

8. **Logs e encerramento**
   - Se `--log` for informado, redireciona toda a saída para um arquivo de log (com `Tee`).
   - Exibe tempos de cada etapa (`[TIMER]`).
   - Ao final, pede `ENTER` antes de fechar o navegador (para inspeção, se desejado).

---

## Estrutura do Projeto

Principais arquivos/módulos:

- `aplatquente.py`  
  Script principal. Contém:
  - `main()` – orquestra tudo: parse de argumentos, login, laço de etapas, geração do plano, preenchimento e confirmação.
  - `processar_etapa()` – fluxo completo de uma etapa.
  - Utilitários de log (`Tee`, `gerenciar_log`).
  - CLI (`parse_args`) com todos os parâmetros de execução.

- `quent1_infra.py`  
  **Infraestrutura Selenium / Edge / navegação**, incluindo:
  - Criação configurada do WebDriver (`create_edge_driver`), com busca automática por `msedgedriver.exe` em diferentes caminhos.
  - Funções de espera e clique:
    - `wait_for_document_ready`
    - `wait_and_click`
    - `safe_find_element`
  - Funções de navegação de alto nível:
    - `perform_search` (pesquisa de etapa)
    - `goto_tab` (navegação entre abas como “Dados da Etapa”, “Questionário PT”, “Análise Ambiental”, “EPI”, “APN-1”)
    - `fechar_modal_etapa`, `clicar_botao_confirmar_rodape`
    - `attempt_auto_login` (login automático, com possibilidade de uso de keyring)
  - Cache simples de elementos DOM (`ElementCache`).

- `quent2_plano.py`  
  **Geração do plano de Trabalho a Quente**, incluindo:
  - Normalização de texto (`normalizar_texto`).
  - Coleta robusta de:
    - Descrição da etapa (`coletar_descricao`).
    - Características do trabalho (`coletar_caracteristicas_trabalho`) por múltiplos métodos (spans, fieldset, regex de bloco).
  - Construção do contexto (`montar_contexto_from_textos`), com diversos flags `tem_*`.
  - Bases padrão:
    - `EPI_RADIOS_BASE` – respostas padrão para EPI adicional.
    - `EPIS_CAT_BASE` – EPIs base por categoria.
    - `QPT_BASE` – respostas padrão para Questionário PT.
  - Ajustes das bases conforme contexto:
    - `montar_base_epi_radios(ctx)`
    - `montar_base_epis_cat(ctx)`
    - `montar_base_qpt(ctx)`
    - `montar_base_apn1(ctx)` (APN-1 até Q020, com mapeamento por tipo de risco).
  - Função principal:
    - `gerar_plano_trabalho_quente(descricao, caracteristicas)` – retorna dict com contexto, QPT, APN-1, EPIs etc.
    - `imprimir_relatorio_plano(...)` – imprime, em formato legível, tudo o que o plano espera de cada formulário.

- `quent3_preenchimento.py`  
  **Rotinas de preenchimento automático**:
  - `QuestionarioPTProcessor`
    - Mapeia linhas do questionário por **código** e por **texto**, tolerando mudanças de numeração.
    - Decide a resposta correta (Sim / Não / NA) e tenta múltiplas estratégias de clique em rádio (input, label, JavaScript, eventos).
    - Gera resumo de sucesso/falha.
  - `EPIAdicionalProcessor`
    - Navega na aba **EPI** (bloco “EPI adicional necessário e proteções”).
    - Mapeia as questões pelos códigos (Q001 etc.) e/ou texto.
    - Marca o rádio correto com base no plano de EPI adicional.
  - `AnaliseAmbientalProcessor`
    - Aba **Análise Ambiental**.
    - Primeiro tenta preencher tudo via JavaScript (marcando “Não” onde aplicável).
    - Se falhar, faz fallback com Selenium tradicional.
  - `APN1Processor`
    - Aba **APN-1**.
    - Coleta dinamicamente as perguntas via XPaths configuráveis.
    - Identifica IDs dos rádios SIM/NÃO.
    - Decide resposta com base em padrões de texto da pergunta + contexto da etapa (altura, sobre o mar, chama, CO₂, espaço confinado, pressurizado, partes móveis, hidrojato, etc.).
    - Marca via JavaScript, disparando eventos para que o Angular detecte a mudança.
  - Funções de interface pública (para manter compatibilidade):
    - `preencher_questionario_pt(...)`
    - `preencher_epi_adicional(...)`
    - `preencher_analise_ambiental(...)`
    - `preencher_apn1(...)`

- `quent4_epi.py`  
  **Processamento da aba EPI (tabela por categoria)**:
  - `EPIProcessor`
    - Para cada categoria relevante (`Vestimentas`, `Óculos`, `Luvas`, `Proteção Respiratória`):
      - Lê a tabela atual de EPIs associados.
      - Compara com o plano (`epis_cat_plano`) e identifica **faltantes** e **excedentes**.
      - Inclui EPIs faltantes via modal de associação (botão `+`):
        - Abre modal.
        - Localiza linhas da tabela pelo texto do EPI (normalizado).
        - Marca checkboxes.
        - Confirma.
      - (Remoção de excedentes está implementada, porém comentada por padrão.)
  - Função pública:
    - `processar_aba_epi(driver, timeout, epis_cat_plano)`

- `html_qpt.txt`  
  Captura de HTML/texto do Questionário PT e da Análise de Acompanhamento da PT, usada como referência para construção dos mapeamentos de QPT.

- `log_aplatquente.txt`  
  Exemplo de log de execução real, mostrando:
  - Login bem-sucedido.
  - Pesquisa de etapa.
  - Descrição/características extraídas.
  - Plano gerado (EPIs, QPT, APN-1, Análise Ambiental).
  - Início do preenchimento do Questionário PT, etc.

- `msedgedriver.exe`  
  WebDriver do Microsoft Edge, distribuído junto ao projeto para facilitar execução (Windows).

---

## Pré-requisitos

- **Ambiente corporativo**
  - Acesso à rede e ao sistema APLAT (P-18) com credenciais válidas.
  - Permissão de uso de automação (verifique políticas internas de TI/Segurança).

- **Sistema operacional**
  - Windows (focado em uso com Microsoft Edge e msedgedriver.exe).

- **Software**
  - Python 3.8+ (recomendável 3.10+).
  - Microsoft Edge instalado.
  - Microsoft Edge WebDriver compatível com a versão do Edge:
    - `msedgedriver.exe` incluído no projeto, mas você pode substituí-lo por uma versão mais atual, se necessário.

- **Bibliotecas Python**
  - [`selenium`](https://pypi.org/project/selenium/)
  - Opcional:
    - [`keyring`](https://pypi.org/project/keyring/) – se você for usar `--use-keyring` para gerenciar senha de forma segura.

---

## Instalação

1. **Clonar o repositório**

   ```bash
   git clone https://github.com/shesaidshesaid/aplatquente.git
   cd aplatquente


   Lógica esperadada:




   

## 1. Visão geral do fluxo

**Objetivo:** Automatizar, para etapas de **Trabalho a Quente** na P-18, o preenchimento de:

* Questionário PT
* EPI adicional necessário e proteções (bloco de rádios na aba EPI)
* Análise Ambiental
* APN-1
* Aba de EPIs vinculados (Vestimentas, Óculos, Luvas, Proteção Respiratória)

**Fluxo alto nível, por etapa (`valor`) e data (`data`):**

1. Login no APLAT (via SSO + keyring, se configurado).
2. Pesquisa da etapa pela combinação:

   * Data da etapa
   * Número da etapa (ex.: `18/164/2024`)
3. Abre o primeiro resultado da lista.
4. Vai para aba **Dados da Etapa**.
5. Lê:

   * **Tipo Trabalho** (combo `Trabalho a Quente`, `Trabalho a Frio`, etc.)
   * **Tipo de Etapa** (PT Diária / PT Extra / etc.)
   * **Descrição da Etapa**
   * **Características do trabalho / Observações** (texto maior com palavras-chave).
6. Se o Tipo Trabalho **não é** “Trabalho a Quente”:

   * Loga que a etapa foi ignorada.
   * Não preenche nada e segue para próxima etapa.
7. Se é “Trabalho a Quente”:

   * Normaliza os textos (caixa alta/baixa, acentos, espaços).
   * Detecta **contextos** (flags booleanas) a partir de palavras-chave.
   * Com base nesses contextos, gera um **plano de preenchimento**:

     * Questionário PT (mapa pergunta → resposta).
     * EPI adicional – rádios.
     * Regras para Análise Ambiental.
     * APN-1 (quais questões serão “Sim”/“Não”).
     * EPIs por categoria (Vestimentas, Óculos, Luvas, Proteção Respiratória).
   * Imprime um relatório de plano (para auditoria).
8. Aplica o plano na interface:

   * Aba **Questionário PT**
   * Aba **EPI** (bloco EPI adicional)
   * Aba **Análise Ambiental**
   * Aba **APN-1**
   * Aba **EPI** (grid de EPIs vinculados)
9. Dá um único **Confirmar** no rodapé da etapa (grava tudo de uma vez).
10. Passa para a próxima etapa, se existir.

---

## 2. Módulo de coleta de dados da etapa

### 2.1. Leitura de Tipo Trabalho

* Localiza o combo “Tipo Trabalho” na aba Dados da Etapa usando o label.
* Lê:

  * `value` (código interno, ex.: `"2"`)
  * texto visível (ex.: `"Trabalho a Quente"`).
* Loga o valor e o texto selecionados.

**Regra principal:**

* Se o texto não corresponde a “Trabalho a Quente” (após normalização), a etapa é **descartada** pela automação (somente log, sem preenchimentos).

---

### 2.2. Leitura de Tipo de Etapa

* Localiza o fieldset “Tipo de Etapa”.
* Lê qual radio está marcado e seu texto (PT Diária, PT Extra, etc.).
* Serve para log / auditoria, mas **não altera** as decisões de preenchimento no momento (a lógica de riscos é guiada por “Trabalho a Quente”, não pelo subtipo de etapa).

---

### 2.3. Descrição da Etapa

* Procura um `textarea` de Descrição dentro de “Dados da Etapa”.
* Extrai valor/texto, remove espaços em branco excedentes.
* Se não encontrar, loga aviso e considera descrição vazia.

---

### 2.4. Características do trabalho / Observações

* Tenta localizar um bloco identificado próximo a “Características do trabalho” (label).
* Se não encontrar esse grupo específico:

  * Usa todo o texto da área “app-dados-da-etapa” como fallback.
* Isso gera um **texto grande** com:

  * Campos de formulário (rótulos, listas, etc.).
  * Itens de categoria (ANDAIME, CALDEIRARIA, ESCALADA INDUSTRIAL, etc.).
  * Observações como “Sobre o Mar”, “Acesso por Cordas”, etc.

Esse texto é a base para as **palavras-chave** de contexto.

---

## 3. Engine de contexto (palavras-chave → flags)

### 3.1. Normalização

Antes de procurar palavras-chave, o sistema aplica normalização:

* Converte para minúsculas.
* Remove acentos e caracteres especiais básicos.
* “Compacta” espaços múltiplos em espaço simples.
* Em algumas partes da lógica (especialmente EPIs) também:

  * Normaliza espaços e quebras de linha em uma única sequência de espaços.

---

### 3.2. Flags de contexto (o que já vemos claramente em log)

Para cada etapa, o plano gera flags booleanas como:

* `tem_acesso_cordas`
* `tem_agulheiro`
* `tem_altura`
* `tem_eletrico`
* `tem_pneumatico`
* `tem_sobre_o_mar`

Cada flag é ligada a um ou mais padrões de texto, por exemplo:

| Flag                | Exemplos de palavras/expressões gatilho                              |
| ------------------- | -------------------------------------------------------------------- |
| `tem_acesso_cordas` | “acesso por cordas”, “escala industrial”, “escalada industrial”      |
| `tem_altura`        | “altura”, “acima de 2m”, referência de trabalho em altura / NR-35    |
| `tem_sobre_o_mar`   | “sobre o mar”, “acima do mar”, “trabalho sobre o mar”                |
| `tem_agulheiro`     | “agulheiro pneumático”, “agulheiro”, “agulha vibratória”             |
| `tem_pneumatico`    | “pneumático”, “pneumatica”, uso explícito de ferramentas pneumáticas |
| `tem_eletrico`      | “painel elétrico”, “equipamento elétrico”, “trabalho elétrico”, etc. |

Na prática, o código varre a **descrição** + **características** e, ao encontrar qualquer gatilho correspondente, marca a flag como `True`.

---

### 3.3. Como as flags são usadas

As flags alimentam a construção de um objeto de **plano de preenchimento**, que tem subestruturas:

* `plano["qpt"]` → Questionário PT (por pergunta)
* `plano["epi_radios"]` → rádios de EPI adicional
* `plano["apn1"]` → respostas por questão APN-1
* `plano["epis_cat"]` → EPIs desejados por categoria (Vestimentas, Óculos, Luvas, Proteção Respiratória)
* Regras de Análise Ambiental (fixo em Trabalho a Quente)

Exemplo real de flags detectadas na etapa `18/164/2024`:

* tem_acesso_cordas = True
* tem_agulheiro = True
* tem_altura = True
* tem_eletrico = True
* tem_pneumatico = True
* tem_sobre_o_mar = True

Isso explica porque o plano fica “pesado” em EPI de altura, salvamento e ruído.

---

## 4. Lógica do plano – Questionário PT

### 4.1. Conceito

* O Questionário PT é representado no plano como um conjunto de **regras por questão**.
* Cada pergunta na tela tem:

  * Uma **ordem** (001, 002, 003…).
  * Um texto (“O trabalho a ser realizado é caracterizado como uma mudança?”, etc.).
* A automação não depende apenas da numeração; ela usa o **texto da pergunta** para mapear a resposta correta, o que torna robusto a reordenações/variações de Q001/Q002.

### 4.2. Padrão base (Trabalho a Quente “normal”)

Para o cenário observado (inspeção com agulheiro, altura, acesso por cordas, sobre o mar), o plano resultou em:

* “Mudança?” → **Não**
* “Permanência do Operador no Local de Trabalho?” → **Não**
* “Acompanhamento Periódico?” → **Sim**
* “As manobras, bloqueios e isolamentos foram executados conforme o plano de isolamento?” → **NA**
* “O equipamento foi drenado/limpo/ventilado?” → **NA**
* “Equipamento sinalizado com etiquetas de advertência?” → **NA**
* “Inspeções prévias em equipamentos elétricos e cabos supensos?” → **Sim**
* “Sistemas/equipamentos de combate a incêndio não normais – salvaguardas definidas?” → **NA**
* “Mangueiras de ar comprimido com engates compatíveis e travados?” → **Sim**  (ligado a contexto pneumático)
* “Local isolado, sinalizado e afastamento do pessoal desnecessário?” → **Sim**
* “Contenção de fagulhas com mantas adequadas?” → **NA**
* “Equipamento acoplado a equipamento elétrico – precauções quanto à energização acidental?” → **NA**
* “Risco de perda de produção?” → **Não**
* “Sensores de fogo e gás inibidos – salvaguardas definidas?” → **NA**
* “Observador instruído quanto uso de combate a incêndio?” → **NA** (para este caso)

**Ideia geral da lógica:**

* Há um **perfil padrão de Trabalho a Quente** que parte de:

  * “Mudança?” → Não (não caracteriza alteração de projeto/procedimento).
  * “Acompanhamento Periódico?” → Sim (trabalho crítico, exige supervisão).
  * Itens ligados a **procedimentos corporativos** (isolamento, drenagem, etiquetagem, etc.) são NA quando:

    * A etapa descrita não fala em abertura de equipamento, linha, tanque, etc.
* Itens diretamente relacionados a contexto detectado:

  * Se há ferramentas pneumáticas → “Mangueiras de ar comprimido possuem engates rápidos compatíveis” = Sim.
  * Se há trabalho em altura/sobre o mar → intensificação de EPI e salvaguardas (refletido mais em APN-1 e EPI do que em QPT, neste cenário).

---

## 5. Lógica do plano – EPI adicional (rádios na aba EPI)

### 5.1. Conceito

Na aba **EPI**, há um bloco “EPI adicional necessário e proteções”, com perguntas do tipo:

* “Cinto de Segurança” → Sim/Não
* “Ventilação Forçada” → Sim/Não
* “Colete Salva-vidas” → Sim/Não
* “Iluminação p/ uso em área classificada (tipo Ex)” → Sim/Não
* “Dupla Proteção Auricular” → Sim/Não
* “Protetor Facial” → Sim/Não

O plano `epi_radios` define para cada uma dessas:

* `Sim` / `Não`.

### 5.2. Regras vistas no cenário (cordas + altura + sobre o mar + pneumático)

Resultado do plano:

* Cinto de Segurança → **Sim**
* Ventilação Forçada → **Não**
* Colete Salva-vidas → **Sim**
* Iluminação Ex → **Não**
* Dupla Proteção Auricular → **Sim**
* Protetor Facial → **Sim**

Interpretação lógica:

* **Altura/acesso por cordas**:

  * `Cinto de Segurança` = Sim
    (Trabalho em altura, NR-35 → obrigatório)
* **Sobre o mar**:

  * `Colete Salva-vidas` = Sim
    (Trabalho com risco de queda no mar)
* **Ferramentas pneumáticas / agulheiro**:

  * `Dupla Proteção Auricular` = Sim (nível de ruído elevado)
  * `Protetor Facial` = Sim (projeção de partículas)
* **Sem indicação de espaço confinado / ventilação crítica**:

  * `Ventilação Forçada` = Não
* **Sem menção explícita a área classificada sem EPI Ex específico nessa etapa**:

  * `Iluminação Ex` = Não (não é que não exista área classificada, mas não há indicação de exceção ao padrão)

---

## 6. Lógica do plano – Análise Ambiental

### 6.1. Regra simples de Trabalho a Quente

Para o caso “Trabalho a Quente” no APLATQUENTE, a Análise Ambiental é tratada com uma **regra fixa**:

* Todas as questões (Líquidos inflamáveis, corrosivos, gás tóxico, sólidos combustíveis, etc.) → **“Não”**.

O motivo:

* A etapa que está sendo automatizada não está assumindo a presença, na interface, de um plano de manuseio de produto químico específico – o risco de Trabalho a Quente é tratado em outro lugar (QPT, EPIs, APN-1).
* O script ainda ignora linhas que não contêm uma pergunta (linhas meramente decorativas/agrupadoras).

---

## 7. Lógica do plano – APN-1

### 7.1. Conceito

APN-1 avalia se, dadas certas condições de risco ampliado, é necessário ou não acionar **APN-2** ou processos adicionais. Cada questão APN-1 é do tipo Sim/Não.

No cenário que analisamos, o plano retorna:

* Sim em:

  * Q007: Trabalho em altura acima de 2 m com risco de queda e não coberto por procedimento rotineiro.
  * Q008: Trabalho será executado sobre o mar.
* Não em todas as demais (Q001, Q002, ..., Q006, Q009, ..., Q020).

### 7.2. Regras inferidas por contexto

Base observado:

* `tem_altura` = True → Q007 = **Sim**
* `tem_sobre_o_mar` = True → Q008 = **Sim**
* Demais flags (elétrico, pneumático, etc.), no cenário observado, não ativaram outras APNs, possivelmente porque:

  * O trabalho em questão está dentro de uma matriz já tratada por PT/TRBR padrão para esses riscos.
  * Não há indicação de choque elétrico fora do padrão (não é intervenção em painel crítico, por exemplo).

**Padrão de construção do plano APN-1:**

1. Inicialmente, todas as questões APN-1 são definidas como **“Não”**.
2. Para cada flag relevante:

   * `tem_altura` → Q007 = Sim.
   * `tem_sobre_o_mar` → Q008 = Sim.
   * (Outras flags, em versões futuras, podem ajustar Q009–Q020, mas no cenário observado a lógica ativa apenas estas.)

---

## 8. Lógica do plano – EPIs por categoria (aba EPI, grid de vinculação)

### 8.1. Conceito

Além dos rádios “EPI adicional”, existe a **lista de EPIs vinculados** organizados por categoria:

* Vestimentas
* Óculos
* Luvas
* Proteção Respiratória

O plano define, para cada categoria, o conjunto de EPIs que **deveriam** estar vinculados.

Na execução, a lógica é:

1. Ler itens atuais da categoria (o que já está associado).
2. Comparar com o conjunto **esperado** do plano.
3. Calcular:

   * Itens faltantes = esperados – atuais.
   * Itens excedentes = atuais – esperados.
4. Incluir faltantes (via modal de associação).
5. Remover excedentes (clicando linha + botão “-”).

### 8.2. Vestimentas (para o cenário observado)

Plano esperado (Trabalho a Quente, altura, cordas, sobre o mar):

* BOTA CANO ALTO
* CAPACETE S/ABAS C/ CARNEIRA E PRESILHA DE QUEIXO EM Y
* CINTO DE SEG. TP PARA-QUEDISTA
* CINTO DE SEGURANÇA PARA RESGATE
* COLETE SALVA VIDAS RF (apenas para trabalhos a quente)
* COLETE SALVA-VIDAS
* DUPLA PROTEÇÃO AUDITIVA
* DUPLO TALABARTE EM Y OU LINHA DE VIDA CONJUGADA TRAVA QUEDA
* EPI´s OBRIGATÓRIOS (CAPACETE, BOTA, PROT. AURIC. E UNIFORME)
* MACACÃO COM GOLA TIPO PADRE E BOLSOS FECHADOS

Efeito das flags:

* `tem_altura` / `tem_acesso_cordas`:

  * GANHA: cinto para-quedista, cinto de resgate, duplo talabarte, bota cano alto, capacete adequado.
* `tem_sobre_o_mar`:

  * GANHA: colete salva-vidas + colete salva-vidas RF.
* `tem_pneumatico` / `tem_agulheiro`:

  * GANHA ou reforça: dupla proteção auditiva.
* “Trabalho a Quente”:

  * GANHA: EPI´s obrigatórios gerais, macacão adequado.

Na situação que você rodou:

* O sistema:

  * adicionou o “EPI´s OBRIGATÓRIOS (CAPACETE, BOTA, PROT. AURIC. E UNIFORME)” que faltava.
  * removeu itens excedentes:

    * VESTIM. RF CLASSE 4
    * VESTIM. TYVEC
    * INTERV. REDE ELETRICA (...)
    * BALACLAVA AE-2

Ou seja, “limpou” tudo que não faz parte do conjunto alvo de Trabalho a Quente com cordas sobre o mar.

---

### 8.3. Óculos

Plano esperado:

* PROTETOR FACIAL
* ÓCULOS AMPLA VISÃO

No cenário:

* Atuais iniciais:

  * PROTETOR FACIAL
  * ÓCULOS AMPLA VISÃO
  * ÓCULOS PROTETOR FACIAL
  * ÓCULOS SEG. CONTRA POEIRA
* Itens faltantes: nenhum.
* Excedentes (para remoção):

  * ÓCULOS PROTETOR FACIAL
  * ÓCULOS SEG. CONTRA POEIRA

Depois da limpeza ficam apenas:

* PROTETOR FACIAL
* ÓCULOS AMPLA VISÃO

Ligação com flags:

* `tem_agulheiro` / `tem_pneumatico`:

  * justificam proteção reforçada para olhos/face → protetor facial + óculos de ampla visão.

---

### 8.4. Luvas

Plano esperado:

* LUVA ANTI-VIBRAÇÃO
* LUVA DE PROTEÇÃO CONTRA IMPACTOS MODELO II (3, 4, 3, 3, 'C', 'P')

No cenário:

* Inicialmente, havia uma lista “poluída” com várias luvas (PVC, isolante, rede elétrica, etc.).
* O plano:

  * Garantiu que as duas luvas de vibração/impacto estivessem presentes.
  * Removeu tudo que era excedente:

    * luva isolante, luva PVC, luva nitrílica, conjunto de luvas para rede elétrica, “NÃO APLICÁVEL”, etc.

Ligação com flags:

* `tem_agulheiro` / `tem_pneumatico`:

  * Justifica luva anti-vibração e luva de impacto.

---

### 8.5. Proteção Respiratória

Plano esperado:

* PEÇA SEMI-FACIAL FILTRANTE 2

No cenário:

* Inicialmente havia:

  * Máscaras C1 para gases ácidos, metilamina, vapor orgânico.
  * * peça semi-facial filtrante 2.
* O plano:

  * Mantém somente o que é aderente ao trabalho de agulheiro/limpeza/inspeção em altura.
  * Remove as máscaras específicas que não são necessárias naquele contexto.

Ligação com flags:

* Até aqui, o cenário mostra que o plano assume **proteção respiratória básica filtrante** (pó, partículas) como suficiente, sem citar produtos químicos específicos na descrição.

---

## 9. Aplicação do plano na interface (sem código, só comportamento)

### 9.1. Questionário PT

* Navega para aba “Questionário PT”.
* Lê todas as linhas que contenham um número de ordem e um texto de pergunta.
* Para cada linha:

  * Identifica a pergunta pelo texto.
  * Procura no `plano["qpt"]` a resposta correspondente (Sim/Não/NA).
  * Seleciona o rádio correto na linha (quando a pergunta existe no plano).
* Ignora:

  * Perguntas não reconhecidas.
  * Linhas vazias ou decorativas.

---

### 9.2. EPI adicional

* Na aba EPI, dentro de “EPI adicional necessário e proteções”:

  * Lê todas as questões (Q001–Q00X).
  * Identifica cada uma pelo texto (“Cinto de Segurança”, etc.).
  * Aplica o `plano["epi_radios"]`, ligando Sim/Não conforme definido.

---

### 9.3. Análise Ambiental

* Vai à aba “Análise Ambiental”.
* Varre as linhas:

  * Ignora linhas sem pergunta (agrupadores).
  * Para cada pergunta de fato, marca **“Não”**.
* É uma aplicação direta da regra fixa.

---

### 9.4. APN-1

* Aba “APN-1”.
* Mesma estratégia:

  * Ignora linhas de placeholder/vazias.
  * Para cada pergunta com texto, identifica o código (Q001, Q002, etc.).
  * Usa o `plano["apn1"]` para marcar cada questão com “Sim” ou “Não”.
* No exemplo:

  * Q007 e Q008 → Sim.
  * Todas as demais → Não.

---

### 9.5. Aba EPI – EPIs vinculados por categoria

Para cada categoria em ordem: **Vestimentas**, **Óculos**, **Luvas**, **Proteção Respiratória**:

1. Localiza o bloco da categoria (pelo rótulo).
2. Lê todos os itens atualmente vinculados.
3. Calcula faltantes e excedentes versus `plano["epis_cat"][categoria]`.

**Inclusão de faltantes:**

* Se existirem faltantes:

  * Clica no botão “+” da categoria.
  * Abre modal de associação de EPI.
  * Dentro da tabela do modal, procura cada EPI pelo texto.
  * Marca a checkbox correspondente.
  * Confirma.
  * Trata popup de erro se o sistema exigir “código de EPI não pode ser vazio”.
  * Aguarda o fechamento do modal.

**Remoção de excedentes:**

* Se existirem excedentes:

  * Para cada EPI excedente:

    * Localiza o EPI na tabela da categoria.
    * Clica na linha.
    * Pressiona o botão “-” da categoria.
    * Aguarda a atualização (linha some / tabela recarrega).
* Se o item não for encontrado:

  * Loga um aviso e segue para o próximo (não aborta).

---

## 10. Confirmação final e idempotência

### 10.1. Confirmação geral

Ao final de todos os preenchimentos:

* Volta ao rodapé da etapa.
* Clica em “Confirmar” (rodapé).
* Esta confirmação grava:

  * QPT.
  * EPI adicional.
  * Análise Ambiental.
  * APN-1.
  * EPIs vinculados.

Não há “salvar parcial” intermediário – o conceito é:

> Monta plano → aplica → um único Confirmar.

---

### 10.2. Idempotência prática

Se você rodar o script **novamente** na mesma etapa, com o mesmo contexto:

* As respostas do QPT, EPI adicional, AA e APN-1 já vão bater com o plano.
* Na aba EPI:

  * Itens faltantes serão zero.
  * Itens excedentes serão zero (ou apenas alguns residuais que não puderam ser removidos por inconsistência de texto).
* Resultado: a segunda execução é quase só leitura + verificação, com mínima modificação.

Isso é importante para:

* Auditar o comportamento.
* Rodar o script em rotina sem medo de “estragar” uma etapa já bem configurada.

---

## 11. Esquema mental resumido (em forma de mapa lógico)

Se alguém te perguntar em 30 segundos “como a lógica do APLATQUENTE decide tudo?”, o resumo é:

1. **Filtro de escopo**
   Só mexe em etapas cujo Tipo Trabalho = “Trabalho a Quente”.

2. **Leitura da realidade**
   Lê descrição + características e identifica contextos (cordas, altura, sobre o mar, agulheiro, pneumático, elétrico…).

3. **Tradução em plano de segurança**
   A partir desses contextos, define:

   * Respostas de Questionário PT (mudança? isolamentos? inspeções?).
   * Necessidade de EPI adicional (cinto, colete, dupla proteção, protetor facial).
   * APN-1 (quais riscos “elevados” justificam S/N).
   * EPIs vinculados por categoria (quais EPIs têm que estar lá e quais devem sair).
   * Análise Ambiental (neste modelo, tudo “Não” para Trabalho a Quente).

4. **Execução na tela**
   Vai em cada aba, aplica o plano, e dá um único Confirmar ao final.

5. **Idempotente**
   Se rodar de novo, o sistema praticamente só verifica e faz pequenos ajustes, porque o plano alvo já está todo refletido na etapa.
