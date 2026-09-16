# -*- coding: utf-8 -*-
"""
Motor de Análisis Fundamental Sectorial — MVP
===============================================

Herramienta de referencia (NO de recomendación de inversión) que interpreta
ratios de análisis fundamental en función de:

    Sector -> Subsector -> Modelo de negocio -> Estilo de inversión -> Ratios disponibles

Devuelve, para cada ratio ingresado:
    dato -> benchmark -> interpretación -> advertencias -> ratios complementarios
    -> información faltante -> contexto de comparación

y, en conjunto, relaciones entre ratios e inconsistencias.

Arquitectura pensada para ser extensible: toda la "base de datos" de
sectores/subsectores/benchmarks vive en estructuras de datos simples
(diccionarios) al inicio del archivo, separadas de la lógica del motor de
reglas y de la interfaz Streamlit. Para escalar el proyecto, estas
estructuras pueden migrarse a un archivo JSON/YAML externo o a una base de
datos sin tocar la lógica del motor.

Ejecutar con:  streamlit run app.py
"""

from __future__ import annotations
import streamlit as st
from dataclasses import dataclass, field
from typing import Optional


# =========================================================================
# 1. BASE DE DATOS: SECTORES, SUBSECTORES Y CLASIFICACIÓN DE RATIOS
# =========================================================================
# Fuente de las clasificaciones: Manual de Referencia (Producto 1) del
# proyecto. Etiquetas: "mercado" = convención observable (Damodaran NYU
# Stern / práctica sell-side); "inferencia" = síntesis metodológica propia
# a validar. Ver manual para el detalle de cada fuente.

