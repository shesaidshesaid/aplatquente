#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
quent3_preenchimento.py
Rotinas de preenchimento automático:
- Questionário PT
- EPI adicional necessário e proteções
- Análise ambiental
- APN-1 (dinâmico por texto, até 20 questões, numeração variável)
"""

import time
import re
import unicodedata
from typing import Dict, Tuple, Any, List, Optional, Set
from functools import wraps, lru_cache
from collections import defaultdict

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    StaleElementReferenceException,
)

from quent1_infra import goto_tab, safe_find_element, wait_for_document_ready
from quent2_plano import normalizar_texto

# -------------------------------------------------------------------
# Constantes e configurações
# -------------------------------------------------------------------
# XPATHS para containers e elementos comuns
XPATH_CONTAINER_EPI = "//app-epi-da-etapa//section[@id='questionario']//div[@id='EPI']"
XPATH_ANALISE_AMBIENTAL = "//div[@id='AMB' or .//h4[contains(.,'O local de trabalho tem:')]]"
XPATH_APN1_ROWS = [
    "//div[@id='APN1']//div[contains(@class,'row') and starts-with(@id,'questao_')]",
    "//app-apn1//div[contains(@class,'row') and starts-with(@id,'questao_')]",
    "//div[contains(@class,'row') and starts-with(@id,'questao_')]",
]

# Padrões para análise de texto
PADROES_ALTURA = frozenset([
    "ALTURA", "2 METROS", "2M", "TRABALHO EM ALTURA", "ELEVADO", "ACESSO POR CORDAS"
])

PADROES_CHAMA = frozenset([
    "CHAMA ABERTA", "SOLDA", "OXICORTE", "ESMERILHADEIRA", "TRABALHO A QUENTE", "CHAMA"
])

PADROES_CO2 = frozenset([
    "PROTEGIDO POR CO2", "PROTEGIDOS POR CO2",
    "PROTEGIDO POR SISTEMA DE CO2", "AMBIENTES PROTEGIDOS POR CO2"
])

PADROES_PRESSURIZADO = frozenset([
    "PRESSURIZADO", "PRESSÃO", "PRESSAO TRAPEADA", "PRESSAO TRAP"
])

PADROES_HIDROJATO = frozenset([
    "HIDROJATO", "HIDROJATEAMENTO", "JATEAMENTO"
])

# Flag global de dry-run para EPI adicional (não clicar, só logar)
DEBUG_EPI_DRY_RUN = False


# -------------------------------------------------------------------
# Decorator para medição de tempo otimizado
# -------------------------------------------------------------------
def timeit_decorator(func_name: Optional[str] = None):
    """Decorator para medição de tempo de execução."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            result = func(*args, **kwargs)
            elapsed = time.perf_counter() - start_time
            name = func_name or func.__name__
            print(f"[TIMER] {name}: {elapsed:.3f}s")
            return result

        return wrapper

    return decorator


# -------------------------------------------------------------------
# Utilitários de normalização e cache
# -------------------------------------------------------------------
@lru_cache(maxsize=512)
def normalizar_string(texto: str) -> str:
    """Normaliza string para comparação: remove acentos, uppercase, espaços."""
    if not texto:
        return ""

    # Remove acentos
    texto = ''.join(c for c in unicodedata.normalize('NFD', texto)
                    if unicodedata.category(c) != 'Mn')

    # Converte para maiúsculas e remove espaços extras
    texto = texto.upper()
    texto = re.sub(r'\s+', ' ', texto).strip()

    return texto


def extrair_digitos_codigo(codigo: str) -> str:
    """Extrai apenas dígitos de um código e padroniza como '001', '002', etc."""
    if not codigo:
        return ""

    digitos = ''.join(c for c in str(codigo) if c.isdigit())
    return digitos.zfill(3) if digitos else ""


# Pergunta específica: "O trabalho a ser realizado é caracterizado como uma mudança?"
TEXTO_MUDANCA_QPT = normalizar_string(
    "O trabalho a ser realizado é caracterizado como uma mudança?"
)


