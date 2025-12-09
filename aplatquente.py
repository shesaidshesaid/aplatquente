#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
aplatquente.py
Automação APLAT (P-18) - Trabalho a Quente
"""

import argparse
import os
import sys
import time
from datetime import datetime
from typing import Tuple, List, Optional, TextIO
from functools import wraps
from contextlib import contextmanager

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from quent1_infra import (
    create_edge_driver,
    wait_for_document_ready,
    perform_search,
    goto_tab,
    fechar_modal_etapa,
    clicar_botao_confirmar_rodape,
    attempt_auto_login,
    safe_find_element,
)
from quent2_plano import (
    normalizar_texto,
    gerar_plano_trabalho_quente,
    imprimir_relatorio_plano,
    coletar_descricao,
    coletar_caracteristicas_trabalho,
)
from quent3_preenchimento import (
    preencher_questionario_pt,
    preencher_epi_adicional,
    preencher_analise_ambiental,
    preencher_apn1,
)
from quent4_epi import processar_aba_epi

# -------------------------------------------------------------------
# Constantes e Configurações
# -------------------------------------------------------------------
DEFAULT_TIMEOUT = 30.0
DEFAULT_SEARCH_TIMEOUT = 30.0
DEFAULT_DETAIL_WAIT = 0.3
DEFAULT_POST_WAIT = 0.3

DEFAULT_APLAT_URL = (
    "https://aplat.petrobras.com.br/#/permissaotrabalho/P-18/planejamento/programacaodiaria"
)


# -------------------------------------------------------------------
# Decorator para medição de tempo otimizado
# -------------------------------------------------------------------
def timeit_decorator(func_name: Optional[str] = None):
    """Decorator para medição de tempo de execução com nome customizado."""

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
# Classes utilitárias otimizadas
# -------------------------------------------------------------------
class Tee:
    """Redireciona output para múltiplos streams."""
    __slots__ = ('streams',)

    def __init__(self, *streams):
        self.streams = streams

    def write(self, data: str):
        """Escreve dados em todos os streams."""
        for stream in self.streams:
            try:
                stream.write(data)
                stream.flush()
            except (IOError, OSError):
                continue

    def flush(self):
        """Flush em todos os streams."""
        for stream in self.streams:
            try:
                stream.flush()
            except (IOError, OSError):
                continue


# -------------------------------------------------------------------
# Funções utilitárias
# -------------------------------------------------------------------
def ts() -> str:
    """Timestamp formatado para logs."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def is_trabalho_quente(tipo_trabalho: str) -> bool:
    """Verifica se o tipo de trabalho é 'Trabalho a Quente'."""
    return "TRABALHO A QUENTE" in normalizar_texto(tipo_trabalho)


# -------------------------------------------------------------------
# Coleta de informações da etapa - versão otimizada
# -------------------------------------------------------------------
def coletar_tipo_trabalho(driver, timeout: float) -> Tuple[str, str, List[Tuple[str, str]]]:
    """
    Coleta informações do campo 'Tipo Trabalho'.

    Returns:
        Tuple com (valor, texto, lista_de_opcoes)
    """
    XPATH_TIPO_TRABALHO = (
        "//span[@id='label-subtitulo' and normalize-space()='Tipo Trabalho']"
        "/ancestor::div[contains(@class,'input-group')][1]"
        "//app-combo-box[@formcontrolname='tipoPT']//select"
    )

    select_element = safe_find_element(driver, XPATH_TIPO_TRABALHO, timeout)
    if not select_element:
        print("[WARN] Não foi possível localizar o combo 'Tipo Trabalho' (tipoPT).")
        return "", "", []

    try:
        selector = Select(select_element)
        # Obtém opção selecionada
        selected_option = selector.first_selected_option if selector.all_selected_options else None
        valor = selected_option.get_attribute("value") if selected_option else ""
        texto = selected_option.text.strip() if selected_option else ""

        # Coleta todas as opções disponíveis
        opcoes = [
            (opt.get_attribute("value") or "", opt.text.strip())
            for opt in selector.options
        ]

        print(f"[INFO] Tipo Trabalho selecionado: value='{valor}', texto='{texto}'")
        return valor, texto, opcoes

    except Exception as e:
        print(f"[WARN] Erro ao coletar tipo de trabalho: {e}")
        return "", "", []