SECTOR_MATRIX = {
    "Financials": {
        "Banks": {
            "principales": ["P/B", "ROE", "Dividend Yield"],
            "secundarios": ["P/E"],
            "cautela": ["EV/EBITDA"],
            "no_recomendados": ["EV/Sales", "P/S"],
            "fuente": "mercado",
            "nota": "El negocio bancario transforma pasivos en activos "
                    "financieros: EV/EBITDA carece de sentido porque la "
                    "'deuda' es el negocio mismo, no una fuente de "
                    "financiamiento externa. Faltan en este MVP ratios "
                    "regulatorios específicos (NIM, CET1, ROTCE, efficiency "
                    "ratio) que deberían priorizarse por sobre P/E.",
        },
        "Insurance": {
            "principales": ["P/B", "ROE"],
            "secundarios": ["P/E", "Dividend Yield"],
            "cautela": ["EV/EBITDA"],
            "no_recomendados": ["P/S"],
            "fuente": "inferencia",
            "nota": "Reservas técnicas y resultado financiero distorsionan "
                    "EBITDA/EBIT. Falta en este MVP el combined ratio.",
        },
    },
    "Technology": {
        "Software / SaaS": {
            "principales": ["EV/Sales", "EV/EBITDA"],
            "secundarios": ["P/E", "PEG"],
            "cautela": ["P/B"],
            "no_recomendados": [],
            "fuente": "mercado",
            "nota": "P/E solo es informativo si la empresa ya es rentable; "
                    "en fase de expansión de ingresos, EV/Sales es el ancla "
                    "principal.",
        },
        "Semiconductors": {
            "principales": ["P/E", "EV/EBITDA", "ROIC"],
            "secundarios": ["P/S", "PEG"],
            "cautela": ["P/B"],
            "no_recomendados": [],
            "fuente": "inferencia",
            "nota": "Sector muy cíclico (capex, inventarios); considerar "
                    "earnings normalizados a mitad de ciclo.",
        },
    },
    "Utilities": {
        "Utilities reguladas": {
            "principales": ["P/E", "EV/EBITDA", "Dividend Yield"],
            "secundarios": ["Debt/EBITDA"],
            "cautela": ["P/S"],
            "no_recomendados": [],
            "fuente": "mercado",
            "nota": "El retorno está regulado por el marco tarifario, no "
                    "por competencia de mercado libre. Deuda/EBITDA "
                    "elevada puede ser normal dada la estabilidad de flujos.",
        },
    },
    "Energy": {
        "Integrated Oil & Gas / E&P": {
            "principales": ["EV/EBITDA", "Debt/EBITDA"],
            "secundarios": [],
            "cautela": ["P/E", "P/B"],
            "no_recomendados": [],
            "fuente": "mercado",
            "nota": "Ciclicidad de precios de commodities: usar EBITDA "
                    "normalizado a mitad de ciclo, no el dato puntual. Un "
                    "P/E muy bajo en pico de precios puede ser engañoso.",
        },
    },
    "Real Estate": {
        "REITs": {
            "principales": ["Dividend Yield"],
            "secundarios": ["Debt/EBITDA"],
            "cautela": [],
            "no_recomendados": ["P/E", "EV/EBITDA"],
            "fuente": "inferencia",
            "nota": "La depreciación contable de inmuebles no refleja la "
                    "realidad económica. Falta en este MVP Price/FFO y "
                    "Price/AFFO, que deberían ser los ratios principales.",
        },
    },
    "Industrials": {
        "Industrials (general)": {
            "principales": ["EV/EBITDA", "ROIC", "Debt/EBITDA"],
            "secundarios": ["P/E"],
            "cautela": ["P/S"],
            "no_recomendados": [],
            "fuente": "mercado",
            "nota": "Capex estructuralmente alto: si está disponible, "
                    "preferir EV/EBIT sobre EV/EBITDA.",
        },
    },
    "Consumer": {
        "Consumer Staples": {
            "principales": ["P/E", "Dividend Yield"],
            "secundarios": ["EV/EBITDA"],
            "cautela": ["P/B"],
            "no_recomendados": [],
            "fuente": "inferencia",
            "nota": "Márgenes y flujos estables; comparar contra historia "
                    "propia es especialmente informativo en este subsector.",
        },
        "Consumer Discretionary / Retail": {
            "principales": ["P/E", "P/S"],
            "secundarios": ["EV/EBITDA"],
            "cautela": ["P/B"],
            "no_recomendados": [],
            "fuente": "inferencia",
            "nota": "Sensible al ciclo de consumo; cruzar con rotación de "
                    "inventario si está disponible.",
        },
    },
    "Healthcare": {
        "Biotech pre-comercial": {
            "principales": ["P/S"],
            "secundarios": [],
            "cautela": [],
            "no_recomendados": ["P/E", "ROE", "ROIC", "EV/EBITDA"],
            "fuente": "inferencia",
            "nota": "Sin ingresos recurrentes ni EBITDA: los ratios de "
                    "rentabilidad no tienen sentido económico. Priorizar "
                    "cash runway y valor de pipeline (fuera del alcance de "
                    "este MVP).",
        },
    },
    "Communication Services": {
        "Telecom": {
            "principales": ["EV/EBITDA", "Dividend Yield", "Debt/EBITDA"],
            "secundarios": ["P/E"],
            "cautela": ["P/S"],
            "no_recomendados": [],
            "fuente": "inferencia",
            "nota": "Negocio intensivo en capital con flujos relativamente "
                    "estables; tolera apalancamiento moderado-alto.",
        },
    },
}


# =========================================================================
# 2. BENCHMARKS DE RATIOS: ESCALA DE 6 NIVELES
# =========================================================================
# "sentido": higher_better | lower_better | context (no hay dirección
# universal deseable sin contexto adicional, p. ej. Dividend Yield).
# "rangos_default": límites superiores de cada nivel (el último nivel no
# tiene límite superior). Estos son benchmarks GENERALES DE MERCADO
# (🏛️ mercado / 🧭 inferencia según el ratio, ver Manual Producto 1).
# "overrides": ajustes por subsector cuando el rango general no aplica.

NIVELES = [
    "Extremadamente bajo",
    "Bajo",
    "Moderado",
    "Normal",
    "Elevado",
    "Extremadamente elevado",
]

