# -*- coding: utf-8 -*-
"""
================================================================================
PROCESAMIENTO AVANZADO DE IMÁGENES SENTINEL-2 PARA ANÁLISIS DE BOSQUE SECO
TROPICAL (Bs-T) — TOOLKIT MULTIMODAL
================================================================================

Autor:          Geog. Mauricio Sarmiento Pancho (msarmientop@unal.edu.co)
Institución:    Fundación Ecosistemas Secos de Colombia - FESC
Versión:        v1.0.0-validation
Fecha:          Abril 2026
Plataforma:     Google Colab + Google Earth Engine (Python API)
Licencia:       MIT License

Descripción:
    Script multimodal para el procesamiento de imágenes Sentinel-2 Level-2A
    (Surface Reflectance, Harmonized) como insumo de apoyo para la
    interpretación y análisis de cobertura vegetal en ecosistemas de Bosque
    Seco Tropical (Bs-T).

    Desarrollado para la Fundación Ecosistemas Secos de Colombia (FESC).
    El script es paramétrico y escalable a cualquier región ajustando el 
    parámetro AOI, pero incluye por defecto las geometrías del Predio 
    Santa Helena (Caribe colombiano) como caso de estudio demostrativo.

    Implementa tres flujos de análisis configurables:
      1. EXPORTAR_IMAGEN: Exportación de escena única (mejor cobertura) o
         mosaico Medoid libre de píxeles sintéticos.
      2. MOSAICO_ESTACIONAL: Composiciones bimodales (4 temporadas climáticas)
         con cálculo de 11 índices espectrales, textura GLCM y deltas
         fenológicos estacionales.
      3. CURVA_FENOLÓGICA: Series de tiempo de índices espectrales con
         suavizado Savitzky-Golay para análisis de dinámica vegetal.

    El enmascaramiento de nubes combina tres métodos de máxima precisión:
      - s2cloudless (probabilidad de nubes)
      - Banda SCL (Scene Classification Layer)
      - Proyección geométrica de sombras basada en ángulo zenital solar

Dependencias principales:
    earthengine-api, geemap, rasterio, geopandas, scipy, matplotlib, pandas,
    numpy, google-colab

Asistencia IA:
    La documentación técnica de este script fue generada con asistencia del
    modelo de IA Gemini (Google DeepMind). La responsabilidad técnica y
    científica de la lógica espacial, los parámetros y las decisiones
    metodológicas recae exclusivamente en el autor humano.

⚠️ ESTADO: VALIDACIÓN / EN DESARROLLO
    Este script se encuentra en fase de validación técnica y ajuste.
    No está liberado para uso en producción. Los resultados deben ser
    verificados de forma independiente antes de su uso en toma de decisiones.
    Versión: 1.0.0-validation
================================================================================
"""

# =================================================================================
# SCRIPT PARA PROCESAMIENTO AVANZADO DE IMÁGENES SENTINEL-2
# Para: Fundación Ecosistemas Secos de Colombia - FESC
# Proceso: Actualización Cobertura de la Tierra / Predio Santa Helena, San Juan
#          Nepomuceno, Bolívar. Fundación Proyecto Tití
# Versión optimizada para Google Earth Engine con Python en Colab
# Última actualización: Abril 2026
# =================================================================================

# ==============================================================================
# SECCIÓN 1: INSTALACIÓN DE LIBRERÍAS ESENCIALES
# ==============================================================================
# Descripción: Verifica la disponibilidad de todas las dependencias necesarias
# para el procesamiento. Si alguna librería no está instalada, se instala
# automáticamente mediante pip.

print("--> [SECCIÓN 1] Verificando e instalando librerías...")

# 1.1 Instalación de librerías
# Intenta importar todas las dependencias. Si alguna falla, ejecuta la
# instalación completa del stack de procesamiento geoespacial.
try:
    import ee
    import geemap
    import rasterio
    import os
    import geopandas as gpd
    import math # Necesario para math.pi
    import pandas as pd
    import numpy as np
    from scipy.signal import savgol_filter
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from google.colab import drive, auth, files
    print("✓ Librerías principales ya instaladas.")
except ImportError:
    print("-> Instalando librerías necesarias (ee, geemap, rasterio)...")
    !pip install earthengine-api==0.1.384 geemap==0.31.0 rasterio geopandas scipy --quiet
    !pip install localtileserver --quiet
    print("✓ Librerías instaladas. Puede que necesites reiniciar el entorno de ejecución.")

# Importaciones después de la instalación
# Se realiza una segunda ronda de importaciones para garantizar que todas
# las librerías estén disponibles tras la instalación condicional.
import ee
import geemap
import rasterio
import os
import geopandas as gpd
import math
import pandas as pd
import numpy as np
from scipy.signal import savgol_filter
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from google.colab import drive, auth
import logging

# Silenciar alertas informativas de autenticación que ensucian la consola
logging.getLogger("google_auth_httplib2").setLevel(logging.ERROR)

print("\n--- [SECCIÓN 1] Finalizada con éxito. ---")

# ==============================================================================
# SECCIÓN 2: AUTENTICACIÓN Y MONTAJE DE GOOGLE DRIVE
# ==============================================================================
# Descripción: Establece la conexión entre el entorno de Colab y Google Drive
# para permitir la lectura de insumos y la escritura de resultados.
# Se definen las rutas de exportación y la carpeta temporal de descarga.

print("--> [SECCIÓN 2] Conectando con Google Drive...")
try:
    # Montaje de Google Drive en el filesystem virtual de Colab.
    # force_remount=True asegura una conexión fresca en cada ejecución.
    # Este es el método estándar y recomendado.
    # Lanzará una ventana emergente para que autorices el acceso.
    drive.mount('/content/drive', force_remount=True)

    # TODO: Reemplazar con la ruta a tu carpeta de proyecto en Google Drive
    DRIVE_BASE_PATH = "/content/drive/MyDrive/FESC"  # <-- Ruta base del proyecto en Drive
    export_folder = os.path.join(DRIVE_BASE_PATH, "Fund_Titi")
    temp_download_folder = "temp_downloads_colab" # Descarga local para velocidad
    os.makedirs(export_folder, exist_ok=True)
    os.makedirs(temp_download_folder, exist_ok=True)
    print(f" -> Carpeta de exportación en Drive: {export_folder}")
    print(f" -> Carpeta de descarga temporal: {temp_download_folder}")
    print(f"✓ Google Drive montado con éxito.")
    print(f" -> Ruta de trabajo establecida en: {DRIVE_BASE_PATH}")

except Exception as e:
    print(f"✗ ERROR CRÍTICO: No se pudo montar Google Drive.")
    print(f"  Detalle del error: {e}")
    # Detiene la ejecución si Drive no se puede montar
    raise SystemExit("Ejecución detenida por fallo en montaje de Drive.")

print("\n--- [SECCIÓN 2] Finalizada con éxito. ---")

# ==============================================================================
# SECCIÓN 3: AUTENTICACIÓN E INICIALIZACIÓN DE GOOGLE EARTH ENGINE (GEE)
# ==============================================================================
# Descripción: Autentica al usuario con Google Cloud y inicializa la API de
# Google Earth Engine. Requiere un proyecto de GCP con la API de Earth Engine
# habilitada.

print("--> [SECCIÓN 3] Autenticando e inicializando Google Earth Engine...")
try:
    # Autentica al usuario para el acceso a GEE.
    # Es un paso que genera un token de credenciales. Puede que no lo pida cada vez.
    auth.authenticate_user()
    print("✓ Autenticación de usuario de Google para GEE completada.")

    # Inicializa la API usando las credenciales obtenidas.
    # TODO: Reemplazar con tu ID de proyecto de Google Cloud Platform
    PROJECT_ID = 'YOUR_GCP_PROJECT_ID'  # <-- ¡IMPORTANTE! CAMBIA ESTO. Nombre de tu proyecto en Google Cloud
                                # Este proyecto debe tener la API de Earth Engine habilitada.
    ee.Initialize(project=PROJECT_ID)
    print(f"✓ Earth Engine inicializado con éxito en el proyecto: '{PROJECT_ID}'.")

except Exception as e:
    print(f"✗ ERROR CRÍTICO: Fallo al inicializar Earth Engine.")
    print(f"  Detalle del error: {e}")
    print("  ACCIÓN RECOMENDADA: Verifica que el ID del proyecto ('{PROJECT_ID}') sea correcto y que la API de Earth Engine esté habilitada en Google Cloud.")
    raise SystemExit("Ejecución detenida por fallo en inicialización de GEE.")

print("\n--- [SECCIÓN 3] Finalizada con éxito. ---")

# ==============================================================================
# SECCIÓN 4: PARÁMETROS DE CONFIGURACIÓN - EDITABLES POR EL USUARIO
# ==============================================================================
# Descripción: Define todos los parámetros de entrada para el análisis
# y busqueda de la(s) imagen(es) de sensores remotos.
# Esta sección centraliza toda la configuración editable: fuentes de datos,
# filtros, modos de análisis, índices espectrales y proyección de salida.
print("\n--> [SECCIÓN 4] Cargando parámetros de configuración...")

# --- 4.1. Fuentes de datos ---
# Colección Sentinel-2 Surface Reflectance (Level-2A), armonizada para
# consistencia radiométrica entre las versiones de procesamiento de ESA.
S2_SR_COLLECTION = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
# Colección de probabilidad de nubes generada por el algoritmo s2cloudless.
S2_CLOUD_PROB_COLLECTION = ee.ImageCollection('COPERNICUS/S2_CLOUD_PROBABILITY')

# --- 4.2 Parámetros de Control Principal ---
# Elige qué tipo de análisis quieres realizar (Copiar y Pegar, según opción deseada).
# Opciones: 'EXPORTAR_IMAGEN', 'MOSAICO_ESTACIONAL', 'CURVA_FENOLÓGICA'
            # Si selecciona la opción MOSAICO ESTACIONAL o CURVA FENOLÓGICA, se recomienda
            # ampliar el rango de tiempo
ANALYSIS_MODE = 'EXPORTAR_IMAGEN'

# --- 4.3. Parámetros de filtrado general (formato YYYY-MM-DD) ---
FECHA_INICIO = '2025-01-01'  # Fecha inicial de búsqueda (formato YYYY-MM-DD)
FECHA_FIN = '2026-04-15'     # Fecha final de búsqueda (formato YYYY-MM-DD)
MAX_NUBES_METADATA = 60    # Porcentaje máximo de nubes permitido (0-100%)
                           # Reducido a 60 para evitar carga innecesaria en el Caribe