def coletar_tipo_etapa(driver, timeout: float) -> str:
    """
    Identifica o tipo de etapa selecionado nos radio buttons.

    Returns:
        Texto do tipo de etapa ou string de erro
    """
    XPATH_FIELDSET = "//legend[contains(normalize-space(),'Tipo de Etapa')]/.."

    try:
        fieldset = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.XPATH, XPATH_FIELDSET))
        )

        # Encontra radio button selecionado
        selected_radio = fieldset.find_element(
            By.XPATH, ".//input[@type='radio' and @checked]"
        )

        if selected_radio:
            radio_id = selected_radio.get_attribute("id")
            if radio_id:
                label = fieldset.find_element(By.XPATH, f".//label[@for='{radio_id}']")
                tipo_etapa_text = label.text.strip()
            else:
                tipo_etapa_text = "(sem ID)"
        else:
            # Fallback: procura manualmente
            tipo_etapa_text = encontrar_radio_selecionado(fieldset)

        print(f"[INFO] Tipo de Etapa selecionado: {tipo_etapa_text}")
        return tipo_etapa_text

    except Exception as e:
        print(f"[WARN] Não foi possível ler 'Tipo de Etapa': {e}")
        return "(erro)"


def encontrar_radio_selecionado(fieldset) -> str:
    """Função auxiliar para encontrar radio button selecionado manualmente."""
    radios = fieldset.find_elements(By.XPATH, ".//input[@type='radio']")
    for radio in radios:
        try:
            if radio.is_selected():
                radio_id = radio.get_attribute("id")
                if radio_id:
                    label = fieldset.find_element(By.XPATH, f".//label[@for='{radio_id}']")
                    return label.text.strip()
        except Exception:
            continue
    return "(não identificado)"


# -------------------------------------------------------------------
# Função principal para processar uma etapa - versão otimizada
# -------------------------------------------------------------------
@timeit_decorator()
def processar_etapa(driver, args, numero_etapa: str, idx: int, total: int) -> bool:
    """Processa uma única etapa e retorna True se bem sucedida."""
    print_separador(f"Iniciando análise da etapa {idx}/{total}: {numero_etapa} (data {args.data})")

    # Fecha modal se não for a primeira etapa
    if idx > 1:
        fechar_modal_etapa(driver, args.timeout)

    # 1. Pesquisar e abrir a etapa
    if not abrir_etapa(driver, args, numero_etapa):
        return False

    # 2. Ir para a aba "Dados da Etapa"
    if not navegar_para_dados_etapa(driver, args.timeout):
        return False

    # 3. Coletar e validar tipo de trabalho
    if not validar_tipo_trabalho(driver, args.timeout):
        return True  # Retorna True mas ignora etapas não-quente

    # 4. Coletar descrição e características
    descricao, caracteristicas = coletar_dados_etapa(driver, args.timeout)

    # 5. Gerar e executar plano
    executar_plano_completo(driver, args, numero_etapa, descricao, caracteristicas)

    # 6. Confirmar a etapa
    confirmar_etapa(driver, args.timeout)

    return True


def print_separador(titulo: str, largura: int = 70):
    """Imprime separador formatado com título."""
    print(f"\n{'=' * largura}")
    print(f"[INFO] {titulo}")
    print(f"{'=' * largura}")