RATIO_BENCHMARKS = {
    "P/E": {
        "sentido": "lower_better",
        "unidad": "x",
        "fuente": "mercado",
        "rangos_default": [6, 10, 15, 20, 30],  # 6 tramos
    },
    "PEG": {
        "sentido": "lower_better",
        "unidad": "x",
        "fuente": "mercado",
        "rangos_default": [0.5, 1.0, 1.5, 2.0, 3.0],
    },
    "P/B": {
        "sentido": "lower_better",
        "unidad": "x",
        "fuente": "mercado",
        "rangos_default": [0.7, 1.0, 1.5, 3.0, 5.0],
        "overrides": {
            "Banks": [0.5, 0.8, 1.1, 1.6, 2.2],
        },
    },
    "P/S": {
        "sentido": "lower_better",
        "unidad": "x",
        "fuente": "inferencia",
        "rangos_default": [0.5, 1.0, 2.0, 4.0, 8.0],
    },
    "EV/Sales": {
        "sentido": "lower_better",
        "unidad": "x",
        "fuente": "inferencia",
        "rangos_default": [1.0, 2.0, 4.0, 8.0, 15.0],
    },
    "EV/EBITDA": {
        "sentido": "lower_better",
        "unidad": "x",
        "fuente": "mercado",
        "rangos_default": [4, 6, 9, 13, 20],
        "overrides": {
            "Integrated Oil & Gas / E&P": [3, 4.5, 6, 8, 11],
            "Software / SaaS": [8, 12, 18, 25, 35],
        },
    },
    "Dividend Yield": {
        "sentido": "context",
        "unidad": "%",
        "fuente": "mercado",
        "rangos_default": [1, 2, 3, 4, 6],
    },
    "ROE": {
        "sentido": "higher_better",
        "unidad": "%",
        "fuente": "mercado",
        "rangos_default": [5, 10, 15, 20, 25],
    },
    "ROIC": {
        "sentido": "higher_better",
        "unidad": "%",
        "fuente": "mercado",
        "rangos_default": [4, 8, 12, 18, 25],
    },
    "FCF Yield": {
        "sentido": "higher_better",
        "unidad": "%",
        "fuente": "mercado",
        "rangos_default": [1, 2, 5, 8, 12],
    },
    "Debt/EBITDA": {
        "sentido": "lower_better",
        "unidad": "x",
        "fuente": "mercado",
        "rangos_default": [1.0, 1.5, 2.5, 4.0, 5.5],
        "overrides": {
            "Utilities reguladas": [2.0, 3.0, 4.5, 6.0, 7.5],
            "Telecom": [1.5, 2.5, 3.5, 5.0, 6.5],
        },
    },
    "Interest Coverage": {
        "sentido": "higher_better",
        "unidad": "x",
        "fuente": "mercado",
        "rangos_default": [1, 2, 4, 6, 10],
    },
    "Current Ratio": {
        "sentido": "context",
        "unidad": "x",
        "fuente": "mercado",
        "rangos_default": [0.7, 1.0, 1.5, 2.0, 3.0],
    },
    "Revenue Growth": {
        "sentido": "higher_better",
        "unidad": "%",
        "fuente": "inferencia",
        "rangos_default": [0, 5, 10, 20, 35],
    },
}

# Ratios complementarios sugeridos por ratio (para la sección "faltantes")
COMPLEMENTARIOS = {
    "P/E": ["Revenue Growth", "ROIC", "PEG"],
    "P/B": ["ROE"],
    "EV/EBITDA": ["Revenue Growth", "Debt/EBITDA"],
    "EV/Sales": ["FCF Yield", "Revenue Growth"],
    "Dividend Yield": ["Current Ratio", "FCF Yield"],  # proxy de payout/FCF
    "Debt/EBITDA": ["Interest Coverage"],
    "ROE": ["Debt/EBITDA"],  # para saber si es apalancamiento
    "FCF Yield": ["Revenue Growth"],
}

