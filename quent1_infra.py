#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
quent1_infra.py
Infraestrutura para automação APLAT - Selenium, login, navegação
"""

import os
import time
from typing import Optional, Tuple, List, Callable, Any
from functools import wraps, lru_cache
from contextlib import contextmanager

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    StaleElementReferenceException,
    ElementClickInterceptedException,
    NoSuchElementException,
)

# -------------------------------------------------------------------
# Constantes e Configurações
# -------------------------------------------------------------------
EDGE_OPTIONS = [
    "--start-maximized",
    "--disable-gpu",
    "--disable-dev-shm-usage",
    "--no-sandbox",
]

# XPATHS reutilizáveis
XPATH_BTN_EXIBIR_OPCOES = "//button[normalize-space()='Exibir opções']"
XPATH_CAMPO_DATA = "//input[@placeholder='Selecione uma data']"
XPATH_CAMPO_NUMERO = "//input[@formcontrolname='numeroetapa']"
XPATH_BTN_PESQUISAR = "//button[normalize-space()='Pesquisar']"
XPATH_BTN_FECHAR = "//app-botoes-etapa//button[normalize-space()='Fechar']"
XPATH_BTN_CONFIRMAR = "//app-botoes-etapa//button[normalize-space()='Confirmar']"
XPATH_MESSAGEBOX = "//app-messagebox//div[contains(@class,'modal') and contains(@class,'in')]"
XPATH_BTN_OK = "//app-messagebox//button[normalize-space()='Ok']"

# Tentativas de login
SUBMIT_XPATHS = [
    "//button[normalize-space()='Entrar']",
    "//button[normalize-space()='Acessar']",
    "//input[@type='submit']",
    "//button[contains(.,'Sign in') or contains(.,'Login')]",
]

# Indicadores de tela principal
MAIN_SCREEN_INDICATORS = [
    "//button[normalize-space()='Exibir opções']",
    "//a[normalize-space()='EPI']",
    "//h3[contains(.,'Cadastro de PT')]",
]

# Caminhos para resultados da pesquisa
SEARCH_RESULT_XPATHS = [
    "(//app-grid//table/tbody/tr)[1]",
    "(//table//tbody//tr)[1]",
    "(//ul[contains(@class,'list-group')]//li[contains(@class,'listagem')])[1]",
]


# -------------------------------------------------------------------
# Decorator para medição de tempo otimizado
# -------------------------------------------------------------------
def timeit_decorator(func_name: Optional[str] = None):
    """Decorator para medição de tempo de execução."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            start_time = time.perf_counter()
            result = func(*args, **kwargs)
            elapsed = time.perf_counter() - start_time
            name = func_name or func.__name__
            print(f"[TIMER] {name}: {elapsed:.3f}s")
            return result

        return wrapper

    return decorator


# -------------------------------------------------------------------
# Cache para elementos frequentemente acessados
# -------------------------------------------------------------------
class ElementCache:
    """Cache simples para elementos DOM."""

    def __init__(self, maxsize: int = 100):
        self.cache = {}
        self.maxsize = maxsize

    def get(self, key: str, driver, finder: Callable) -> Optional[Any]:
        """Obtém elemento do cache ou busca."""
        if key not in self.cache:
            element = finder()
            if element:
                self._add_to_cache(key, element)
        return self.cache.get(key)

    def _add_to_cache(self, key: str, element: Any):
        """Adiciona elemento ao cache."""
        if len(self.cache) >= self.maxsize:
            # Remove o mais antigo (simples FIFO)
            self.cache.pop(next(iter(self.cache)))
        self.cache[key] = element

    def clear(self):
        """Limpa o cache."""
        self.cache.clear()


element_cache = ElementCache()