# -------------------------------------------------------------------
# Questionário PT - Módulo otimizado
# -------------------------------------------------------------------
class QuestionarioPTProcessor:
    """Processador otimizado para Questionário PT."""

    def __init__(self, driver, timeout: float):
        self.driver = driver
        self.timeout = timeout
        self.question_map = None

    @timeit_decorator()
    def preencher(self, qpt_plano: Dict[Tuple[str, str], str]) -> Tuple[int, int]:
        """Preenche Questionário PT baseado no plano fornecido."""
        print("[STEP] Preenchendo aba 'Questionário PT'...")
        goto_tab(self.driver, "Questionário PT", self.timeout)

        # Aguarda carregamento da aba/questionário
        try:
            wait_for_document_ready(self.driver, self.timeout)
        except Exception as e:
            print(f"[WARN] wait_for_document_ready falhou na aba QPT: {e}")

        try:
            WebDriverWait(self.driver, self.timeout).until(
                EC.presence_of_element_located(
                    (By.XPATH, "//div[contains(@class,'row') and starts-with(@id,'questao_')]")
                )
            )
        except TimeoutException:
            print("[WARN] Nenhuma linha de questão encontrada na aba QPT após o timeout")

        time.sleep(0.2)

        self._construir_mapa_perguntas()
        sucessos, total = self._processar_questoes(qpt_plano)

        # Clica em Confirmar para salvar o Questionário PT
        self._clicar_confirmar_qpt()

        return sucessos, total

    def _construir_mapa_perguntas(self):
        """Constrói mapa de perguntas da tela."""
        rows = self.driver.find_elements(
            By.XPATH, "//div[contains(@class,'row') and starts-with(@id,'questao_')]"
        )

        mapa_codigo = {}
        mapa_texto = defaultdict(list)

        for row in rows:
            info = self._extrair_info_pergunta(row)
            if info:
                chave_codigo = (info['cod_norm'], info['texto_norm'])
                mapa_codigo[chave_codigo] = info
                mapa_texto[info['texto_norm']].append(info)

        self.question_map = {
            'by_code': mapa_codigo,
            'by_text': dict(mapa_texto),
        }

    def _extrair_info_pergunta(self, row) -> Optional[dict]:
        """Extrai informações de uma pergunta individual."""
        try:
            ordem_elem = row.find_element(By.CSS_SELECTOR, ".ordem")
            pergunta_elem = row.find_element(By.CSS_SELECTOR, ".pergunta")
        except NoSuchElementException:
            return None

        cod_raw = ordem_elem.text or ""
        texto_raw = pergunta_elem.text or ""

        cod_norm = extrair_digitos_codigo(cod_raw)
        texto_norm = normalizar_string(texto_raw)

        if not texto_norm:
            return None

        return {
            'row': row,
            'ordem': cod_raw.strip(),
            'texto': texto_raw.strip(),
            'cod_norm': cod_norm,
            'texto_norm': texto_norm,
        }

    def _processar_questoes(self, qpt_plano: Dict[Tuple[str, str], str]) -> Tuple[int, int]:
        """Processa todas as questões do plano."""
        total_processadas = 0
        sucessos = 0

        for (codigo, texto), resposta in qpt_plano.items():
            if resposta is None:
                continue

            resposta_str = str(resposta).strip()
            if not resposta_str:
                continue

            total_processadas += 1

            if self._processar_questao_individual(codigo, texto, resposta_str):
                sucessos += 1

        self._log_resultado(total_processadas, sucessos)
        return sucessos, total_processadas

    def _processar_questao_individual(self, codigo: str, texto: str, resposta: str) -> bool:
        """Processa uma questão individual."""
        info = self._encontrar_questao(codigo, texto)
        if not info:
            print(f"[WARN] Questão não encontrada: código='{codigo}', texto='{texto}'")
            return False

        print(f"[INFO] Respondendo Q{info['ordem']}: '{info['texto'][:70]}...' com '{resposta}'")

        resposta_norm = normalizar_string(resposta)
        sucesso = self._marcar_resposta(info['row'], resposta)

        # Se for a pergunta de "mudança" e a resposta for NÃO, tratar o popup de confirmação
        try:
            if sucesso and self._eh_pergunta_mudanca(info) and resposta_norm in ("NAO", "NÃO", "NO", "N"):
                self._lidar_popup_mudanca()
        except Exception as e:
            print(f"[WARN] Erro ao tratar popup de Mudança: {e}")

        return sucesso

    def _eh_pergunta_mudanca(self, info: dict) -> bool:
        """Detecta se a questão é a pergunta de 'Mudança' do Questionário PT."""
        texto_norm = info.get("texto_norm") or normalizar_string(info.get("texto", ""))
        if not texto_norm:
            return False
        return TEXTO_MUDANCA_QPT in texto_norm

    def _lidar_popup_mudanca(self):
        """
        Trata o popup que aparece ao marcar 'Não' na pergunta:
        'O trabalho a ser realizado é caracterizado como uma mudança?'.

        Estratégia:
        - Após marcar 'Não', aguarda 1 segundo.
        - Tenta localizar o botão "Sim" do popup:
            /html/body/app-root/div/app-confirm-dialog/div/div/div/div[3]/div/button[1]
          ou pelo id="okButton".
        - Clica em "Sim" e segue o fluxo normal.
        """
        try:
            # Espera fixa de 1 segundo após marcar "Não"
            time.sleep(1.0)

            # Espera curta para o botão ficar clicável
            wait = WebDriverWait(self.driver, 1.0)

            botao_sim = None
            locators = [
                # 1) Pelo ID (mais robusto)
                (By.ID, "okButton"),
                # 2) Pelo XPATH absoluto informado
                (By.XPATH, "/html/body/app-root/div/app-confirm-dialog/div/div/div/div[3]/div/button[1]"),
            ]

            for by, selector in locators:
                try:
                    botao_sim = wait.until(
                        EC.element_to_be_clickable((by, selector))
                    )
                    if botao_sim:
                        break
                except TimeoutException:
                    botao_sim = None
                    continue

            if not botao_sim:
                print("[WARN] Popup de Mudança: botão 'Sim' não encontrado dentro de 1s.")
                return

            # Garante que o botão esteja visível na tela e clica
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block:'center', inline:'nearest'});",
                botao_sim,
            )
            time.sleep(0.1)
            botao_sim.click()
            print("[CLICK] Botão 'Sim' do popup de Mudança clicado")

        except TimeoutException:
            print("[WARN] Popup de Mudança não apareceu dentro do tempo limite.")
        except Exception as e:
            print(f"[WARN] Erro ao tentar clicar em 'Sim' no popup de Mudança: {e}")

    def _clicar_confirmar_qpt(self):
        """Clica no botão 'Confirmar' do Questionário PT e trata modais."""
        try:
            wait = WebDriverWait(self.driver, self.timeout)
            btn = wait.until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//app-botoes-etapa//button[normalize-space()='Confirmar']")
                )
            )

            # **ADICIONAR: Fechar modais antes de clicar**
            from quent1_infra import ensure_no_messagebox
            ensure_no_messagebox(self.driver, 2)

            self.driver.execute_script(
                "arguments[0].scrollIntoView({block:'center', inline:'nearest'});",
                btn,
            )
            time.sleep(0.1)
            btn.click()
            print("[CLICK] Botão 'Confirmar' do Questionário PT acionado")

            # **ADICIONAR: Aguardar e fechar possíveis modais após clique**
            time.sleep(1)
            ensure_no_messagebox(self.driver, 3)

        except TimeoutException:
            print("[WARN] Botão 'Confirmar' do Questionário PT não encontrado/visível")
        except Exception as e:
            print(f"[WARN] Erro ao clicar em 'Confirmar' no Questionário PT: {e}")

    def _encontrar_questao(self, codigo: str, texto: str) -> Optional[dict]:
        """Encontra questão usando código e texto."""
        cod_norm = extrair_digitos_codigo(codigo)
        texto_norm = normalizar_string(texto)

        # Busca por código e texto
        if self.question_map['by_code']:
            info = self.question_map['by_code'].get((cod_norm, texto_norm))
            if info:
                return info

        # Fallback: busca apenas por texto
        if texto_norm in self.question_map['by_text']:
            candidatos = self.question_map['by_text'][texto_norm]
            if candidatos:
                if len(candidatos) > 1:
                    print(f"[WARN] Múltiplas questões para texto '{texto}'")
                return candidatos[0]

        return None

    def _marcar_resposta(self, row, resposta: str) -> bool:
        """Marca resposta em uma linha específica do Questionário PT."""
        resposta_original = str(resposta).strip()
        resposta_norm = normalizar_string(resposta_original)

        # Mapeia respostas possíveis para consistência
        if resposta_norm in ["SIM", "S", "YES", "Y"]:
            alvo = "Sim"
        elif resposta_norm in ["NAO", "NÃO", "N", "NO"]:
            alvo = "Não"
        elif resposta_norm in ["NA", "N/A", "NÃO APLICÁVEL", "NÃO SE APLICA"]:
            alvo = "NA"
        else:
            alvo = resposta_original  # Fallback

        print(f"[DEBUG] Marcando resposta: '{resposta_original}' -> normalizada: '{resposta_norm}' -> alvo: '{alvo}'")

        try:
            container = row.find_element(By.CSS_SELECTOR, ".resposta")
        except NoSuchElementException:
            print("[WARN] Container de resposta (.resposta) não encontrado")
            return False

        # Procura todos os spans de opção de resposta
        spans_opcoes = container.find_elements(By.XPATH, ".//span[.//input[@type='radio']]")
        print(f"[DEBUG] Encontrados {len(spans_opcoes)} spans de opções")

        # Tenta encontrar e marcar a opção correta
        for span in spans_opcoes:
            try:
                # Encontra o label dentro do span
                label = span.find_element(By.TAG_NAME, "label")
                texto_label = label.text.strip() if label.text else ""

                print(f"[DEBUG] Opção encontrada: '{texto_label}'")

                # Verifica se este é o label que queremos (comparação flexível)
                if self._texto_label_corresponde(texto_label, alvo):
                    try:
                        # Tenta clicar no input primeiro
                        input_radio = span.find_element(By.XPATH, ".//input[@type='radio']")
                        print(
                            f"[DEBUG] Clicando no input para: '{texto_label}' (ID: {input_radio.get_attribute('id')})")

                        # Scroll para visibilidade
                        self.driver.execute_script(
                            "arguments[0].scrollIntoView({block:'center', behavior:'smooth'});",
                            input_radio
                        )
                        time.sleep(0.1)

                        # Tenta múltiplas estratégias de clique
                        if self._clicar_radio_com_estrategias(input_radio, label):
                            # Verifica se foi marcado corretamente
                            time.sleep(0.1)
                            if input_radio.is_selected():
                                print(f"[OK] Resposta '{texto_label}' marcada com sucesso")
                                return True
                            else:
                                print(f"[WARN] Input não foi selecionado após clique")
                        else:
                            print(f"[WARN] Falha nas estratégias de clique para '{texto_label}'")

                    except Exception as e:
                        print(f"[ERROR] Erro ao marcar opção '{texto_label}': {e}")

            except Exception as e:
                print(f"[DEBUG] Erro ao processar span: {e}")
                continue

        print(f"[ERROR] Não foi possível encontrar/marcar a opção '{alvo}'")
        return False

    def _texto_label_corresponde(self, texto_label: str, alvo: str) -> bool:
        """Verifica se o texto do label corresponde ao alvo desejado."""
        texto_label_norm = normalizar_string(texto_label)
        alvo_norm = normalizar_string(alvo)

        # Para "NA", aceita apenas variações de "não se aplica", sem confundir com "NÃO"
        if alvo_norm in ("NA", "N/A"):
            # Normalizações possíveis para rótulos de NA
            possiveis_na = (
                "NA",
                "N/A",
                "NAO APLICAVEL",
                "NAO SE APLICA",
                "NAO SE APLICAR",
                "NAO APLICAVEL AO TRABALHO",
                "NAO SE APLICA AO TRABALHO",
            )
            if texto_label_norm in possiveis_na:
                return True

            # Aceita textos maiores contendo claramente "NAO SE APLICA" ou "NAO APLICAVEL"
            if "NAO SE APLICA" in texto_label_norm or "NAO APLICAVEL" in texto_label_norm:
                return True

            # Importante: NÃO considerar "NAO" ou "NAO." isolado como NA
            return False

        # Para "Sim" e "Não", comparações diretas
        elif alvo_norm == "SIM":
            return texto_label_norm == "SIM"
        elif alvo_norm in ["NAO", "NÃO"]:
            return texto_label_norm in ["NAO", "NÃO"]

        # Fallback: comparação exata normalizada
        return texto_label_norm == alvo_norm

    def _clicar_radio_com_estrategias(self, input_radio, label) -> bool:
        """Tenta múltiplas estratégias para clicar em um radio button."""
        estrategias = [
            # Estratégia 1: JavaScript no input
            lambda: self.driver.execute_script("arguments[0].click();", input_radio),

            # Estratégia 2: JavaScript no label
            lambda: self.driver.execute_script("arguments[0].click();", label),

            # Estratégia 3: Clique direto no input
            lambda: input_radio.click(),

            # Estratégia 4: Clique direto no label
            lambda: label.click(),

            # Estratégia 5: Actions API (simulada via JS)
            lambda: self.driver.execute_script("""
                var evt = new MouseEvent('click', {
                    bubbles: true,
                    cancelable: true,
                    view: window
                });
                arguments[0].dispatchEvent(evt);
            """, input_radio),
        ]

        for idx, estrategia in enumerate(estrategias, 1):
            try:
                estrategia()
                time.sleep(0.05)

                # Verifica se funcionou
                if input_radio.is_selected():
                    print(f"[DEBUG] Estratégia {idx} funcionou")
                    return True

            except Exception as e:
                print(f"[DEBUG] Estratégia {idx} falhou: {e}")
                continue

        return False

    def _mapear_opcoes_resposta(self, container) -> Dict[str, Tuple[Any, Any]]:
        """Mapeia opções de resposta disponíveis."""
        opcoes = {}
        spans = container.find_elements(By.XPATH, ".//span[.//input[@type='radio']]")

        for span in spans:
            try:
                input_el = span.find_element(By.XPATH, ".//input[@type='radio']")
                label_el = span.find_element(By.TAG_NAME, "label")
                texto_label = label_el.text or ""
                texto_norm = normalizar_string(texto_label)

                # Simplifica para categorias principais
                if "SIM" in texto_norm:
                    chave = "SIM"
                elif "NAO" in texto_norm or "NÃO" in texto_norm:
                    chave = "NAO"
                elif texto_norm in ("NA", "N/A"):
                    chave = "NA"
                else:
                    chave = texto_norm

                opcoes[chave] = (input_el, label_el)
            except NoSuchElementException:
                continue

        return opcoes

    def _determinar_alvo_resposta(self, resposta_norm: str, opcoes: Dict[str, Tuple]) -> Optional[Tuple]:
        """Determina qual opção selecionar baseado na resposta normalizada."""
        if resposta_norm in ("SIM", "NAO", "NA"):
            return opcoes.get(resposta_norm)

        # Fallback: busca direta
        return opcoes.get(resposta_norm)

    def _clicar_radio_com_retry(self, input_el, label_el, max_tentativas: int = 3) -> bool:
        """Clica em rádio com múltiplas tentativas e validação."""
        radio_id = input_el.get_attribute("id")

        for tentativa in range(max_tentativas):
            try:
                # Scroll e clique
                self.driver.execute_script(
                    "arguments[0].scrollIntoView({block:'center', inline:'nearest'});",
                    label_el or input_el
                )

                # Tenta múltiplas estratégias
                if not self._tentar_cliques_radio(input_el, label_el):
                    continue

                # Valida seleção
                if self._validar_selecao_radio(input_el, radio_id):
                    return True

            except StaleElementReferenceException:
                if tentativa == max_tentativas - 1:
                    break
                time.sleep(0.1 * (tentativa + 1))

        print(f"[WARN] Falha ao marcar rádio id={radio_id}")
        return False

    def _tentar_cliques_radio(self, input_el, label_el) -> bool:
        """Tenta múltiplas estratégias de clique no rádio."""
        estrategias = [
            lambda: label_el.click() if label_el else False,
            lambda: self.driver.execute_script("arguments[0].click();", label_el) if label_el else False,
            lambda: input_el.click(),
            lambda: self.driver.execute_script("arguments[0].click();", input_el),
        ]

        for estrategia in estrategias:
            try:
                estrategia()
                time.sleep(0.05)
                if input_el.is_selected():
                    return True
            except Exception:
                continue

        return False

    def _validar_selecao_radio(self, input_el, radio_id: str) -> bool:
        """Valida se o rádio está realmente selecionado."""
        try:
            if radio_id:
                # Re-localiza por ID para garantir
                elemento = self.driver.find_element(By.ID, radio_id)
                return elemento.is_selected()
            return input_el.is_selected()
        except Exception:
            return False

    def _log_resultado(self, total: int, sucessos: int):
        """Log do resultado do processamento."""
        falhas = total - sucessos
        print(f"\n[RESUMO] Questionário PT:")
        print(f"  • Total de questões: {total}")
        print(f"  • Marcadas com sucesso: {sucessos}")
        print(f"  • Falhas: {falhas}")
        print(f"  • Taxa de sucesso: {(sucessos / total * 100):.1f}%" if total > 0 else "0%")


