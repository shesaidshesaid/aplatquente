#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
quent4_epi.py
Processamento da aba EPI:
- Leitura dos EPIs atuais por categoria
- Inclusão de itens faltantes conforme plano
- (Remoção de excedentes opcional)
"""

import time
from typing import Dict, List, Tuple, Set, Optional, NamedTuple, Any
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

from quent1_infra import goto_tab

# -------------------------------------------------------------------
# Constantes e configurações
# -------------------------------------------------------------------
CATEGORIAS_EPI = ["Vestimentas", "Óculos", "Luvas", "Proteção Respiratória"]

# XPATHS comuns
XPATH_LABEL_CATEGORIA = "//app-epi-da-etapa//label[normalize-space()='{}']"
XPATH_MODAL_CONTENT = "//app-epi-da-etapa//app-associar-epi//app-modal//div[contains(@class,'modal-content')]"
XPATH_MODAL_TABLE = "//app-epi-da-etapa//app-associar-epi//table//tr[.//td]"
XPATH_BTN_CONFIRMAR = "//app-epi-da-etapa//app-associar-epi//button[normalize-space()='Confirmar']"
XPATH_BTN_CANCELAR = "//app-epi-da-etapa//app-associar-epi//button[normalize-space()='Cancelar']"


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
# Classes de dados para melhor organização
# -------------------------------------------------------------------
class ResultadoComparacao(NamedTuple):
    """Resultado da comparação de itens EPI."""
    faltantes: Set[str]
    excedentes: Set[str]


class CategoriaInfo(NamedTuple):
    """Informações de uma categoria EPI."""
    nome: str
    label_element: Any
    container: Any
    itens_atuais: List[str]


# -------------------------------------------------------------------
# Utilitários de manipulação de texto e XPATH
# -------------------------------------------------------------------
@lru_cache(maxsize=128)
def normalizar_texto_epi(texto: str) -> str:
    """Normaliza texto para comparações de EPI."""
    if not texto:
        return ""
    return ' '.join(texto.split()).upper().strip()


def criar_xpath_literal(texto: str) -> str:
    """
    Cria literal XPath seguro para strings contendo aspas.

    Exemplo: "O'Connor" -> "concat('O',\"'\",'Connor')"
    """
    if "'" not in texto:
        return f"'{texto}'"
    if '"' not in texto:
        return f'"{texto}"'

    partes = texto.split("'")
    concat_parts = []
    for i, parte in enumerate(partes):
        concat_parts.append(f"'{parte}'")
        if i < len(partes) - 1:
            concat_parts.append('"\'"')

    return f"concat({', '.join(concat_parts)})"


# -------------------------------------------------------------------
# Classe principal de processamento EPI
# -------------------------------------------------------------------
class EPIProcessor:
    """Processador otimizado para aba EPI."""

    def __init__(self, driver, timeout: float):
        self.driver = driver
        self.timeout = timeout
        self.categorias_info: Dict[str, CategoriaInfo] = {}

    @timeit_decorator()
    def processar(self, epis_cat_plano: Dict[str, Set[str]]):
        """Processa a aba EPI completa."""
        print("[STEP] Processando aba 'EPI'...")
        goto_tab(self.driver, "EPI", self.timeout)

        # Processa todas as categorias
        for categoria in CATEGORIAS_EPI:
            self._processar_categoria(categoria, epis_cat_plano)

        print("[INFO] Aba EPI processada")

    def _processar_categoria(self, categoria: str, plano: Dict[str, Set[str]]):
        """Processa uma categoria específica."""
        print(f"\n[EPI] Processando categoria: {categoria}")

        # Coleta informações da categoria
        info = self._coletar_info_categoria(categoria)
        if not info:
            return

        # Compara com plano
        resultado = self._comparar_com_plano(info, plano)

        # Inclui itens faltantes
        if resultado.faltantes:
            self._incluir_itens_faltantes(categoria, resultado.faltantes)

        # Remoção de excedentes (opcional - comentado)
        # if resultado.excedentes:
        #     self._remover_itens_excedentes(categoria, resultado.excedentes)

    def _coletar_info_categoria(self, categoria: str) -> Optional[CategoriaInfo]:
        """Coleta todas as informações de uma categoria."""
        try:
            label = WebDriverWait(self.driver, self.timeout).until(
                EC.presence_of_element_located(
                    (By.XPATH, XPATH_LABEL_CATEGORIA.format(categoria))
                )
            )

            container = self._obter_container_categoria(label)
            itens = self._extrair_itens_categoria(container)

            info = CategoriaInfo(categoria, label, container, itens)
            self.categorias_info[categoria] = info

            return info

        except TimeoutException:
            print(f"[WARN] Categoria '{categoria}' não encontrada")
            return None
        except Exception as e:
            print(f"[ERROR] Erro ao coletar info da categoria '{categoria}': {e}")
            return None

    def _obter_container_categoria(self, label_element) -> Optional[Any]:
        """Obtém container da categoria a partir do label."""
        try:
            return label_element.find_element(
                By.XPATH, "./ancestor::div[contains(@class,'row')][1]/.."
            )
        except NoSuchElementException:
            try:
                return label_element.find_element(By.XPATH, "./ancestor::div[1]")
            except NoSuchElementException:
                return None

    def _extrair_itens_categoria(self, container) -> List[str]:
        """Extrai itens EPI do container da categoria."""
        if not container:
            return []

        itens = []
        try:
            tbodies = container.find_elements(By.XPATH, ".//table/tbody")
            for tbody in tbodies:
                linhas = tbody.find_elements(By.XPATH, ".//tr")
                for linha in linhas:
                    item = self._extrair_item_linha(linha)
                    if item:
                        itens.append(item)
        except Exception as e:
            print(f"[DEBUG] Erro ao extrair itens: {e}")

        print(f"[INFO] Categoria - {len(itens)} item(s) encontrado(s)")
        return itens

    def _extrair_item_linha(self, linha) -> Optional[str]:
        """Extrai texto do item de uma linha da tabela."""
        try:
            celula = linha.find_element(By.XPATH, "./td[1]")
            texto = celula.get_attribute("title") or celula.text or ""
            texto_limpo = texto.strip()
            return texto_limpo if texto_limpo else None
        except Exception:
            return None

    def _comparar_com_plano(self, info: CategoriaInfo, plano: Dict[str, Set[str]]) -> ResultadoComparacao:
        """Compara itens atuais com o plano esperado."""
        esperados = plano.get(info.nome, set())
        atuais_set = set(info.itens_atuais)

        faltantes = esperados - atuais_set
        excedentes = atuais_set - esperados

        self._log_comparacao(info.nome, esperados, atuais_set, faltantes, excedentes)

        return ResultadoComparacao(faltantes, excedentes)

    def _log_comparacao(self, categoria: str, esperados: Set[str],
                        atuais: Set[str], faltantes: Set[str], excedentes: Set[str]):
        """Log detalhado da comparação."""
        print(f"[EPI] {categoria} - Comparação:")
        print(f"  Esperados ({len(esperados)}): {sorted(esperados) if esperados else 'nenhum'}")
        print(f"  Atuais    ({len(atuais)}): {sorted(atuais) if atuais else 'nenhum'}")

        if faltantes:
            print(f"  Faltantes ({len(faltantes)}):")
            for item in sorted(faltantes):
                print(f"    • {item}")

        if excedentes:
            print(f"  Excedentes ({len(excedentes)}):")
            for item in sorted(excedentes):
                print(f"    • {item}")

    def _incluir_itens_faltantes(self, categoria: str, itens_faltantes: Set[str]):
        """Inclui itens faltantes na categoria."""
        print(f"[EPI] Incluindo {len(itens_faltantes)} item(s) em '{categoria}'")

        # Verifica se botão '+' está disponível
        if not self._verificar_botao_adicionar(categoria):
            return

        # Abre modal de associação
        if not self._abrir_modal_associacao(categoria):
            return

        # Seleciona itens no modal
        self._selecionar_itens_modal(categoria, itens_faltantes)

        # Confirma associação
        self._confirmar_modal_associacao()

    def _verificar_botao_adicionar(self, categoria: str) -> bool:
        """Verifica se botão '+' está habilitado."""
        try:
            label = self.categorias_info[categoria].label_element
            linha_cabecalho = label.find_element(
                By.XPATH, "./ancestor::div[contains(@class,'row')][1]"
            )

            # Procura botão '+'
            btn_add = linha_cabecalho.find_element(
                By.XPATH, ".//button[normalize-space()='+']"
            )

            if btn_add.is_enabled():
                return True
            else:
                print(f"[WARN] Botão '+' desabilitado para '{categoria}'")
                return False

        except NoSuchElementException:
            print(f"[WARN] Botão '+' não encontrado para '{categoria}'")
            return False
        except Exception as e:
            print(f"[ERROR] Erro ao verificar botão '+': {e}")
            return False

    def _abrir_modal_associacao(self, categoria: str) -> bool:
        """Abre modal de associação de EPI."""
        try:
            label = self.categorias_info[categoria].label_element
            linha_cabecalho = label.find_element(
                By.XPATH, "./ancestor::div[contains(@class,'row')][1]"
            )

            # Clica no botão '+'
            btn_add = linha_cabecalho.find_element(
                By.XPATH, ".//button[normalize-space()='+']"
            )
            btn_add.click()

            print(f"[CLICK] Modal de associação aberto para '{categoria}'")

            # Aguarda modal abrir
            WebDriverWait(self.driver, self.timeout).until(
                EC.visibility_of_element_located((By.XPATH, XPATH_MODAL_CONTENT))
            )

            return True

        except Exception as e:
            print(f"[ERROR] Falha ao abrir modal para '{categoria}': {e}")
            return False

    def _selecionar_itens_modal(self, categoria: str, itens: Set[str]):
        """Seleciona itens no modal de associação."""
        if not itens:
            return

        # Aguarda tabela carregar
        try:
            WebDriverWait(self.driver, 2).until(
                EC.presence_of_element_located((By.XPATH, XPATH_MODAL_TABLE))
            )
        except TimeoutException:
            print(f"[WARN] Modal vazio para '{categoria}'")
            self._fechar_modal_associacao()
            return

        # Seleciona cada item
        for item in sorted(itens):
            self._selecionar_item_modal(categoria, item)

    def _selecionar_item_modal(self, categoria: str, item: str):
        """Seleciona um item específico no modal com busca flexível."""
        # **CORREÇÃO: Buscar por partes do texto para EPI Obrigatório**
        item_lower = item.lower()

        # Tentar diferentes estratégias de busca
        estrategias_busca = [
            # Busca exata
            lambda: f"//tr[.//td[normalize-space()='{item}']]",
            # Busca por contém
            lambda: f"//tr[.//td[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{item_lower}')]]",
            # Busca por parte do texto (para EPI Obrigatório)
            lambda: f"//tr[.//td[contains(., 'EPI') and contains(., 'OBRIGATÓRIOS')]]",
            lambda: f"//tr[.//td[contains(., 'EPI') and contains(., 'OBRIGATORIOS')]]",
        ]

        for estrategia in estrategias_busca:
            try:
                xpath = estrategia()
                linha = self.driver.find_element(By.XPATH, xpath)
                if linha:
                    # Marca checkbox
                    checkbox = linha.find_element(By.XPATH, ".//td[1]//input[@type='checkbox']")
                    if not checkbox.is_selected():
                        checkbox.click()
                        print(f"[EPI] Item marcado: '{item}' (encontrado com busca flexível)")
                        return
            except NoSuchElementException:
                continue
            except StaleElementReferenceException:
                print(f"[WARN] Elemento STALE ao marcar '{item}'")
                return
            except Exception as e:
                continue

        print(f"[WARN] Item não encontrado no modal (mesmo com busca flexível): '{item}'")

    def _buscar_elemento_com_retry(self, xpath: str, max_tentativas: int = 3) -> Optional[Any]:
        """Busca elemento com retry em caso de falha."""
        for tentativa in range(max_tentativas):
            try:
                elemento = self.driver.find_element(By.XPATH, xpath)
                return elemento
            except NoSuchElementException:
                if tentativa == max_tentativas - 1:
                    break
                time.sleep(0.3)

        return None

    def _confirmar_modal_associacao(self):
        """Confirma seleção no modal."""
        try:
            # Clica em Confirmar
            btn_confirmar = WebDriverWait(self.driver, self.timeout).until(
                EC.element_to_be_clickable((By.XPATH, XPATH_BTN_CONFIRMAR))
            )
            btn_confirmar.click()

            print("[CLICK] Modal confirmado")

            # Trata popup de código vazio (se aparecer)
            self._tratar_popup_codigo_vazio()

            # Aguarda modal fechar
            self._aguardar_modal_fechar()

        except TimeoutException:
            print("[WARN] Botão Confirmar não encontrado")
            self._fechar_modal_associacao()
        except Exception as e:
            print(f"[ERROR] Erro ao confirmar modal: {e}")

    def _tratar_popup_codigo_vazio(self):
        """Trata popup de código EPI vazio."""
        try:
            WebDriverWait(self.driver, 2).until(
                EC.visibility_of_element_located((
                    By.XPATH,
                    "//div[contains(@class,'modal-content')]"
                    "//h5[contains(.,'código de EPI não pode ser vazio')]"
                ))
            )

            btn_ok = self.driver.find_element(
                By.XPATH,
                "//div[contains(@class,'modal-content')]"
                "//button[normalize-space()='Ok']"
            )
            btn_ok.click()

            print("[CLICK] Popup de código vazio tratado")

            WebDriverWait(self.driver, self.timeout).until(
                EC.invisibility_of_element_located((
                    By.XPATH,
                    "//div[contains(@class,'modal-content')]"
                    "//h5[contains(.,'código de EPI não pode ser vazio')]"
                ))
            )

        except TimeoutException:
            pass  # Popup não apareceu

    def _aguardar_modal_fechar(self):
        """Aguarda modal fechar."""
        try:
            WebDriverWait(self.driver, self.timeout).until(
                EC.invisibility_of_element_located((By.XPATH, XPATH_MODAL_CONTENT))
            )
            print("[INFO] Modal fechado")
        except TimeoutException:
            print("[WARN] Modal pode ainda estar visível")
        finally:
            time.sleep(0.5)

    def _fechar_modal_associacao(self):
        """Fecha modal de associação."""
        try:
            btn_cancelar = self.driver.find_element(By.XPATH, XPATH_BTN_CANCELAR)
            btn_cancelar.click()
            time.sleep(0.1)
        except Exception:
            pass

    def _remover_itens_excedentes(self, categoria: str, itens_excedentes: Set[str]):
        """Remove itens excedentes (opcional - mantido para compatibilidade)."""
        print(f"[EPI] Removendo {len(itens_excedentes)} item(s) excedentes de '{categoria}'")

        for item in sorted(itens_excedentes):
            self._remover_item_excedente(categoria, item)

    def _remover_item_excedente(self, categoria: str, item: str):
        """Remove um item excedente específico."""
        info = self.categorias_info.get(categoria)
        if not info:
            return

        item_norm = normalizar_texto_epi(item)
        xpath_literal = criar_xpath_literal(item_norm)

        for tentativa in range(2):
            try:
                # Reconstrói o XPath para busca
                xpath_linha = (
                        ".//table/tbody/tr[.//td[normalize-space()="
                        + xpath_literal
                        + " or normalize-space(@title)="
                        + xpath_literal
                        + "]]"
                )

                # Tenta encontrar a linha
                linha = info.container.find_element(By.XPATH, xpath_linha)

                # Clica na linha para selecionar
                celula = linha.find_element(By.XPATH, "./td[1]")
                self.driver.execute_script(
                    "arguments[0].scrollIntoView({block:'center'});", celula
                )
                celula.click()
                time.sleep(0.1)

                # Encontra botão '-'
                label = info.label_element
                linha_cabecalho = label.find_element(
                    By.XPATH, "./ancestor::div[contains(@class,'row')][1]"
                )

                btn_remover = linha_cabecalho.find_element(
                    By.XPATH, ".//button[normalize-space()='-']"
                )
                btn_remover.click()

                print(f"[EPI] Item removido: '{item}'")

                # Aguarda remoção
                try:
                    WebDriverWait(self.driver, self.timeout).until(EC.staleness_of(linha))
                except TimeoutException:
                    time.sleep(0.3)

                time.sleep(0.2)
                break

            except StaleElementReferenceException:
                if tentativa == 1:
                    print(f"[WARN] Falha ao remover '{item}' após STALE")
                time.sleep(0.3)
            except NoSuchElementException:
                print(f"[WARN] Item não encontrado para remoção: '{item}'")
                break
            except Exception as e:
                print(f"[WARN] Erro ao remover '{item}': {e}")
                break


# -------------------------------------------------------------------
# Função pública de compatibilidade
# -------------------------------------------------------------------
@timeit_decorator()
def processar_aba_epi(driver, timeout: float, epis_cat_plano: Dict[str, Set[str]]):
    """Processa a aba EPI (interface pública para compatibilidade)."""
    processor = EPIProcessor(driver, timeout)
    processor.processar(epis_cat_plano)