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