ESTILOS = ["Value", "Growth", "Quality", "Cyclical", "Defensive", "Otro / no definido"]


# =========================================================================
# 3. MOTOR DE REGLAS
# =========================================================================

@dataclass
class InterpretacionRatio:
    ratio: str
    valor: float
    nivel: str
    importancia: str          # principal | secundario | cautela | no_recomendado | no_clasificado
    benchmark_usado: list
    fuente_benchmark: str
    interpretacion: str
    advertencias: list = field(default_factory=list)
    complementarios_faltantes: list = field(default_factory=list)
    es_extremo: bool = False


def clasificar_importancia(sector: str, subsector: str, ratio: str) -> tuple[str, str, str]:
    """Devuelve (importancia, fuente_clasificacion, nota_subsector)."""
    info = SECTOR_MATRIX.get(sector, {}).get(subsector)
    if not info:
        return "no_clasificado", "inferencia", (
            "Subsector no incluido todavía en la base de datos del MVP: "
            "se aplican benchmarks generales sin ajuste sectorial."
        )
    if ratio in info["principales"]:
        return "principal", info["fuente"], info["nota"]
    if ratio in info["secundarios"]:
        return "secundario", info["fuente"], info["nota"]
    if ratio in info["cautela"]:
        return "cautela", info["fuente"], info["nota"]
    if ratio in info["no_recomendados"]:
        return "no_recomendado", info["fuente"], info["nota"]
    return "no_clasificado", info["fuente"], info["nota"]


def detectar_extremo(ratio: str, valor: float) -> Optional[str]:
    """Chequeos de datos extremos / no representativos (Sección 20 del brief)."""
    if ratio in ("P/E", "EV/EBITDA", "EV/Sales", "P/B", "P/S") and valor < 0:
        return (
            f"{ratio} negativo: el denominador (utilidad/EBITDA/valor libro) "
            f"es negativo. Este ratio NO es económicamente representativo "
            f"en este caso — no debe interpretarse con la escala estándar. "
            f"Métrica alternativa sugerida: EV/Sales o P/S si el ratio "
            f"afectado es de utilidad; earnings normalizados si es cíclico."
        )
    if ratio == "P/E" and valor > 100:
        return (
            "P/E extremadamente alto (>100x): frecuentemente señal de "
            "utilidad contable cercana a cero (denominador casi nulo) más "
            "que de una valuación genuinamente extrema. Verificar la "
            "calidad y magnitud de la utilidad antes de interpretar."
        )
    if ratio == "Debt/EBITDA" and valor > 8:
        return (
            "Deuda/EBITDA extremadamente alta (>8x): revisar si el EBITDA "
            "está deprimido por un evento puntual (denominador anormalmente "
            "bajo) antes de concluir riesgo de solvencia estructural."
        )
    return None


def nivel_por_rango(valor: float, cortes: list) -> str:
    for i, corte in enumerate(cortes):
        if valor < corte:
            return NIVELES[i]
    return NIVELES[-1]


def obtener_benchmark(ratio: str, subsector: str) -> tuple[list, str]:
    meta = RATIO_BENCHMARKS[ratio]
    overrides = meta.get("overrides", {})
    if subsector in overrides:
        return overrides[subsector], "mercado (ajustado por subsector)"
    return meta["rangos_default"], meta["fuente"]


