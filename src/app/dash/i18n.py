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
    "spain_year": {"es": "Año", "en": "Year"},
    "spain_document": {"es": "Documento", "en": "Document"},
    "spain_indicator": {"es": "Indicador", "en": "Indicator"},
    "spain_select_year": {"es": "Selecciona un año", "en": "Select a year"},
    "spain_select_document": {
        "es": "Selecciona un documento",
        "en": "Select a document",
    },
    "spain_select_indicator": {
        "es": "Selecciona un indicador",
        "en": "Select an indicator",
    },
    "spain_previous": {"es": "Anterior", "en": "Previous"},
    "spain_next": {"es": "Siguiente", "en": "Next"},
    "spain_no_documents": {
        "es": "No hay documentos disponibles",
        "en": "No documents available",
    },
    "spain_no_content": {
        "es": "No hay contenido disponible",
        "en": "No content available",
    },
    "spain_figure": {"es": "Figura", "en": "Figure"},
    "spain_source": {"es": "Fuente", "en": "Source"},
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
    "privacy_download_data": {"es": "Descargar mis datos", "en": "Download my data"},
    "privacy_zone": {"es": "Zona de privacidad", "en": "Privacy area"},
    "privacy_delete_my_data": {"es": "Eliminar mis datos", "en": "Delete my data"},
    "privacy_delete_account": {"es": "Eliminar cuenta", "en": "Delete account"},
    "privacy_confirm_deletion": {
        "es": "Confirmar eliminación",
        "en": "Confirm deletion",
    },
    "privacy_irreversible": {
        "es": "Esta acción no se puede deshacer.",
        "en": "This action cannot be undone.",
    },
    "privacy_enter_email": {"es": "Introduce tu correo", "en": "Enter your email"},
    "privacy_enter_password": {
        "es": "Introduce tu contraseña",
        "en": "Enter your password",
    },
    "privacy_account_deleted": {
        "es": "Tu cuenta y los datos personales asociados han sido eliminados.",
        "en": "Your account and associated personal data have been deleted.",
    },
    "privacy_deletion_error": {
        "es": "No se ha podido completar la eliminación de tus datos. Inténtalo de nuevo o contacta con el equipo responsable.",
        "en": "Your data could not be deleted. Try again or contact the responsible team.",
    },
    "privacy_notice": {
        "es": "RainbowLens DataHub utiliza los datos necesarios para gestionar tu cuenta y ofrecer las funcionalidades solicitadas. Puedes consultar qué información se conserva y solicitar la eliminación de tu cuenta en cualquier momento.",
        "en": "RainbowLens DataHub uses the data required to manage your account and provide the requested features. You can review what information is stored and request the deletion of your account at any time.",
    },
    "privacy_understood": {"es": "Entendido", "en": "Got it"},
    "privacy_deleted_heading": {"es": "Cuenta eliminada", "en": "Account deleted"},
    "privacy_cancel": {"es": "Cancelar", "en": "Cancel"},
    "privacy_controller": {
        "es": "Responsable del tratamiento",
        "en": "Data controller",
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
            "Explora indicadores sociodemográficos y legales del colectivo LGBTIQ+ en Europa "
            "mediante mapas interactivos, gráficos comparativos y paneles estadísticos."
        ),
        "en": (
            "Explore sociodemographic and legal indicators for LGBTIQ+ people in Europe "
            "through interactive maps, comparative charts and statistical dashboards."
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
            "Analiza la evolución histórica del ranking legal de ILGA-Europe y consulta una "
            "proyección exploratoria cuando existan datos suficientes."
        ),
        "en": (
            "Analyse the ILGA-Europe legal ranking over time and review an exploratory "
            "projection when sufficient data exists."
        ),
    },
    "home_trends_action": {"es": "Ver Tendencias", "en": "View Trends"},
    "home_trends_aria": {
        "es": "Abrir la sección Tendencias",
        "en": "Open the Trends section",
    },
    "home_spain_description": {
        "es": (
            "Consulta informes nacionales, documentación procesada automáticamente y gráficos "
            "extraídos de publicaciones sobre la situación LGBTIQ+ en España."
        ),
        "en": (
            "Browse national reports, automatically processed documents and charts extracted "
            "from publications on the situation of LGBTIQ+ people in Spain."
        ),
    },
    "home_spain_action": {"es": "Explorar España", "en": "Explore Spain"},
    "home_spain_aria": {
        "es": "Abrir la sección España",
        "en": "Open the Spain section",
    },
    "home_didactics_description": {
        "es": (
            "Accede al glosario LGBTIQ+, recursos educativos, materiales docentes y juegos "
            "interactivos para aprender de forma sencilla."
        ),
        "en": (
            "Access the LGBTIQ+ glossary, educational resources, teaching materials and "
            "interactive games for an approachable learning experience."
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
        "es": (
            "Conoce el proyecto RainbowLens DataHub, las fuentes oficiales utilizadas, la "
            "metodología y los objetivos de la plataforma."
        ),
        "en": (
            "Discover the RainbowLens DataHub project, its official sources, methodology and "
            "the platform's goals."
        ),
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
            "Access your account to view your profile and use your personalised report "
            "templates."
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
        "es": "Configuración",
        "en": "Configuration",
    },
    "report_advanced_options": {
        "es": "Opciones avanzadas",
        "en": "Advanced options",
    },
    "report_advanced_restricted": {
        "es": (
            "Las opciones avanzadas están disponibles únicamente para "
            "determinados perfiles profesionales."
        ),
        "en": ("Advanced options are available only to selected professional profiles."),
    },
    "report_advanced_toggle": {
        "es": "Mostrar u ocultar las opciones avanzadas",
        "en": "Show or hide advanced options",
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
    "download_excel": {
        "es": "Descargar Excel",
        "en": "Download Excel",
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
            "Este país no forma parte de la Unión Europea y no está incluido "
            "en esta encuesta FRA."
        ),
        "en": (
            "This country is not part of the European Union and is not included "
            "in this FRA survey."
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
    "loading_information": {
        "es": "Cargando información...",
        "en": "Loading information...",
    },
    "loading_indicators": {
        "es": "Cargando indicadores...",
        "en": "Loading indicators...",
    },
    "updating_visualisations": {
        "es": "Actualizando visualizaciones...",
        "en": "Updating visualisations...",
    },
    "updating_map": {"es": "Actualizando mapa...", "en": "Updating map..."},
    "generating_chart": {"es": "Generando gráfico...", "en": "Generating chart..."},
    "loading_trends": {"es": "Calculando tendencia...", "en": "Calculating trend..."},
    "processing_document": {
        "es": "Procesando documento...",
        "en": "Processing document...",
    },
    "generating_report": {"es": "Generando informe...", "en": "Generating report..."},
    "uploading_file": {"es": "Subiendo archivo...", "en": "Uploading file..."},
    "importing_data": {"es": "Importando datos...", "en": "Importing data..."},
    "deleting_data": {"es": "Eliminando datos...", "en": "Deleting data..."},
    "wait_updating_data": {
        "es": "Espera mientras actualizamos los datos.",
        "en": "Please wait while we update the data.",
    },
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
    "trends_not_enough": {"es": "No hay información suficiente.", "en": "There is not enough information."},
    "trends_not_enough_projection": {
        "es": "No hay información suficiente para generar una proyección fiable. Se muestra únicamente la serie histórica disponible.",
        "en": "There is not enough information to generate a reliable projection. Only the available historical series is shown.",
    },
    "trends_exploratory_warning": {
        "es": "Estimación exploratoria: la serie contiene entre tres y cinco observaciones, por lo que solo se aplica una regresión lineal y el horizonte se limita a un año.",
        "en": "Exploratory estimate: the series contains three to five observations, so only linear regression is applied and the horizon is limited to one year.",
    },
    "trends_error_loading_series": {"es": "Error al cargar la serie.", "en": "Error loading the series."},
    "trends_error_analysis": {
        "es": "No se ha podido generar el análisis temporal.",
        "en": "The temporal analysis could not be generated.",
    },
    "trends_year_singular": {"es": "1 año", "en": "1 year"},
    "trends_years_two": {"es": "2 años", "en": "2 years"},
    "trends_years_three": {"es": "3 años", "en": "3 years"},
    "trends_historical_data": {"es": "Datos históricos", "en": "Historical data"},
    "trends_forecast": {"es": "Proyección", "en": "Projection"},
    "trends_uncertainty": {"es": "Incertidumbre estimada", "en": "Estimated uncertainty"},
    "trends_chart_title": {"es": "Evolución y proyección", "en": "Evolution and projection"},
    "trends_year": {"es": "Año", "en": "Year"},
    "trends_legal_score": {"es": "Puntuación legal", "en": "Legal score"},
    "trends_historical_observation": {"es": "Dato histórico", "en": "Historical observation"},
    "trends_projection_observation": {"es": "Proyección", "en": "Projection"},
    "trends_estimated_value": {"es": "Puntuación estimada", "en": "Estimated score"},
    "trends_estimated_interval": {"es": "Intervalo estimado", "en": "Estimated interval"},
    "trends_forecast_starts": {"es": "Inicio de la proyección", "en": "Projection starts"},
    "trends_historical_source": {
        "es": "Datos históricos: ILGA-Europe Rainbow Map.",
        "en": "Historical data: ILGA-Europe Rainbow Map.",
    },
    "trends_projection_source": {
        "es": "Proyección estadística: RainbowLens DataHub.",
        "en": "Statistical projection: RainbowLens DataHub.",
    },
    "trends_upward": {"es": "Ascendente", "en": "Upward"},
    "trends_downward": {"es": "Descendente", "en": "Downward"},
    "trends_stable": {"es": "Estable", "en": "Stable"},
    "trends_trend": {"es": "Tendencia", "en": "Trend"},
    "trends_total_change": {"es": "Cambio histórico", "en": "Historical change"},
    "trends_last_value": {"es": "Último valor", "en": "Latest value"},
    "trends_selected_model": {"es": "Modelo utilizado", "en": "Model used"},
    "trends_mean_error": {"es": "Error medio", "en": "Mean error"},
    "trends_points": {"es": "puntos", "en": "points"},
    "trends_projection_method": {"es": "Método de proyección", "en": "Projection method"},
    "trends_method_summary": {
        "es": "La proyección se calcula comparando modelos estadísticos sencillos sobre los datos históricos disponibles. Se simulan predicciones sobre años ya conocidos para medir su precisión y se selecciona el modelo con menor error sin introducir complejidad innecesaria.",
        "en": "The projection compares simple statistical models using the available historical data. Predictions are simulated for years already known to measure accuracy, and the model with the lowest error is selected without introducing unnecessary complexity.",
    },
    "trends_validation_mean_error": {"es": "Error medio de validación", "en": "Validation mean error"},
    "trends_years_used": {"es": "Años utilizados", "en": "Years used"},
    "trends_observations": {"es": "Observaciones", "en": "Observations"},
    "trends_how_calculated": {
        "es": "¿Cómo se ha calculado esta proyección?",
        "en": "How was this projection calculated?",
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
        "es": "Cada modelo se prueba mediante una ventana expansiva: se entrena con los primeros años, predice el siguiente año conocido y repite el proceso incorporando progresivamente las observaciones reales.",
        "en": "Each model is tested with an expanding window: it is trained on the earlier years, predicts the next known year, and repeats the process while progressively adding the observed values.",
    },
    "trends_error_comparison": {"es": "Comparación de errores", "en": "Error comparison"},
    "trends_model": {"es": "Modelo", "en": "Model"},
    "trends_validation_folds": {"es": "Predicciones evaluadas", "en": "Evaluated predictions"},
    "trends_model_selection": {"es": "Selección del modelo", "en": "Model selection"},
    "trends_selection_lowest_error": {
        "es": "{model} fue seleccionado porque obtuvo el menor MAE durante la validación temporal.",
        "en": "{model} was selected because it obtained the lowest MAE during temporal validation.",
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
        "es": "La banda de incertidumbre utiliza el RMSE observado en la validación temporal y aumenta con la raíz del horizonte. Es una banda de error empírica, no un intervalo de confianza probabilístico.",
        "en": "The uncertainty band uses the RMSE observed during temporal validation and grows with the square root of the horizon. It is an empirical error band, not a probabilistic confidence interval.",
    },
    "trends_uncertainty_unavailable": {
        "es": "No se muestra una banda de incertidumbre porque existen muy pocas predicciones históricas evaluables.",
        "en": "No uncertainty band is shown because too few historical predictions can be evaluated.",
    },
    "trends_limitations": {"es": "Limitaciones", "en": "Limitations"},
    "trends_limitations_detail": {
        "es": "Esta proyección es una estimación matemática basada exclusivamente en la evolución histórica de la puntuación global. Los cambios legislativos pueden producir variaciones bruscas que el modelo no puede anticipar. La estimación no representa una predicción oficial de ILGA-Europe.",
        "en": "This projection is a mathematical estimate based exclusively on the historical evolution of the overall score. Legislative changes may cause abrupt variations that the model cannot anticipate. The estimate is not an official ILGA-Europe prediction.",
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
    "statistics_initial_prompt": {
        "es": "Selecciona una categoría y un indicador para comenzar.",
        "en": "Select a category and an indicator to get started.",
    },
    "statistics_no_data": {
        "es": "No hay datos disponibles para esta selección.",
        "en": "No data is available for this selection.",
    },
    "statistics_error": {
        "es": "No se han podido cargar las estadísticas. Inténtalo de nuevo.",
        "en": "Statistics could not be loaded. Please try again.",
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
