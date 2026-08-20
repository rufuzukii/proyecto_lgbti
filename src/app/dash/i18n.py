from __future__ import annotations

from typing import Any

from dash import html
from dash.development.base_component import Component

SUPPORTED_LANGUAGES = {"es", "en"}
COUNTRY_NAMES: dict[str, tuple[str, str]] = {
    "AD": ("Andorra", "Andorra"),
    "AL": ("Albania", "Albania"),
    "AM": ("Armenia", "Armenia"),
    "AT": ("Austria", "Austria"),
    "AZ": ("Azerbaiyán", "Azerbaijan"),
    "BA": ("Bosnia y Herzegovina", "Bosnia and Herzegovina"),
    "BE": ("Bélgica", "Belgium"),
    "BG": ("Bulgaria", "Bulgaria"),
    "BY": ("Bielorrusia", "Belarus"),
    "CH": ("Suiza", "Switzerland"),
    "CY": ("Chipre", "Cyprus"),
    "CZ": ("República Checa", "Czechia"),
    "DE": ("Alemania", "Germany"),
    "DK": ("Dinamarca", "Denmark"),
    "EE": ("Estonia", "Estonia"),
    "ES": ("España", "Spain"),
    "FI": ("Finlandia", "Finland"),
    "FR": ("Francia", "France"),
    "GB": ("Reino Unido", "United Kingdom"),
    "GE": ("Georgia", "Georgia"),
    "GR": ("Grecia", "Greece"),
    "HR": ("Croacia", "Croatia"),
    "HU": ("Hungría", "Hungary"),
    "IE": ("Irlanda", "Ireland"),
    "IS": ("Islandia", "Iceland"),
    "IT": ("Italia", "Italy"),
    "LI": ("Liechtenstein", "Liechtenstein"),
    "LT": ("Lituania", "Lithuania"),
    "LU": ("Luxemburgo", "Luxembourg"),
    "LV": ("Letonia", "Latvia"),
    "MT": ("Malta", "Malta"),
    "MC": ("Mónaco", "Monaco"),
    "MD": ("Moldavia", "Moldova"),
    "ME": ("Montenegro", "Montenegro"),
    "MK": ("Macedonia del Norte", "North Macedonia"),
    "NL": ("Países Bajos", "Netherlands"),
    "NO": ("Noruega", "Norway"),
    "PL": ("Polonia", "Poland"),
    "PT": ("Portugal", "Portugal"),
    "RO": ("Rumanía", "Romania"),
    "RS": ("Serbia", "Serbia"),
    "RU": ("Rusia", "Russia"),
    "SM": ("San Marino", "San Marino"),
    "SE": ("Suecia", "Sweden"),
    "SI": ("Eslovenia", "Slovenia"),
    "SK": ("Eslovaquia", "Slovakia"),
    "TR": ("Turquía", "Türkiye"),
    "UA": ("Ucrania", "Ukraine"),
    "VA": ("Ciudad del Vaticano", "Vatican City"),
    "XK": ("Kosovo", "Kosovo"),
}
UI_TEXT = {
    "ilga_normalization_note_title": {
        "es": "Nota metodológica",
        "en": "Methodological note",
    },
    "ilga_normalization_note_body": {
        "es": (
            "Los datos de este año utilizaban originalmente una escala distinta a 0-100. "
            "Para permitir su comparación visual con ediciones posteriores, se han "
            "normalizado linealmente a una escala de 0 a 100."
        ),
        "en": (
            "The data for this year originally used a scale different from 0-100. "
            "To allow visual comparison with later editions, the values have been "
            "linearly normalized to a 0-100 scale."
        ),
    },
    "ilga_normalization_series_note_body": {
        "es": (
            "Los datos de los años indicados utilizaban originalmente escalas distintas a "
            "0-100. Para permitir su comparación visual con ediciones posteriores, se han "
            "normalizado linealmente a una escala de 0 a 100."
        ),
        "en": (
            "The data for the years shown originally used scales different from 0-100. "
            "To allow visual comparison with later editions, the values have been linearly "
            "normalized to a 0-100 scale."
        ),
    },
    "ilga_normalization_note_scale": {
        "es": "Escala original: {original_min} a {original_max}.",
        "en": "Original scale: {original_min} to {original_max}.",
    },
    "ilga_normalization_note_caution": {
        "es": (
            "Los valores se muestran en una escala común para facilitar la comparación "
            "visual entre ediciones; esto no elimina las diferencias metodológicas."
        ),
        "en": (
            "Values are shown on a common scale to facilitate visual comparison between "
            "editions; this does not remove methodological differences."
        ),
    },
    "footer_attributions_title": {
        "es": "Atribuciones",
        "en": "Attributions",
    },
    "footer_attribution_fra_text": {
        "es": (
            "Fuente: European Union Agency for Fundamental Rights (FRA), EU "
            "LGBT/LGBTI/LGBTIQ Surveys 2012, 2019 y 2023. Datos procesados y "
            "visualizados por RainbowLens DataHub. La FRA no participa en esta adaptación."
        ),
        "en": (
            "Source: European Union Agency for Fundamental Rights (FRA), EU "
            "LGBT/LGBTI/LGBTIQ Surveys 2012, 2019 and 2023. Data processed and "
            "visualised by RainbowLens DataHub. FRA is not involved in this adaptation."
        ),
    },
    "footer_attribution_ilga_text": {
        "es": (
            "Agradecemos a ILGA-Europe su labor de recopilación, análisis y difusión de "
            "información sobre la situación de los derechos LGBTI en Europa. Los datos han "
            "sido procesados y adaptados para su visualización en RainbowLens DataHub. "
            "RainbowLens DataHub no está afiliada ni representa oficialmente a ILGA-Europe."
        ),
        "en": (
            "We thank ILGA-Europe for its work collecting, analysing and sharing information "
            "about the situation of LGBTI rights in Europe. The data have been processed and "
            "adapted for visualisation in RainbowLens DataHub. RainbowLens DataHub is not "
            "affiliated with and does not officially represent ILGA-Europe."
        ),
    },
    "footer_attribution_felgtbi_text": {
        "es": (
            "Federación Estatal de Lesbianas, Gais, Trans, Bisexuales, Intersexuales y más — "
            "FELGTBI+. Contenido procesado y adaptado para su visualización en RainbowLens "
            "DataHub. RainbowLens DataHub no está afiliada ni representa oficialmente a FELGTBI+."
        ),
        "en": (
            "Federación Estatal de Lesbianas, Gais, Trans, Bisexuales, Intersexuales y más — "
            "FELGTBI+. Content processed and adapted for visualisation in RainbowLens DataHub. "
            "RainbowLens DataHub is not affiliated with and does not officially represent FELGTBI+."
        ),
    },
    "source_fra_label": {"es": "FRA", "en": "FRA"},
    "source_ilga_label": {"es": "ILGA-Europe", "en": "ILGA-Europe"},
    "source_felgtbi_label": {"es": "FELGTBI+", "en": "FELGTBI+"},
    "fra_survey_2012": {"es": "Encuesta FRA 2012", "en": "FRA Survey 2012"},
    "fra_survey_2019": {"es": "Encuesta FRA 2019", "en": "FRA Survey 2019"},
    "fra_survey_2023": {"es": "Encuesta FRA 2023", "en": "FRA Survey 2023"},
    "about_primary_sources_title": {
        "es": "Fuentes principales de datos y situación social",
        "en": "Main data and social-context sources",
    },
    "footer_copyright": {
        "es": "© {year} RainbowLens DataHub",
        "en": "© {year} RainbowLens DataHub",
    },
    "privacy_title": {
        "es": "Privacidad y protección de datos",
        "en": "Privacy and data protection",
    },
    "privacy_data_collected": {"es": "Datos que recopilamos", "en": "Data we collect"},
    "privacy_purposes": {"es": "Finalidades", "en": "Purposes"},
    "privacy_legal_basis": {"es": "Base jurídica", "en": "Legal basis"},
    "privacy_retention": {"es": "Conservación", "en": "Retention"},
    "privacy_recipients": {"es": "Destinatarios", "en": "Recipients"},
    "privacy_rights": {"es": "Tus derechos", "en": "Your rights"},
    "privacy_manage_data": {"es": "Gestionar mis datos", "en": "Manage my data"},
    "privacy_account_deleted": {
        "es": "Tu cuenta y los datos personales asociados han sido eliminados.",
        "en": "Your account and associated personal data have been deleted.",
    },
    "privacy_notice": {
        "es": "RainbowLens DataHub utiliza los datos necesarios para gestionar tu cuenta y ofrecer las funcionalidades solicitadas. Puedes consultar qué información se conserva y solicitar la eliminación de tu cuenta en cualquier momento.",
        "en": "RainbowLens DataHub uses the data required to manage your account and provide the requested features. You can review what information is stored and request the deletion of your account at any time.",
    },
    "privacy_understood": {"es": "Entendido", "en": "Got it"},
    "privacy_deleted_heading": {"es": "Cuenta eliminada", "en": "Account deleted"},
    "privacy_controller": {
        "es": "Responsable del tratamiento",
        "en": "Data controller",
    },
    "privacy_on_this_page": {
        "es": "En esta página",
        "en": "On this page",
    },
    "privacy_contact": {"es": "Contacto", "en": "Contact"},
    "privacy_controller_name_label": {
        "es": "Responsable:",
        "en": "Controller:",
    },
    "privacy_location_label": {"es": "Ubicación:", "en": "Location:"},
    "privacy_controller_location": {
        "es": "Málaga, España",
        "en": "Málaga, Spain",
    },
    "privacy_identity_document_label": {
        "es": "NIF/Pasaporte:",
        "en": "NIF/Passport:",
    },
    "privacy_identity_document_value": {
        "es": "Disponible para el usuario que acredite su identidad y desee ejercer sus derechos ARCO",
        "en": "Available to users who verify their identity and wish to exercise their data protection rights.",
    },
    "privacy_contact_email_label": {
        "es": "Correo electrónico:",
        "en": "Email:",
    },
    "privacy_security": {"es": "Cómo protegemos los datos", "en": "How we protect data"},
    "privacy_backups": {"es": "Copias de seguridad", "en": "Backups"},
    "navigation_home": {"es": "Inicio", "en": "Home"},
    "navigation_statistics": {"es": "Estadísticas", "en": "Statistics"},
    "navigation_trends": {"es": "Tendencias", "en": "Trends"},
    "navigation_spain": {"es": "España", "en": "Spain"},
    "navigation_didactics": {"es": "Didáctica", "en": "Learning"},
    "navigation_about": {"es": "Acerca de", "en": "About"},
    "home_sections_eyebrow": {
        "es": "Explora RainbowLens",
        "en": "Explore RainbowLens",
    },
    "home_sections_title": {
        "es": "Todo el DataHub a tu alcance",
        "en": "The whole DataHub at your fingertips",
    },
    "home_sections_lead": {
        "es": (
            "Accede directamente a los datos, análisis y recursos principales de la plataforma."
        ),
        "en": ("Go directly to the platform's main data, analysis and learning resources."),
    },
    "home_statistics_description": {
        "es": (
            "Explora datos sociodemográficos y legales de Europa mediante mapas, rankings, "
            "comparaciones y segmentaciones."
        ),
        "en": (
            "Explore European sociodemographic and legal data through maps, rankings, "
            "comparisons and segmentations."
        ),
    },
    "home_statistics_action": {
        "es": "Ir a Estadísticas",
        "en": "Go to Statistics",
    },
    "home_statistics_aria": {
        "es": "Abrir la sección Estadísticas",
        "en": "Open the Statistics section",
    },
    "home_trends_description": {
        "es": (
            "Analiza la evolución histórica de la situación legal LGBTIQ+ y consulta "
            "proyecciones estadísticas exploratorias basadas en los datos disponibles; "
            "no son predicciones oficiales."
        ),
        "en": (
            "Analyse the historical evolution of the LGBTIQ+ legal situation and review "
            "exploratory statistical projections based on available data; they are not "
            "official predictions."
        ),
    },
    "home_trends_action": {"es": "Ver Tendencias", "en": "View Trends"},
    "home_trends_aria": {
        "es": "Abrir la sección Tendencias",
        "en": "Open the Trends section",
    },
    "home_spain_description": {
        "es": (
            "Consulta informes y análisis de FELGTBI+ por año, documento e indicador, con "
            "textos y figuras extraídos de las publicaciones originales."
        ),
        "en": (
            "Browse FELGTBI+ reports and analyses by year, document and indicator, including "
            "text and figures extracted from the original publications."
        ),
    },
    "home_spain_action": {"es": "Explorar España", "en": "Explore Spain"},
    "home_spain_aria": {
        "es": "Abrir la sección España",
        "en": "Open the Spain section",
    },
    "home_didactics_description": {
        "es": (
            "Aprende conceptos LGBTIQ+ mediante el glosario, juegos interactivos y recursos "
            "educativos."
        ),
        "en": (
            "Learn LGBTIQ+ concepts through the glossary, interactive games and educational "
            "resources."
        ),
    },
    "home_didactics_action": {
        "es": "Ir a Didáctica",
        "en": "Go to Learning",
    },
    "home_didactics_aria": {
        "es": "Abrir la sección Didáctica",
        "en": "Open the Learning section",
    },
    "home_about_description": {
        "es": "Conoce las fuentes, la metodología y el objetivo de RainbowLens DataHub.",
        "en": "Learn about RainbowLens DataHub's sources, methodology and purpose.",
    },
    "home_legal_map_explanation": {
        "es": (
            "El mapa muestra la puntuación global de protección legal LGBTIQ+ de cada país "
            "en una escala de 0 a 100. Los valores más altos indican mayor reconocimiento y "
            "protección legal según los datos disponibles."
        ),
        "en": (
            "The map shows each country's overall LGBTIQ+ legal protection score on a scale "
            "from 0 to 100. Higher values indicate greater legal recognition and protection "
            "in the available data."
        ),
    },
    "home_legal_map_helper": {
        "es": "Explora Europa y consulta la puntuación global de protección legal LGBTIQ+.",
        "en": "Explore Europe and view the overall LGBTIQ+ legal protection score.",
    },
    "home_legal_ranking_empty": {
        "es": "No hay puntuaciones legales disponibles para este año.",
        "en": "No legal scores are available for this year.",
    },
    "home_legal_export_error": {
        "es": "No se ha podido generar la imagen. Inténtalo de nuevo.",
        "en": "The image could not be generated. Please try again.",
    },
    "home_ilga_country_eyebrow": {
        "es": "Detalle de criterios ILGA",
        "en": "ILGA criteria detail",
    },
    "home_ilga_country_title": {
        "es": "Situación legal por país en 2026",
        "en": "Legal situation by country in 2026",
    },
    "home_ilga_country_intro": {
        "es": (
            "Selecciona un país para consultar qué medidas de protección y reconocimiento "
            "legal LGBTIQ+ recoge ILGA-Europe en el Rainbow Map 2026."
        ),
        "en": (
            "Select a country to review the LGBTIQ+ legal protection and recognition "
            "measures reflected in ILGA-Europe's 2026 Rainbow Map."
        ),
    },
    "home_ilga_country_empty": {
        "es": "Selecciona un país para consultar su situación legal en 2026.",
        "en": "Select a country to view its legal situation in 2026.",
    },
    "home_legal_country_label": {
        "es": "País",
        "en": "Country",
    },
    "home_legal_country_placeholder": {
        "es": "Selecciona un país",
        "en": "Select a country",
    },
    "home_legal_country_no_data": {
        "es": "No hay información legal disponible para este país en 2026.",
        "en": "No legal information is available for this country in 2026.",
    },
    "home_legal_country_error": {
        "es": "No se ha podido cargar la información legal. Inténtalo de nuevo.",
        "en": "The legal information could not be loaded. Please try again.",
    },
    "home_about_action": {"es": "Más información", "en": "More information"},
    "home_about_aria": {
        "es": "Abrir la sección Acerca de",
        "en": "Open the About section",
    },
    "home_login_title": {"es": "Inicia sesión", "en": "Sign in"},
    "home_login_description": {
        "es": (
            "Accede a tu cuenta para consultar tu perfil y utilizar tus plantillas de "
            "informe personalizadas."
        ),
        "en": (
            "Access your account to view your profile and use your personalised report templates."
        ),
    },
    "home_login_action": {"es": "Iniciar sesión", "en": "Sign in"},
    "home_login_aria": {
        "es": "Abrir la página de inicio de sesión",
        "en": "Open the sign-in page",
    },
    "home_profile_title": {"es": "Tu perfil", "en": "Your profile"},
    "home_profile_description": {
        "es": (
            "Accede directamente a tu perfil, tus datos de cuenta y las plantillas de "
            "informe adaptadas a tu perfil profesional."
        ),
        "en": (
            "Go directly to your profile, account details and report templates tailored "
            "to your professional profile."
        ),
    },
    "home_profile_action": {"es": "Ir a mi perfil", "en": "Go to my profile"},
    "home_profile_aria": {
        "es": "Abrir mi perfil de usuario",
        "en": "Open my user profile",
    },
    "report_module_name": {
        "es": "Informe",
        "en": "Report",
    },
    "report_generation_eyebrow": {
        "es": "Generación de informes",
        "en": "Report generation",
    },
    "report_configuration": {
        "es": "Selecciona el contenido",
        "en": "Select the content",
    },
    "report_login_required": {
        "es": "Debes iniciar sesión para generar informes.",
        "en": "You must sign in to generate reports.",
    },
    "download_table": {
        "es": "Descargar tabla",
        "en": "Download table",
    },
    "download_csv": {
        "es": "Descargar CSV",
        "en": "Download CSV",
    },
    "no_export_data": {
        "es": "No hay datos para exportar",
        "en": "No data available to export",
    },
    "no_data": {
        "es": "Sin datos",
        "en": "No data",
    },
    "chart_value": {
        "es": "Valor",
        "en": "Value",
    },
    "chart_not_enough_information": {
        "es": "No hay suficiente información",
        "en": "There is not enough information",
    },
    "chart_percentage": {
        "es": "Porcentaje",
        "en": "Percentage",
    },
    "chart_no_data_grey": {
        "es": "Sin datos: gris",
        "en": "No data: grey",
    },
    "fra_map_percentage_scale": {
        "es": "Escala porcentual",
        "en": "Percentage scale",
    },
    "fra_map_no_data": {
        "es": "Sin datos",
        "en": "No data",
    },
    "fra_map_no_data_selection": {
        "es": "No hay datos disponibles para esta selección.",
        "en": "No data is available for this selection.",
    },
    "fra_map_outside_scope": {
        "es": "Fuera del ámbito de la encuesta FRA",
        "en": "Outside the scope of the FRA survey",
    },
    "fra_map_outside_scope_hover": {
        "es": (
            "Este país no forma parte de la Unión Europea y no está incluido en esta encuesta FRA."
        ),
        "en": (
            "This country is not part of the European Union and is not included in this FRA survey."
        ),
    },
    "fra_ranked_reason_title": {
        "es": "¿Cómo interpretar estas respuestas?",
        "en": "How should these responses be interpreted?",
    },
    "fra_ranked_reason_intro": {
        "es": (
            "En esta pregunta, las respuestas indican la importancia atribuida a esta causa "
            "entre las tres razones principales seleccionadas:"
        ),
        "en": (
            "For this question, the responses indicate the importance assigned to this reason "
            "among the three main reasons selected:"
        ),
    },
    "fra_ranked_reason_1st": {
        "es": "1st: primera razón en importancia.",
        "en": "1st: the most important reason.",
    },
    "fra_ranked_reason_2nd": {
        "es": "2nd: segunda razón en importancia.",
        "en": "2nd: the second most important reason.",
    },
    "fra_ranked_reason_3rd": {
        "es": "3rd: tercera razón en importancia.",
        "en": "3rd: the third most important reason.",
    },
    "fra_ranked_reason_not_selected": {
        "es": "Not selected: la causa no fue seleccionada entre las tres razones principales.",
        "en": (
            "Not selected: this reason was not selected among the three most important reasons."
        ),
    },
    "loading_statistics": {
        "es": "Cargando estadísticas...",
        "en": "Loading statistics...",
    },
    "loading_indicators": {
        "es": "Cargando indicadores...",
        "en": "Loading indicators...",
    },
    "loading_trends": {"es": "Calculando tendencia...", "en": "Calculating trend..."},
    "processing_document": {
        "es": "Procesando documento...",
        "en": "Processing document...",
    },
    "generating_report": {"es": "Generando informe...", "en": "Generating report..."},
    "contact_success": {
        "es": "Tu mensaje se ha enviado correctamente.",
        "en": "Your message was sent successfully.",
    },
    "contact_validation_error": {
        "es": "Revisa los campos y los archivos adjuntos antes de volver a intentarlo.",
        "en": "Review the fields and attachments before trying again.",
    },
    "contact_delivery_error": {
        "es": "No se ha podido enviar el mensaje. Inténtalo de nuevo más tarde.",
        "en": "The message could not be sent. Try again later.",
    },
    "contact_rate_limited": {
        "es": "Has alcanzado el límite temporal de envíos. Inténtalo más tarde.",
        "en": "You have reached the temporary submission limit. Try again later.",
    },
    "trends_name": {"es": "Tendencias", "en": "Trends"},
    "trends_eyebrow": {"es": "Análisis legal histórico", "en": "Historical legal analysis"},
    "trends_title": {
        "es": "Evolución de la situación legal LGBTIQ+",
        "en": "Evolution of the LGBTIQ+ legal situation",
    },
    "trends_lead": {
        "es": "Analiza la evolución histórica de la puntuación global de protección legal LGBTIQ+ de los países europeos y genera una estimación de su posible evolución futura a partir de los datos históricos disponibles.",
        "en": "Analyse the historical evolution of the overall LGBTIQ+ legal protection score across European countries and generate an estimate of its possible future evolution based on the available historical data.",
    },
    "trends_country": {"es": "País", "en": "Country"},
    "trends_historical_range": {"es": "Rango histórico", "en": "Historical range"},
    "trends_forecast_horizon": {"es": "Horizonte de proyección", "en": "Projection horizon"},
    "trends_select_country": {"es": "Selecciona un país", "en": "Select a country"},
    "trends_initial_prompt": {
        "es": "Selecciona un país para analizar su puntuación legal global.",
        "en": "Select a country to analyse its overall legal score.",
    },
    "trends_not_enough": {
        "es": "No hay información suficiente.",
        "en": "There is not enough information.",
    },
    "trends_not_enough_projection": {
        "es": "No hay información suficiente para generar una proyección fiable. Se muestra únicamente la serie histórica disponible.",
        "en": "There is not enough information to generate a reliable projection. Only the available historical series is shown.",
    },
    "trends_exploratory_warning": {
        "es": "Estimación exploratoria: la serie contiene entre tres y cinco observaciones, por lo que solo se aplica una regresión lineal y el horizonte se limita a un año.",
        "en": "Exploratory estimate: the series contains three to five observations, so only linear regression is applied and the horizon is limited to one year.",
    },
    "trends_error_loading_series": {
        "es": "Error al cargar la serie.",
        "en": "Error loading the series.",
    },
    "trends_error_analysis": {
        "es": "No se ha podido generar el análisis temporal.",
        "en": "The temporal analysis could not be generated.",
    },
    "trends_year_singular": {"es": "1 año", "en": "1 year"},
    "trends_years_two": {"es": "2 años", "en": "2 years"},
    "trends_years_three": {"es": "3 años", "en": "3 years"},
    "trends_historical_data": {"es": "Datos históricos", "en": "Historical data"},
    "trends_forecast": {"es": "Tendencia estimada", "en": "Estimated trend"},
    "trends_uncertainty": {"es": "Margen de incertidumbre", "en": "Uncertainty range"},
    "trends_chart_title": {"es": "Evolución y proyección", "en": "Evolution and projection"},
    "trends_year": {"es": "Año", "en": "Year"},
    "trends_legal_score": {"es": "Puntuación legal", "en": "Legal score"},
    "trends_historical_observation": {"es": "Dato histórico", "en": "Historical observation"},
    "trends_projection_observation": {
        "es": "Proyección RainbowLens DataHub",
        "en": "RainbowLens DataHub projection",
    },
    "trends_value_type": {"es": "Tipo", "en": "Type"},
    "trends_estimated_value": {"es": "Puntuación estimada", "en": "Estimated score"},
    "trends_estimated_interval": {
        "es": "Margen de incertidumbre",
        "en": "Uncertainty range",
    },
    "trends_forecast_starts": {"es": "Inicio de la proyección", "en": "Projection starts"},
    "trends_historical_source": {
        "es": "Datos históricos: ILGA-Europe Rainbow Map.",
        "en": "Historical data: ILGA-Europe Rainbow Map.",
    },
    "trends_projection_source": {
        "es": "Procesamiento y proyección: RainbowLens DataHub.",
        "en": "Processing and projection: RainbowLens DataHub.",
    },
    "trends_upward": {"es": "Ascendente", "en": "Upward"},
    "trends_downward": {"es": "Descendente", "en": "Downward"},
    "trends_stable": {"es": "Estable", "en": "Stable"},
    "trends_irregular": {"es": "Irregular", "en": "Irregular"},
    "trends_trend": {"es": "Tendencia", "en": "Trend"},
    "trends_total_change": {"es": "Cambio histórico", "en": "Historical change"},
    "trends_last_value": {"es": "Último valor", "en": "Latest value"},
    "trends_selected_model": {"es": "Método utilizado", "en": "Method used"},
    "trends_mean_error": {
        "es": "Diferencia media en las pruebas",
        "en": "Average difference in testing",
    },
    "trends_points": {"es": "puntos", "en": "points"},
    "trends_projection_method": {
        "es": "Método utilizado para esta proyección",
        "en": "Method used for this projection",
    },
    "trends_method_summary": {
        "es": "RainbowLens DataHub prueba varios métodos con los años conocidos y comprueba cuál representa mejor la evolución ya observada. Después utiliza el método más adecuado sin añadir complejidad innecesaria.",
        "en": "RainbowLens DataHub tests several methods against known years and checks which one best represents the evolution already observed. It then uses the most suitable method without adding unnecessary complexity.",
    },
    "trends_validation_mean_error": {
        "es": "Diferencia media durante las pruebas",
        "en": "Average difference during testing",
    },
    "trends_years_used": {"es": "Años utilizados", "en": "Years used"},
    "trends_observations": {"es": "Observaciones", "en": "Observations"},
    "trends_how_calculated": {
        "es": "Ver metodología detallada",
        "en": "View detailed methodology",
    },
    "trends_data_collection": {"es": "Recopilación de datos", "en": "Data collection"},
    "trends_data_collection_detail": {
        "es": "Se recuperan las puntuaciones globales históricas de {country} entre {start} y {end}: {observations} observaciones.",
        "en": "The historical overall scores for {country} are retrieved from {start} to {end}: {observations} observations.",
    },
    "trends_data_validation": {"es": "Validación de los datos", "en": "Data validation"},
    "trends_data_validation_detail": {
        "es": "Se eliminan valores nulos, se ordena la serie por año, se revisan duplicados y no se inventan observaciones para años ausentes. Años ausentes: {missing}.",
        "en": "Null values are removed, the series is sorted by year, duplicates are checked, and no observations are invented for missing years. Missing years: {missing}.",
    },
    "trends_no_missing_years": {"es": "ninguno", "en": "none"},
    "trends_models_evaluated": {"es": "Modelos evaluados", "en": "Models evaluated"},
    "trends_temporal_validation": {"es": "Validación temporal", "en": "Temporal validation"},
    "trends_temporal_validation_detail": {
        "es": "Cada método intenta estimar un año que ya conocemos utilizando solo los años anteriores. El proceso se repite varias veces para comprobar cómo habría funcionado antes de proyectar el futuro. Esta comprobación se denomina validación temporal.",
        "en": "Each method tries to estimate a year we already know using only earlier years. This is repeated several times to check how it would have performed before projecting the future. This check is called temporal validation.",
    },
    "trends_error_comparison": {"es": "Comparación de errores", "en": "Error comparison"},
    "trends_model": {"es": "Modelo", "en": "Model"},
    "trends_validation_folds": {"es": "Predicciones evaluadas", "en": "Evaluated predictions"},
    "trends_model_selection": {"es": "Selección del modelo", "en": "Model selection"},
    "trends_selection_lowest_error": {
        "es": "Entre los métodos evaluados, {model} fue el que representó mejor la evolución histórica disponible durante las pruebas.",
        "en": "Among the evaluated methods, {model} represented the available historical evolution most accurately during testing.",
    },
    "trends_selection_simplicity": {
        "es": "{model} fue seleccionado porque ofreció una precisión similar a modelos más complejos utilizando una estructura más sencilla y estable.",
        "en": "{model} was selected because it offered accuracy similar to more complex models with a simpler and more stable structure.",
    },
    "trends_final_training": {"es": "Entrenamiento final", "en": "Final training"},
    "trends_final_training_detail": {
        "es": "El modelo seleccionado se vuelve a ajustar utilizando todas las observaciones históricas disponibles dentro del rango elegido.",
        "en": "The selected model is fitted again using every available historical observation within the chosen range.",
    },
    "trends_projection": {"es": "Proyección", "en": "Projection"},
    "trends_projection_detail": {
        "es": "El modelo final estima los próximos {horizon} años sin añadir esos valores a la base de datos histórica.",
        "en": "The final model estimates the next {horizon} years without adding those values to the historical database.",
    },
    "trends_limits": {"es": "Límites", "en": "Limits"},
    "trends_score_limits_detail": {
        "es": "Los resultados visibles se restringen a la escala real del Rainbow Map, de 0 a 100. El valor bruto del modelo se conserva únicamente para diagnóstico.",
        "en": "Displayed results are restricted to the Rainbow Map scale of 0 to 100. The model's raw value is retained only for diagnostics.",
    },
    "trends_uncertainty_detail": {
        "es": "La zona alrededor de la línea muestra un margen razonable basado en los errores observados durante las pruebas. Suele ampliarse al alejarse de los datos históricos porque la estimación es menos segura. Técnicamente utiliza el RMSE y no constituye un intervalo de confianza probabilístico.",
        "en": "The area around the line shows a reasonable range based on errors observed during testing. It usually widens further from the historical data because the estimate is less certain. Technically, it uses RMSE and is not a probabilistic confidence interval.",
    },
    "trends_uncertainty_unavailable": {
        "es": "No se muestra una banda de incertidumbre porque existen muy pocas predicciones históricas evaluables.",
        "en": "No uncertainty band is shown because too few historical predictions can be evaluated.",
    },
    "trends_limitations": {"es": "Limitaciones", "en": "Limitations"},
    "trends_limitations_detail": {
        "es": "Esta proyección utiliza exclusivamente la evolución histórica de la puntuación global. Los derechos LGBTIQ+ pueden cambiar rápidamente por nuevas leyes, decisiones judiciales, cambios políticos o reformas institucionales que el método no puede anticipar. La estimación no representa una predicción oficial de ILGA-Europe.",
        "en": "This projection uses only the historical evolution of the overall score. LGBTIQ+ rights can change quickly because of new laws, court decisions, political changes or institutional reforms that the method cannot anticipate. The estimate is not an official ILGA-Europe prediction.",
    },
    "trends_model_linear": {"es": "Regresión lineal", "en": "Linear regression"},
    "trends_model_holt": {
        "es": "Suavizado exponencial de Holt",
        "en": "Holt exponential smoothing",
    },
    "trends_model_quadratic": {
        "es": "Regresión polinómica de grado 2",
        "en": "Second-degree polynomial regression",
    },
    "trends_interpret_title": {
        "es": "Cómo interpretar esta gráfica",
        "en": "How to interpret this chart",
    },
    "trends_interpret_intro": {
        "es": "La gráfica muestra cómo ha evolucionado la puntuación de protección legal LGBTIQ+ de {country} y, cuando existen suficientes datos, estima cómo podría continuar durante los próximos años. La estimación no es una predicción oficial de futuros cambios legales.",
        "en": "The chart shows how {country}'s LGBTIQ+ legal-protection score has evolved and, when enough data is available, estimates how it might continue over the next few years. The estimate is not an official prediction of future legal changes.",
    },
    "trends_time_axis_title": {"es": "Años", "en": "Years"},
    "trends_time_axis_detail": {
        "es": "La parte inferior representa el paso del tiempo. Los años anteriores muestran información histórica y los años posteriores corresponden a la estimación de RainbowLens DataHub.",
        "en": "The lower part represents the passage of time. Earlier years show historical information and later years correspond to the RainbowLens DataHub estimate.",
    },
    "trends_score_axis_title": {"es": "Puntuación legal", "en": "Legal score"},
    "trends_score_axis_detail": {
        "es": "La altura de cada punto representa la puntuación en una escala de 0 a 100. Un valor mayor indica que el país reconoce y protege legalmente más derechos según los criterios de ILGA-Europe.",
        "en": "The height of each point represents the score on a scale from 0 to 100. A higher value means that the country legally recognises and protects more rights under ILGA-Europe's criteria.",
    },
    "trends_score_caveat": {
        "es": "La puntuación describe principalmente el marco legal: por sí sola no mide toda la calidad de vida ni la ausencia de discriminación social.",
        "en": "The score mainly describes the legal framework: on its own, it does not measure overall quality of life or the absence of social discrimination.",
    },
    "trends_history_explanation_title": {"es": "Datos históricos", "en": "Historical data"},
    "trends_history_explanation": {
        "es": "Cada punto de un año pasado representa la puntuación registrada para {country} por ILGA-Europe.",
        "en": "Each point for a past year represents the score recorded for {country} by ILGA-Europe.",
    },
    "trends_estimate_explanation_title": {
        "es": "Tendencia estimada",
        "en": "Estimated trend",
    },
    "trends_estimate_explanation": {
        "es": "La línea discontinua prolonga los patrones observados para mostrar cómo podría continuar la evolución si se mantuvieran tendencias parecidas. No significa que esa puntuación vaya a producirse necesariamente.",
        "en": "The dashed line extends the observed patterns to show how the evolution might continue if similar trends persisted. It does not mean that this score will necessarily occur.",
    },
    "trends_uncertainty_explanation_title": {
        "es": "Margen de incertidumbre",
        "en": "Uncertainty range",
    },
    "trends_uncertainty_explanation": {
        "es": "La zona sombreada muestra un margen razonable para la estimación. Cuanto más nos alejamos de los datos históricos, mayor puede ser la incertidumbre.",
        "en": "The shaded area shows a reasonable range for the estimate. The further it extends from the historical data, the greater the uncertainty may be.",
    },
    "trends_evolution_title": {
        "es": "Qué muestra la evolución de {country}",
        "en": "What {country}'s evolution shows",
    },
    "trends_evolution_increase": {
        "es": "Entre {start} y {end}, la puntuación legal aumentó de {initial} a {final} puntos.",
        "en": "Between {start} and {end}, the legal score increased from {initial} to {final} points.",
    },
    "trends_evolution_decrease": {
        "es": "Entre {start} y {end}, la puntuación legal descendió de {initial} a {final} puntos.",
        "en": "Between {start} and {end}, the legal score fell from {initial} to {final} points.",
    },
    "trends_evolution_same": {
        "es": "Entre {start} y {end}, la puntuación comenzó y terminó en {final} puntos.",
        "en": "Between {start} and {end}, the score started and ended at {final} points.",
    },
    "trends_evolution_upward": {
        "es": "En conjunto, la puntuación siguió una tendencia ascendente durante el periodo analizado.",
        "en": "Overall, the score followed an upward trend during the analysed period.",
    },
    "trends_evolution_downward": {
        "es": "En conjunto, la puntuación siguió una tendencia descendente durante el periodo analizado.",
        "en": "Overall, the score followed a downward trend during the analysed period.",
    },
    "trends_evolution_stable": {
        "es": "La puntuación varió poco durante el periodo analizado y se mantuvo relativamente estable.",
        "en": "The score changed little during the analysed period and remained relatively stable.",
    },
    "trends_evolution_irregular": {
        "es": "La serie alternó aumentos y descensos relevantes, por lo que no presenta una dirección uniforme durante todo el periodo.",
        "en": "The series alternated between meaningful rises and falls, so it does not show one consistent direction across the whole period.",
    },
    "trends_largest_change": {
        "es": "Uno de los mayores cambios entre observaciones consecutivas se produjo entre {start} y {end}: {change} puntos.",
        "en": "One of the largest changes between consecutive observations occurred between {start} and {end}: {change} points.",
    },
    "trends_method_friendly_linear": {"es": "Tendencia lineal", "en": "Linear trend"},
    "trends_method_friendly_holt": {
        "es": "Tendencia adaptada a los cambios recientes",
        "en": "Trend adapted to recent changes",
    },
    "trends_method_friendly_quadratic": {"es": "Tendencia curva", "en": "Curved trend"},
    "trends_statistical_method": {
        "es": "Método estadístico: {method}",
        "en": "Statistical method: {method}",
    },
    "trends_method_explanation_linear": {
        "es": "Busca la dirección general seguida por los datos. Es adecuado cuando la puntuación aumenta o disminuye de forma relativamente constante y prolonga esa dirección hacia los próximos años.",
        "en": "It finds the general direction followed by the data. It is suitable when the score rises or falls relatively steadily and extends that direction into the next few years.",
    },
    "trends_method_explanation_holt": {
        "es": "Observa toda la evolución, pero presta especial atención a los cambios recientes. Puede adaptarse mejor cuando el ritmo de avance o retroceso ha cambiado con el tiempo.",
        "en": "It considers the whole evolution while giving particular attention to recent changes. It can adapt better when the pace of progress or decline has changed over time.",
    },
    "trends_method_explanation_quadratic": {
        "es": "Representa evoluciones que no siguen una línea completamente recta. Puede reflejar que el avance se acelera, se ralentiza o cambia progresivamente de ritmo.",
        "en": "It represents evolutions that do not follow a completely straight line. It can reflect progress accelerating, slowing down or gradually changing pace.",
    },
    "trends_model_example_linear": {
        "es": "Ejemplo sencillo: 50 → 53 → 56 → 59.",
        "en": "Simple example: 50 → 53 → 56 → 59.",
    },
    "trends_model_example_holt": {
        "es": "Ejemplo sencillo: 50 → 51 → 52 → 58 → 64.",
        "en": "Simple example: 50 → 51 → 52 → 58 → 64.",
    },
    "trends_model_example_quadratic": {
        "es": "Ejemplo sencillo: 40 → 48 → 55 → 60 → 63.",
        "en": "Simple example: 40 → 48 → 55 → 60 → 63.",
    },
    "trends_selection_title": {"es": "Cómo se elige", "en": "How it is selected"},
    "trends_error_metrics_explanation": {
        "es": "El error medio indica cuántos puntos se alejaron las estimaciones de los valores conocidos, por término medio. La segunda medida da más importancia a los errores grandes. En ambos casos, un valor menor indica que el método reprodujo mejor los años utilizados para comprobarlo.",
        "en": "Average error shows how many points the estimates differed from known values on average. The second measure gives greater weight to large errors. For both measures, a lower value means the method reproduced the testing years more accurately.",
    },
    "trends_mae_column": {"es": "Error medio (MAE)", "en": "Average error (MAE)"},
    "trends_rmse_column": {
        "es": "Atención a errores grandes (RMSE)",
        "en": "Emphasis on large errors (RMSE)",
    },
    "trends_glossary_title": {"es": "Conceptos utilizados", "en": "Concepts used"},
    "trends_glossary_score": {
        "es": "Valor entre 0 y 100 que resume el reconocimiento y la protección legal LGBTIQ+ según los criterios del índice utilizado.",
        "en": "A value from 0 to 100 summarising LGBTIQ+ legal recognition and protection under the criteria of the index used.",
    },
    "trends_glossary_trend": {
        "es": "Dirección general que siguen los valores con el paso del tiempo.",
        "en": "The general direction followed by values over time.",
    },
    "trends_glossary_projection": {
        "es": "Estimación de cómo podrían continuar los valores si se mantienen patrones parecidos a los observados.",
        "en": "An estimate of how values might continue if patterns similar to those observed persist.",
    },
    "trends_glossary_uncertainty": {
        "es": "Rango que refleja que una estimación futura no puede conocerse con total precisión.",
        "en": "A range reflecting that a future estimate cannot be known with complete precision.",
    },
    "statistics_initial_prompt": {
        "es": "Selecciona una categoría y un indicador para comenzar.",
        "en": "Select a category and an indicator to get started.",
    },
    "statistics_survey_empty": {
        "es": "Todavía no hay datos disponibles para esta encuesta.",
        "en": "No data is available for this survey yet.",
    },
    "statistics_no_data": {
        "es": "No hay datos disponibles para esta selección.",
        "en": "No data is available for this selection.",
    },
    "statistics_error": {
        "es": "No se han podido cargar las estadísticas. Inténtalo de nuevo.",
        "en": "Statistics could not be loaded. Please try again.",
    },
    "statistics_countries_compared": {
        "es": "Países comparados",
        "en": "Countries compared",
    },
    "statistics_distribution": {
        "es": "Distribución",
        "en": "Distribution",
    },
    "statistics_european_average": {
        "es": "Media europea",
        "en": "European average",
    },
    "statistics_percentage_points_compared": {
        "es": "puntos porcentuales respecto a la media europea",
        "en": "percentage points compared with the European average",
    },
}