# --- 4.4 Parámetros para el Enmascaramiento de nubes avanzado ---
# Combinación: Banda SCL + dataset s2cloudless
CLD_PRB_THRESH = 30 # Umbral de probabilidad de nubes ((0-100%); valores mayores que, son considerados nubes
                    # Reducido a 30 para mejor detección de cirros
NIR_DARK_THRESHOLD = 0.15 # Umbral de Reflectancia en el Infrarojo Cercano, para identificar píxeles oscuros;
                          # valores menores que, son considerados posibles sombras de nubes
SCL_MASK_CLASSES = [3, 8, 9, 10] # 3: Sombras de nubes, Probabilidad de nubes: 8 Media, 9 Alta, 10 Cirrus

# --- 4.5 Parámetros de Área de Interés (AOI) ---
# Ajustar de acuerdo con el nombre del asset cargado en GEE
# Define si se usa un shapefile completo (ej. un predio, un ÁP, etc) o se filtra una base de datos (ej. Municipios, Deptos, etc)
USAR_FILTRO_ATRIBUTO = True  # True: Busca un registro específico (ej. un municipio en DIVIPOLA).
                             # False: Usa todo el shapefile cargado (ej. Predio_Santa_Helena).

# Ruta del Asset en GEE (Funciona para ambos casos). Ajustar de acuerdo con el nombre del asset cargado en GEE
# Caso 1 (Municipios): 'projects/YOUR_GCP_PROJECT_ID/assets/Municipios202204_wgs84'
# Caso 2 (Predio): 'projects/YOUR_GCP_PROJECT_ID/assets/Mi_Shapefile_Predio'
# TODO: Reemplazar con la ruta a tu asset en GEE
RUTA_ASSET_AOI = 'projects/YOUR_GCP_PROJECT_ID/assets/YOUR_ASSET_NAME'  # <-- Reemplazar con tu asset

# Parámetros de filtrado (SOLO SI USAR_FILTRO_ATRIBUTO = True)
COLUMNA_FILTRO = 'MpNombre'       # Nombre de la columna en la tabla de atributos
                                  # Ajustar de acuerdo con el nombre del campo a filtrar en el asset
VALOR_FILTRO = 'San Juan Nepomuceno' # Valor a buscar (Mayusculas Sensitivo)

ZONA_BUFFER_m = 2000 # Opcional: Buffer en metros. Ajustar según se requiera añadir un buffer alrededor del AOI


# --- 4.6 Parámetros para ANALYSIS_MODE: 'EXPORTAR_IMAGEN' ---
# (Copiar y Pegar según opción deseada)
MODO_OPERACION = 'MOSAICO'   # Opciones: 'MOSAICO', 'ESCENA_ÚNICA'. Cambiar según necesidad
ESCALA_EXPORTACION = 10  # Resolución espacial en metros para el archivo de salida

# SELECTOR DE SISTEMA DE COORDENADAS DE REFERENCIA (CRS) PARA EXPORTACIÓN
# Paso 1: Definición de las opciones de proyección disponibles.
    # GEE no reconoce el 'EPSG:9377', se usa la representación Well-Known Text (WKT) para el CRS
    # En caso de que se requiera otrs CRS que no este registrado en GEE, se puede editar esta sección de WKT
    # para incluir los datos correspondiente
WKT_EPSG_9377 = """
PROJCS["MAGNA-SIRGAS 2018 / Origen-Nacional",
    GEOGCS["MAGNA-SIRGAS 2018",
        DATUM["Marco Geocentrico Nacional de Referencia 2018",
            SPHEROID["GRS 1980",6378137,298.257222101,
                AUTHORITY["EPSG","7019"]],
            TOWGS84[0,0,0,0,0,0,0],
            AUTHORITY["EPSG","1164"]],
        PRIMEM["Greenwich",0,
            AUTHORITY["EPSG","8901"]],
        UNIT["degree",0.0174532925199433,
            AUTHORITY["EPSG","9122"]],
        AUTHORITY["EPSG","9376"]],
    PROJECTION["Transverse_Mercator"],
    PARAMETER["latitude_of_origin",4],
    PARAMETER["central_meridian",-73],
    PARAMETER["scale_factor",0.9992],
    PARAMETER["false_easting",5000000],
    PARAMETER["false_northing",2000000],
    UNIT["metre",1,
        AUTHORITY["EPSG","9001"]],
    AXIS["Easting",EAST],
    AXIS["Northing",NORTH],
    AUTHORITY["EPSG","9377"]]
"""
PROJECTION_OPTIONS = {
    'MAGNA SIRGAS ORIGEN NACIONAL': WKT_EPSG_9377,
    'WGS84': 'EPSG:4326',
    # Se pueden añadir más opciones aquí, según sea necesario
}

# Paso 2: Selecciona la proyección deseada escribiendo una de las claves del diccionario anterior.
PROJECTION_CHOICE = 'MAGNA SIRGAS ORIGEN NACIONAL'

# Paso 3: El script asigna automáticamente la proyección correcta para la exportación. No tocar.
CRS_EXPORTACION = PROJECTION_OPTIONS[PROJECTION_CHOICE]

# --- 4.7 Parámetros para ANALYSIS_MODE: 'MOSAICO_ESTACIONAL' ---
# Definir meses para cada estación, basada en el régimen de precipitaciones
# bimodal del Caribe colombiano.
MESES_LLUVIA_PPAL = [9, 10, 11] # Sep-Nov Máxima biomasa acumulada.
MESES_LLUVIA_SEC = [4, 5] # Abr-May Arranque vegetativo
MESES_SEQUIA_PPAL = [12, 1, 2, 3] # Dic-Mar Senescencia total (línea base)
MESES_SEQUIA_SEC = [6, 7, 8] # Jun-Ago Veranillo de San Juan. Estrés hídrico leve

# --- 4.8 Parámetros para ANALYSIS_MODE: 'CURVA_FENOLÓGICA' ---
# Se Puede usar un rango de fechas más amplio que el definido en la sección 4.3 para ver la variabilidad interanual.
    # Si se decide un rango más amplio, se debe ajustar la sección 4.3 a dicho rango para que pueda ejecutarse correctamente
    # la verificación de disponibilidad, incluida en la sección 7
FECHA_INICIO_FENOLOGIA = '2023-10-01'
FECHA_FIN_FENOLOGIA = '2025-11-30'

# --- 4.9 Configuración de Índices de Vegetación ---
# Define qué índices quieres calcular y exportar. Se pueden incluir todos aquellos que sean necesarios.
# Si se incluyen más índices, estos deben ser descritos (formula) en la Seccion 6.2 CÁLCULO DE ÍNDICES DE VEGETACIÓN
# NDVI: Estándar.
# EVI: Mejora en biomasa alta.
# SAVI: CRÍTICO para Bs-T en época seca Minimiza/Reduce la influencia/impacto del brillo del suelo en zonas con baja densidad de vegetación.
        # Cobertura vegetal baja-moderada.
# MSAVI2: SAVI modificado, Autoajustable, resuelve la subjetividad del SAVI en el Factor de Ajuste L;
          # minimiza aún más el efecto del suelo desnudo sin necesidad de configurar previamente el factor de ajuste
# OSAVI: SAVI optimizado, tiene en cuenta el valor estándar del factor de ajuste del fondo del dosel (0,16)
         # ofrece mayor sensibilidad a la cobertura vegetal cuando esta supera el 50%
# NDMI: Estrés hídrico / contenido de humedad, previo a la defoliación.
# NIRv: Estimación de Carbono, diferencia bosque maduro de secundario denso por estructura.
# NDRE: Detectar la calidad de la clorofila, entre dos parches con NDVI alto, > NDRE es probablemente el Bosque Maduro
        # (más capas de hojas, más clorofila acumulada) frente a un rastrojo joven.
# NBR: Normalized Burn Ratio, permite detectar disturbios asociados principalmente a quemas
# BCI: Bare Soil Index, crítico para identificar suelo desnudo expuesto en épocas de sequía máxima
# CIre: Chlorophyll Index Red Edge, superior al NDRE estándar para detección de estrés hídrico temprano.
INDICES_A_CALCULAR = ['NDVI', 'EVI', 'SAVI', 'MSAVI2', 'OSAVI', 'NDMI', 'NIRv', 'NDRE', 'NBR', 'BSI', 'CIre']

# --- 4.10 Análisis de Textura (GLCM) ---
# Vital para diferenciar coberturas CLC Colombia estructuralmente Lisas (ej.Pastos Limpios, cultivos, Suelo Desnudo)
  # de coberturas CLC Colombia estructuralmente Rugosas (Bosque, Vegetación Secundaria) en época de lluvias.
# WARNING: Aumenta significativamente el tiempo de procesamiento.
CALCULAR_TEXTURA = True  # True para calcular Entropía y Contraste, False para desactivar

# --- 4.11 Bandas de interés (para facilitar su uso posterior) ---
BANDAS_S2 = ['B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B8', 'B11','B12', 'SCL'] # Azul, Verde, Rojo, NIR, SWIR1, s2cloudless (se pueden agregar más, según necesidad)
NOMBRES_BANDAS = ['blue', 'green', 'red', 'rededge1', 'rededge2', 'rededge3', 'nir', 'swir1', 'swir2', 'SCL'] # Ajustar según bandas incluidas

# --- Resumen de parámetros en consola ---
print("\n--- RESUMEN DE PARÁMETROS ---")
print(f"  * MODO DE ANÁLISIS: {ANALYSIS_MODE}")
if ANALYSIS_MODE == 'EXPORTAR_IMAGEN':
    print(f"  * MODO DE OPERACIÓN: {MODO_OPERACION}")

if ZONA_BUFFER_m > 0:
    print(f"  * Buffer AOI: {ZONA_BUFFER_m} metros")
else:
    print("  * Buffer AOI: NO APLICADO (Geometría original)")

# Fechas según el modo
if ANALYSIS_MODE == 'CURVA_FENOLÓGICA':
    print(f"  * Rango de Fechas: {FECHA_INICIO_FENOLOGIA} a {FECHA_FIN_FENOLOGIA}")
else:
    print(f"  * Rango de Fechas: {FECHA_INICIO} a {FECHA_FIN}")

print(f"  * AOI Geográfico: {VALOR_FILTRO if USAR_FILTRO_ATRIBUTO else 'Asset completo'}")
print(f"  * Tolerancia Nubes (Metadato): {MAX_NUBES_METADATA}%")
print(f"  * Probabilidad Nube (S2_CLOUD_PROB): {CLD_PRB_THRESH}%")
print(f"  * Umbral de Sombra (NIR_DARK): {NIR_DARK_THRESHOLD}")