# -------------------------------------------------------------------
# EPI adicional - Módulo otimizado
# -------------------------------------------------------------------
class EPIAdicionalProcessor:
    """Processador otimizado para EPI adicional."""

    def __init__(self, driver, timeout: float):
        self.driver = driver
        self.timeout = timeout
        self.debug = False

    @timeit_decorator()
    def preencher(self, epi_radios_plano, debug: bool = False):
        """Preenche bloco 'EPI adicional necessário e proteções'."""
        self.debug = debug

        print("[STEP] Preenchendo EPI adicional...")
        goto_tab(self.driver, "EPI", self.timeout)

        # LOG de quantos containers existem p/ esse XPATH
        containers = self.driver.find_elements(By.XPATH, XPATH_CONTAINER_EPI)
        print(f"[DEBUG][EPI] Containers EPI encontrados (raw XPATH): {len(containers)}")

        container = self._obter_container_epi()
        if not container:
            print("[DEBUG][EPI] Container EPI não encontrado – abortando EPI adicional.")
            return

        # Mostra um pedaço do HTML do container para garantir que é o lugar certo
        try:
            html_preview = container.get_attribute("outerHTML")[:500]
            html_preview = html_preview.replace("\n", " ").replace("\r", " ")
            print(f"[DEBUG][EPI] Container EPI (preview HTML): {html_preview}")
        except Exception:
            pass

        mapa_respostas = self._extrair_mapa_respostas(epi_radios_plano)
        print(f"[DEBUG][EPI] mapa_respostas extraído: {mapa_respostas}")

        self._processar_questoes_epi(container, mapa_respostas)

    def _obter_container_epi(self):
        """Obtém container do EPI adicional."""
        try:
            return WebDriverWait(self.driver, self.timeout).until(
                EC.presence_of_element_located((By.XPATH, XPATH_CONTAINER_EPI))
            )
        except TimeoutException:
            print("[ERROR] Container EPI adicional não encontrado")
            return None

    def _extrair_mapa_respostas(self, epi_radios_plano) -> Dict[str, str]:
        """Extrai mapa de códigos para respostas."""
        mapa = {}

        def processar_item(chave, valor):
            if isinstance(chave, str) and chave.upper().startswith("Q"):
                resposta = self._extrair_resposta_valor(valor)
                if resposta:
                    mapa[chave.upper()] = resposta

        if isinstance(epi_radios_plano, dict):
            for chave, valor in epi_radios_plano.items():
                if isinstance(chave, (tuple, list)) and len(chave) > 0:
                    processar_item(chave[0], valor)
                else:
                    processar_item(chave, valor)

        return mapa

    def _extrair_resposta_valor(self, valor) -> Optional[str]:
        """Extrai resposta de um valor complexo."""
        if isinstance(valor, (str, int, float)):
            resposta = str(valor).strip().upper()
            return resposta if resposta in ("SIM", "NÃO", "NAO") else None

        if isinstance(valor, dict):
            for campo in ("resp", "resposta", "valor", "value"):
                if campo in valor and valor[campo]:
                    resposta = str(valor[campo]).strip().upper()
                    if resposta in ("SIM", "NÃO", "NAO"):
                        return resposta

        if isinstance(valor, (list, tuple)) and valor:
            return self._extrair_resposta_valor(valor[0])

        return None

    def _processar_questoes_epi(self, container, mapa_respostas: Dict[str, str]):
        """Processa todas as questões de EPI adicional."""
        rows = container.find_elements(By.XPATH, ".//div[starts-with(@id,'questao_')]")
        print(f"[INFO][EPI] EPI adicional: {len(rows)} questões encontradas dentro do container EPI")

        for row in rows:
            self._processar_questao_epi(row, mapa_respostas)

        print("[INFO][EPI] EPI adicional concluído")

    def _processar_questao_epi(self, row, mapa_respostas: Dict[str, str]):
        """Processa uma questão individual de EPI."""
        info = self._extrair_info_questao(row)
        if not info:
            print("[DEBUG][EPI] Questão sem info – ignorando.")
            return

        resposta = self._obter_resposta_esperada(info, mapa_respostas)
        print(f"[DEBUG][EPI] Questão {info['codigo']}: '{info['pergunta'][:60]}...' "
              f"→ resposta esperada: {resposta}")

        if not resposta:
            return

        self._marcar_resposta_epi(row, info['codigo'], info['pergunta'], resposta)

    def _extrair_info_questao(self, row) -> Optional[Dict]:
        """Extrai informações da questão."""
        try:
            # Ordem
            ordem_elem = row.find_element(By.CSS_SELECTOR, ".ordem")
            ordem_raw = ordem_elem.text.strip() if ordem_elem.text else ""
            ordem = ordem_raw.lstrip("0") or ordem_raw

            # Pergunta
            pergunta_elem = row.find_element(By.XPATH, ".//div[contains(@class,'pergunta')]")
            pergunta = pergunta_elem.text.strip() if pergunta_elem.text else ""

            return {
                'codigo': f"Q{ordem.zfill(3)}" if ordem else None,
                'pergunta': pergunta,
            }
        except NoSuchElementException:
            return None

    def _obter_resposta_esperada(self, info: Dict, mapa_respostas: Dict[str, str]) -> Optional[str]:
        """Obtém resposta esperada para a questão."""
        # Tenta por código
        if info['codigo'] and info['codigo'] in mapa_respostas:
            return mapa_respostas[info['codigo']]

        # Tenta por texto da pergunta
        if info['pergunta']:
            pergunta_norm = normalizar_string(info['pergunta'])
            for chave, valor in mapa_respostas.items():
                if isinstance(chave, str) and normalizar_string(chave) == pergunta_norm:
                    return valor

        return None

    def _marcar_resposta_epi(self, row, codigo: str, pergunta: str, resposta: str):
        """Marca resposta na questão de EPI."""
        alvo_label = "Sim" if normalizar_string(resposta) == "SIM" else "Não"

        print(f"[DEBUG][EPI] MARCAR {codigo or '?'} → '{alvo_label}' | {pergunta[:80]}...")

        # Se estiver em modo dry-run, NÃO clicar, apenas logar
        if self.debug:
            print("[DEBUG][EPI] DRY-RUN ATIVO – nenhum clique será efetuado.")
            return

        try:
            resposta_div = row.find_element(By.CSS_SELECTOR, ".resposta.simnao")
            spans = resposta_div.find_elements(By.TAG_NAME, "span")

            for span in spans:
                try:
                    label = span.find_element(By.TAG_NAME, "label")
                    if normalizar_string(label.text) == normalizar_string(alvo_label):
                        self.driver.execute_script(
                            "arguments[0].scrollIntoView({block:'center'});", label
                        )
                        label.click()
                        print(f"[INFO][EPI] EPI adicional {codigo or '?'}: '{alvo_label}' | {pergunta[:50]}...")
                        return
                except NoSuchElementException:
                    continue
        except NoSuchElementException:
            print(f"[WARN][EPI] Container de resposta não encontrado para {codigo or '?'}")


