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

   1. Escopo geral

Fonte: log_aplat_unificado.txt (mesmo formato do htmlaplat.py).

Os scripts filtram apenas etapas com:

Tipo de Trabalho: Trabalho a Quente.

Textos usados para regras de contexto:

Descrição

Características do trabalho / Observações

Antes de procurar palavras-chave:

Remove acentos, cedilha, til etc.

Converte para MAIÚSCULO.

Usa o texto normalizado de descrição + características.

Busca sempre a expressão inteira na ordem correta, ex.: "ACESSO POR CORDAS" tem que aparecer assim, não apenas “acesso” e “cordas” separados.

2. Base e regras – EPI (rádios principais)
2.1. Base global (sem contexto)
Código	Pergunta	Base (sem contexto)
Q001	Cinto de Segurança	Não
Q002	Ventilação Forçada	Não
Q003	Colete Salva-vidas	Não
Q004	Iluminação p/ uso em área classificada (Ex)	Não
Q005	Dupla Proteção Auricular	Sim
Q006	Protetor Facial	Sim (ajustado por contexto)
2.2. Regras de contexto para EPI rádios

Tudo é decidido em cima de ctx, montado a partir de Descrição+Características normalizadas.

2.2.1. “Acesso por Cordas” / “Sobre o mar”

Se ACESSO POR CORDAS no texto:

Q001 – Cinto de Segurança → Sim

Se SOBRE O MAR no texto:

Q001 – Cinto de Segurança → Sim

Q003 – Colete Salva-vidas → Sim

2.2.2. Risco para olhos (hazard_olhos)

Consideramos hazard_olhos = True se existir pelo menos um de:

“CHAMA ABERTA”

“ESMERILHADEIRA”

“OXICORTE”

“SOLDA”

“TRATAMENTO MECÂNICO”

“AGULHEIRO”

“LIXADEIRA PNEUMATIC…” (qualquer variação ex.: PNEUMÁTICA)

“LIXADEIRA” (genérico)

“CORTE” (palavra inteira, não vale “OXICORTE”)

“SERRA SABRE”

Regra para Q006 – Protetor Facial:

Se hazard_olhos = True → Q006 esperado = 'Sim'

Se hazard_olhos = False → Q006 esperado = 'Não'

3. Base e regras – EPIs vinculados por categoria
3.1. Base global (sem contexto)

Luvas

LUVA DE PROTEÇÃO CONTRA IMPACTOS MODELO II (3, 4, 3, 3, 'C', 'P')

Proteção Respiratória

Base neutra:

"NÃO APLICÁVEL"
(em contextos de risco, substituído por EPIs específicos)

Vestimentas

DUPLA PROTEÇÃO AUDITIVA

EPI´s OBRIGATÓRIOS (CAPACETE, BOTA, PROT. AURIC. E UNIFORME)

OBS: BALACLAVA saiu da base global. Hoje só entra por contexto de chama aberta / esmerilhadeira / oxicorte / solda.

Óculos

Base “de risco”:

ÓCULOS AMPLA VISÃO

PROTETOR FACIAL

3.2. Regra “sem risco para olhos”

Se não houver nenhum dos termos de risco (hazard_olhos = False):

Categoria Óculos passa a ter como base apenas:

ÓCULOS SEGURANÇA CONTRA IMPACTO

Em paralelo, como já visto:

Q006 – Protetor Facial esperado = Não

3.3. Regras para “chama aberta / esmerilhadeira / oxicorte / solda”

Se existir qualquer de:

“CHAMA ABERTA”

“ESMERILHADEIRA”

“OXICORTE”

“SOLDA”

então:

Luvas – adicionais obrigatórios

LUVA ARAMIDA

LUVA DE RASPA

Vestimentas – adicionais obrigatórios

BALACLAVA

AVENTAL DE RASPA

CAPUZ

MANGA DE RASPA

PERNEIRA DE RASPA

VESTIM. COMPLETA DE RASPA

Proteção Respiratória

Base deixa de ser "NÃO APLICÁVEL" e passa a ser:

PEÇA SEMI-FACIAL FILTRANTE 2

Óculos

Mantém base de risco (ÓCULOS AMPLA VISÃO, PROTETOR FACIAL).

Adiciona sempre:

MÁSCARA SOLDADOR

Adiciona condicionalmente:

Se “SOLDa” ou “OXICORTE”:

LENTE DE ACORDO COM AMPERAGEM DA MÁQUINA

Se “OXICORTE”:

ÓCULOS MAÇARIQUEIRO

3.4. Regras para “TRATAMENTO MECÂNICO / AGULHEIRO / LIXADEIRA PNEUMÁTIC…”

Se existir qualquer de:

“TRATAMENTO MECANICO”

“AGULHEIRO”

“LIXADEIRA PNEUMATIC…” (qualquer variação)

então:

Proteção Respiratória

Base passa a ser:

PEÇA SEMI-FACIAL FILTRANTE 2
(ou seja, deixa de ser "NÃO APLICÁVEL")

Luvas

Adicional obrigatório:

LUVA ANTI-VIBRAÇÃO

3.5. Regras para “pneumático / pneumática”

Se texto contiver algo com “PNEUMATIC…”

(já coberto pelas regras acima para QPT e risco olhos)

Influencia:

Q007 do QPT (mangueiras de ar comprimido) → ver Seção 4.3.

hazard_olhos = True (por “LIXADEIRA PNEUMATIC…” ou outros).

3.6. “Acesso por Cordas”

Se contiver “ACESSO POR CORDAS”:

Vestimentas – adicionais obrigatórios

BOTA CANO ALTO

CAPACETE S/ABAS C/ CARNEIRA E PRESILHA DE QUEIXO EM Y

CINTO DE SEG. TP PARA-QUEDISTA

CINTO DE SEGURANÇA PARA RESGATE

DUPLO TALABARTE EM Y OU LINHA DE VIDA CONJUGADA TRAVA QUEDA

MACACÃO COM GOLA TIPO PADRE E BOLSOS FECHADOS

3.7. “Sobre o mar”

Se contiver “SOBRE O MAR”:

Vestimentas – adicionais obrigatórios

BOTA CANO ALTO

CAPACETE S/ABAS C/ CARNEIRA E PRESILHA DE QUEIXO EM Y

CINTO DE SEG. TP PARA-QUEDISTA

CINTO DE SEGURANÇA PARA RESGATE

COLETE SALVA VIDAS RF (apenas para trabalhos a quente)

COLETE SALVA-VIDAS

DUPLO TALABARTE EM Y OU LINHA DE VIDA CONJUGADA TRAVA QUEDA

MACACÃO COM GOLA TIPO PADRE E BOLSOS FECHADOS

3.8. Tratamento especial de “NÃO APLICÁVEL”

Base global de Proteção Respiratória sem risco = {"NÃO APLICÁVEL"}.

Em qualquer contexto em que a base passe a ser, por exemplo,
{"PEÇA SEMI-FACIAL FILTRANTE 2"}, o item "NÃO APLICÁVEL" não está mais na base.

Se a etapa trouxer "NÃO APLICÁVEL" junto com EPIs respiratórios:

"NÃO APLICÁVEL" é marcado como Adicional (amarelo) no relatório.

Na prática isso te mostra visualmente o erro: não faz sentido ter EPI + “não aplicável”.

4. Base e regras – Questionário PT (Trabalho a Quente)
4.1. Base global (sem contexto)

Chave = (código, texto idêntico ao relatório). Simplificando:

Q001 – O trabalho a ser realizado é caracterizado como uma mudança? → Não

Q001 – Permanência do Operador no Local de Trabalho? → Não

Q002 – Acompanhamento Periódico? → Sim

Q002 – As manobras, bloqueios e isolamentos… → NA

Q003 – O equipamento foi drenado… → NA

Q004 – O equipamento está corretamente sinalizado… → NA

Q005 – Inspeções prévias em equipamentos elétricos… → NA (ajustado por contexto)

Q006 – Sistemas de combate a incêndio não operacionais… → NA