# Parámetros específicos para Estacional y Fenología
if ANALYSIS_MODE in ['MOSAICO_ESTACIONAL', 'CURVA_FENOLÓGICA']:
    print(f"  * Temporadas (Meses): Lluvia Ppal {MESES_LLUVIA_PPAL} | Lluvia Sec {MESES_LLUVIA_SEC} | Sequía Ppal {MESES_SEQUIA_PPAL} | Sequía Sec {MESES_SEQUIA_SEC}")
    print(f"  * Índices espectrales activos: {', '.join(INDICES_A_CALCULAR)}")
    if ANALYSIS_MODE == 'MOSAICO_ESTACIONAL':
        print(f"  * Calcular Textura GLCM: {'SÍ' if CALCULAR_TEXTURA else 'NO'}")

print(f"  * Escala de Exportación: {ESCALA_EXPORTACION} m/px")
print(f"  * Proyección de salida: {PROJECTION_CHOICE}")
print("-------------------------------------------------------")

print("✓ Parámetros cargados.")
print("\n--- [SECCIÓN 4] Finalizada con éxito. ---")

# ==============================================================================
# SECCIÓN 5: PREPARACIÓN DEL ÁREA DE INTERÉS (AOI) - VERSIÓN HÍBRIDA
# ==============================================================================
# Descripción: Carga el AOI desde un Asset completo o filtrando una colección,
             # valida su existencia, aplica buffer y visualiza.
# Soporta dos modos de operación:
#   - Filtrado por atributo: Selecciona un polígono específico (ej. municipio)
#   - Asset completo: Usa la geometría disuelta de todo el shapefile

print("\n--> [SECCIÓN 5] Preparando el Área de Interés (AOI)...")

try:
    # 1. Cargar la colección base desde el Asset
    # ee.FeatureCollection() carga el asset vectorial almacenado en GEE
    print(f" -> Cargando Asset desde: {RUTA_ASSET_AOI}")
    coleccion_base = ee.FeatureCollection(RUTA_ASSET_AOI)

    # Variable para el nombre de visualización
    nombre_capa_aoi = "AOI Definido"

    # 2. Lógica de Selección de Geometría
    if USAR_FILTRO_ATRIBUTO:
        print(f" -> MODO ACTIVO: Filtrado por atributo ('{COLUMNA_FILTRO}' = '{VALOR_FILTRO}')")

        # Filtrar la colección por el atributo especificado
        aoi_feature = coleccion_base.filter(ee.Filter.eq(COLUMNA_FILTRO, VALOR_FILTRO))

        # Validación de existencia — detiene el script si no se encuentra el registro
        count = aoi_feature.size().getInfo()
        if count == 0:
            print(f"❌ ERROR CRÍTICO: No se encontró ningún registro donde '{COLUMNA_FILTRO}' sea '{VALOR_FILTRO}'.")
            print("   ACCIÓN RECOMENDADA: Verifica la ortografía, mayúsculas/minúsculas o el nombre de la columna.")
            raise ValueError(f'El registro "{VALOR_FILTRO}" no fue encontrado en el asset.')

        # Obtener la geometría base del filtro
        aoi_base = aoi_feature.geometry()
        nombre_capa_aoi = f"AOI: {VALOR_FILTRO}"
        print(f" -> Registro encontrado. Usando geometría del filtro.")

    else:
        print(" -> MODO ACTIVO: Uso directo del Asset completo (Sin filtrado)")

        # Validación de que el asset no esté vacío
        count = coleccion_base.size().getInfo()
        if count == 0:
            print("❌ ERROR CRÍTICO: El Asset cargado está vacío (0 geometrías).")
            raise ValueError('El Asset especificado no contiene geometrías.')

        # Obtener la geometría base (Unión de todas las geometrías del shapefile)
        # .geometry() en una FeatureCollection realiza la unión disuelta de los polígonos
        aoi_base = coleccion_base.geometry()

        # Intentar obtener un nombre representativo si existe, sino usar genérico
        try:
            # Intenta tomar el nombre del primer feature si es un shapefile simple
            test_feat = ee.Feature(coleccion_base.first())
            props = test_feat.propertyNames().getInfo()
            if 'Nombre' in props: # Ajustar según tus shapefiles comunes
                nombre_capa_aoi = f"AOI: {test_feat.get('Nombre').getInfo()}"
            else:
                nombre_capa_aoi = "AOI: Shapefile Completo"
        except:
            nombre_capa_aoi = "AOI: Shapefile Completo"

        print(f" -> Asset validado ({count} elementos). Geometría unificada cargada.")

    # 3. Aplicar Buffer
    # El buffer amplía la geometría del AOI para incluir contexto espacial
    # circundante. El parámetro maxError=1 optimiza el cálculo en geometrías complejas.
    if ZONA_BUFFER_m > 0:
        print(f" -> Aplicando un buffer de {ZONA_BUFFER_m} metros al AOI...")
        # Nota técnica: El error máximo de 1 metro se define para optimizar el cálculo en geometrías complejas
        aoi = aoi_base.buffer(distance=ZONA_BUFFER_m, maxError=1)
    else:
        print(" -> No se especificó buffer. Usando la geometría original.")
        aoi = aoi_base

    print("✓ Geometría del AOI definida exitosamente.")

    # 4. Visualización interactiva
    # Genera un mapa de geemap centrado en el AOI con estilo de contorno
    # amarillo y relleno transparente para permitir ver capas debajo.
    try:
        Map = geemap.Map()
        # Centrar el mapa en el AOI (con zoom dinámico)
        Map.centerObject(aoi, 11)

        # Añadir la capa.
        # Usamos style para contorno amarillo y relleno transparente, ideal para ver imágenes debajo
        vis_aoi = {'color': 'yellow', 'fillColor': '00000000', 'width': 2}
        Map.addLayer(aoi, vis_aoi, nombre_capa_aoi)

        print(" -> Mapa interactivo generado abajo:")
        display(Map)
    except Exception as e:
        print(f"⚠️ Advertencia de visualización: {e}")
        print("   El procesamiento continúa, pero no se pudo renderizar el mapa interactivo.")
        pass
    print(f"✓ {nombre_capa_aoi} listo para el procesamiento.")

except Exception as e:
    print("\n🛑 PROCESO DETENIDO EN SECCIÓN 5")
    print(f"   Detalle del error: {e}")
    raise e

print("\n--- [SECCIÓN 5] Finalizada con éxito. ---")

# ==============================================================================
# SECCIÓN 6: FUNCIONES DE PROCESAMIENTO AVANZADAS
# ==============================================================================
# Descripción: Define las funciones para el enmascaramiento combinado de máxima
# precisión con Bandas S2 s2cloudless y SCL, las funciones para el análisis
# estacional (calculo de índices de vegetación, Deltas Estacionales, y
# análisis de textura).

print("\n--> [SECCIÓN 6] Definiendo funciones de procesamiento avanzado...")

# --- 6.1. Función de enmascaramiento de nubes (Método s2cloudless + SCL) ---

def _apply_scl_mask(image):
    """Aplica máscara booleana basada en la banda SCL de Sentinel-2.

    Reclasifica los píxeles de la banda Scene Classification Layer (SCL)
    en dos categorías: válidos (0) e inválidos (1), según las clases
    definidas en SCL_MASK_CLASSES (sombras de nubes, nubes medias/altas
    y cirros).

    Args:
        image (ee.Image): Imagen Sentinel-2 con banda 'SCL' disponible.

    Returns:
        ee.Image: Imagen binaria (0=válido, 1=inválido) resultado del
            remapeo de las clases SCL seleccionadas.
    """
    scl = image.select('SCL')
    # Crea una máscara booleana. El píxel es malo (1) si pertenece a alguna de las clases.
    return scl.remap(SCL_MASK_CLASSES, ee.List.repeat(1, len(SCL_MASK_CLASSES)), 0)

def _project_shadows(image, cloud_mask):
    """Proyecta sombras de nubes dinámicamente usando el ángulo zenital solar.

    Calcula geométricamente la distancia y dirección de proyección de sombras
    a partir del ángulo zenital y azimutal solar de los metadatos de la imagen,
    junto con una altura estimada de la base de nubes convectivas para el
    Caribe colombiano (2000 m).

    La máscara de sombras resultante se intersecta con píxeles oscuros en
    la banda NIR (B8) para evitar falsos positivos en cuerpos de agua.

    Args:
        image (ee.Image): Imagen Sentinel-2 con metadatos solares
            ('MEAN_SOLAR_AZIMUTH_ANGLE', 'MEAN_SOLAR_ZENITH_ANGLE')
            y banda 'B8' (NIR).
        cloud_mask (ee.Image): Máscara binaria de nubes (1=nube, 0=libre)
            sobre la cual proyectar las sombras.

    Returns:
        ee.Image: Máscara binaria de sombras proyectadas (1=sombra, 0=libre).
    """
    # Obtener ángulo zenital solar de los metadatos de la imagen
    mean_solar_azimuth = ee.Number(image.get('MEAN_SOLAR_AZIMUTH_ANGLE'))
    mean_solar_zenith = ee.Number(image.get('MEAN_SOLAR_ZENITH_ANGLE'))

    # Convertir a radianes
    azimuth_rad = mean_solar_azimuth.multiply(math.pi / 180.0)
    zenith_rad = mean_solar_zenith.multiply(math.pi / 180.0)

    # Encontrar la distancia al origen de la sombra y los offsets X e Y en píxeles.
    # Altura estimada de la base de nubes convectivas en el Caribe colombiano
    # Cumulonimbus: base ~1500-2500m. Usamos 2000m como valor conservador.
    CLOUD_BASE_HEIGHT_M = 2000
    # Resolución espacial del sensor (10m para Sentinel-2 bandas ópticas)
    PIXEL_SCALE_M = 10

    # Distancia de proyección en metros: D = H * tan(zenith)
    shadow_distance_m = ee.Number(CLOUD_BASE_HEIGHT_M).multiply(zenith_rad.tan())
    # Convertir a píxeles
    shadow_distance_px = shadow_distance_m.divide(PIXEL_SCALE_M)

    # Calcular desplazamiento en X e Y (en píxeles)
    shadow_dx = azimuth_rad.cos().multiply(shadow_distance_px)
    shadow_dy = azimuth_rad.sin().multiply(shadow_distance_px)

    # Aplicar la transformación a la máscara de nubes para obtener la máscara de sombra proyectada.
    # Proyectar la máscara de nubes con el desplazamiento calculado
    cloud_mask_offset = cloud_mask.reproject(
        crs=image.select('B2').projection(), # Usar la proyección de una banda de la imagen
        scale=image.select('B2').projection().nominalScale() # Usar la escala nominal
    ).translate(shadow_dx, shadow_dy)

    # Obtener píxeles oscuros en la banda NIR (posibles sombras o agua).
    is_dark = image.select('B8').lt(NIR_DARK_THRESHOLD)

    # Combinar con la máscara de nubes desplazada para asegurar que solo las sombras reales sean enmascaradas.
    shadow_mask = cloud_mask_offset.And(is_dark) # Corregido: .And() en lugar de .Or() — solo sombra si está oscuro
    return shadow_mask

