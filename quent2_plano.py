#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
quent2_plano.py

Geração do plano de trabalho a quente (contexto, QPT, EPI adicional, APN-1, EPI).
"""

import re
import unicodedata
import time
from typing import Dict, Any, Tuple, List

from selenium.webdriver.common.by import By


# -------------------------------------------------------------------
# Decorator para medição de tempo
# -------------------------------------------------------------------
def timeit_decorator(func_name=None):
    def decorator(func):
        def wrapper(*args, **kwargs):
            start = time.time()
            result = func(*args, **kwargs)
            elapsed = time.time() - start
            name = func_name or func.__name__
            print(f"[TIMER] {name}: {elapsed:.3f}s")
            return result

        return wrapper

    return decorator


# -------------------------------------------------------------------
# Normalização de texto
# -------------------------------------------------------------------
def normalizar_texto(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.upper()
    s = re.sub(r"\s+", " ", s).strip()
    return s


# -------------------------------------------------------------------
# Coleta de descrição e características da etapa
# -------------------------------------------------------------------
@timeit_decorator()
def coletar_descricao(driver, timeout: float) -> str:
    from quent1_infra import safe_find_element

    candidatos = [
        "//app-dados-da-etapa//textarea[contains(@formcontrolname,'descricao')]",
        "//textarea[contains(@formcontrolname,'descricao')]",
        "//textarea[@id='descricao']",
    ]
    for xp in candidatos:
        try:
            el = safe_find_element(driver, xp, timeout)
            if el:
                texto = (el.get_attribute("value") or el.text or "").strip()
                if texto:
                    print(f"[DEBUG] Descrição obtida usando XPath: {xp}")
                    return texto
        except Exception:
            continue
    print("[WARN] Não foi possível localizar a Descrição da Etapa pelos XPaths padrão.")
    return ""


@timeit_decorator()
def coletar_caracteristicas_trabalho(driver, timeout: float) -> str:
    """Coleta as características do trabalho da etapa."""
    from quent1_infra import safe_find_element

    caracteristicas_lista: List[str] = []

    # Método 1: spans com classe 'nomecaracteristica'
    try:
        elementos = driver.find_elements(
            By.XPATH, "//app-input-caracteristicas//span[@class='nomecaracteristica']"
        )
        for elem in elementos:
            texto = elem.text.strip()
            if texto and texto not in caracteristicas_lista:
                caracteristicas_lista.append(texto)

        if caracteristicas_lista:
            resultado = ", ".join(caracteristicas_lista)
            print(f"[DEBUG] Características encontradas (Método 1): {resultado}")
            return resultado
    except Exception as e:
        print(f"[DEBUG] Falha no método 1: {e}")

    # Método 2: fieldset "Características do trabalho"
    try:
        fieldset = safe_find_element(
            driver,
            "//fieldset[contains(.//legend, 'Características do trabalho')]",
            timeout,
        )
        if fieldset:
            texto = fieldset.text
            linhas = texto.split("\n")
            for linha in linhas:
                linha = linha.strip()
                if not linha or "Características do trabalho" in linha:
                    continue
                if linha and linha not in caracteristicas_lista:
                    caracteristicas_lista.append(linha)

            if caracteristicas_lista:
                resultado = ", ".join(caracteristicas_lista)
                print(f"[DEBUG] Características encontradas (Método 2): {resultado}")
                return resultado
    except Exception as e:
        print(f"[DEBUG] Falha no método 2: {e}")

    # Método 3: regex no texto completo (fallback)
    try:
        bloco = safe_find_element(driver, "//app-dados-da-etapa", timeout)
        if bloco:
            texto_completo = bloco.text.strip()
            padrao = (
                r"Características do trabalho\s*-\s*(.*?)(?=\n\s*\n|\n[A-ZÀ-Ú][a-zà-ú]|$)"
            )
            match = re.search(padrao, texto_completo, re.DOTALL | re.IGNORECASE)
            if match:
                caracteristicas = match.group(1).strip()
                caracteristicas = re.sub(
                    r"[\u25b6\u25c0\u25b2\u25bc]", "", caracteristicas
                ).strip()
                linhas = [
                    linha.strip()
                    for linha in caracteristicas.split("\n")
                    if linha.strip()
                ]
                resultado = ", ".join(linhas)
                print(
                    f"[DEBUG] Características extraídas via regex: '{resultado}'"
                )
                return resultado
    except Exception as e:
        print(f"[WARN] Não foi possível localizar 'Características do trabalho': {e}")

    return ""


# -------------------------------------------------------------------
# Montagem de contexto a partir dos textos
# -------------------------------------------------------------------
def montar_contexto_from_textos(
    descricao: str, caracteristicas: str
) -> Dict[str, Any]:
    desc = normalizar_texto(descricao or "")
    carac = normalizar_texto(caracteristicas or "")
    texto = f"{desc} {carac}".strip()

    ctx: Dict[str, Any] = {}
    ctx["texto_full"] = texto

    # **CORREÇÃO: Melhorar detecção de ESPAÇO CONFINADO**
    ctx["tem_espaco_confinado"] = any(
        frase in texto
        for frase in (
            "ESPACO CONFINADO",
            "INTERIOR DE ESPACO",
            "ESPACO CONFINADO -",
            "DENTRO DE",
            "INTERIOR DO",
        )
    ) or "ESPACO CONFINADO" in texto

    # **CORREÇÃO: Melhorar detecção de ALTURA**
    ctx["tem_altura"] = any(
        frase in texto
        for frase in (
            "ALTURA",
            "ACESSO POR CORDAS",
            "CORDAS",
            "NR-35",
            "TRABALHO EM ALTURA",
        )
    ) or "ALTURA" in texto

    # Restante das flags mantidas
    ctx["tem_acesso_cordas"] = "ACESSO POR CORDAS" in texto
    ctx["tem_sobre_o_mar"] = "SOBRE O MAR" in texto
    ctx["tem_chama"] = any(
        ch in texto for ch in ("CHAMA ABERTA", "ESMERILHADEIRA", "OXICORTE", "SOLDA")
    )
    ctx["tem_oxicorte"] = "OXICORTE" in texto
    ctx["tem_solda"] = bool(re.search(r"\bSOLDA\b", texto))
    ctx["tem_co2"] = any(
        frase in texto
        for frase in (
            "AMBIENTES PROTEGIDOS POR CO2",
            "PROTEGIDO POR SISTEMA DE CO2",
            "PROTEGIDOS POR CO2",
            "PROTEGIDO POR CO2",
        )
    )
    ctx["tem_trat_mec"] = "TRATAMENTO MECANICO" in texto
    ctx["tem_agulheiro"] = "AGULHEIRO" in texto
    ctx["tem_lix_pneum"] = "LIXADEIRA PNEUMATIC" in texto
    ctx["tem_lixadeira"] = "LIXADEIRA" in texto
    ctx["tem_pneumatico"] = "PNEUMATIC" in texto
    ctx["tem_eletrico"] = "ELETRIC" in texto
    ctx["tem_corte"] = bool(re.search(r"\bCORTE\b", texto))
    ctx["tem_serra_sabre"] = "SERRA SABRE" in texto
    ctx["tem_pressurizado"] = "PRESSURIZADO" in texto
    ctx["tem_hidrojato"] = ("HIDROJATO" in texto) or ("HIDROJATEAMENTO" in texto)
    ctx["tem_partes_moveis"] = "PARTES MOVEIS" in texto

    return ctx


# -------------------------------------------------------------------
# Bases de EPI adicional (radios), EPIs por categoria e QPT
# -------------------------------------------------------------------
EPI_Q001_CINTO = ("Q001", "Cinto de Segurança")
EPI_Q002_VENT = ("Q002", "Ventilação Forçada")
EPI_Q003_COLETE = ("Q003", "Colete Salva-vidas")
EPI_Q004_ILUM = ("Q004", "Iluminação p/ uso em área classificada (tipo Ex)")
EPI_Q005_DPA = ("Q005", "Dupla Proteção Auricular")
EPI_Q006_PROT_FACIAL = ("Q006", "Protetor Facial")

EPI_RADIOS_BASE: Dict[Tuple[str, str], str] = {
    EPI_Q001_CINTO: "Não",
    EPI_Q002_VENT: "Não",
    EPI_Q003_COLETE: "Não",
    EPI_Q004_ILUM: "Não",
    EPI_Q005_DPA: "Sim",
    EPI_Q006_PROT_FACIAL: "Sim",
}

EPIS_CAT_BASE: Dict[str, set] = {
    "Luvas": {
        "LUVA DE PROTEÇÃO CONTRA IMPACTOS MODELO II (3, 4, 3, 3, 'C', 'P')",
    },
    "Proteção Respiratória": {
        "NÃO APLICÁVEL",
    },
    "Vestimentas": {
        "DUPLA PROTEÇÃO AUDITIVA",
        "EPI´s OBRIGATÓRIOS (CAPACETE, BOTA, PROT. AURIC. E UNIFORME)",
    },
    "Óculos": {
        "ÓCULOS AMPLA VISÃO",
        "PROTETOR FACIAL",
    },
}

QPT_Q001_MUDANCA = (
    "Q001",
    "O trabalho a ser realizado é caracterizado como uma mudança?",
)
QPT_Q001_PERMANENCIA = (
    "Q001",
    "Permanência do Operador no Local de Trabalho?",
)

QPT_Q002_ACOMP = (
    "Q002",
    "Acompanhamento Periódico? (Em caso de Acompanhamento Periódico, efetuar verificações de ____em___horas)",
)
QPT_Q002_MANOBRAS = (
    "Q002",
    "As manobras, bloqueios e isolamentos foram executados conforme o plano de isolamento?",
)

QPT_Q003_DRENADO = (
    "Q003",
    "O equipamento foi drenado e/ou lavado e/ou limpo e/ou ventilado ?",
)

QPT_Q004_SINALIZADO = (
    "Q004",
    "O equipamento está corretamente sinalizado com etiquetas de advertência ?",
)

QPT_Q005_INSPECOES = (
    "Q005",
    "Foram realizadas inspeções prévias nos equipamentos elétricos (luminárias, quadros, painéis, conexões, cabos, etc) e os cabos elétricos estão supensos?",
)

QPT_Q006_COMB_INC = (
    "Q006",
    "Caso os sistemas e equipamentos de combate a incêndio do local onde será executado o trabalho não estejam em condições normais de operação, foram definidas salvaguardas?",
)

QPT_Q007_MANG_AR = (
    "Q007",
    "As mangueiras de ar comprimido possuem engates rápidos compatíveis e os mesmos estão travados",
)

QPT_Q008_LOCAL_ISOLADO = (
    "Q008",
    "O local foi isolado, sinalizado e o pessoal desnecessário  afastado ?",
)

QPT_Q009_FAGULHAS = (
    "Q009",
    "Foi providenciada a contenção de fagulhas com mantas e materiais adequados?",
)

QPT_Q010_ACOPLADO = (
    "Q010",
    "Caso o equipamento esteja acoplado a equipamento elétrico (ex: motor elétrico),  foram tomadas precauções quanto à energização acidental do equipamento ?",
)

QPT_Q011_TAMPONAMENTOS = (
    "Q011",
    "Foi providenciado Tamponamentos de drenos, ralos, vents e outras aberturas próximas ao local do trabalho?",
)

QPT_Q012_RISCO_PP = (
    "Q012",
    "A execução deste trabalho pode causar Risco de Perda de Produção?",
)

QPT_Q013_INIBIR_SENSORES = (
    "Q013",
    "Caso necessário inibir sensores do sistema de detecção de fogo e gás, foram definidas salvaguardas para suprir a inibição?",
)

QPT_Q014_OBSERVADOR = (
    "Q014",
    "O observador foi instruído quanto a utilização dos equipamentos de combate a incêndio?",
)

QPT_BASE: Dict[Tuple[str, str], str] = {
    QPT_Q001_MUDANCA: "Não",
    QPT_Q001_PERMANENCIA: "Não",
    QPT_Q002_ACOMP: "Sim",
    QPT_Q002_MANOBRAS: "NA",
    QPT_Q003_DRENADO: "NA",
    QPT_Q004_SINALIZADO: "NA",
    QPT_Q005_INSPECOES: "NA",
    QPT_Q006_COMB_INC: "NA",
    QPT_Q007_MANG_AR: "NA",
    QPT_Q008_LOCAL_ISOLADO: "Sim",
    QPT_Q009_FAGULHAS: "NA",
    QPT_Q010_ACOPLADO: "NA",
    QPT_Q011_TAMPONAMENTOS: "NA",
    QPT_Q012_RISCO_PP: "Não",
    QPT_Q013_INIBIR_SENSORES: "NA",
    QPT_Q014_OBSERVADOR: "NA",
}


# -------------------------------------------------------------------
# Montagem das bases específicas
# -------------------------------------------------------------------
def montar_base_epi_radios(ctx: Dict[str, Any]) -> Dict[Tuple[str, str], str]:
    base = dict(EPI_RADIOS_BASE)

    if ctx.get("tem_altura") or ctx.get("tem_acesso_cordas") or ctx.get("tem_sobre_o_mar"):
        base[EPI_Q001_CINTO] = "Sim"

    if ctx.get("tem_sobre_o_mar"):
        base[EPI_Q003_COLETE] = "Sim"

    hazard_olhos = (
        ctx.get("tem_chama")
        or ctx.get("tem_trat_mec")
        or ctx.get("tem_agulheiro")
        or ctx.get("tem_lix_pneum")
        or ctx.get("tem_lixadeira")
        or ctx.get("tem_corte")
        or ctx.get("tem_serra_sabre")
    )
    base[EPI_Q006_PROT_FACIAL] = "Sim" if hazard_olhos else "Não"

    return base


def montar_base_epis_cat(ctx: Dict[str, Any]) -> Dict[str, set]:
    base: Dict[str, set] = {cat: set(itens) for cat, itens in EPIS_CAT_BASE.items()}

    hazard_olhos = (
        ctx.get("tem_chama")
        or ctx.get("tem_trat_mec")
        or ctx.get("tem_agulheiro")
        or ctx.get("tem_lix_pneum")
        or ctx.get("tem_lixadeira")
        or ctx.get("tem_corte")
        or ctx.get("tem_serra_sabre")
    )

    if not hazard_olhos:
        base["Óculos"] = {"ÓCULOS SEGURANÇA CONTRA IMPACTO"}

    if ctx.get("tem_chama"):
        base.setdefault("Luvas", set()).update(
            {
                "LUVA ARAMIDA",
                "LUVA DE RASPA",
            }
        )
        base.setdefault("Vestimentas", set()).update(
            {
                "BALACLAVA",
                "AVENTAL DE RASPA",
                "CAPUZ",
                "MANGA DE RASPA",
                "PERNEIRA DE RASPA",
                "VESTIM. COMPLETA DE RASPA",
            }
        )
        base["Proteção Respiratória"] = {"PEÇA SEMI-FACIAL FILTRANTE 2"}
        base.setdefault("Óculos", set()).add("MÁSCARA SOLDADOR")

    if ctx.get("tem_solda") or ctx.get("tem_oxicorte"):
        base.setdefault("Óculos", set()).add(
            "LENTE DE ACORDO COM AMPERAGEM DA MÁQUINA"
        )
    if ctx.get("tem_oxicorte"):
        base.setdefault("Óculos", set()).add("ÓCULOS MAÇARIQUEIRO")

    if ctx.get("tem_trat_mec") or ctx.get("tem_agulheiro") or ctx.get("tem_lix_pneum"):
        base["Proteção Respiratória"] = {"PEÇA SEMI-FACIAL FILTRANTE 2"}
        base.setdefault("Luvas", set()).add("LUVA ANTI-VIBRAÇÃO")

    if ctx.get("tem_altura") or ctx.get("tem_acesso_cordas"):
        base.setdefault("Vestimentas", set()).update(
            {
                "BOTA CANO ALTO",
                "CAPACETE S/ABAS C/ CARNEIRA E PRESILHA DE QUEIXO EM Y",
                "CINTO DE SEG. TP PARA-QUEDISTA",
                "CINTO DE SEGURANÇA PARA RESGATE",
                "DUPLO TALABARTE EM Y OU LINHA DE VIDA CONJUGADA TRAVA QUEDA",
                "MACACÃO COM GOLA TIPO PADRE E BOLSOS FECHADOS",
            }
        )

    if ctx.get("tem_sobre_o_mar"):
        base.setdefault("Vestimentas", set()).update(
            {
                "BOTA CANO ALTO",
                "CAPACETE S/ABAS C/ CARNEIRA E PRESILHA DE QUEIXO EM Y",
                "CINTO DE SEG. TP PARA-QUEDISTA",
                "CINTO DE SEGURANÇA PARA RESGATE",
                "COLETE SALVA VIDAS RF (apenas para trabalhos a quente)",
                "COLETE SALVA-VIDAS",
                "DUPLO TALABARTE EM Y OU LINHA DE VIDA CONJUGADA TRAVA QUEDA",
                "MACACÃO COM GOLA TIPO PADRE E BOLSOS FECHADOS",
            }
        )

    return base


def montar_base_qpt(ctx: Dict[str, Any]) -> Dict[Tuple[str, str], str]:
    base = dict(QPT_BASE)

    if ctx.get("tem_chama") or ctx.get("tem_eletrico"):
        base[QPT_Q005_INSPECOES] = "Sim"
    else:
        base[QPT_Q005_INSPECOES] = "NA"

    if (
        ctx.get("tem_pneumatico")
        or ctx.get("tem_trat_mec")
        or ctx.get("tem_agulheiro")
        or ctx.get("tem_lix_pneum")
    ):
        base[QPT_Q007_MANG_AR] = "Sim"
    else:
        base[QPT_Q007_MANG_AR] = "NA"

    if ctx.get("tem_chama"):
        base[QPT_Q009_FAGULHAS] = "Sim"
    else:
        base[QPT_Q009_FAGULHAS] = "NA"

    if ctx.get("tem_chama"):
        base[QPT_Q011_TAMPONAMENTOS] = "Sim"
    else:
        base[QPT_Q011_TAMPONAMENTOS] = "NA"

    if ctx.get("tem_co2") and ctx.get("tem_chama"):
        base[QPT_Q013_INIBIR_SENSORES] = "Sim"
    else:
        base[QPT_Q013_INIBIR_SENSORES] = "NA"

    if ctx.get("tem_chama"):
        base[QPT_Q014_OBSERVADOR] = "Sim"
    else:
        base[QPT_Q014_OBSERVADOR] = "NA"

    return base


def montar_base_apn1(ctx: Dict[str, Any]) -> Dict[str, str]:
    """
    Base APN-1 corrigida para considerar ESPAÇO CONFINADO e ALTURA.
    """
    base = {f"Q{num:03d}": "Não" for num in range(1, 21)}

    # **CORREÇÃO: Espaço confinado → Q006**
    if ctx.get("tem_espaco_confinado"):
        base["Q006"] = "Sim"

    # **CORREÇÃO: Altura ou acesso por cordas → Q007**
    if ctx.get("tem_altura") or ctx.get("tem_acesso_cordas"):
        base["Q007"] = "Sim"

    # Sobre o mar → Q008
    if ctx.get("tem_sobre_o_mar"):
        base["Q008"] = "Sim"

    # Chama aberta → Q010
    if ctx.get("tem_chama"):
        base["Q010"] = "Sim"

    # CO2 → Q019
    if ctx.get("tem_co2"):
        base["Q019"] = "Sim"

    # Pressurizado → Q013
    if ctx.get("tem_pressurizado"):
        base["Q013"] = "Sim"

    # Hidrojato → Q016
    if ctx.get("tem_hidrojato"):
        base["Q016"] = "Sim"

    # Partes móveis → Q017
    if ctx.get("tem_partes_moveis"):
        base["Q017"] = "Sim"

    return base


# -------------------------------------------------------------------
# Geração do plano e relatório
# -------------------------------------------------------------------
def gerar_plano_trabalho_quente(
    descricao: str, caracteristicas: str
) -> Dict[str, Any]:
    ctx = montar_contexto_from_textos(descricao, caracteristicas)

    base_epi_radios = montar_base_epi_radios(ctx)
    base_epis_cat = montar_base_epis_cat(ctx)
    base_qpt = montar_base_qpt(ctx)
    base_apn1 = montar_base_apn1(ctx)

    plano = {
        "contexto": ctx,
        "epi_radios": base_epi_radios,
        "epis_cat": base_epis_cat,
        "qpt": base_qpt,
        "apn1": base_apn1,
        "analise_ambiental": "Todas as questões devem ser respondidas com 'Não' (regra fixa).",
    }
    return plano


def imprimir_relatorio_plano(
    numero_etapa: str,
    data_str: str,
    tipo_trabalho_txt: str,
    descricao: str,
    caracteristicas: str,
    plano: Dict[str, Any],
):
    print("\n" + "-" * 80)
    print(
        f"[PLANO] Etapa {numero_etapa} | Data: {data_str} | Tipo de Trabalho: {tipo_trabalho_txt}"
    )
    print("-" * 80)

    print(f"[INFO] Descrição (len={len(descricao)}):")
    print(f"       {descricao}")
    print(f"[INFO] Características do trabalho / Observações:")
    print(f"       {caracteristicas}")

    ctx = plano["contexto"]
    flags_true = [k for k, v in ctx.items() if k.startswith("tem_") and v]
    print("\n[CONTEXTOS DETECTADOS]")
    if flags_true:
        for f in sorted(flags_true):
            print(f"  - {f} = True")
    else:
        print("  (nenhum gatilho específico detectado)")

    print("\n[EPI (RÁDIOS PRINCIPAIS) – PLANO ESPERADO]")
    epi_radios = plano["epi_radios"]
    for (codigo, texto), resp in sorted(epi_radios.items(), key=lambda x: x[0]):
        print(f"  {codigo}: resp='{resp}' | {texto}")

    print("\n[EPIs VINCULADOS POR CATEGORIA – PLANO ESPERADO]")
    epis_cat: Dict[str, set] = plano["epis_cat"]
    for cat in sorted(epis_cat.keys()):
        itens = sorted(epis_cat[cat])
        print(f"  Categoria: {cat}")
        if itens:
            for item in itens:
                print(f"    - {item}")
        else:
            print("    (nenhum EPI esperado para esta categoria)")

    print("\n[QUESTIONÁRIO PT – PLANO ESPERADO]")
    qpt = plano["qpt"]
    for (codigo, texto), resp in sorted(qpt.items(), key=lambda x: x[0]):
        print(f"  {codigo}: resp='{resp}' | {texto}")

    print("\n[APN-1 – PLANO ESPERADO]")
    apn1 = plano["apn1"]
    sims = {k: v for k, v in apn1.items() if v == "Sim"}
    if sims:
        print("  Questões com resposta 'Sim':")
        for codigo in sorted(sims.keys()):
            print(f"    {codigo}: 'Sim'")
    else:
        print("  (nenhuma questão com 'Sim'; todas permanecem 'Não')")

    print("  Questões com resposta 'Não':")
    for codigo in sorted(apn1.keys()):
        if apn1[codigo] == "Não":
            print(f"    {codigo}: 'Não'")

    print("\n[ANÁLISE AMBIENTAL – PLANO ESPERADO]")
    print("  Todas as questões devem ser respondidas com 'Não' (regra fixa para Trabalho a Quente).")
    print("-" * 80 + "\n")