def abrir_etapa(driver, args, numero_etapa: str) -> bool:
    """Pesquisa e abre a etapa especificada."""
    try:
        perform_search(
            driver,
            args.data,
            numero_etapa,
            args.timeout,
            args.search_timeout,
            args.detail_wait,
        )
        return True
    except TimeoutException as e:
        print(f"[ERROR] Falha ao localizar resultados para '{numero_etapa}': {e}")
        return False


def navegar_para_dados_etapa(driver, timeout: float) -> bool:
    """Navega para a aba 'Dados da Etapa'."""
    try:
        goto_tab(driver, "Dados da Etapa", timeout)
        return True
    except TimeoutException:
        print("[ERROR] Aba 'Dados da Etapa' não encontrada. Pulando esta etapa.")
        return False


def validar_tipo_trabalho(driver, timeout: float) -> bool:
    """Valida se o tipo de trabalho é 'Trabalho a Quente'."""
    _, tipo_trabalho_txt, _ = coletar_tipo_trabalho(driver, timeout)
    coletar_tipo_etapa(driver, timeout)  # Apenas para logging

    if not is_trabalho_quente(tipo_trabalho_txt):
        print(f"[INFO] Tipo Trabalho NÃO é 'Trabalho a Quente' (é '{tipo_trabalho_txt}'). Etapa será ignorada.")
        return False
    return True


def coletar_dados_etapa(driver, timeout: float) -> Tuple[str, str]:
    """Coleta descrição e características da etapa."""
    descricao = coletar_descricao(driver, timeout)
    caracteristicas = coletar_caracteristicas_trabalho(driver, timeout)

    if not descricao:
        print("[INFO] Descrição: (não encontrada ou vazia)")
    if not caracteristicas:
        print("[INFO] Características do trabalho: (não encontradas ou vazias)")

    return descricao, caracteristicas


def executar_plano_completo(driver, args, numero_etapa: str,
                            descricao: str, caracteristicas: str):
    """Gera e executa o plano completo de trabalho a quente."""
    plano = gerar_plano_trabalho_quente(descricao, caracteristicas)

    imprimir_relatorio_plano(
        numero_etapa,
        args.data,
        coletar_tipo_trabalho(driver, args.timeout)[1],  # Apenas texto
        descricao,
        caracteristicas,
        plano,
    )

    # Preencher todos os questionários
    preencher_questionarios(driver, args, plano, descricao, caracteristicas)


def preencher_questionarios(driver, args, plano: dict,
                            descricao: str, caracteristicas: str):
    """Gerencia o preenchimento de todos os questionários."""
    formularios = [
        ("Questionário PT", lambda: preencher_questionario_pt(driver, args.timeout, plano["qpt"])),
        ("EPI adicional", lambda: preencher_epi_adicional(driver, args.timeout, plano["epi_radios"])),
        ("Análise Ambiental", lambda: preencher_analise_ambiental(driver, args.timeout)),
        ("APN-1", lambda: preencher_apn1(driver, args.timeout, descricao, caracteristicas)),
        ("EPI", lambda: processar_aba_epi(driver, args.timeout, plano["epis_cat"])),
    ]

    for nome_form, executar in formularios:
        try:
            executar()
        except Exception as e:
            print(f"[ERROR] Erro no preenchimento de {nome_form}: {e}")


def confirmar_etapa(driver, timeout: float):
    """Confirma a etapa no rodapé."""
    try:
        print("[INFO] Efetuando confirmação geral da etapa no rodapé...")
        clicar_botao_confirmar_rodape(driver, timeout)
    except Exception as e:
        print(f"[WARN] Falha na confirmação geral da etapa: {e}")