def interpretar_ratio(sector: str, subsector: str, estilo: str,
                       ratio: str, valor: float) -> InterpretacionRatio:
    importancia, fuente_clasif, nota = clasificar_importancia(sector, subsector, ratio)

    extremo_msg = detectar_extremo(ratio, valor)
    advertencias = []

    if ratio not in RATIO_BENCHMARKS:
        return InterpretacionRatio(
            ratio=ratio, valor=valor, nivel="N/D", importancia=importancia,
            benchmark_usado=[], fuente_benchmark="n/a",
            interpretacion="Ratio no incluido todavía en la base de "
                            "benchmarks del MVP.",
            advertencias=["Agregar este ratio requiere investigación y "
                           "validación de rango antes de operacionalizarlo."],
        )

    cortes, fuente_bench = obtener_benchmark(ratio, subsector)

    if extremo_msg:
        nivel = "No representativo"
        advertencias.append(extremo_msg)
    else:
        nivel = nivel_por_rango(valor, cortes)

    # Interpretación base según sentido del ratio
    meta = RATIO_BENCHMARKS[ratio]
    if nivel != "No representativo":
        if meta["sentido"] == "lower_better":
            if nivel in ("Extremadamente bajo", "Bajo"):
                interp = (f"{ratio} relativamente bajo frente al benchmark "
                           f"considerado — puede reflejar infravaloración "
                           f"relativa, pero también riesgo o deterioro no "
                           f"capturado por el número. Requiere contraste "
                           f"con calidad de negocio y tendencia.")
            elif nivel in ("Elevado", "Extremadamente elevado"):
                interp = (f"{ratio} relativamente elevado frente al "
                           f"benchmark considerado — puede estar "
                           f"justificado por crecimiento, calidad o "
                           f"rentabilidad superiores; no implica "
                           f"sobrevaluación por sí solo.")
            else:
                interp = f"{ratio} dentro del rango considerado 'normal' para el benchmark utilizado."
        elif meta["sentido"] == "higher_better":
            if nivel in ("Extremadamente bajo", "Bajo"):
                interp = (f"{ratio} relativamente bajo — señal potencial de "
                           f"menor calidad/rentabilidad relativa; verificar "
                           f"causa (estructural vs. cíclica/puntual).")
            elif nivel in ("Elevado", "Extremadamente elevado"):
                interp = (f"{ratio} relativamente elevado — señal potencial "
                           f"de calidad/rentabilidad superior; verificar "
                           f"sostenibilidad (apalancamiento, one-offs).")
            else:
                interp = f"{ratio} dentro del rango considerado 'normal'."
        else:  # context
            interp = (f"{ratio} = {valor}{meta['unidad']}. Este ratio no "
                       f"tiene una dirección universalmente deseable — su "
                       f"lectura depende del estilo de inversión y del "
                       f"contexto de payout/sostenibilidad.")
    else:
        interp = "Ver advertencia: ratio no representativo en este caso."

    # Ajustes por importancia sectorial
    if importancia == "no_recomendado":
        advertencias.append(
            f"Este ratio está clasificado como NO RECOMENDADO para "
            f"{subsector}: {nota}"
        )
    elif importancia == "cautela":
        advertencias.append(
            f"Este ratio debe usarse con cautela en {subsector}: {nota}"
        )
    elif importancia == "no_clasificado":
        advertencias.append(nota)

    # Ajustes por estilo (Sección 5/6 del Manual)
    ajuste_estilo = _ajuste_por_estilo(ratio, nivel, estilo)
    if ajuste_estilo:
        advertencias.append(ajuste_estilo)

    complementarios = COMPLEMENTARIOS.get(ratio, [])

    return InterpretacionRatio(
        ratio=ratio, valor=valor, nivel=nivel, importancia=importancia,
        benchmark_usado=cortes, fuente_benchmark=fuente_bench,
        interpretacion=interp, advertencias=advertencias,
        complementarios_faltantes=complementarios,
        es_extremo=bool(extremo_msg),
    )