# -------------------------------------------------------------------
# Criação e configuração do WebDriver
# -------------------------------------------------------------------
def create_edge_driver() -> webdriver.Edge:
    """Cria e configura instância do WebDriver Edge."""
    options = EdgeOptions()

    # Adiciona argumentos de forma mais eficiente
    options.add_experimental_option('excludeSwitches', ['enable-logging'])
    for arg in EDGE_OPTIONS:
        options.add_argument(arg)

    # Tenta localizar o webdriver
    driver_paths = [
        ".venv/msedgedriver.exe",
        "msedgedriver.exe",
        os.path.join(os.getcwd(), "msedgedriver.exe"),
    ]

    for driver_path in driver_paths:
        if os.path.exists(driver_path):
            print(f"[INFO] Usando msedgedriver local: {driver_path}")
            try:
                service = EdgeService(driver_path)
                driver = webdriver.Edge(service=service, options=options)
                maximize_window(driver)
                return driver
            except Exception as e:
                print(f"[WARN] Falha ao usar {driver_path}: {e}")
                continue

    # Fallback: usar driver do sistema PATH
    try:
        driver = webdriver.Edge(options=options)
        maximize_window(driver)
        return driver
    except Exception as e:
        print(f"[ERROR] Falha ao criar WebDriver: {e}")
        raise RuntimeError(f"Não foi possível iniciar o WebDriver Edge: {e}")


def maximize_window(driver: webdriver.Edge):
    """Maximiza a janela do navegador com tratamento de erro."""
    try:
        driver.maximize_window()
    except Exception:
        # Silenciosamente ignora falhas de maximização
        pass


# -------------------------------------------------------------------
# Utilitários de espera e localização
# -------------------------------------------------------------------
def wait_for_document_ready(driver: webdriver.Edge, timeout: float):
    """Aguarda até que o documento esteja completamente carregado."""
    start_time = time.perf_counter()

    WebDriverWait(driver, timeout).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )

    elapsed = time.perf_counter() - start_time
    print(f"[TIMER] Document ready: {elapsed:.3f}s")


def wait_and_click(driver: webdriver.Edge, xpath: str, timeout: float,
                   description: str = "") -> Optional[Any]:
    """Aguarda elemento ficar clicável e clica nele."""
    label = description or xpath[:50] + "..." if len(xpath) > 50 else xpath

    try:
        element = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((By.XPATH, xpath))
        )
        element.click()
        print(f"[CLICK] {label}")
        return element
    except TimeoutException:
        print(f"[WARN] Timeout ao aguardar elemento: {label}")
        return None


def safe_find_element(driver: webdriver.Edge, xpath: str,
                      timeout: float) -> Optional[Any]:
    """
    Encontra elemento de forma segura com timeout.

    Returns:
        Elemento encontrado ou None se timeout
    """
    try:
        return WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.XPATH, xpath))
        )
    except TimeoutException:
        return None


def find_visible_element(driver: webdriver.Edge, xpaths: List[str],
                         timeout: float = 5.0) -> Optional[Any]:
    """Encontra o primeiro elemento visível entre múltiplos XPaths."""
    for xpath in xpaths:
        try:
            element = WebDriverWait(driver, timeout).until(
                EC.visibility_of_element_located((By.XPATH, xpath))
            )
            return element
        except TimeoutException:
            continue
    return None


# -------------------------------------------------------------------
# Login e autenticação
# -------------------------------------------------------------------
def _wait_main_screen(driver: webdriver.Edge, timeout: float) -> bool:
    """Verifica se a tela principal foi carregada."""
    try:
        WebDriverWait(driver, timeout).until(
            EC.any_of(*[EC.presence_of_element_located((By.XPATH, xp))
                        for xp in MAIN_SCREEN_INDICATORS])
        )
        return True
    except TimeoutException:
        return False


def _perform_login(driver: webdriver.Edge, username: str,
                   password: str, timeout: float) -> bool:
    """Executa o processo de login com credenciais fornecidas."""
    # Localiza campo de usuário
    user_fields = driver.find_elements(
        By.XPATH, "//input[@type='text' or @type='email' or not(@type)]"
    )
    user_field = next((f for f in user_fields if f.is_displayed() and f.is_enabled()), None)

    if user_field:
        clear_and_send_keys(user_field, username)

    # Localiza campo de senha
    pwd_field = find_visible_element(
        driver, ["//input[@type='password' and not(@disabled)]"], timeout=2
    )

    if pwd_field:
        clear_and_send_keys(pwd_field, password)
    else:
        return False

    # Tenta submeter o formulário
    return submit_login_form(driver)