# -------------------------------------------------------------------
# Argumentos de linha de comando - versão otimizada
# -------------------------------------------------------------------
def parse_args():
    """Configura e parseia argumentos de linha de comando."""
    parser = argparse.ArgumentParser(
        description=(
            "aplatquente.py – Trabalho a Quente "
            "(gera plano + preenche Questionário PT, EPI adicional, Análise Ambiental, APN-1 e EPI)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    # Grupo: Configurações de URL e dados
    parser.add_argument(
        "--url",
        default=DEFAULT_APLAT_URL,
        help="URL do APLAT (padrão: programação diária da P-18)"
    )
    parser.add_argument(
        "--data",
        required=True,
        help="Data no formato dd/mm/aaaa para filtro da etapa"
    )
    parser.add_argument(
        "--valor",
        nargs="+",
        required=True,
        help="Um ou mais números da etapa (ex: '2/1015/2024')"
    )

    # Grupo: Configurações de login
    parser.add_argument(
        "--use-keyring",
        action="store_true",
        help="Usar keyring para senha"
    )
    parser.add_argument(
        "--user",
        help="Usuário para login (obrigatório se usar keyring)"
    )
    parser.add_argument(
        "--keyring-service",
        default="aplat.petrobras",
        help="Nome do serviço no keyring (default: aplat.petrobras)"
    )

    # Grupo: Configurações de tempo
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help="Timeout padrão de waits explícitos"
    )
    parser.add_argument(
        "--search-timeout",
        type=float,
        default=DEFAULT_SEARCH_TIMEOUT,
        help="Timeout máximo para aguardar resultado da pesquisa (em segundos)"
    )
    parser.add_argument(
        "--detail-wait",
        type=float,
        default=DEFAULT_DETAIL_WAIT,
        help="Pausa após abrir a etapa"
    )
    parser.add_argument(
        "--post-wait",
        type=float,
        default=DEFAULT_POST_WAIT,
        help="Pausa final antes de encerrar"
    )

    # Grupo: Logs e debug
    parser.add_argument(
        "--log",
        help="Se informado, salva todo o output deste script em um arquivo TXT."
    )
    parser.add_argument(
        "--debug-locators",
        action="store_true",
        help="Ativa logs detalhados de XPaths / localizadores usados no Selenium."
    )

    return parser.parse_args()


@contextmanager
def gerenciar_log(args):
    """Context manager para gerenciar arquivo de log."""
    original_stdout = sys.stdout
    log_file = None

    if args.log:
        try:
            log_file = open(args.log, "w", encoding="utf-8")
            sys.stdout = Tee(original_stdout, log_file)
            print(f"[INFO] Log TXT ativado. Arquivo: {args.log}")
            yield
        except Exception as e:
            print(f"[WARN] Não foi possível abrir o arquivo de log '{args.log}': {e}")
            sys.stdout = original_stdout
            yield
        finally:
            if log_file:
                try:
                    sys.stdout = original_stdout
                    log_file.close()
                except Exception:
                    pass
    else:
        yield


# -------------------------------------------------------------------
# Função principal otimizada
# -------------------------------------------------------------------
@timeit_decorator("script_completo")
def main():
    """Função principal do script."""
    args = parse_args()

    with gerenciar_log(args):
        print("[INFO] Iniciando aplatquente.py (plano + preenchimento QPT / EPI adicional / AA / APN-1 / EPI).")
        if args.debug_locators:
            print("[INFO] DEBUG_LOCATORS ativado: serão registrados detalhes de XPaths / localizadores.")

        driver = create_edge_driver()

        try:
            # Login e preparação
            if not attempt_auto_login(driver, args, args.timeout, args.url):
                print("[ERROR] Abortando por falha de login.")
                return

            wait_for_document_ready(driver, args.timeout)

            # Processar cada etapa
            total_etapas = len(args.valor)
            for idx, numero_etapa in enumerate(args.valor, 1):
                processar_etapa(driver, args, numero_etapa, idx, total_etapas)

            print("[INFO] Processo concluído (plano + preenchimento QPT / EPI adicional / AA / APN-1 / EPI).")
            time.sleep(args.post_wait)

        finally:
            try:
                input("Pressione ENTER para encerrar e fechar o navegador...")
            except EOFError:
                pass
            finally:
                driver.quit()


if __name__ == "__main__":
    main()