def _ajuste_por_estilo(ratio: str, nivel: str, estilo: str) -> Optional[str]:
    if estilo == "Growth" and ratio in ("P/E", "EV/Sales", "EV/EBITDA") and nivel in (
        "Elevado", "Extremadamente elevado"
    ):
        return (
            "Estilo Growth declarado: un múltiplo elevado en esta familia "
            "no debe leerse automáticamente como sobrevaloración. Cruzar "
            "con crecimiento de ingresos, ROIC y duración esperada del "
            "crecimiento antes de concluir."
        )
    if estilo == "Value" and ratio in ("P/E", "P/B", "EV/EBITDA") and nivel in (
        "Extremadamente bajo", "Bajo"
    ):
        return (
            "Estilo Value declarado: distinguir infravaloración genuina de "
            "'value trap'. Verificar ROIC, tendencia de márgenes y deuda "
            "antes de interpretar el múltiplo bajo como oportunidad."
        )
    if estilo == "Cyclical" and ratio in ("P/E", "EV/EBITDA"):
        return (
            "Estilo Cyclical declarado: este ratio puede estar distorsionado "
            "por la posición actual del ciclo de utilidades/EBITDA. "
            "Preferir, si está disponible, la versión normalizada a mitad "
            "de ciclo en lugar del dato puntual."
        )
    if estilo == "Quality" and ratio == "ROIC" and nivel in ("Bajo", "Extremadamente bajo"):
        return (
            "Estilo Quality declarado: un ROIC bajo es una señal de alerta "
            "central para este estilo — la tesis de calidad depende "
            "fuertemente de un ROIC alto y estable."
        )
    return None


# ---- Relaciones entre ratios (Sección 10 del Manual) ------------------

def analizar_relaciones(valores: dict) -> list:
    """Devuelve una lista de mensajes de consistencia/inconsistencia entre
    pares o tríos de ratios, cuando los datos necesarios están presentes."""
    msgs = []

    pe = valores.get("P/E")
    growth = valores.get("Revenue Growth")
    roic = valores.get("ROIC")
    if pe is not None and growth is not None and roic is not None:
        if pe > 25 and growth > 15 and roic > 12:
            msgs.append(
                "P/E elevado + crecimiento elevado + ROIC elevado: "
                "combinación internamente consistente con creación de "
                "valor sostenida — el múltiplo tiene sustento fundamental, "
                "sujeto a que el crecimiento se sostenga."
            )
        elif pe > 25 and growth < 8 and roic < 8:
            msgs.append(
                "⚠️ P/E elevado + crecimiento bajo + ROIC bajo: "
                "combinación de alerta — el múltiplo no encuentra "
                "sustento claro en el crecimiento ni en la rentabilidad "
                "sobre el capital invertido."
            )

    pb = valores.get("P/B")
    roe = valores.get("ROE")
    if pb is not None and roe is not None:
        if pb > 3 and roe < 10:
            msgs.append(
                "⚠️ P/B elevado + ROE bajo: inconsistente con la identidad "
                "P/B ≈ ROE × P/E — el mercado está pagando un múltiplo "
                "sobre valor libro no respaldado por la rentabilidad sobre "
                "patrimonio actual."
            )
        elif pb > 3 and roe > 18:
            msgs.append(
                "P/B elevado + ROE elevado: consistente — el mercado paga "
                "una prima sobre el valor libro justificada por la alta "
                "rentabilidad sobre patrimonio."
            )

    debt_ebitda = valores.get("Debt/EBITDA")
    interest_cov = valores.get("Interest Coverage")
    if debt_ebitda is not None and interest_cov is not None:
        if debt_ebitda > 3.5 and interest_cov < 3:
            msgs.append(
                "⚠️ Deuda/EBITDA elevada + cobertura de intereses baja: "
                "combinación de riesgo financiero a vigilar — el "
                "apalancamiento no está acompañado de un colchón cómodo "
                "frente a los gastos financieros."
            )

    div_yield = valores.get("Dividend Yield")
    fcf_yield = valores.get("FCF Yield")
    if div_yield is not None and fcf_yield is not None:
        if div_yield > 5 and fcf_yield < 2:
            msgs.append(
                "⚠️ Dividend yield alto + FCF yield bajo: el dividendo "
                "podría no estar totalmente respaldado por generación de "
                "caja propia — riesgo de sostenibilidad del pago si la "
                "brecha persiste."
            )

    return msgs


