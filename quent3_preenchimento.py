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

from quent1_infra import goto_tab, safe_find_element
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

    texto = unicodedata.normalize("NFD", texto)
    texto = ''.join(c for c in texto if unicodedata.category(c) != 'Mn')
    texto = texto.upper()
    texto = re.sub(r'\s+', ' ', texto).strip()

    return texto


def extrair_digitos_codigo(codigo: str) -> str:
    """Extrai apenas dígitos de um código e padroniza como '001', '002', etc."""
    if not codigo:
        return ""

    digitos = ''.join(c for c in str(codigo) if c.isdigit())
    return digitos.zfill(3) if digitos else ""


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
        time.sleep(0.5)

        self._construir_mapa_perguntas()
        return self._processar_questoes(qpt_plano)

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
        return self._marcar_resposta(info['row'], resposta)

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

        # Para "NA", aceita várias formas
        if alvo_norm in ["NA", "N/A"]:
            return any(termo in texto_label_norm for termo in ["NA", "N/A", "NÃO APLICÁVEL", "NÃO SE APLICA"])

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

            # Estratégia 5: Actions API
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

    @timeit_decorator()
    def preencher(self, epi_radios_plano):
        """Preenche bloco 'EPI adicional necessário e proteções'."""
        print("[STEP] Preenchendo EPI adicional...")
        goto_tab(self.driver, "EPI", self.timeout)

        container = self._obter_container_epi()
        if not container:
            return

        mapa_respostas = self._extrair_mapa_respostas(epi_radios_plano)
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
        print(f"[INFO] EPI adicional: {len(rows)} questões encontradas")

        for row in rows:
            self._processar_questao_epi(row, mapa_respostas)

        print("[INFO] EPI adicional concluído")

    def _processar_questao_epi(self, row, mapa_respostas: Dict[str, str]):
        """Processa uma questão individual de EPI."""
        info = self._extrair_info_questao(row)
        if not info:
            return

        resposta = self._obter_resposta_esperada(info, mapa_respostas)
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

        try:
            resposta_div = row.find_element(By.CSS_SELECTOR, ".resposta.simnao")
            spans = resposta_div.find_elements(By.TAG_NAME, "span")

            for span in spans:
                try:
                    label = span.find_element(By.TAG_NAME, "label")
                    if normalizar_string(label.text) == alvo_label:
                        self.driver.execute_script(
                            "arguments[0].scrollIntoView({block:'center'});", label
                        )
                        label.click()
                        print(f"[INFO] EPI adicional {codigo or '?'}: '{alvo_label}' | {pergunta[:50]}...")
                        return
                except NoSuchElementException:
                    continue
        except NoSuchElementException:
            print(f"[WARN] Container de resposta não encontrado para {codigo or '?'}")


# -------------------------------------------------------------------
# Análise Ambiental - Módulo otimizado
# -------------------------------------------------------------------
class AnaliseAmbientalProcessor:
    """Processador otimizado para Análise Ambiental."""

    def __init__(self, driver, timeout: float):
        self.driver = driver
        self.timeout = timeout

    @timeit_decorator()
    def preencher(self):
        """Preenche todas as questões da Análise Ambiental como 'Não'."""
        print("[STEP] Preenchendo Análise Ambiental...")
        goto_tab(self.driver, "Análise Ambiental", self.timeout)

        # Tenta método JavaScript primeiro
        if self._preencher_via_javascript():
            return

        # Fallback: método tradicional
        self._preencher_via_tradicional()

    def _preencher_via_javascript(self) -> bool:
        """Método rápido via JavaScript."""
        try:
            script = """
            var count = 0;
            var labels = document.querySelectorAll(
                '#AMB label, [id*="AMB"] label, div[id*="questao_"] label'
            );

            labels.forEach(function(label) {
                if (label.textContent.trim().toUpperCase() === 'NÃO' || 
                    label.textContent.trim().toUpperCase() === 'NAO') {
                    var input = label.previousElementSibling;
                    if (input && input.type === 'radio' && !input.checked) {
                        input.click();
                        count++;
                    }
                }
            });
            return count;
            """

            count = self.driver.execute_script(script)
            print(f"[INFO] Análise Ambiental: {count} questões marcadas via JavaScript")
            return True
        except Exception as e:
            print(f"[WARN] JavaScript falhou: {e}")
            return False

    def _preencher_via_tradicional(self):
        """Método tradicional via Selenium."""
        container = safe_find_element(self.driver, XPATH_ANALISE_AMBIENTAL, self.timeout)
        if not container:
            return

        rows = container.find_elements(
            By.XPATH,
            ".//div[contains(@class,'row') and .//div[contains(@class,'ordem') "
            "and string-length(normalize-space(text()))>0]]"
        )

        for row in rows:
            try:
                nao_label = row.find_element(
                    By.XPATH, ".//label[contains(translate(text(), 'ÁÀÂÃÉÊÍÓÔÕÚÇ', 'AAAAEEIOOOUC'), 'NAO') "
                              "or contains(translate(text(), 'ÁÀÂÃÉÊÍÓÔÕÚÇ', 'AAAAEEIOOOUC'), 'NÃO')]"
                )
                self.driver.execute_script("arguments[0].click();", nao_label)
            except Exception:
                continue

        print("[INFO] Análise Ambiental concluída via método tradicional")