def clear_and_send_keys(element, text: str):
    """Limpa campo e insere texto com tratamento de erro."""
    try:
        element.clear()
    except Exception:
        pass
    element.send_keys(text)


def submit_login_form(driver: webdriver.Edge) -> bool:
    """Tenta submeter formulário de login por múltiplos métodos."""
    # Método 1: Botões de submit específicos
    for xpath in SUBMIT_XPATHS:
        try:
            btn = driver.find_element(By.XPATH, xpath)
            if btn.is_displayed() and btn.is_enabled():
                btn.click()
                print(f"[LOGIN] Submit via botão: {xpath}")
                return True
        except Exception:
            continue

    # Método 2: ENTER no campo de senha
    try:
        pwd_field = driver.find_element(By.XPATH, "//input[@type='password']")
        pwd_field.send_keys(Keys.ENTER)
        print("[LOGIN] Submit via ENTER")
        return True
    except Exception:
        pass

    return False


@timeit_decorator()
def attempt_auto_login(driver: webdriver.Edge, args, timeout: float, url: str) -> bool:
    """Tenta login automático via keyring ou manual."""
    print(f"[INFO] Acessando APLAT: {url}")
    driver.get(url)
    wait_for_document_ready(driver, timeout)

    # Verifica se já está logado (SSO)
    if not is_login_required(driver):
        if _wait_main_screen(driver, timeout):
            print("[LOGIN] SSO ativo ou já autenticado")
            return True

    # Tenta login com keyring
    if try_keyring_login(driver, args, timeout):
        return True

    # Login manual
    return manual_login(driver, timeout)


def is_login_required(driver: webdriver.Edge) -> bool:
    """Verifica se campos de login estão visíveis."""
    try:
        WebDriverWait(driver, 3).until(
            EC.visibility_of_element_located(
                (By.XPATH, "//input[@type='password' and not(@disabled)]")
            )
        )
        return True
    except TimeoutException:
        return False


def try_keyring_login(driver: webdriver.Edge, args, timeout: float) -> bool:
    """Tenta login usando keyring."""
    try:
        import keyring
    except ImportError:
        return False

    if not (args.use_keyring and args.user):
        return False

    service = args.keyring_service or "aplat.petrobras"
    secret = keyring.get_password(service, args.user)

    if not secret:
        print(f"[WARN] Senha não encontrada no keyring (service='{service}', user='{args.user}').")
        return False

    print(f"[LOGIN] Tentando login automático para usuário: {args.user}")

    try:
        if _perform_login(driver, args.user, secret, timeout):
            # Aguarda transição de tela
            try:
                WebDriverWait(driver, 5).until(
                    EC.staleness_of(driver.find_element(
                        By.XPATH, "//input[@type='password' and not(@disabled)]"
                    ))
                )
            except Exception:
                pass

            if _wait_main_screen(driver, max(8, int(timeout))):
                print("[INFO] Login realizado com sucesso (keyring).")
                return True
    except Exception as e:
        print(f"[WARN] Erro no login automático com keyring: {e}")

    return False


def manual_login(driver: webdriver.Edge, timeout: float) -> bool:
    """Solicita login manual do usuário."""
    print("[INFO] Verifique se o login foi realizado (SSO / usuário e senha).")
    print("[INFO] Caso necessário, faça o login manualmente no navegador.")

    try:
        input("Pressione ENTER aqui no console depois que a tela principal do APLAT estiver aberta...\n")
    except EOFError:
        pass

    if _wait_main_screen(driver, timeout):
        print("[INFO] Login confirmado (manual/automático).")
        return True

    print("[ERROR] Não foi possível confirmar a tela principal do APLAT após tentativa de login.")
    return False