# -------------------------------------------------------------------
# Análise Ambiental - Módulo otimizado
# -------------------------------------------------------------------
# -------------------------------------------------------------------
# Análise Ambiental - Módulo otimizado (somente 5 perguntas AMB)
# -------------------------------------------------------------------
class AnaliseAmbientalProcessor:
    """Processador otimizado da Análise Ambiental."""

    def __init__(self, driver, timeout: float):
        self.driver = driver
        self.timeout = timeout

    @timeit_decorator()
    def preencher(self):
        """Preenche todas as questões da Análise Ambiental como 'Não'."""
        print("[STEP] Preenchendo Análise Ambiental...")
        goto_tab(self.driver, "Análise Ambiental", self.timeout)
        time.sleep(0.3)

        # Localizar o container principal
        container = self._localizar_container_amb()
        if not container:
            print("[WARN] Container AMB não encontrado")
            return

        # Processar questões
        total, sucessos = self._processar_questoes_amb(container)
        print(f"[INFO] Análise Ambiental: {sucessos}/{total} questões marcadas como 'Não'")

    def _localizar_container_amb(self):
        """Localiza o container principal da Análise Ambiental."""
        try:
            # Tentar diferentes localizadores
            localizadores = [
                "//div[@id='AMB']",
                "//div[contains(@class,'ambiental')]",
                "//div[h4[contains(.,'O local de trabalho tem:')]]",
                "//div[h4[contains(.,'Análise Ambiental')]]",
            ]

            for loc in localizadores:
                try:
                    container = WebDriverWait(self.driver, 2).until(
                        EC.presence_of_element_located((By.XPATH, loc))
                    )
                    print(f"[DEBUG][AMB] Container encontrado com: {loc}")
                    return container
                except TimeoutException:
                    continue

        except Exception as e:
            print(f"[ERROR][AMB] Falha ao localizar container: {e}")

        return None

    def _processar_questoes_amb(self, container):
        """Processa todas as questões dentro do container."""
        # Encontrar linhas de questões
        rows = container.find_elements(
            By.XPATH, ".//div[starts-with(@id,'questao_') or contains(@class,'row question-row')]"
        )

        if not rows:
            # Tentar método alternativo
            rows = container.find_elements(
                By.XPATH, ".//div[contains(@class,'row') and .//div[contains(@class,'pergunta')]]"
            )

        print(f"[DEBUG][AMB] Encontradas {len(rows)} linhas de questões")

        total = len(rows)
        sucessos = 0

        for idx, row in enumerate(rows, 1):
            try:
                if self._marcar_nao_questao(row, idx):
                    sucessos += 1
            except Exception as e:
                print(f"[WARN][AMB] Erro na questão {idx}: {e}")

        return total, sucessos

    def _marcar_nao_questao(self, row, idx: int) -> bool:
        """Marca uma questão específica como 'Não'."""
        try:
            # Obter texto da pergunta para logging
            pergunta = "?"
            try:
                pergunta_elem = row.find_element(By.XPATH, ".//div[contains(@class,'pergunta')]")
                pergunta = pergunta_elem.text[:50] + "..." if len(pergunta_elem.text) > 50 else pergunta_elem.text
            except:
                pass

            # Encontrar container de resposta
            resposta_container = row.find_element(
                By.XPATH, ".//div[contains(@class,'resposta')]"
            )

            # Encontrar opção "Não"
            # Método 1: Procurar por label
            labels = resposta_container.find_elements(By.TAG_NAME, "label")
            label_nao = None

            for label in labels:
                texto = normalizar_string(label.text or "")
                if texto in ["NAO", "NÃO", "N"]:
                    label_nao = label
                    break

            if label_nao:
                # Clique no label
                self.driver.execute_script("arguments[0].scrollIntoView(true);", label_nao)
                time.sleep(0.05)

                # Tenta múltiplas estratégias de clique
                estrategias = [
                    lambda: self.driver.execute_script("arguments[0].click();", label_nao),
                    lambda: label_nao.click(),
                ]

                for estrategia in estrategias:
                    try:
                        estrategia()
                        time.sleep(0.1)

                        # Verificar se foi marcado
                        # Encontrar input associado
                        input_id = label_nao.get_attribute("for")
                        if input_id:
                            input_elem = row.find_element(By.ID, input_id)
                            if input_elem.is_selected():
                                print(f"[INFO][AMB] Questão {idx}: '{pergunta}' → Não [OK]")
                                return True
                    except:
                        continue

            # Método 2: Procurar input diretamente pelo value
            inputs = resposta_container.find_elements(By.TAG_NAME, "input")
            for input_elem in inputs:
                input_type = input_elem.get_attribute("type")
                if input_type == "radio":
                    value = input_elem.get_attribute("value") or ""
                    # Normalmente 1=Não, 0=Sim
                    if value == "1":
                        self.driver.execute_script("arguments[0].scrollIntoView(true);", input_elem)
                        self.driver.execute_script("arguments[0].click();", input_elem)
                        time.sleep(0.1)

                        if input_elem.is_selected():
                            print(f"[INFO][AMB] Questão {idx}: '{pergunta}' → Não [OK]")
                            return True

            print(f"[WARN][AMB] Questão {idx}: Não conseguiu marcar 'Não'")
            return False

        except Exception as e:
            print(f"[ERROR][AMB] Falha na questão {idx}: {e}")
            return False



