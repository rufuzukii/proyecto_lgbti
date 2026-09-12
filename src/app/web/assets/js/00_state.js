(function (window) {
  const app = (window.RainbowLens = window.RainbowLens || {});

  const LANGUAGE_KEY = "rainbowlens-language";
  const THEME_KEY = "rainbowlens-theme";
  const SUPPORTED = ["es", "en"];
  const THEMES = ["light", "dark"];

  function isSupportedLanguage(language) {
    return SUPPORTED.includes(language);
  }

  function isSupportedTheme(theme) {
    return THEMES.includes(theme);
  }

  function storedValue(key) {
    try {
      return window.localStorage.getItem(key);
    } catch (_error) {
      return null;
    }
  }

  function currentLanguage() {
    const saved = storedValue(LANGUAGE_KEY);
    if (isSupportedLanguage(saved)) {
      return saved;
    }
    const applied = window.document && window.document.documentElement.lang;
    return isSupportedLanguage(applied) ? applied : "es";
  }

  function currentTheme() {
    const saved = storedValue(THEME_KEY);
    if (isSupportedTheme(saved)) {
      return saved;
    }
    const applied = document.documentElement.dataset.theme;
    return isSupportedTheme(applied) ? applied : "light";
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