# -------------------------------------------------------------------
# Pesquisa e navegação
# -------------------------------------------------------------------
@timeit_decorator()
def perform_search(driver: webdriver.Edge, data_str: str, numero_etapa: str,
                   timeout: float, search_timeout: float, detail_wait: float):
    """Executa pesquisa de etapa no APLAT."""
    print(f"[INFO] Iniciando pesquisa para etapa: {numero_etapa}")

    # Abre opções de pesquisa
    wait_and_click(driver, XPATH_BTN_EXIBIR_OPCOES, timeout, "Exibir opções")

    # Preenche data
    fill_field(driver, XPATH_CAMPO_DATA, data_str, timeout, "Campo data")

    # Preenche número da etapa
    fill_field(driver, XPATH_CAMPO_NUMERO, numero_etapa, timeout, "Campo número etapa")

    # Executa pesquisa
    wait_and_click(driver, XPATH_BTN_PESQUISAR, timeout, "Pesquisar")

    print(f"[INFO] Aguardando resultados da pesquisa (até {int(search_timeout)}s)...")

    # Aguarda e clica no primeiro resultado
    click_first_search_result(driver, search_timeout, detail_wait)


def fill_field(driver: webdriver.Edge, xpath: str, value: str,
               timeout: float, field_name: str):
    """Preenche campo de formulário."""
    element = WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((By.XPATH, xpath))
    )
    clear_and_send_keys(element, value)
    print(f"[INFO] {field_name} preenchido: {value}")


def click_first_search_result(driver: webdriver.Edge, search_timeout: float,
                              detail_wait: float):
    """Localiza e clica no primeiro resultado da pesquisa."""
    start_time = time.perf_counter()

    def find_clickable_result(driver):
        for xpath in SEARCH_RESULT_XPATHS:
            elements = driver.find_elements(By.XPATH, xpath)
            for element in elements:
                try:
                    if element.is_displayed() and element.is_enabled():
                        return element, xpath
                except StaleElementReferenceException:
                    continue
        return None

    # Aguarda resultado
    result = WebDriverWait(driver, search_timeout).until(find_clickable_result)
    row, xpath_used = result

    # Clique com retry
    for attempt in range(3):
        try:
            click_element_with_retry(driver, row)
            break
        except StaleElementReferenceException:
            if attempt == 2:
                raise
            print("[WARN] Elemento STALE, tentando novamente...")
            time.sleep(0.5)
            row = find_clickable_result(driver)[0]

    elapsed = time.perf_counter() - start_time
    print(f"[INFO] Resultado aberto (XPath: {xpath_used})")
    print(f"[TIMER] perform_search: {elapsed:.3f}s")

    time.sleep(detail_wait)


def click_element_with_retry(driver: webdriver.Edge, element):
    """Tenta clicar em elemento com múltiplas estratégias."""
    try:
        ActionChains(driver).double_click(element).perform()
    except Exception:
        try:
            element.click()
        except Exception:
            driver.execute_script("arguments[0].click();", element)


# -------------------------------------------------------------------
# Navegação por abas
# -------------------------------------------------------------------
@timeit_decorator()
def goto_tab(driver: webdriver.Edge, tab_label: str, timeout: float):
    """Navega para uma aba específica."""
    xpath = f"//ul[contains(@class,'tabAplat')]//a[normalize-space()='{tab_label}']"

    # Verifica se já está na aba ativa
    if is_tab_active(driver, xpath):
        print(f"[INFO] Aba '{tab_label}' já está ativa.")
        return

    # Navega para a aba
    element = WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((By.XPATH, xpath))
    )
    element.click()

    print(f"[CLICK] Navegado para aba: {tab_label}")
    time.sleep(0.1)


def is_tab_active(driver: webdriver.Edge, xpath: str) -> bool:
    """Verifica se a aba já está ativa."""
    try:
        active_tab = driver.find_element(
            By.XPATH, f"{xpath}/parent::li[contains(@class,'active')]"
        )
        return bool(active_tab)
    except NoSuchElementException:
        return False