def mask_s2_clouds_maximum_precision(image):
    """Aplica enmascaramiento combinado de máxima precisión para nubes y sombras.

    Combina tres métodos complementarios de detección:
      1. s2cloudless: Probabilidad de nubes por machine learning (umbral CLD_PRB_THRESH).
      2. SCL (Scene Classification Layer): Clasificación categórica de la ESA.
      3. Proyección geométrica de sombras: Basada en ángulos solares y altura
         estimada de nubes.

    Un píxel es enmascarado si CUALQUIERA de los tres métodos lo detecta como
    inválido (lógica OR).

    Args:
        image (ee.Image): Imagen Sentinel-2 con propiedad 's2cloudless'
            (añadida por el Join previo), banda 'SCL' y metadatos solares.

    Returns:
        ee.Image: Imagen enmascarada con solo píxeles válidos, conservando
            la propiedad 'system:time_start' para trazabilidad temporal.
    """
    # 1. Obtener la probabilidad de nubes (propiedad añadida por el Join).
    cloud_prob = ee.Image(image.get('s2cloudless')).select('probability')

    # 2. Crear máscara a partir de s2cloudless.
    s2c_mask = cloud_prob.gt(CLD_PRB_THRESH)

    # 3. Crear máscara a partir de la banda SCL.
    scl_mask = _apply_scl_mask(image)

    # 4. Crear máscara de sombras proyectadas.
    shadow_mask = _project_shadows(image, s2c_mask)

    # 5. Combinar todas las máscaras. Un píxel es inválido si es detectado por CUALQUIER método.
    final_mask = s2c_mask.Or(scl_mask).Or(shadow_mask)

    # 6. Aplicar la máscara invertida (.Not()) y mantener las propiedades.
    return image.updateMask(final_mask.Not()).copyProperties(image, ["system:time_start"])

def preprocess_s2_image(image):
    """Preprocesa una imagen Sentinel-2: escalado radiométrico, selección y renombramiento de bandas.

    Aplica operaciones finales: escalado SOLO a bandas espectrales (dividir
    DN / 10000 para obtener reflectancia 0-1), selección y renombramiento
    de bandas de salida a nombres descriptivos.
    La banda SCL se mantiene en su dominio entero categórico (0-11) para
    preservar su uso como máscara.
    Adicionalmente, extrae el mes de la fecha de captura y lo almacena
    como propiedad 'month' para el análisis estacional.

    Args:
        image (ee.Image): Imagen Sentinel-2 enmascarada con bandas originales
            (B2-B12, SCL) y propiedad 'system:time_start'.

    Returns:
        ee.Image: Imagen con bandas renombradas a nombres descriptivos
            ('blue', 'green', 'red', 'rededge1-3', 'nir', 'swir1-2', 'SCL'),
            escalada a reflectancia (0-1) excepto SCL, con propiedad 'month'.
    """
    # 1. Seleccionar las bandas espectrales originales y renombrarlas a nombres descriptivos.
    # Bandas espectrales (deben escalarse: DN / 10000 → reflectancia 0-1)
    bandas_espectrales = ['B2', 'B3', 'B4', 'B5', 'B6', 'B7','B8', 'B11', 'B12' ]
    nombres_espectrales = ['blue', 'green', 'red', 'rededge1', 'rededge2', 'rededge3', 'nir', 'swir1', 'swir2']

    # 2. Asegurar que las bandas existen antes de seleccionar
    bands_present = image.bandNames()

    # 3. Seleccionar y renombrar bandas espectrales.
    img_espectral = image.select(bands_present).select(bandas_espectrales, nombres_espectrales)

    # 4. Escalar SOLO las bandas espectrales.
    img_escalada = img_espectral.divide(10000)

    # 5. Mantener SCL sin escalar (banda categórica entera 0-11)
    scl = image.select(bands_present).select('SCL')
    # Unir imagen escalada + SCL intacta
    img_final = img_escalada.addBands(scl)

    # 6. Copiar las propiedades (incluyendo 'system:time_start') desde la imagen original
    # a la imagen procesada *después* de la selección, renombrado y escalado.
    # Extraer el mes de la fecha de la imagen y lo define como la propiedad 'month'
    month_val = image.date().get('month')
    return img_final.copyProperties(image, ['system:time_start']) \
                              .set('month', month_val)


# --- 6.2 CÁLCULO DE ÍNDICES DE VEGETACIÓN ---

def add_vegetation_indices(image):
    """Calcula 11 índices espectrales avanzados y los añade como nuevas bandas.

    Suite de índices diseñada específicamente para la discriminación de
    coberturas en ecosistemas de Bosque Seco Tropical (Bs-T), incluyendo
    índices de vegetación, humedad, suelo y clorofila.

    Args:
        image (ee.Image): Imagen Sentinel-2 preprocesada con bandas
            renombradas ('blue', 'green', 'red', 'rededge1-3', 'nir',
            'swir1', 'swir2').

    Returns:
        ee.Image: Imagen original con 11 bandas adicionales:
            'NDVI', 'EVI', 'SAVI', 'MSAVI2', 'OSAVI', 'NDMI',
            'NIRv', 'NDRE', 'NBR', 'BSI', 'CIre'.
    """
    # 1. Índices Básicos
    # NDVI: Normalized Difference Vegetation Index (Biomasa general)
    # Formula: (NIR − Rojo) / (NIR + Rojo)
    ndvi = image.normalizedDifference(['nir', 'red']).rename('NDVI')

    # EVI: Enhanced Vegetation Index (Mejor para alta biomasa y Estructura de dosel, corrección atmosférica)
      # Formula: 2.5 * (NIR - RED) / ((NIR + 6 * RED - 7.5 * BLUE) + 1)
    evi = image.expression(
        '2.5 * (NIR - RED) / ((NIR + 6 * RED - 7.5 * BLUE) + 1)', {
            'NIR': image.select('nir'), 'RED': image.select('red'), 'BLUE': image.select('blue')
        }).rename('EVI')

    # SAVI: Soil Adjusted Vegetation Index (CRÍTICO para Bs-T en sequía donde se ve el suelo)
      # L = 0.5 (factor de ajuste estándar)
    savi = image.expression(
        '((NIR - RED) / (NIR + RED + 0.5)) * (1 + 0.5)', {
            'NIR': image.select('nir'), 'RED': image.select('red')
        }).rename('SAVI')

    # 2. Índices Avanzados para Bs-T
    # MSAVI2: Modified Soil Adjusted Vegetation Index 2 (Autoajustable, resuelve la subjetividad del SAVI en el Factor de Ajuste L.)
      # Excelente para zonas de transición suelo-vegetación
      # Formula: MSAVI2:(2 * NIR + 1 - sqrt((2 * NIR + 1)^2 - 8 * (NIR - Red))) / 2
    msavi2 = image.expression(
        '(2 * NIR + 1 - sqrt(pow((2 * NIR + 1), 2) - 8 * (NIR - RED))) / 2', {
            'NIR': image.select('nir'), 'RED': image.select('red')
        }).rename('MSAVI2')

    # OSAVI: Optimized Soil Adjusted Vegetation Index 2 (Autoajustable, tiene en cuenta el valor estándar del factor
             # de ajuste del fondo del dosel (0,16
      # Excelente para zonas de transición suelo-vegetación
      # Formula: OSAVI:(NIR - Red) / (NIR + Red + 0.16)
    osavi = image.expression(
        '((NIR - RED) / (NIR + RED + 0.16))', {
            'NIR': image.select('nir'), 'RED': image.select('red')
        }).rename('OSAVI')

    # NDMI: Normalized Difference Moisture Index (NIR - SWIR) / (NIR + SWIR)
      # Útil para detectar húmedad y estrés hídrico en la vegetación
    ndmi = image.normalizedDifference(['nir', 'swir1']).rename('NDMI')

    # NIRv Near-Infrared Reflectance of Vegetation (Proxy de Biomasa y GPP)
      # Formula: NIRv: NDVI * NIR
    nirv = ndvi.multiply(image.select('nir')).rename('NIRv')

    # NDRE: Normalized Difference Red Edge (para detectar Clorofila / Estrés temprano)
      # Formula: NDRE:(NIR − RedEdge) / (NIR + RedEdge)
    ndre = image.normalizedDifference(['nir','rededge1']).rename('NDRE')

    # NBR: Normalized Burn Ratio permite la detección de cicatrices de incendios forestales y para el caso de Bs-T
    # es útil para detectar suelo desnudo expuesto, humedad en el suelo y vegetación severamente estresada durante la sequía
      # Formula: NBR:(NIR − swir2) / (NIR + swir2)
    nbr = image.normalizedDifference(['nir', 'swir2']).rename('NBR')

    # BSI: Bare Soil Index Burn Ratio para cuantificar la presencia de suelo desnudo, durante la época de sequía máxima (senescencia)
      # Formula: BSI = (SWIR1 + RED) - (NIR + BLUE) / (SWIR1 + RED) + (NIR + BLUE)
    bsi = image.expression(
        '((SWIR1 + RED) - (NIR + BLUE)) / ((SWIR1 + RED) + (NIR + BLUE))', {
            'SWIR1': image.select('swir1'), 'RED': image.select('red'),
            'NIR': image.select('nir'), 'BLUE': image.select('blue')
        }).rename('BSI')

    # CIre (Chlorophyll Index Red-Edge - Índice de Clorofila en el Borde Rojo) más sensible al contenido real de clorofila en el dosel que el NDVI
    # permite detectar estrés hídrico temprano en el Bs-T
      # Formula: ((NIR / rededge3)-1)
    cire = image.expression(
        '(NIR / REDEDGE3) - 1', {
            'NIR': image.select('nir'), 'REDEDGE3': image.select('rededge3')
        }).rename('CIre')

    return image.addBands([ndvi, evi, savi, msavi2, osavi, ndmi, nirv, ndre, nbr, bsi, cire])

# --- 6.3 CÁLCULO DE TEXTURA ---

