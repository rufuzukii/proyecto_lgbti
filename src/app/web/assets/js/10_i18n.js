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
    applyTranslatedAttributes(selected);
    applyLocalizedRoutes(selected);
    applyRouteMetadata(selected);
    const privacyPhrase = document.getElementById("privacy-delete-phrase");
    const privacyLanguage = document.getElementById("privacy-delete-language");
    if (privacyPhrase) {
      privacyPhrase.placeholder = selected === "en" ? "DELETE MY ACCOUNT" : "ELIMINAR MI CUENTA";
    }
    if (privacyLanguage) {
      privacyLanguage.value = selected;
    }
    document.querySelectorAll(".current-language-input").forEach((input) => {
      input.value = selected;
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

  function applyTranslatedAttributes(language) {
    ["alt", "aria-label", "title"].forEach((attribute) => {
      const esAttribute = `data-i18n-${attribute}-es`;
      const enAttribute = `data-i18n-${attribute}-en`;
      document.querySelectorAll(`[${esAttribute}][${enAttribute}]`).forEach((node) => {
        const value = node.getAttribute(language === "en" ? enAttribute : esAttribute);
        if (typeof value === "string" && node.getAttribute(attribute) !== value) {
          node.setAttribute(attribute, value);
        }
      });
    });
  }

  function applyLocalizedRoutes(language) {
    const routes = app.routes && app.routes.routes ? app.routes.routes : {};
    const pathIndex = app.routes && app.routes.pathIndex ? app.routes.pathIndex : {};
    document.querySelectorAll("a[href]").forEach((node) => {
      const current = node.getAttribute("href") || "";
      if (!current || current.startsWith("#") || current.startsWith("mailto:")) {
        return;
      }
      let parsed;
      try {
        parsed = new URL(current, window.location.origin);
      } catch (_error) {
        return;
      }
      if (parsed.origin !== window.location.origin) {
        return;
      }
      const route = routes[pathIndex[parsed.pathname]];
      if (!route || !route[language]) {
        return;
      }
      const suffix = parsed.search + parsed.hash;
      node.setAttribute("href", route[language] + suffix);
    });
  }

  function applyRouteMetadata(language) {
    const routeConfig = app.routes || {};
    const routeId = routeConfig.pathIndex ? routeConfig.pathIndex[window.location.pathname] : null;
    const route = routeConfig.routes && routeId ? routeConfig.routes[routeId] : null;
    if (!route) {
      return;
    }
    setHeadLink("canonical", null, route[language]);
    setHeadLink("alternate", "es", route.es);
    setHeadLink("alternate", "en", route.en);
    const title = routeConfig.titles && routeConfig.titles[routeId];
    if (title && title[language]) {
      document.title = `${title[language]} · RainbowLens DataHub`;
    }
  }

  function setHeadLink(rel, hreflang, path) {
    const selector = hreflang
      ? `link[rel="${rel}"][hreflang="${hreflang}"]`
      : `link[rel="${rel}"]:not([hreflang])`;
    let link = document.head.querySelector(selector);
    if (!link) {
      link = document.createElement("link");
      link.rel = rel;
      if (hreflang) {
        link.hreflang = hreflang;
      }
      document.head.insertAdjacentElement("beforeend", link);
    }
    link.href = new URL(path, window.location.origin).href;
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
