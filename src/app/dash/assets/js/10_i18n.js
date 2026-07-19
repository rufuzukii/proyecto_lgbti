(function (window, document) {
  const app = (window.RainbowLens = window.RainbowLens || {});
  const config = app.config;
  const state = app.state;

  function applyLanguage(language) {
    const selected = state.isSupportedLanguage(language) ? language : "es";
    document.documentElement.lang = selected;
    if (document.body) {
      document.body.dataset.language = selected;
    }

    document.querySelectorAll("[data-i18n-es][data-i18n-en]").forEach((node) => {
      const value = selected === "es" ? node.dataset.i18nEs : node.dataset.i18nEn;
      setTextNodeValue(node, value);
    });

    if (app.segmentedControls) {
      app.segmentedControls.syncActiveStates();
    }

    document.querySelectorAll("[data-language-toggle]").forEach((button) => {
      const label = state.labelFor(selected);
      const ariaLabel = selected === "es" ? "Cambiar idioma a ingl\u00e9s" : "Switch language to Spanish";
      button.setAttribute("aria-label", ariaLabel);
      button.setAttribute("title", ariaLabel);
      setTextNodeValue(button, label);
    });

    if (app.theme) {
      app.theme.applyToggleLabels(state.currentTheme(), selected);
    }
  }

  function setLanguage(language) {
    window.localStorage.setItem(config.LANGUAGE_KEY, language);
    applyLanguage(language);
  }

  function applySelectTranslations(_language) {
    // Dash owns dropdown internals. Mutating .Select-* text nodes here can
    // race React unmounts and trigger removeChild errors.
  }

  function setTextNodeValue(node, value) {
    if (!node || typeof value !== "string") {
      return;
    }
    if (node.childNodes.length !== 1 || !node.firstChild || node.firstChild.nodeType !== 3) {
      return;
    }
    if (node.firstChild.nodeValue !== value) {
      node.firstChild.nodeValue = value;
    }
  }

  app.i18n = {
    applyLanguage,
    applySelectTranslations,
    setTextNodeValue,
    setLanguage,
  };
})(window, document);