def add_glcm_texture(image):
    """Calcula métricas de textura GLCM sobre la banda NIR a dos escalas espaciales.

    Genera 4 bandas de textura (Entropía y Contraste) a dos ventanas
    espaciales (30m y 70m efectivos) para diferenciar coberturas CLC Colombia
    estructuralmente lisas (ej. Pastos Limpios, cultivos, Suelo Desnudo)
    de coberturas estructuralmente rugosas (Bosque, Vegetación Secundaria).

    El cálculo promedia la co-ocurrencia en 4 direcciones simultáneas
    (0°, 45°, 90°, 135°) para obtener resultados rotacionalmente invariantes.

    Args:
        image (ee.Image): Imagen Sentinel-2 preprocesada con banda 'nir'
            en reflectancia (0-1).

    Returns:
        ee.Image: Imagen original con 4 bandas adicionales de textura:
            'NIR_ENTROPY_30m', 'NIR_CONTRAST_30m',
            'NIR_ENTROPY_70m', 'NIR_CONTRAST_70m' (todas como Float32).

    Note:
        ⚠️ El cálculo GLCM aumenta significativamente el tiempo de
        procesamiento. Se recomienda activar solo para análisis estacional
        de temporadas de lluvia.
    """
    # 1. Seleccionar NIR y escalar a enteros (0-255) para optimizar GLCM
    # Se multiplica por 100 (si reflectance es 0-1) y se ajusta.
    # Como ya esta escalada la imagen, el valor 0.5 (50% refl) * 255 es un buen rango.
    # Un método robusto es normalizar min-max, pero para eficiencia usaremos multiplicador.
    nir_int = image.select('nir').multiply(255).toInt()

    # 2. Calcular GLCM
    # Calculo del Promedio de co-ocurrencia de niveles de gris (GLCM) - para reducir variabilidad anisotrópica no deseada -
      # en 4 direcciones simultáneamente:
        # 0° (horizontal: izquierda → derecha)
        # 45° (diagonal: abajo-izquierda → arriba-derecha)
        # 90° (vertical: abajo → arriba)
        # 135° (diagonal inversa)
    # Evaluación por ventanas (ventana 3x3 a 10m = 30m efectivos, textura local; ventana 7x7 = 70m efectivos
      # captura la rugosidad del dosel a escala de rodal, más relevante para distinguir bosque maduro de secundario en el Bs-T.
        # size=1 equivale a ventana de 3x3 píxeles (kernel) = 30m.
        # size=3 equivale a ventana de 7x7 píxeles (kernel) = 70m.
      # se promedian las 4 direcciones → resultado rotacionalmente invariante
    glcm_1 = nir_int.glcmTexture(size=1, average=True)
    glcm_3 = nir_int.glcmTexture(size=3, average=True)

    # 3. Seleccionar métricas clave
    # Entropy: Mide desorden (Alto en bosque, bajo en cultivos monocultivo)
    # Contrast: Mide contraste local (Alto en bordes y doseles irregulares)
    entropy_1 = glcm_1.select('nir_ent').rename('NIR_ENTROPY_30m')
    contrast_1 = glcm_1.select('nir_contrast').rename('NIR_CONTRAST_30m')

    entropy_3 = glcm_3.select('nir_ent').rename('NIR_ENTROPY_70m')
    contrast_3 = glcm_3.select('nir_contrast').rename('NIR_CONTRAST_70m')
    # Convertir a float para mantener compatibilidad en exportación
    return image.addBands([entropy_1.toFloat(), contrast_1.toFloat(), entropy_3.toFloat(), contrast_3.toFloat()])


# --- 6.4 CÁLCULO DE DELTAS ---

def calcular_deltas(img_wet, img_dry, prefix):
    """Calcula diferencias estacionales (Deltas) entre temporadas húmeda y seca.

    Genera imágenes de cambio fenológico sustrayendo los valores de índices
    espectrales de la temporada seca a la temporada húmeda. Valores positivos
    indican mayor vigor/biomasa/humedad en la temporada húmeda.

    Los deltas calculados son ecológicamente relevantes para Bs-T:
      - Estructura del dosel: SAVI, MSAVI2, OSAVI
      - Contenido hídrico: NDMI
      - Salud/vigor vegetal: NDVI
      - Productividad primaria bruta: NIRv
      - Calidad de clorofila: NDRE

    Args:
        img_wet (ee.Image): Mosaico de temporada húmeda con bandas de índices.
        img_dry (ee.Image): Mosaico de temporada seca con bandas de índices.
        prefix (str): Prefijo para los nombres de las bandas resultantes
            (ej. 'DELTA_MAX', 'DELTA_MID').

    Returns:
        ee.Image: Imagen multibanda con los deltas calculados, nombrados
            como '{prefix}_SAVI', '{prefix}_MSAVI2', etc.
    """
    d_savi = img_wet.select('SAVI').subtract(img_dry.select('SAVI')).rename(f'{prefix}_SAVI')
    d_msavi = img_wet.select('MSAVI2').subtract(img_dry.select('MSAVI2')).rename(f'{prefix}_MSAVI2')
    d_osavi = img_wet.select('OSAVI').subtract(img_dry.select('OSAVI')).rename(f'{prefix}_OSAVI')
    d_ndmi = img_wet.select('NDMI').subtract(img_dry.select('NDMI')).rename(f'{prefix}_NDMI')
    d_ndvi = img_wet.select('NDVI').subtract(img_dry.select('NDVI')).rename(f'{prefix}_NDVI')
    d_nirv = img_wet.select('NIRv').subtract(img_dry.select('NIRv')).rename(f'{prefix}_NIRv')
    d_ndre = img_wet.select('NDRE').subtract(img_dry.select('NDRE')).rename(f'{prefix}_NDRE')

    # Verificar si existe NDRE antes de calcular (por si acaso)
    bandas = img_wet.bandNames().getInfo()
    out = d_msavi.addBands([d_ndmi, d_osavi, d_ndvi, d_nirv])
    if 'NDRE' in bandas:
         d_ndre = img_wet.select('NDRE').subtract(img_dry.select('NDRE')).rename(f'{prefix}_NDRE')
         out = out.addBands(d_ndre)
    return out.addBands([d_savi]) # Include d_savi here and remove the redundant d_msavi.addBands at the beginning

# --- 6.5 CÁLCULO MEDOID ---

def medoid(collection):
    """Genera un composite Medoid píxel a píxel para evitar valores espectrales sintéticos.

    A diferencia de la composición por mediana que puede generar píxeles
    "espectralmente sintéticos" (combinación de valores de diferentes fechas
    que no corresponden a ninguna observación real), el método Medoid
    selecciona para cada píxel la observación real cuyo vector espectral
    es más cercano a la mediana de la colección.

    Esto es especialmente relevante para productos destinados a
    fotointerpretación visual, donde la coherencia espectral inter-banda
    es crítica.

    Args:
        collection (ee.ImageCollection): Colección de imágenes Sentinel-2
            preprocesadas y enmascaradas.

    Returns:
        ee.Image: Imagen composite donde cada píxel proviene de una
            observación real (la más cercana a la mediana espectral).
    """
    bandas_originales = collection.first().bandNames()
    median = collection.median()

    def calcular_distancia(img):
        """Calcula la distancia euclidiana invertida de cada píxel respecto a la mediana.

        Args:
            img (ee.Image): Imagen individual de la colección.

        Returns:
            ee.Image: Imagen con banda 'inv_dist' añadida (distancia
                invertida para uso con qualityMosaic).
        """
        # Distancia euclidiana de las bandas del píxel respecto a la mediana
        dist = img.subtract(median).pow(2).reduce(ee.Reducer.sum()).sqrt()
        # QualityMosaic escoge el píxel con el valor MÁS ALTO de la banda guía.
        # Para forzarlo a escoger la distancia MÁS BAJA (el píxel medoid real),
        # multiplicamos la distancia por -1.
        inv_dist = dist.multiply(-1).rename('inv_dist')
        return img.addBands(inv_dist)

    return collection.map(calcular_distancia).qualityMosaic('inv_dist').select(bandas_originales)

print("✓ Funciones avanzadas para el Enmascaramiento de Nubes y el análisis estacional (calculo de índices \nde vegetación, Deltas Estacionales, y análisis de textura), definidas con éxito.")
print("\n--- [SECCIÓN 6] Finalizada con éxito. ---")

# ==============================================================================
# SECCIÓN 7: BÚSQUEDA, PRE-PROCESAMIENTO Y VERIFICACIÓN
# ==============================================================================
# Descripción: Ejecuta el flujo completo de pre-procesamiento:
#   1. Filtrado espacio-temporal de las colecciones S2_SR y S2_CLOUD_PROBABILITY
#   2. Join de ambas colecciones por identificador de escena (system:index)
#   3. Aplicación del enmascaramiento combinado (s2cloudless + SCL + sombras)
#   4. Preprocesamiento radiométrico (escalado, renombramiento)
#   5. Verificación de disponibilidad de imágenes
#   6. Comparación visual antes/después del enmascaramiento
#   7. Reporte de densidad de imágenes por temporada climática y año

print("\n--> [SECCIÓN 7] Ejecutando búsqueda y pre-procesamiento de imágenes...")

# --- 7.1. Filtrado inicial y unión de colecciones ---
# Se filtran ambas colecciones (S2_SR y Cloud Probability) por el mismo rango
# de fechas y extensión espacial, luego se unen por system:index para que
# cada imagen tenga acceso a su capa de probabilidad de nubes correspondiente.
print(" -> Filtrando y uniendo colecciones S2_SR y S2_CLOUD_PROBABILITY...")

s2_sr = ee.ImageCollection(S2_SR_COLLECTION) \
  .filterDate(FECHA_INICIO, FECHA_FIN) \
  .filterBounds(aoi) \
  .filter(ee.Filter.lte('CLOUDY_PIXEL_PERCENTAGE', MAX_NUBES_METADATA)) \

s2_cloud_prob = ee.ImageCollection(S2_CLOUD_PROB_COLLECTION) \
  .filterDate(FECHA_INICIO, FECHA_FIN) \
  .filterBounds(aoi)

# Join por system:index: vincula cada imagen S2_SR con su correspondiente
# capa de probabilidad de nubes del dataset s2cloudless.
join_filter = ee.Filter.equals(leftField='system:index', rightField='system:index')
s2_sr_with_cloud_prob = ee.Join.saveFirst('s2cloudless').apply(s2_sr, s2_cloud_prob, join_filter)
coleccion_unida = ee.ImageCollection(s2_sr_with_cloud_prob)