# -------------------------------------------------------------------
# APN-1 - Módulo otimizado
# -------------------------------------------------------------------
class APN1Processor:
    """Processador otimizado para APN-1."""

    def __init__(self, driver, timeout: float):
        self.driver = driver
        self.timeout = timeout

    @timeit_decorator()
    def preencher(self, descricao: str, caracteristicas: str):
        """Preenche APN-1 baseado no contexto da etapa."""
        print("[STEP] Preenchendo APN-1 (análise dinâmica por texto)...")
        goto_tab(self.driver, "APN-1", self.timeout)
        time.sleep(0.5)

        # Normalizar contexto
        contexto = normalizar_string(f"{descricao} {caracteristicas}")
        print(f"[DEBUG][APN1] Contexto normalizado: {contexto[:200]}...")

        # Coletar perguntas
        perguntas = self._coletar_perguntas()

        if not perguntas:
            print("[WARN] Nenhuma pergunta APN-1 encontrada")
            return

        # Processar cada pergunta
        self._processar_perguntas(perguntas, contexto)

    def _coletar_perguntas(self) -> List[Dict]:
        """Coleta todas as perguntas APN-1 da tela de forma otimizada."""
        rows = []

        # Tentar diferentes XPaths
        xpaths_tentativas = [
            "//div[starts-with(@id,'questao_')]",
            "//div[contains(@class,'row') and starts-with(@id,'questao_')]",
            "//div[@id='APN1']//div[starts-with(@id,'questao_')]",
        ]

        for xpath in xpaths_tentativas:
            try:
                rows = self.driver.find_elements(By.XPATH, xpath)
                if rows:
                    print(f"[DEBUG][APN1] Encontradas {len(rows)} perguntas com XPath: {xpath}")
                    break
            except Exception:
                continue

        if not rows:
            print("[DEBUG][APN1] Nenhuma pergunta APN-1 encontrada")
            return []

        perguntas = []
        for idx, row in enumerate(rows, 1):
            pergunta_info = self._extrair_info_pergunta(row, idx)
            if pergunta_info:
                perguntas.append(pergunta_info)

        print(f"[INFO] APN-1: {len(perguntas)} perguntas coletadas")
        return perguntas

    def _extrair_info_pergunta(self, row, indice: int) -> Optional[Dict]:
        """Extrai informações de uma pergunta individual."""
        try:
            # Texto da pergunta
            pergunta_elem = row.find_element(By.XPATH, ".//div[contains(@class,'pergunta')]")
            texto = pergunta_elem.text.strip() if pergunta_elem.text else ""

            if not texto:
                return None

            texto_norm = normalizar_string(texto)

            # IDs dos radio buttons (SIM/NÃO)
            id_sim, id_nao = self._extrair_ids_radios(row)

            # Ordem/número da questão
            ordem_elem = row.find_element(By.XPATH, ".//div[contains(@class,'ordem')]")
            ordem = ordem_elem.text.strip() if ordem_elem.text else str(indice)

            return {
                'indice': indice,
                'ordem': ordem,
                'texto': texto,
                'texto_norm': texto_norm,
                'id_sim': id_sim,
                'id_nao': id_nao,
                'row': row,
            }
        except Exception as e:
            print(f"[DEBUG][APN1] Erro ao extrair pergunta {indice}: {e}")
            return None

    def _extrair_ids_radios(self, row) -> Tuple[Optional[str], Optional[str]]:
        """Extrai IDs dos radio buttons SIM/NÃO."""
        id_sim, id_nao = None, None

        try:
            # Procura por inputs radio
            radios = row.find_elements(By.XPATH, ".//input[@type='radio']")

            for radio in radios:
                radio_id = radio.get_attribute("id") or ""
                value = radio.get_attribute("value") or ""

                # Verifica pelo value (0=Sim, 1=Não)
                if value == "0" or "sim" in radio_id.lower():
                    id_sim = radio_id
                elif value == "1" or "nao" in radio_id.lower() or "não" in radio_id.lower():
                    id_nao = radio_id

            # Fallback: procura por labels
            if not id_sim or not id_nao:
                labels = row.find_elements(By.XPATH, ".//label")
                for label in labels:
                    texto = normalizar_string(label.text or "")
                    if texto in ["SIM", "S"]:
                        id_sim = label.get_attribute("for")
                    elif texto in ["NAO", "NÃO", "N"]:
                        id_nao = label.get_attribute("for")

        except Exception as e:
            print(f"[DEBUG][APN1] Erro ao extrair IDs de rádio: {e}")

        return id_sim, id_nao

    def _processar_perguntas(self, perguntas: List[Dict], contexto: str):
        """Processa todas as perguntas coletadas."""
        sucessos = 0
        falhas = 0

        for pergunta in perguntas:
            if self._processar_pergunta_individual(pergunta, contexto):
                sucessos += 1
            else:
                falhas += 1

        print(f"[DONE] APN-1 finalizado: {sucessos} sucessos, {falhas} falhas")

    def _processar_pergunta_individual(self, pergunta: Dict, contexto: str) -> bool:
        """Processa uma pergunta individual."""
        # Determinar resposta baseada no contexto
        resposta = self._determinar_resposta(pergunta['texto_norm'], contexto)

        # Selecionar ID correto
        id_alvo = None
        if resposta == "Sim" and pergunta['id_sim']:
            id_alvo = pergunta['id_sim']
        elif resposta == "Não" and pergunta['id_nao']:
            id_alvo = pergunta['id_nao']

        if not id_alvo:
            print(f"[WARN] P{pergunta['ordem']}: ID não encontrado para '{resposta}'")
            return False

        print(f"[INFO] P{pergunta['ordem']} → {resposta} | '{pergunta['texto'][:50]}...'")

        return self._marcar_resposta(pergunta['row'], id_alvo, resposta)

    def _determinar_resposta(self, texto_pergunta: str, contexto: str) -> str:
        """Determina resposta baseada no texto da pergunta e contexto."""
        # Por padrão, todas são "Não"
        resposta = "Não"

        # Mapeamento de padrões de pergunta para palavras-chave no contexto
        mapeamento = [
            # Espaço confinado
            (["espaco confinado", "interior de espaco"], ["ESPACO CONFINADO"]),

            # Altura
            (["altura acima de 2m", "trabalho em altura", "acesso por cordas"],
             ["ALTURA", "ACESSO POR CORDAS"]),

            # Sobre o mar
            (["sobre o mar"], ["SOBRE O MAR"]),

            # Chama aberta
            (["chama aberta", "solda", "oxicorte", "esmerilhadeira"],
             ["CHAMA ABERTA", "SOLDA", "OXICORTE", "ESMERILHADEIRA"]),

            # CO2
            (["protegido por co2", "ambientes protegidos por co2", "sistema de co2"],
             ["PROTEGIDO POR CO2", "AMBIENTES PROTEGIDOS POR CO2"]),

            # Pressurizado
            (["pressurizado", "sistema pressurizado"], ["PRESSURIZADO"]),

            # Hidrojato
            (["hidrojateamento", "hidrojato"], ["HIDROJATO", "HIDROJATEAMENTO"]),

            # Partes móveis
            (["partes moveis", "partes moveis expostas"], ["PARTES MOVEIS"]),
        ]

        # Verificar cada padrão
        for padroes_pergunta, palavras_chave in mapeamento:
            for padrao in padroes_pergunta:
                if padrao in texto_pergunta:
                    # Verificar se alguma palavra-chave está no contexto
                    for palavra in palavras_chave:
                        if palavra in contexto:
                            return "Sim"

        return resposta

    def _marcar_resposta(self, row, element_id: str, resposta: str) -> bool:
        """Marca resposta via JavaScript ou clique direto."""
        try:
            # Primeiro tentar via JavaScript (mais robusto)
            script = f"""
            var element = document.getElementById("{element_id}");
            if (!element) return false;

            // Scroll para visibilidade
            element.scrollIntoView({{block: 'center', behavior: 'smooth'}});

            // Marcar elemento
            element.checked = true;

            // Disparar eventos para Angular
            element.dispatchEvent(new Event('change', {{bubbles: true}}));
            element.dispatchEvent(new Event('input', {{bubbles: true}}));

            return element.checked === true;
            """

            resultado = self.driver.execute_script(script)

            if resultado:
                print(f"[DEBUG][APN1] Resposta '{resposta}' marcada via JavaScript")
                return True

            # Fallback: clique direto
            time.sleep(0.1)
            element = row.find_element(By.ID, element_id)
            element.click()

            # Verificar se foi marcado
            time.sleep(0.1)
            if element.is_selected():
                print(f"[DEBUG][APN1] Resposta '{resposta}' marcada via clique")
                return True

        except Exception as e:
            print(f"[DEBUG][APN1] Erro ao marcar resposta: {e}")

            # Último recurso: clique via ActionChains
            try:
                from selenium.webdriver.common.action_chains import ActionChains
                element = row.find_element(By.ID, element_id)
                ActionChains(self.driver).move_to_element(element).click().perform()
                time.sleep(0.1)
                return element.is_selected()
            except Exception as e2:
                print(f"[ERROR][APN1] Falha completa ao marcar resposta: {e2}")

        return False