# =========================================================================
# 4. INTERFAZ STREAMLIT
# =========================================================================

st.set_page_config(page_title="Motor de Análisis Fundamental Sectorial", layout="wide")

st.title("📊 Motor de Análisis Fundamental Sectorial — MVP")
st.caption(
    "Herramienta de referencia y guía metodológica. **No emite "
    "recomendaciones de compra/venta.** Los benchmarks marcados como "
    "'inferencia' deben validarse con fuentes primarias antes de uso "
    "profesional. Ver el Manual de Referencia (Producto 1) del proyecto "
    "para el detalle teórico completo."
)

with st.sidebar:
    st.header("1. Clasificación de la empresa")
    sector = st.selectbox("Sector", list(SECTOR_MATRIX.keys()))
    subsector = st.selectbox("Subsector", list(SECTOR_MATRIX[sector].keys()))
    modelo_negocio = st.text_input("Modelo de negocio (texto libre, opcional)",
                                     placeholder="p. ej. SaaS, integrado, marketplace…")
    estilo = st.selectbox("Estilo de inversión declarado", ESTILOS)

    st.header("2. Ratios disponibles")
    st.caption("Dejá en blanco (o en 0 sin tildar) los que no tengas.")

    valores_input = {}
    for ratio in RATIO_BENCHMARKS.keys():
        col1, col2 = st.columns([3, 1])
        with col2:
            incluir = st.checkbox("Usar", key=f"chk_{ratio}", value=False)
        with col1:
            val = st.number_input(
                f"{ratio} ({RATIO_BENCHMARKS[ratio]['unidad']})",
                key=f"val_{ratio}", value=0.0, step=0.1, format="%.2f",
                disabled=not incluir,
            )
        if incluir:
            valores_input[ratio] = val

    analizar_btn = st.button("Analizar", type="primary")