# --- 7.2. Aplicar las funciones de enmascaramiento ---
# Pipeline secuencial: primero enmascaramiento de nubes/sombras, luego
# preprocesamiento radiométrico (escalado, renombramiento, propiedad month).
print(" -> Aplicando enmascaramiento avanzado a la colección...")

coleccion_procesada = coleccion_unida.map(mask_s2_clouds_maximum_precision).map(preprocess_s2_image)

# --- 7.3. VERIFICACIÓN Y COMPARACIÓN VISUAL ---
# Verifica si la colección contiene imágenes después del procesamiento.
# Detiene el script si la colección está vacía.

print(" -> Verificando disponibilidad y preparando capas de comparación...")
count = coleccion_procesada.size().getInfo()
print('=' * 50)
print(f'VERIFICACIÓN: Se encontraron {count} imágenes válidas tras el pre-procesamiento.')
print('=' * 50)
if count == 0:
    print('⚠️ Proceso terminado. No hay escenas disponibles con los criterios definidos. Sugerencias:')
    print('   1. Amplía el rango de fechas.')
    print('   2. Aumenta el porcentaje de nubes permitido (MAX_NUBES_METADATA).')
    print('3. Verifica que el área de interés sea correcta')
    raise SystemExit("Proceso detenido. No hay imágenes para procesar.")
else:
    print("✓ Verificación superada. Añadiendo capas de comparación al mapa para verificar el enmascaramiento...")

    try:
        # Seleccionar la primera imagen de cada colección para comparar
        composicion_antes = coleccion_unida.median()
        composicion_despues = coleccion_procesada.median()

        # Crear nombres de capa dinámicos basados en MODO_OPERACION
        label_map = {
            'MOSAICO': 'Mosaico de comparación',
            'ESCENA_ÚNICA': 'Colección de escenas (Mediana)'
            }
        label_prefix = label_map.get(MODO_OPERACION, 'Resultado de comparación') # .get() es seguro si el modo no existe

        nombre_capa_antes = f'{label_prefix} ANTES de enmascarar'
        nombre_capa_despues = f'{label_prefix} DESPUÉS de enmascarar'

        # Parámetros de visualización consistentes con el estado de cada imagen
        # Antes: bandas originales en DN (0-3000), Después: reflectancia (0-0.3)
        vis_params_antes = {'bands': ['B4', 'B3', 'B2'], 'min': 0, 'max': 3000, 'gamma': 1.2}
        vis_params_despues = {'bands': ['red', 'green', 'blue'], 'min': 0.0, 'max': 0.3, 'gamma': 1.2}

        # Añadir las capas al mapa usando la variable 'aoi'
        Map.addLayer(composicion_antes.clip(aoi), vis_params_antes, nombre_capa_antes, False)
        Map.addLayer(composicion_despues.clip(aoi), vis_params_despues, nombre_capa_despues, True)
        print(f"✓ Capas: '{nombre_capa_antes}' y '{nombre_capa_despues}', de verificación añadidas. \nActívalas/desactívalas en el mapa de la sección 5 para ver la diferencia.")
    except Exception as e:
        pass

# --- 7.3. REPORTE DE DENSIDAD DE IMÁGENES ---
# Reporte del número y distribución de imágenes válidas por año y por temporada
# para tener mayor control de la densidad de observaciones.
# La cuota teórica asume ~6 pases mensuales de Sentinel-2A+2B combinados.
print("\n📊 REPORTE DE DENSIDAD DE IMÁGENES POR TEMPORADA Y AÑO:")
print("="*60)
temporadas_rep = {
    'LLUVIA_PPAL': MESES_LLUVIA_PPAL,
    'LLUVIA_SEC':  MESES_LLUVIA_SEC,
    'SEQUIA_PPAL': MESES_SEQUIA_PPAL,
    'SEQUIA_SEC':  MESES_SEQUIA_SEC
}
for nombre, meses in temporadas_rep.items():
    col_temp = coleccion_procesada.filter(ee.Filter.inList('month', meses))
    anos = range(int(FECHA_INICIO[:4]), int(FECHA_FIN[:4]) + 1)
    reporte_anual = {}
    for ano in anos:
        col_ano = col_temp.filter(ee.Filter.calendarRange(ano, ano, 'year'))

        # 1. Total de Escenas (Tiles MGRS individuales)
        n_escenas = col_ano.size().getInfo()

        # 2. Total de Fechas Únicas de Sobrevuelo
        if n_escenas > 0:
            fechas_milis = col_ano.aggregate_array('system:time_start')
            def format_date(milis):
                return ee.Date(milis).format('YYYY-MM-dd')
            fechas_unicas = ee.List(fechas_milis).map(format_date).distinct()
            n_fechas = fechas_unicas.size().getInfo()
        else:
            n_fechas = 0

        reporte_anual[ano] = {'escenas': n_escenas, 'fechas': n_fechas}

    total_escenas = sum([d['escenas'] for d in reporte_anual.values()])
    total_fechas = sum([d['fechas'] for d in reporte_anual.values()])

    print(f"\n  📅 {nombre} (Meses: {meses}) → Total: {total_escenas} escenas en {total_fechas} días de captura")

    # Cuota teórica de días: Sentinel-2 (A y B combinados) pasa ~6 veces por mes
    cuota_teorica_dias = len(meses) * 6

    for ano, metrics in reporte_anual.items():
        n_f = metrics['fechas']
        n_e = metrics['escenas']

        if cuota_teorica_dias > 0:
            porcentaje = (n_f / cuota_teorica_dias) * 100
        else:
            porcentaje = 0

        if porcentaje >= 70:
            estado = "🟢 ÓPTIMA"
        elif porcentaje >= 40:
            estado = "🟡 MEDIA"
        elif porcentaje > 0:
            estado = "🟠 BAJA"
        else:
            estado = "🔴 NULA/CRÍTICA"

        print(f"     {ano}: {n_e:3d} escenas capturadas en {n_f:2d} días ({porcentaje:5.1f}% de cobertura temporal) [{estado}]")
print("="*60)

print("\n--- [SECCIÓN 7] Finalizada con éxito.Se puede continuar con el procesamiento. ---")

# ==============================================================================
# SECCIÓN 8: EJECUCIÓN DEL ANÁLISIS PRINCIPAL
# ==============================================================================
# Descripción: Ejecuta el flujo de trabajo correspondiente al ANALYSIS_MODE
# seleccionado en la Sección 4. Soporta tres modos:
#   - EXPORTAR_IMAGEN: Escena única o mosaico Medoid → Export a Drive
#   - MOSAICO_ESTACIONAL: 4 composiciones bimodales + índices + textura + deltas
#   - CURVA_FENOLÓGICA: Series de tiempo → CSV con estadísticas zonales

print(f"\n--> [SECCIÓN 8] Iniciando análisis en modo: '{ANALYSIS_MODE}'...")

# Diccionario para almacenar capas para visualización (Sección 9)
layers_to_map = {}
producto_final = None # Inicializar variable global para evitar error en sección 9

# ===================== MODO: EXPORTAR_IMAGEN =====================
# Lógica para ANALYSIS_MODE
if ANALYSIS_MODE == 'EXPORTAR_IMAGEN':
    # 8.1 Flujo de trabajo: Exportación de Escena Única/Mosaico
    print(" -> Ejecutando flujo de trabajo: Exportación de Imagen.")

    # 1. Variable para almacenar el resultado que se usará en la visualización
    producto_a_exportar = None

    if MODO_OPERACION == 'MOSAICO':
        # Modo MOSAICO: Composite Medoid de toda la colección procesada
        print(" -> Modo MOSAICO: Creando una composición medoid...")

        # 1. Crear el mosaico a partir de la colección ya procesada
        mosaico = medoid(coleccion_procesada)
        layers_to_map['Mosaico Medoid'] = mosaico
        producto_a_exportar = mosaico # Asignar a la variable intermedia

        # 2. Construir el nombre del archivo
        nombre_archivo = f'S2_SR_{VALOR_FILTRO}_MOSAICO_{FECHA_INICIO}_a_{FECHA_FIN}'
        print(f" -> Nombre de archivo para exportación: {nombre_archivo}")
        print(f" -> Iniciando exportación a CRS: {CRS_EXPORTACION}")

    elif MODO_OPERACION == 'ESCENA_ÚNICA':
        # Modo ESCENA_ÚNICA: Selecciona la escena con más píxeles válidos en el AOI
        print(" -> Modo ESCENA_ÚNICA: Seleccionando la escena con más píxeles válidos...")

        # 1. Optimización lógica: Función para contar píxeles válidos en el AOI por imagen
        def add_valid_pixel_count(image):
            """Cuenta los píxeles válidos (no enmascarados) de la banda NIR dentro del AOI.

            Args:
                image (ee.Image): Imagen procesada con banda 'nir'.

            Returns:
                ee.Image: Imagen con propiedad 'valid_pixel_count' añadida.
            """
            # Contar el número de píxeles de la banda 'nir' que no están enmascarados
            valid_pixels = image.select('nir').reduceRegion(
                reducer=ee.Reducer.count(),
                geometry=aoi,
                scale=10,
                bestEffort=True,
                maxPixels=1e10
            ).get('nir')
            return image.set('valid_pixel_count', valid_pixels)

        # 2. Aplicar la función y ordenar la colección para encontrar la "mejor" escena
        coleccion_con_conteo = coleccion_procesada.map(add_valid_pixel_count)
        mejor_escena = ee.Image(coleccion_con_conteo.sort('valid_pixel_count', False).first())
        layers_to_map['Escena Unica'] = mejor_escena
        producto_a_exportar = mejor_escena # Asignar a la variable intermedia

        # 3. Obtener la fecha de la escena seleccionada para el nombre del archivo
        fecha_escena = ee.Date(mejor_escena.get('system:time_start')).format('YYYY-MM-dd').getInfo()
        nombre_archivo = f'S2_SR_{VALOR_FILTRO}_ESCENA_{fecha_escena}'
        print(f" -> Escena seleccionada del {fecha_escena}")
        print(f" -> Nombre de archivo para exportación: {nombre_archivo}")
        print(f" -> Iniciando exportación a CRS: {CRS_EXPORTACION}")

    else:
        raise ValueError(f"Modo de operación '{MODO_OPERACION}' no reconocido. Use 'MOSAICO' o 'ESCENA_ÚNICA'.")

    # 2. Aplicar el clip según el AOI definido
    print(f" -> Aplicando clip final al producto con el AOI definido.")
    producto_final = producto_a_exportar.clip(aoi)

    # 3. Configurar y lanzar la tarea de exportación a Google Drive
    export_task = ee.batch.Export.image.toDrive(
        image=producto_final.select(['red', 'green', 'blue', 'nir']), # Exporta el producto ya recortado
        description=nombre_archivo,
        folder='Fund_Titi',
        fileNamePrefix=nombre_archivo,
        scale=ESCALA_EXPORTACION,
        region=aoi, # Se usa .bounds() para la región, una práctica recomendada
        crs=CRS_EXPORTACION,
        maxPixels=1e13
    )
    export_task.start()