# -------------------------------------------------------------------
# Funções de interface pública (mantidas para compatibilidade)
# -------------------------------------------------------------------
@timeit_decorator()
def preencher_questionario_pt(driver, timeout: float, qpt_plano: Dict[Tuple[str, str], str]):
    """Interface pública para preenchimento do Questionário PT."""
    processor = QuestionarioPTProcessor(driver, timeout)
    resultado = processor.preencher(qpt_plano)

    # Apenas confirmação normal, sem fluxo adicional
    print("[INFO] Questionário PT concluído")
    return resultado


@timeit_decorator()
def preencher_epi_adicional(driver, timeout: float, epi_radios_plano):
    """Interface pública para preenchimento de EPI adicional."""
    print("\n[DEBUG][EPI] ===== INÍCIO preencher_epi_adicional =====")

    # **ADICIONAR: Fechar qualquer modal aberto antes de navegar**
    from quent1_infra import ensure_no_messagebox, click_messagebox_ok
    ensure_no_messagebox(driver, timeout)

    print(f"[DEBUG][EPI] epi_radios_plano (raw): {repr(epi_radios_plano)}")

    processor = EPIAdicionalProcessor(driver, timeout)
    processor.preencher(epi_radios_plano, debug=DEBUG_EPI_DRY_RUN)

    print("[DEBUG][EPI] ===== FIM preencher_epi_adicional =====\n")


@timeit_decorator()
def preencher_analise_ambiental(driver, timeout: float):
    """Interface pública para preenchimento da Análise Ambiental."""
    processor = AnaliseAmbientalProcessor(driver, timeout)
    processor.preencher()




@timeit_decorator()
def preencher_apn1(driver, timeout: float, descricao: str, caracteristicas: str):
    """Interface pública para preenchimento do APN-1."""
    processor = APN1Processor(driver, timeout)
    processor.preencher(descricao, caracteristicas)