Q007 – Mangueiras de ar comprimido… → NA (ajustado por contexto)

Q008 – Local isolado / sinalizado… → Sim

Q009 – Contenção de fagulhas com mantas… → NA (ajustado por contexto)

Q010 – Equipamento acoplado a motor elétrico… → NA

Q011 – Tamponamentos de drenos, ralos, vents… → NA (ajustado por contexto)

Q012 – Risco de Perda de Produção? → Não

Q013 – Inibir sensores de fogo e gás… → NA (ajustado por contexto CO2+chama)

Q014 – Observador instruído para uso de combate a incêndio? → NA (ajustado por contexto)

4.2. Regras de contexto para QPT
4.2.1. Q005 – inspeções em equipamentos elétricos

Se houver:

“CHAMA ABERTA” ou

qualquer “ELETRIC…” (cobre elétrico/eléctrico/eléctrica)

então:

Q005 esperado = Sim
Caso contrário → NA

4.2.2. Q007 – mangueiras de ar comprimido

Se houver qualquer de:

“PNEUMATIC…”

“TRATAMENTO MECANICO”

“AGULHEIRO”

“LIXADEIRA PNEUMATIC…”

então:

Q007 esperado = Sim
Caso contrário → NA

4.2.3. Q009 – contenção de fagulhas

Se houver “CHAMA ABERTA / ESMERILHADEIRA / OXICORTE / SOLDA”:

Q009 esperado = Sim
Caso contrário → NA

4.2.4. Q011 – tamponamentos

Se houver “CHAMA ABERTA / ESMERILHADEIRA / OXICORTE / SOLDA”:

Q011 esperado = Sim
Caso contrário → NA

4.2.5. Q013 – sensores de fogo e gás (CO2 + chama)

Se houver CO2 + chama, i.e.:

“AMBIENTES PROTEGIDOS POR CO2” e

qualquer de “CHAMA ABERTA / ESMERILHADEIRA / OXICORTE / SOLDA”

então:

Q013 esperado = Sim
Caso contrário → NA

4.2.6. Q014 – observador instruído

Se houver “CHAMA ABERTA / ESMERILHADEIRA / OXICORTE / SOLDA”:

Q014 esperado = Sim
Caso contrário → NA

5. Critério de divergência – EPI rádios, EPIs categoria, QPT

No relatório relatorioaplat_trabalho_quente_divergencias.html:

Só entra etapa em que exista pelo menos uma divergência em:

EPI (rádios principais), ou

EPIs por categoria, ou

Questionário PT.

5.1. Tipos de divergência

EPI rádios / QPT

extra: pergunta existe na etapa, mas não existe na base daquele contexto.

Ex.: pergunta diferente, ou Q com texto diferente → amarelo.

missing: pergunta existe na base, mas não apareceu na etapa.

diff: pergunta existe nos dois, mas:

resposta da etapa ≠ resposta esperada na base.

EPIs por categoria

Para cada categoria:

missing (vermelho): item esperado na base, não presente na etapa.

extra (amarelo): item presente na etapa, mas não está na base daquele contexto.

5.2. Cores no HTML

Divergência em texto de EPI rádios / QPT:

<span class='diff-yellow'>...</span> → amarelo

Divergência em EPIs por categoria:

missing → texto em vermelho (diff-red)

extra → texto em amarelo (diff-yellow)

6. APN-1 – Base e regras (Trabalho a Quente)

APN-1 está em outro relatório, mas com a mesma lógica geral de contexto.

6.1. Base global de APN-1

Para todas as 20 questões (Q001…Q020) a base é:

resp = 'Não'

Ou seja, tudo é “Não” por padrão, e as regras abaixo sobem para “Sim” quando o risco está presente.

6.2. Regras de contexto para APN-1

As palavras-chave são buscadas em Descrição + Características (normalizadas).

6.2.1. Altura / Acesso por Cordas

Se contiver:

“ALTURA” ou

“ACESSO POR CORDAS”

então:

Q007 esperado = Sim
“Este trabalho será executado em altura acima de 2m…?”