# -------------------------------------------------------------------
# Gerenciamento de modais e popups
# -------------------------------------------------------------------
def fechar_modal_etapa(driver: webdriver.Edge, timeout: float):
    """Fecha modal da etapa se estiver aberto."""
    try:
        btn = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((By.XPATH, XPATH_BTN_FECHAR))
        )
        btn.click()
        print("[CLICK] Modal da etapa fechado")
        time.sleep(0.5)
    except TimeoutException:
        print("[WARN] Modal já fechado ou botão não encontrado.")


def is_messagebox_open(driver: webdriver.Edge) -> bool:
    """Verifica se messagebox está aberto."""
    try:
        box = driver.find_element(By.XPATH, XPATH_MESSAGEBOX)
        return box.is_displayed()
    except Exception:
        return False


def click_messagebox_ok(driver: webdriver.Edge, timeout: float) -> bool:
    """Fecha messagebox clicando em Ok."""
    try:
        btn_ok = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((By.XPATH, XPATH_BTN_OK))
        )
        btn_ok.click()

        WebDriverWait(driver, timeout).until(
            EC.invisibility_of_element_located((By.XPATH, XPATH_MESSAGEBOX))
        )
        print("[CLICK] MessageBox fechado")
        return True
    except TimeoutException:
        return False


def ensure_no_messagebox(driver: webdriver.Edge, timeout: float):
    """Garante que não há messagebox aberta."""
    if is_messagebox_open(driver):
        click_messagebox_ok(driver, timeout)


def clicar_botao_confirmar_rodape(driver: webdriver.Edge, timeout: float):
    """Clica no botão Confirmar no rodapé."""
    try:
        ensure_no_messagebox(driver, timeout)

        btn = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((By.XPATH, XPATH_BTN_CONFIRMAR))
        )

        try:
            btn.click()
        except ElementClickInterceptedException:
            ensure_no_messagebox(driver, timeout)
            driver.execute_script("arguments[0].click();", btn)

        # Verifica se abriu messagebox de confirmação
        try:
            WebDriverWait(driver, 3).until(
                EC.presence_of_element_located((By.XPATH, XPATH_MESSAGEBOX))
            )
            click_messagebox_ok(driver, timeout)
        except TimeoutException:
            pass

        time.sleep(0.3)
        print("[CLICK] Botão Confirmar acionado")
    except TimeoutException:
        print("[WARN] Botão 'Confirmar' não encontrado.")


def handle_popup_gim_fam(driver: webdriver.Edge, timeout: float) -> bool:
    """Trata popup específico de GIM/FAM."""
    try:
        WebDriverWait(driver, 2).until(
            EC.visibility_of_element_located((
                By.XPATH,
                "//div[contains(@class,'modal-content')]"
                "//h5[contains(.,'deseja realmente excluir o nº da GIM/FAM')]"
            ))
        )

        btn_ok = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((By.ID, "okButton"))
        )
        btn_ok.click()

        WebDriverWait(driver, timeout).until(
            EC.invisibility_of_element_located((By.ID, "okButton"))
        )

        print("[CLICK] Popup GIM/FAM tratado")
        return True
    except TimeoutException:
        return False


# -------------------------------------------------------------------
# Context managers para operações comuns
# -------------------------------------------------------------------
@contextmanager
def suppress_stale_reference(max_attempts: int = 3):
    """
    Context manager para suprir exceções StaleElementReferenceException
    com retry automático.
    """
    attempt = 0
    while attempt < max_attempts:
        try:
            yield
            break
        except StaleElementReferenceException:
            attempt += 1
            if attempt == max_attempts:
                raise
            time.sleep(0.5)


# -------------------------------------------------------------------
# Funções utilitárias avançadas
# -------------------------------------------------------------------
def wait_for_element_state(driver: webdriver.Edge, xpath: str,
                           condition: Callable, timeout: float) -> bool:
    """Aguarda elemento atingir um estado específico."""
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: condition(d.find_element(By.XPATH, xpath))
        )
        return True
    except TimeoutException:
        return False


def retry_on_stale(func: Callable, max_retries: int = 3) -> Callable:
    """Decorator para retry em caso de StaleElementReferenceException."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except StaleElementReferenceException:
                if attempt == max_retries - 1:
                    raise
                time.sleep(0.5 * (attempt + 1))

    return wrapper