# ===================== MODO: MOSAICO_ESTACIONAL =====================
elif ANALYSIS_MODE == 'MOSAICO_ESTACIONAL':
  # 8.2 Flujo de trabajo: Generación MOSAICO ESTACIONAL y Cálculo Índices de Vegetación y Cálculo Textura
    print(" -> Ejecutando Análisis Estacional Bimodal para Bosque Seco Tropical")

    # 1. Definición de las Temporadas Climáticas (Diccionario para iterar)
    temporadas = {
        'LLUVIA_PPAL': MESES_LLUVIA_PPAL,
        'LLUVIA_SEC':  MESES_LLUVIA_SEC,
        'SEQUIA_PPAL': MESES_SEQUIA_PPAL,
        'SEQUIA_SEC':  MESES_SEQUIA_SEC
    }

    # 2. Inicializar mosaicos_procesados aquí para asegurar que está vacío al inicio de este modo
    mosaicos_procesados = {}

    # 3. Validar que la colección tenga la propiedad 'month'
    # Tomamos una imagen de prueba
    try:
        test_img = coleccion_procesada.first()
        props = test_img.propertyNames().getInfo()
        if 'month' not in props:
            print("⚠️ ALERTA: La propiedad 'month' no se detectó en las imágenes. El filtro fallará.")
    except:
        pass

    # 4. Generación de Mosaicos (Con validación de existencia)
    for nombre, meses in temporadas.items():
        print(f"-> Buscando imágenes para: {nombre} (Meses: {meses})...")
        # 4.1 Filtrar colección procesada por meses
        col_temp = coleccion_procesada.filter(ee.Filter.inList('month', meses))

        # 4.2 Contar cuántas imágenes pasaron el filtro
        count_temp = col_temp.size().getInfo()

        # 4.3 Realizar Analisis Estacional
        if count_temp > 0:
            print(f"-> ✓ Imágenes disponibles: {count_temp}. Generando mosaicos...")
            # a. Reducción (Medoid) y Clip
            img_base = medoid(col_temp).clip(aoi)
            # b. Calcular Índices Espectrales (Para TODAS las temporadas)
            print(f"-> Calculando Índices de Vegetación para {nombre}...")
            img_indices = add_vegetation_indices(img_base)
            # c. Cálcular Textura (Opcional, SOLO para Lluvias, donde el contraste Estructural del dosel es más evidente)
            if CALCULAR_TEXTURA and ('LLUVIA' in nombre):
                print(f"-> Calculando Textura GLCM (Entropía y Contraste) para {nombre}...")
                img_indices = add_glcm_texture(img_indices)
            # d. Guardar el mosaico procesado en el diccionario
            mosaicos_procesados[nombre] = img_indices
            layers_to_map[f'{nombre} (RGB)'] = img_indices # Para visualización, si se desea
            # e. Asignar un producto final por defecto para la seccion 9
            if producto_final is None:
                producto_final = img_indices
            print(f"✓ Mosaico para temporada {nombre} procesado y almacenado.")

        else:
            print(f"-> ⚠️ ADVERTENCIA: No se encontraron imágenes válidas para {nombre}. Se omitirá la creación del mosaico.")
            print("->Sugerencia: Aumenta MAX_NUBES_METADATA, Verifica si tu rango de fechas (Sección 4.3) cubre los meses {meses}.")

    # 4. Cálculo de DELTA (Solo si existen los pares necesarios)
    # (Cambios Fenológicos Estratégicos) Calcula los ecológicamente relevantes para Bs-T.
    # Delta = Lluvia - Sequía. Estructura (SAVI, MSAVI2 y OSAVI), Agua (NDMI), Clorofila (NDRE), Productividad Primaria Bruta (NIRv),
                               # Salud - Densidad - Vigor (NDVI)
    # Para mayor detalle sobre uso Deltas en Bs-T, revisar el documento Protocolo Técnico Bs-T
    print("-> Generando imágenes de cambio (DELTAS) para SAVI, MSAVI2, OSAVI, NDMI, NDVI, NIRv y NDRE...")

    # 4.1. Amplitud Máxima (Ciclo Principal: Sep-Nov vs Ene-Mar)
        # Captura la caducidad total y estrés máximo.
    if 'LLUVIA_PPAL' in mosaicos_procesados and 'SEQUIA_PPAL' in mosaicos_procesados:
        delta_max = calcular_deltas(mosaicos_procesados['LLUVIA_PPAL'], mosaicos_procesados['SEQUIA_PPAL'], 'DELTA_MAX')
        mosaicos_procesados['ANALISIS_DELTA_MAX'] = delta_max
        layers_to_map['DELTA MAX (MSAVI2)'] = delta_max.select('DELTA_MAX_MSAVI2')

        print("✓ Delta Máximo calculado exitosamente.")

    else:
        print("-> ⚠️ ADVERTENCIA: No se pudo calcular DELTA_MAX. Faltan mosaicos principales.")

    # 4.2. Amplitud Media (Ciclo Secundario: Abr-May vs Jun-Ago)
        # Captura dinámicas de cultivos semestrales y resistencia al "Veranillo de San Juan"
    if 'LLUVIA_SEC' in mosaicos_procesados and 'SEQUIA_SEC' in mosaicos_procesados:
        delta_mid = calcular_deltas(mosaicos_procesados['LLUVIA_SEC'], mosaicos_procesados['SEQUIA_SEC'], 'DELTA_MID')
        mosaicos_procesados['ANALISIS_DELTA_MID'] = delta_mid
        layers_to_map['DELTA MID (NDMI)'] = delta_mid.select('DELTA_MID_NDMI')

        print("✓ Delta Medio (Veranillo de San Juan) calculado exitosamente.")

    else:
        print("-> ⚠️ ADVERTENCIA: No se pudo calcular DELTA_MID. Faltan mosaicos secundarios.")


    # 5. Exportación Masiva
    # Configura y lanza tareas de exportación para cada mosaico estacional
    # y cada imagen de análisis delta. Todas las bandas se convierten a Float32
    # para evitar errores de compatibilidad en la exportación GeoTIFF.
    if not mosaicos_procesados:
      print("\n🛑 DETENIDO: No se generó ningún mosaico para exportar.")
    else:
        print(" -> Iniciando configuración de tareas de exportación...")
        print(" -> NOTA: Se convertirán todas las bandas a Float32 para evitar errores de compatibilidad.")
        bandas_base = ['red', 'green', 'blue', 'nir']
        for nombre_prod, imagen in mosaicos_procesados.items():
            print(f"-> Configurando exportación para: {nombre_prod}")

            # 5.1 Determinar bandas a exportar dinámicamente
            bandas_img = imagen.bandNames().getInfo()

            # 5.2 Lógica de selección de bandas
            if 'DELTA' in nombre_prod: # Para imágenes Delta, exporta todos los calculados (MSAVI, NDMI, NDRE...)
                bandas_export = bandas_img
            else: # Para Mosaicos exporta: Base + Indices Configurados + Textura (si existe)
                target = set(bandas_base + INDICES_A_CALCULAR + ['NIR_ENTROPY_30m', 'NIR_CONTRAST_30m', 'NIR_ENTROPY_70m', 'NIR_CONTRAST_70m'])
                bandas_export = list(target.intersection(bandas_img))

            print(f" -> Bandas seleccionadas: {bandas_export}")

            # 5.3 Corrección de tipos de datos
            # Seleccionamos las bandas y forzamos la conversión a Float32 unificado.
            imagen_a_exportar = imagen.select(bandas_export).toFloat()

            # 5.4 Limpieza de nombres de archivo para evitar caracteres inválidos
            safe_name = nombre_prod.replace(" ", "_").replace("(", "").replace(")", "")

            print(f" -> Bandas finales a exportar para {safe_name}")

            # 5.5. Exportación a Google Drive
            task = ee.batch.Export.image.toDrive(
                image=imagen_a_exportar,
                description=f'S2_{VALOR_FILTRO}_{safe_name}',
                folder='Fund_Titi',
                fileNamePrefix=f'S2_{VALOR_FILTRO}_{safe_name}',
                scale=ESCALA_EXPORTACION,
                region=aoi,
                crs=CRS_EXPORTACION,
                maxPixels=1e13
            )
            task.start()
            print(f"✓ Tarea de exportación para '{safe_name}' iniciada correctamente (Cast to Float32 aplicado).")


# ===================== MODO: CURVA_FENOLÓGICA =====================
elif ANALYSIS_MODE == 'CURVA_FENOLÓGICA':
  # 8.3 Flujo de trabajo: Generación datos para Análisis Curva Fenológica
    print(" -> Generando Series de Tiempo Completas...")

    # 1. Preparar colección con índices
    col_fenologia = coleccion_procesada.map(add_vegetation_indices)

    # 2. Función de reducción Combinada (Mean, StdDev, Count)
    # Establece el valor medio, qué tanto varía dentro del municipio (heterogeneidad)
    # y cuántos píxeles válidos hubo (confiabilidad).
    combined_reducer = ee.Reducer.mean().combine(
        reducer2=ee.Reducer.stdDev(), sharedInputs=True
    ).combine(
        reducer2=ee.Reducer.count(), sharedInputs=True
    )

    def reduce_region_all_indices(image):
        """Aplica reducción zonal combinada (media, desviación, conteo) sobre el AOI.

        Args:
            image (ee.Image): Imagen con bandas de índices espectrales.

        Returns:
            ee.Image: Imagen con propiedades estadísticas añadidas
                ('{indice}_mean', '{indice}_stdDev', '{indice}_count')
                y propiedad 'date' formateada.
        """
        stats = image.reduceRegion(
            reducer=combined_reducer,
            geometry=aoi,
            scale=30, # Escala 30m es suficiente para estadísticas regionales y más rápido,
            bestEffort=True,
            maxPixels=1e9
        )
        # Formatear fecha
        #date_str = image.date().format('YYYY-MM-dd')
        return image.setMulti(stats).set('date', image.date().format('YYYY-MM-dd'))

    # 3. Aplicar reducción y filtrar nulos (imágenes vacías tras máscara)
    ts_features = col_fenologia.map(reduce_region_all_indices).filter(ee.Filter.notNull(['NDVI_mean']))

    # 4. Filtrar nulos (imágenes vacías tras máscara)
    #ts_features = ts_features.filter(ee.Filter.notNull(['NDVI_mean']))

    # 5. Exportar a CSV
    # GEE añade sufijos _mean, _stdDev, _count a las bandas
    # Construye la lista de selectores dinámicamente (Media y Desviación para CADA índice configurado)
    selectores_csv = ['date', 'system:index','NDVI_count']
    for ind in INDICES_A_CALCULAR:
        selectores_csv.append(f'{ind}_mean')
        selectores_csv.append(f'{ind}_stdDev')

    print(f" -> Columnas a exportar en CSV: {selectores_csv}")

    # 6. Exportar tabla (CSV) a Google Drive
    task_table = ee.batch.Export.table.toDrive(
        collection=ts_features,
        description=f'FENOLOGIA {VALOR_FILTRO} FULL',
        folder='Fund_Titi',
        fileNamePrefix=f'FENOLOGIA_{VALOR_FILTRO}_TimeSeries',
        fileFormat='CSV',
        selectors=selectores_csv # <--- FILTRADO DINÁMICO
    )
    task_table.start()
    print("✓ Tarea de exportación de Tabla CSV iniciada correctamente.")