if analizar_btn:
    if not valores_input:
        st.warning("Ingresá al menos un ratio para analizar.")
    else:
        info_subsector = SECTOR_MATRIX.get(sector, {}).get(subsector, {})

        st.subheader(f"Contexto: {sector} → {subsector} → Estilo: {estilo}")
        if modelo_negocio:
            st.caption(f"Modelo de negocio declarado: {modelo_negocio}")
        if info_subsector:
            st.info(f"**Nota sectorial**: {info_subsector.get('nota', '')}")

        st.markdown("---")
        st.subheader("1️⃣ Interpretación individual de cada ratio")

        resultados = {}
        for ratio, valor in valores_input.items():
            res = interpretar_ratio(sector, subsector, estilo, ratio, valor)
            resultados[ratio] = res

            badge = {
                "principal": "🟢 PRINCIPAL para este subsector",
                "secundario": "🟡 SECUNDARIO para este subsector",
                "cautela": "🟠 USAR CON CAUTELA en este subsector",
                "no_recomendado": "🔴 NO RECOMENDADO en este subsector",
                "no_clasificado": "⚪ Sin clasificación sectorial específica",
            }.get(res.importancia, "")

            with st.expander(f"**{ratio} = {valor}{RATIO_BENCHMARKS.get(ratio, {}).get('unidad', '')}**  |  Nivel: {res.nivel}  |  {badge}"):
                st.write(f"**Dato ingresado:** {valor}{RATIO_BENCHMARKS.get(ratio, {}).get('unidad', '')}")
                if res.benchmark_usado:
                    st.write(f"**Benchmark utilizado** (fuente: {res.fuente_benchmark}): "
                             f"cortes de nivel = {res.benchmark_usado} "
                             f"(niveles: {', '.join(NIVELES)})")
                st.write(f"**Interpretación:** {res.interpretacion}")
                if res.advertencias:
                    st.write("**Advertencias:**")
                    for a in res.advertencias:
                        st.markdown(f"- {a}")
                faltantes = [c for c in res.complementarios_faltantes if c not in valores_input]
                if faltantes:
                    st.write(f"**Para interpretar mejor este ratio, sería útil conocer:** "
                             f"{', '.join(faltantes)}")

        st.markdown("---")
        st.subheader("2️⃣ Relaciones entre ratios / inconsistencias")
        relaciones = analizar_relaciones(valores_input)
        if relaciones:
            for r in relaciones:
                st.markdown(f"- {r}")
        else:
            st.caption("No hay suficientes ratios combinables cargados para "
                       "evaluar relaciones cruzadas, o no se detectaron "
                       "patrones destacables con los datos ingresados.")

        st.markdown("---")
        st.subheader("3️⃣ Información faltante relevante para este subsector")
        principales = set(info_subsector.get("principales", []))
        ingresados = set(valores_input.keys())
        faltan_principales = principales - ingresados
        if faltan_principales:
            st.warning(
                f"Para {subsector}, los siguientes ratios están clasificados "
                f"como PRINCIPALES y no fueron ingresados: "
                f"{', '.join(faltan_principales)}. Sin ellos, el "
                f"diagnóstico fundamental de este subsector queda incompleto."
            )
        else:
            st.success("Se ingresaron todos los ratios principales "
                       "clasificados para este subsector (dentro del "
                       "alcance de este MVP).")

        st.markdown("---")
        st.subheader("4️⃣ Qué debería compararse")
        st.markdown(f"""
- **Peer group**: empresas del mismo subsector (**{subsector}**), modelo de
  negocio comparable y tamaño similar — no alcanza con "mismo sector amplio".
- **Historia propia**: comparar cada ratio contra el promedio/mediana de
  **5-10 años de la propia empresa**, verificando si hubo cambios
  estructurales (crecimiento, tasas, márgenes, riesgo) antes de usar ese
  benchmark como ancla.
- **Mercado agregado**: contextualizar contra el nivel general de tasas de
  interés y el múltiplo agregado del mercado en el momento del análisis.
- **Benchmark sectorial**: los rangos utilizados en este informe (ver
  columna "benchmark utilizado" en cada ratio).
        """)

        st.markdown("---")
        st.subheader("5️⃣ Diagnóstico fundamental (descriptivo, no prescriptivo)")
        descriptores = []
        for ratio, res in resultados.items():
            if res.nivel in ("Extremadamente bajo", "Bajo"):
                sentido = RATIO_BENCHMARKS.get(ratio, {}).get("sentido")
                if sentido == "lower_better":
                    descriptores.append(f"múltiplo {ratio} relativamente bajo")
                elif sentido == "higher_better":
                    descriptores.append(f"{ratio} relativamente bajo (posible señal de menor calidad relativa)")
            elif res.nivel in ("Elevado", "Extremadamente elevado"):
                sentido = RATIO_BENCHMARKS.get(ratio, {}).get("sentido")
                if sentido == "lower_better":
                    descriptores.append(f"múltiplo {ratio} relativamente elevado")
                elif sentido == "higher_better":
                    descriptores.append(f"{ratio} relativamente elevado (posible señal de rentabilidad/calidad superior)")

        if descriptores:
            st.markdown("**Clasificación descriptiva del conjunto:** " + "; ".join(descriptores) + ".")
        st.caption(
            "Esta clasificación es descriptiva, no una recomendación de "
            "compra/venta. Cada afirmación debe leerse junto con las "
            "advertencias, relaciones e información faltante señaladas "
            "arriba antes de derivar cualquier conclusión analítica."
        )

else:
    st.info("Completá la clasificación sectorial y al menos un ratio en la "
            "barra lateral, y presioná **Analizar**.")

st.markdown("---")
st.caption(
    "MVP con fines metodológicos. Arquitectura extensible: la base de "
    "sectores/subsectores/benchmarks (diccionarios SECTOR_MATRIX y "
    "RATIO_BENCHMARKS al inicio de este archivo) puede ampliarse o "
    "migrarse a una fuente de datos externa sin modificar el motor de "
    "reglas."
)
