(function (window) {
  const app = (window.RainbowLens = window.RainbowLens || {});

  const LANGUAGE_KEY = "rainbowlens-language";
  const THEME_KEY = "rainbowlens-theme";
  const SUPPORTED = ["es", "en"];
  const THEMES = ["light", "dark"];
  const LABELS = [
    ["Situaci\u00f3n legal LGBTIQ+ en Europa", "LGBTIQ+ legal situation in Europe"],
    ["Discriminaci\u00f3n y datos sociales", "Discrimination and social data"],
    ["Encuesta europea LGBTIQ+", "European LGBTIQ+ survey"],
    ["Mapa legal europeo", "European legal map"],
    ["Estado LGBTIQ+ en Espa\u00f1a", "LGBTIQ+ status in Spain"],
    ["Fuente de datos", "Data source"],
    ["Selecciona una fuente", "Select a data source"],
    ["No hay fuentes de datos disponibles.", "No data sources are available."],
    ["No hay fuentes de datos", "No data sources"],
    ["No se han encontrado colecciones espa\u00f1olas disponibles.", "No Spanish collections were found."],
    ["Anterior", "Previous"],
    ["Siguiente", "Next"],
    ["No hay secciones disponibles", "No sections available"],
    ["La secci\u00f3n seleccionada ya no est\u00e1 disponible", "The selected section is no longer available"],
    ["Documento", "Document"],
    ["Selecciona un documento", "Select a document"],
    ["Selecciona un documento para cargar sus indicadores.", "Select a document to load its indicators."],
    ["No hay documentos disponibles", "No documents available"],
    ["El documento seleccionado ya no est\u00e1 disponible", "The selected document is no longer available"],
    ["Selecciona una categor\u00eda", "Select a category"],
    ["Selecciona primero una categor\u00eda", "Select a category first"],
    ["Selecciona un indicador", "Select an indicator"],
    ["Selecciona un criterio", "Select a criterion"],
    ["Selecciona un indicador social", "Select a social indicator"],
    ["Selecciona en el mapa o aqu\u00ed", "Select on the map or here"],
    ["Activa la vista de datos sociales", "Enable the social data view"],
    ["No hay informaci\u00f3n disponible para esta categor\u00eda", "No information is available for this category"],
    ["Todos los criterios de la categor\u00eda", "All criteria in the category"],
    ["Sin organizaci\u00f3n", "No organization"],
  ];

  function isSupportedLanguage(language) {
    return SUPPORTED.includes(language);
  }

  function isSupportedTheme(theme) {
    return THEMES.includes(theme);
  }

  function currentLanguage() {
    const saved = window.localStorage.getItem(LANGUAGE_KEY);
    return isSupportedLanguage(saved) ? saved : "es";
  }

  function currentTheme() {
    const saved = window.localStorage.getItem(THEME_KEY);
    return isSupportedTheme(saved) ? saved : "light";
  }

  function labelFor(language) {
    return language === "es" ? "ES" : "EN";
  }

  function nextLanguage(language) {
    return language === "es" ? "en" : "es";
  }

  function nextTheme(theme) {
    return theme === "dark" ? "light" : "dark";
  }

  app.config = {
    LABELS,
    LANGUAGE_KEY,
    SUPPORTED,
    THEME_KEY,
    THEMES,
  };

  app.state = {
    currentLanguage,
    currentTheme,
    isSupportedLanguage,
    isSupportedTheme,
    labelFor,
    nextLanguage,
    nextTheme,
  };
})(window);