# -------------------------------------------------------------------
# APN-1 - Módulo otimizado
# -------------------------------------------------------------------
class APN1Processor:
    """Processador otimizado para APN-1."""

    def __init__(self, driver, timeout: float):
        self.driver = driver
        self.timeout = timeout
        self.padroes_perguntas = self._inicializar_padroes()

    def _inicializar_padroes(self) -> Dict[str, List[Set[str]]]:
        """Inicializa padrões de perguntas APN-1."""
        return {
            'altura': (PADROES_ALTURA, {"ALTURA", "ACESSO POR CORDAS", "SOBRE O MAR"}),
            'sobre_mar': ({"SOBRE O MAR", "MARÍTIMO"}, {"SOBRE O MAR"}),
            'chama': (PADROES_CHAMA, {"CHAMA ABERTA", "SOLDA", "OXICORTE", "ESMERILHADEIRA"}),
            'co2': ({"CO2", "GÁS CARBÔNICO"}, PADROES_CO2),
            'espaco_confinado': ({"ESPAÇO CONFINADO", "CONFINADO"}, {"ESPAÇO CONFINADO"}),
            'pressurizado': (PADROES_PRESSURIZADO, {"PRESSURIZADO"}),
            'partes_moveis': ({"PARTES MOVEIS", "PARTES MÓVEIS"}, {"PARTES MOVEIS"}),
            'hidrojato': (PADROES_HIDROJATO, {"HIDROJATO", "HIDROJATEAMENTO"}),
        }

    @timeit_decorator()
    def preencher(self, descricao: str, caracteristicas: str):
        """Preenche APN-1 baseado no contexto da etapa."""
        print("[STEP] Preenchendo APN-1 (análise dinâmica por texto)...")
        goto_tab(self.driver, "APN-1", self.timeout)
        time.sleep(0.5)

        contexto = normalizar_string(f"{descricao} {caracteristicas}")
        perguntas = self._coletar_perguntas()

        if not perguntas:
            print("[WARN] Nenhuma pergunta APN-1 encontrada")
            return

        self._processar_perguntas(perguntas, contexto)

    def _coletar_perguntas(self) -> List[Dict]:
        """Coleta todas as perguntas APN-1 da tela."""
        rows = self._encontrar_rows_apn1()
        if not rows:
            return []

        perguntas = []
        for idx, row in enumerate(rows, 1):
            pergunta = self._extrair_pergunta(row, idx)
            if pergunta:
                perguntas.append(pergunta)

        print(f"[INFO] APN-1: {len(perguntas)} perguntas coletadas")
        return perguntas

    def _encontrar_rows_apn1(self):
        """Encontra rows das perguntas APN-1."""
        for xpath in XPATH_APN1_ROWS:
            rows = self.driver.find_elements(By.XPATH, xpath)
            if rows:
                return rows
        return []

    def _extrair_pergunta(self, row, indice: int) -> Optional[Dict]:
        """Extrai informações de uma pergunta individual."""
        try:
            # Texto da pergunta
            pergunta_elem = row.find_element(By.XPATH, ".//div[contains(@class,'pergunta')]")
            texto = pergunta_elem.text.strip() if pergunta_elem.text else ""
            texto_norm = normalizar_string(texto)

            # IDs dos radio buttons
            id_sim, id_nao = self._extrair_ids_radios(row)

            return {
                'indice': indice,
                'texto': texto,
                'texto_norm': texto_norm,
                'id_sim': id_sim,
                'id_nao': id_nao,
            }
        except Exception:
            return None

    def _extrair_ids_radios(self, row) -> Tuple[Optional[str], Optional[str]]:
        """Extrai IDs dos radio buttons SIM/NÃO."""
        id_sim, id_nao = None, None

        # Tenta padrão APN1_
        radios = row.find_elements(By.XPATH, ".//input[contains(@id,'APN1_')]")
        for radio in radios:
            rid = radio.get_attribute("id")
            if rid and rid.endswith("_0"):
                id_sim = rid
            elif rid and rid.endswith("_1"):
                id_nao = rid

        # Fallback: procura por outros padrões
        if not (id_sim and id_nao):
            radios = row.find_elements(By.XPATH, ".//input[@type='radio']")
            for radio in radios:
                rid = radio.get_attribute("id") or ""
                value = radio.get_attribute("value") or ""

                if value == "0" or "sim" in rid.lower():
                    id_sim = rid
                elif value == "1" or "nao" in rid.lower() or "não" in rid.lower():
                    id_nao = rid

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
        resposta = self._determinar_resposta(pergunta['texto_norm'], contexto)
        id_alvo = pergunta['id_sim'] if resposta == "Sim" else pergunta['id_nao']

        if not id_alvo:
            print(f"[WARN] P{pergunta['indice']:02d}: ID não encontrado para '{resposta}'")
            return False

        print(f"[INFO] P{pergunta['indice']:02d} → {resposta} | '{pergunta['texto'][:50]}...'")

        return self._marcar_via_javascript(id_alvo)

    def _determinar_resposta(self, texto_pergunta: str, contexto: str) -> str:
        """Determina resposta baseada no texto da pergunta e contexto."""
        # Padrão: todas começam como "Não"
        resposta = "Não"

        for padrao_nome, (padroes_pergunta, padroes_contexto) in self.padroes_perguntas.items():
            if self._verificar_padrao(texto_pergunta, padroes_pergunta):
                if self._verificar_padrao(contexto, padroes_contexto):
                    resposta = "Sim"
                    break

        return resposta

    def _verificar_padrao(self, texto: str, padroes: Set[str]) -> bool:
        """Verifica se texto contém algum dos padrões."""
        return any(padrao in texto for padrao in padroes)

    def _marcar_via_javascript(self, element_id: str) -> bool:
        """Marca resposta via JavaScript."""
        script = f"""
        var element = document.getElementById("{element_id}");
        if (!element) return false;

        try {{
            element.disabled = false;
            element.focus();
            element.click();

            // Dispara eventos para garantir que Angular detecte a mudança
            element.dispatchEvent(new Event('input', {{bubbles: true}}));
            element.dispatchEvent(new Event('change', {{bubbles: true}}));

            return element.checked === true;
        }} catch(e) {{
            return false;
        }}
        """

        try:
            resultado = self.driver.execute_script(script)
            return bool(resultado)
        except Exception as e:
            print(f"[DEBUG] JavaScript falhou: {e}")
            return False


# -------------------------------------------------------------------
# Funções de interface pública (mantidas para compatibilidade)
# -------------------------------------------------------------------
@timeit_decorator()
def preencher_questionario_pt(driver, timeout: float, qpt_plano: Dict[Tuple[str, str], str]):
    """Interface pública para preenchimento do Questionário PT."""
    processor = QuestionarioPTProcessor(driver, timeout)
    processor.preencher(qpt_plano)


@timeit_decorator()
def preencher_epi_adicional(driver, timeout: float, epi_radios_plano):
    """Interface pública para preenchimento de EPI adicional."""
    processor = EPIAdicionalProcessor(driver, timeout)
    processor.preencher(epi_radios_plano)


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