# --- Mensajes de estado post-exportación ---
if ANALYSIS_MODE == 'CURVA_FENOLÓGICA':
    print("\n⚠️ ATENCIÓN: La tarea de exportación del CSV a Drive ha iniciado en segundo plano.")
    print("   Deberás esperar a que finalice en GEE antes de poder ejecutar la Sección 9.")
else:
    print(f"\n⚠️ ATENCIÓN: Tarea(s) de exportación de {ANALYSIS_MODE} y '{MODO_OPERACION} iniciada(s) en segundo plano.")
    print("   Monitorea el progreso en la pestaña 'Tasks' de GEE.")
    print(" ✓ Puedes pasar inmediatamente a la Sección 10 para visualizar el producto en el mapa interactivo).")

print("\n--- [SECCIÓN 8] Finalizada con éxito. ---")

# ==============================================================================
# SECCIÓN 9: ANÁLISIS FENOLÓGICO (SUAVIZADO Y MÉTRICAS)
# ==============================================================================
# Descripción: Aplica suavizado Savitzky-Golay sobre la serie temporal (CSV
# exportado) eliminando ruido atmosférico residual, y genera curvas
# fenológicas con umbrales ecológicos superpuestos.
# Requiere que el CSV haya sido exportado exitosamente por GEE (Sección 8).

print("\n--> [SECCIÓN 9] Análisis Fenológico (Suavizado Savitzky-Golay)...")
print("⚠️ IMPORTANTE: Ejecuta esta celda SÓLO cuando GEE haya terminado de exportar el CSV a tu Google Drive.")

def analizar_fenologia_csv():
    """Procesa la serie temporal de índices desde CSV y genera curvas fenológicas suavizadas.

    Pipeline completo de post-procesamiento fenológico:
      1. Carga y filtrado del CSV exportado por GEE
      2. Regularización temporal a composites de 15 días
      3. Interpolación lineal de vacíos (gap filling)
      4. Suavizado Savitzky-Golay (ventana=11, orden=3)
      5. Generación de gráfica con umbrales ecológicos para Bs-T

    La gráfica resultante incluye:
      - Curva NDVI bruta vs. suavizada con rangos de referencia para Bosque
        Maduro (0.55-0.80) y Sequía (0.20-0.45)
      - Curva NDMI suavizada para seguimiento de contenido hídrico
      - Bandas temporales de lluvias (azul) y sequías (marrón) del Caribe

    Returns:
        None: Genera y guarda la gráfica en Google Drive como PNG.

    Raises:
        FileNotFoundError: Si el CSV aún no ha sido exportado por GEE.
    """
    try:
        csv_path = f"{DRIVE_BASE_PATH}/Fund_Titi/FENOLOGIA_{VALOR_FILTRO}_TimeSeries.csv"
        if not os.path.exists(csv_path):
            print("❌ CSV aún no exportado o no disponible localmente. ¡Espera a que finalice la tarea de GEE!")
            return

        df = pd.read_csv(csv_path, parse_dates=['date']).sort_values('date').reset_index(drop=True)
        # Filtrar observaciones con pocas muestras (ruido por nubes)
        if 'NDVI_count' in df.columns:
            df = df[df['NDVI_count'] > 100].copy()

        # PASO 1: Regularización temporal (Composites de 15 días)
        # Agrupa observaciones irregulares de Sentinel-2 en ventanas fijas.
        # Es un requisito matemático estricto para que el filtro Savitzky-Golay funcione
        # El filtro Savitzky-Golay requiere matemáticamente datos equidistantes en el tiempo.
        df.set_index('date', inplace=True)
        df = df.resample('15D').mean(numeric_only=True)
        df.reset_index(inplace=True)
        # Parámetros del filtro Savitzky-Golay
        WINDOW = 11   # Tamaño de ventana (debe ser impar)
        POLYORDER = 3 # Orden del polinomio de ajuste

        for indice in INDICES_A_CALCULAR:
            col = f'{indice}_mean'
            if col in df.columns:
              # Paso 2: Interpolar vacíos (Gap filling). Para llenar "huecos" de datos generados
              # por el enmascaramiento de nubes y sombras
              # Rellena con una línea recta matemática los bloques de 15 días que quedaron totalmente
              # vacíos (NaN) por culpa de nubes severas.
                df[col] = df[col].interpolate(method='linear', limit_direction='both')
                # Paso 3: Filtro Savitzky-Golay (Suavizado algorítmico)
                # Aún en días sin nubes visibles, la atmósfera tiene aerosoles que causan "ruido atmosférico".
                # Elimina el "ruido" atmosférico (caídas bruscas e irreales en el NDVI de un día para otro) pero conservando
                # intacta la forma natural (crestas y valles) y biológica de los picos de verdor.
                df[f'{indice}_smooth'] = savgol_filter(df[col].values, WINDOW, POLYORDER)

        # Paso 4: Extracción de Métricas (Renderizado y Contexto Ecológico)
        # Grafica las curvas y superpone umbrales fenológicos teóricos (Bosque/Sequía)
        # y los meses climáticos para interpretar si la vegetación reacciona a la lluvia.
        fig, axes = plt.subplots(2, 1, figsize=(16, 10))
        ax1 = axes[0]
        ax1.scatter(df['date'], df['NDVI_mean'], color='lightgray', s=8, alpha=0.6, label='NDVI bruto')
        ax1.plot(df['date'], df['NDVI_smooth'], color='#2d6a4f', linewidth=2.5, label='NDVI suavizado')
          # a. Añade bandas horizontales de color que muestran los umbrales teóricos
        ax1.axhspan(0.55, 0.80, alpha=0.1, color='green', label='Rango Bosque Maduro')
        ax1.axhspan(0.20, 0.45, alpha=0.1, color='orange', label='Rango Sequía')
          # b. Añade bandas verticales azules y marrones para marcar los meses calendario de lluvias (Sep-Nov) y sequías (Dic-Mar).
        for ano in df['date'].dt.year.unique():
            ax1.axvspan(pd.Timestamp(f'{ano}-09-01'), pd.Timestamp(f'{ano}-11-30'), alpha=0.08, color='blue')
            ax1.axvspan(pd.Timestamp(f'{ano}-12-01'), pd.Timestamp(f'{ano+1}-03-31'), alpha=0.08, color='sienna')

        ax1.set_title(f'Curva Fenológica - {VALOR_FILTRO}')
        ax1.legend()
        ax1.xaxis.set_major_formatter(mdates.DateFormatter('%b-%Y'))

        ax2 = axes[1]
        ax2.plot(df['date'], df['NDMI_smooth'], color='#0077b6', linewidth=2, label='NDMI suavizado')
        ax2.axhline(0, color='gray', linestyle='--')
        ax2.legend()

        plt.tight_layout()
        plt.savefig(f"{DRIVE_BASE_PATH}/Fund_Titi/Fenologia_{VALOR_FILTRO}_Curva.png")
        print("✓ Curva fenológica generada y guardada exitosamente.")
    except Exception as e:
        print(f"Error en suavizado: {e}")

if ANALYSIS_MODE == 'CURVA_FENOLÓGICA':
    print("-> La función 'analizar_fenologia_csv()' está lista para usarse.")

print("\n--- [SECCIÓN 9] Finalizada con éxito. ---")

# ==============================================================================
# SECCIÓN 10: VISUALIZACIÓN DEL PRODUCTO FINAL
# ==============================================================================
# Descripción: Añade el resultado del procesamiento al mapa interactivo de
# geemap (creado en Sección 5) para una verificación visual inmediata.
# Soporta visualización de escena única/mosaico y mosaicos estacionales.

print("\n--> [SECCIÓN 10] Visualizando el producto final en el mapa de la Sección 5...")

try:
    # Definir parámetros de visualización estándar para color natural
    vis_params = {
        'bands': ['red', 'green', 'blue'],
        'min': 0.0,
        'max': 0.3,
        'gamma': 1.2
    }
    capas_agregadas = 0

    if ANALYSIS_MODE == 'EXPORTAR_IMAGEN' and producto_final is not None:
        label = f'Resultado ({MODO_OPERACION})'
        # Recortar el producto final al AOI para una visualización limpia
        # Añadir la capa al mapa 'Map' que fue creado en la Sección 5
        Map.addLayer(producto_final.clip(aoi), vis_params, label)
        capas_agregadas += 1
        # Centrar el mapa en el resultado
        Map.centerObject(aoi, 11)

    elif ANALYSIS_MODE == 'MOSAICO_ESTACIONAL' and mosaicos_procesados:
            # Añadir las 4 temporadas al mapa (RGB)
            for nombre, img in mosaicos_procesados.items():
                if 'DELTA' not in nombre: # Evitamos visualizar los deltas en RGB porque fallarían
                    Map.addLayer(img.clip(aoi), vis_params, f'Mosaico {nombre}', False)
                    capas_agregadas += 1
            # Centrar el mapa en el resultado
            Map.centerObject(aoi, 11)

    if capas_agregadas > 0:
        print(f"✓ {capas_agregadas} capas añadidas al mapa interactivo para revisión visual.")
        print("   (El mapa esta en la Sección 5, haz scroll para verlo)")

except Exception as e:
    print("⚠️ No se pudo generar un producto final para visualizar.")

print("\n--- [SECCIÓN 10] Finalizada con éxito. ---")