6.2.2. Sobre o mar

Se contiver:

“SOBRE O MAR”

então:

Q007 esperado = Sim

Q008 esperado = Sim
“Este trabalho será executado sobre o mar?”

6.2.3. Chama aberta

Se contiver:

“CHAMA ABERTA”

então:

Q010 esperado = Sim
“O trabalho envolverá chama aberta (solda, corte, esmerilhamento)?”

(Você está usando isso como confirmação de que a equipe marcou corretamente o risco, coerente com EPI/QPT.)

6.2.4. Ambientes protegidos por CO2 / sistema de CO2

Se contiver qualquer de:

“PROTEGIDO POR SISTEMA DE CO2”

“PROTEGIDOS POR CO2”

“PROTEGIDO POR CO2”

(e tipicamente o seu log já traz “AMBIENTES PROTEGIDOS POR CO2” em Características)

então:

Q019 esperado = Sim
“O trabalho envolve manutenção em sistema de combate a incêndio por CO2 ou será realizado no interior de ambientes protegidos por CO2?”

6.2.5. Espaço confinado

Se contiver:

“ESPAÇO CONFINADO”

então:

Q006 esperado = Sim
“Este trabalho será executado no interior de espaços confinados?”

6.2.6. Equipamento pressurizado

Se contiver:

“PRESSURIZADO”

então:

Q013 esperado = Sim
“O trabalho envolverá a abertura de equipamento ou linha, ou será realizado em equipamentos e sistemas pressurizados…?”

6.2.7. Partes móveis

Se contiver:

“PARTES MOVEIS” (sem acento mesmo, após normalização)

então:

Q015 esperado = Sim
“Durante a execução do trabalho pode haver aproximação do executante com partes móveis de máquinas ou equipamentos…?”

6.2.8. Hidrojato / Hidrojateamento

Se contiver:

“HIDROJATO” ou

“HIDROJATEAMENTO”

então:

Q018 esperado = Sim
“O trabalho é de hidrojateamento?”

6.3. Critério de divergência – APN-1

No relatório APN-1 (Trabalho a Quente):

Monta-se uma base dinâmica base_apn para cada etapa (com as regras acima).

Lê-se as respostas de APN-1 (Q001…Q020).

Para cada questão:

Só é incluída no HTML se houver divergência, segundo:

Sim indevido

Resposta da etapa = Sim

Base esperada ≠ Sim (ou seja, base é Não ou NA)
→ Linha exibida como:
Qxxx: resp='Sim' (ESPERADO: 'Não') | ...

Sim faltando

Base esperada = Sim

Resposta da etapa ≠ Sim (Não ou NA)
→ Linha exibida como:
Qxxx: resp='Não' (ESPERADO: 'Sim') | ...

Se uma etapa não tiver nenhuma divergência em APN-1, ela não aparece no relatório APN-1.

No HTML:

Título por etapa (número, data, tipo de trabalho).

Mostra:

Descrição

Características

Bloco “APN-1 – divergências em relação à base” com apenas as questões que estão fora do padrão.

7. Resumo operacional

Para Trabalho a Quente você passa a ter:

Relatório de divergências principais
relatorioaplat_trabalho_quente_divergencias.html
→ EPIs (rádio), EPIs por categoria, Questionário PT

Somente etapas onde alguma coisa difere do padrão (base + regras de contexto).

Itens faltando = vermelho; itens a mais ou respostas diferentes = amarelo.

Relatório de divergências APN-1
(ex.: tquenteapn1.py gerando seu HTML)

Somente questões de APN-1 que não batem com o que o contexto da tarefa indica.

Você lê Descrição/Características + APN-1 e enxerga rápido:

riscos que deveriam estar marcados e não estão, ou

riscos que foram marcados sem aparecer no texto.

Com isso, o “padrão Trabalho a Quente” está fechado em quatro camadas:

Texto da tarefa (Descrição + Características)

EPIs (rádios + categorias)

Questionário PT

APN-1

todas dirigidas por um conjunto único de regras de contexto que você vem refinando.