def text_attrs(es: str, en: str) -> dict[str, Any]:
    return {
        "data-i18n-es": es,
        "data-i18n-en": en,
    }


def attribute_attrs(attribute: str, es: str, en: str) -> dict[str, Any]:
    clean_attribute = str(attribute or "").strip().lower().replace("_", "-")
    if clean_attribute not in {"alt", "aria-label", "title"}:
        raise ValueError("Unsupported translatable attribute")
    return {
        f"data-i18n-{clean_attribute}-es": es,
        f"data-i18n-{clean_attribute}-en": en,
    }


def dash_attrs(attrs: dict[str, Any]) -> dict[str, Any]:
    return attrs


def text(
    es: str,
    en: str,
    *,
    class_name: str | None = None,
    language: str | None = None,
) -> Component:
    props = text_attrs(es, en)
    if class_name:
        props["className"] = class_name
    value = en if language == "en" else es
    return html.Span(value, **props)


def ui_text(key: str, language: str = "es") -> str:
    translations = UI_TEXT.get(key)
    if not translations:
        return key
    clean_language = language if language in SUPPORTED_LANGUAGES else "es"
    return translations.get(clean_language) or translations["es"]


def ui_text_component(
    key: str,
    *,
    class_name: str | None = None,
    language: str | None = None,
) -> Component:
    return text(
        ui_text(key, "es"),
        ui_text(key, "en"),
        class_name=class_name,
        language=language,
    )


def country_labels(country_code: str, fallback: str = "") -> tuple[str, str]:
    code = str(country_code or "").strip().upper()
    labels = COUNTRY_NAMES.get(code)
    if labels:
        return labels
    clean_fallback = str(fallback or code).strip()
    return clean_fallback, clean_fallback
