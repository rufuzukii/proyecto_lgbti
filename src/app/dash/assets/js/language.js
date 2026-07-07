(function () {
  const LANGUAGE_KEY = "rainbowlens-language";
  const THEME_KEY = "rainbowlens-theme";
  const SUPPORTED = new Set(["es", "en"]);
  const THEMES = new Set(["light", "dark"]);
  const LABELS = [
    ["Situacion legal LGBTIQ+ en Europa", "LGBTIQ+ legal situation in Europe"],
    ["Discriminacion y datos sociales", "Discrimination and social data"],
    ["Selecciona una categoria", "Select a category"],
    ["Selecciona primero una categoria", "Select a category first"],
    ["Selecciona un topico", "Select a topic"],
    ["Activa la vista FRA", "Enable the FRA view"],
    ["No hay documentos para esta categoria", "No documents for this category"],
  ];

  function currentLanguage() {
    const saved = window.localStorage.getItem(LANGUAGE_KEY);
    return SUPPORTED.has(saved) ? saved : "es";
  }

  function currentTheme() {
    const saved = window.localStorage.getItem(THEME_KEY);
    return THEMES.has(saved) ? saved : "light";
  }

  function labelFor(lang) {
    return lang === "es" ? "ES" : "EN";
  }

  function nextLanguage(lang) {
    return lang === "es" ? "en" : "es";
  }

  function nextTheme(theme) {
    return theme === "dark" ? "light" : "dark";
  }

  function applyLanguage(lang) {
    const language = SUPPORTED.has(lang) ? lang : "es";
    document.documentElement.lang = language;
    if (document.body) {
      document.body.dataset.language = language;
    }

    document.querySelectorAll("[data-i18n-es][data-i18n-en]").forEach((node) => {
      const value = language === "es" ? node.dataset.i18nEs : node.dataset.i18nEn;
      if (typeof value === "string" && node.textContent !== value) {
        node.textContent = value;
      }
    });
    applySelectTranslations(language);

    document.querySelectorAll("[data-language-toggle]").forEach((button) => {
      const label = labelFor(language);
      button.setAttribute(
        "aria-label",
        language === "es" ? "Cambiar idioma a inglés" : "Switch language to Spanish"
      );
      button.setAttribute("title", button.getAttribute("aria-label"));
      if (button.textContent !== label) {
        button.textContent = label;
      }
    });
    applyThemeToggleLabels(currentTheme(), language);
  }

  function setLanguage(lang) {
    window.localStorage.setItem(LANGUAGE_KEY, lang);
    applyLanguage(lang);
  }

  function applyTheme(theme) {
    const selected = THEMES.has(theme) ? theme : "light";
    document.documentElement.dataset.theme = selected;
    if (document.body) {
      document.body.dataset.theme = selected;
    }

    document.querySelectorAll("[data-theme-option]").forEach((button) => {
      const isActive = button.dataset.themeOption === selected;
      button.classList.toggle("is-active", isActive);
      button.setAttribute("aria-pressed", isActive ? "true" : "false");
    });
    applyThemeToggleLabels(selected, currentLanguage());

    restylePlotly(selected, 0);
  }

  function setTheme(theme) {
    window.localStorage.setItem(THEME_KEY, theme);
    applyTheme(theme);
  }

  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-language-toggle]");
    if (button) {
      setLanguage(nextLanguage(currentLanguage()));
      return;
    }

    const themeButton = event.target.closest("[data-theme-option]");
    if (themeButton) {
      setTheme(themeButton.dataset.themeOption);
      return;
    }

    const themeToggle = event.target.closest("[data-theme-toggle]");
    if (themeToggle) {
      setTheme(themeToggle.dataset.themeTarget || nextTheme(currentTheme()));
    }
  });

  document.addEventListener("DOMContentLoaded", () => {
    applyLanguage(currentLanguage());
    applyTheme(currentTheme());
  });

  let pendingRefresh = null;
  const observer = new MutationObserver(() => {
    if (pendingRefresh !== null) {
      return;
    }
    pendingRefresh = window.setTimeout(() => {
      pendingRefresh = null;
      applyLanguage(currentLanguage());
      restylePlotly(currentTheme(), 0);
    }, 80);
  });
  observer.observe(document.documentElement, { childList: true, subtree: true });
  applyTheme(currentTheme());

  function restylePlotly(theme, attempt) {
    if (!window.Plotly) {
      if (attempt < 12) {
        window.setTimeout(() => restylePlotly(theme, attempt + 1), 120);
      }
      return;
    }

    const dark = theme === "dark";
    const colors = {
      paper: dark ? "#111827" : "#ffffff",
      plot: dark ? "#111827" : "#ffffff",
      font: dark ? "#f7f9fc" : "#252a31",
      axis: dark ? "#aeb8c7" : "#252a31",
      grid: dark ? "#2d3748" : "#e5e9eb",
      geoBg: dark ? "#111827" : "#ffffff",
      geoLand: dark ? "#1a2232" : "#edf1f4",
      geoOcean: dark ? "#0a0e17" : "#dcebf2",
      geoCoast: dark ? "#536176" : "#b9c0ca",
      mapbox: dark ? "carto-darkmatter" : "open-street-map",
    };
    const layout = {
      paper_bgcolor: colors.paper,
      plot_bgcolor: colors.plot,
      "font.color": colors.font,
      "xaxis.color": colors.axis,
      "yaxis.color": colors.axis,
      "xaxis.gridcolor": colors.grid,
      "yaxis.gridcolor": colors.grid,
      "geo.bgcolor": colors.geoBg,
      "geo.landcolor": colors.geoLand,
      "geo.oceancolor": colors.geoOcean,
      "geo.coastlinecolor": colors.geoCoast,
      "mapbox.style": colors.mapbox,
    };

    document.querySelectorAll(".js-plotly-plot").forEach((graph) => {
      if (isPlotlyThemeApplied(graph, colors)) {
        graph.dataset.themeApplied = theme;
        return;
      }
      graph.dataset.themeApplied = theme;
      window.Plotly.relayout(graph, layout).catch(() => {});
    });
  }

  function isPlotlyThemeApplied(graph, colors) {
    const layout = graph.layout;
    if (!layout) {
      return false;
    }
    if (layout.paper_bgcolor !== colors.paper || layout.plot_bgcolor !== colors.plot) {
      return false;
    }
    if (layout.geo) {
      return (
        layout.geo.bgcolor === colors.geoBg &&
        layout.geo.landcolor === colors.geoLand &&
        layout.geo.oceancolor === colors.geoOcean &&
        layout.geo.coastlinecolor === colors.geoCoast
      );
    }
    if (layout.mapbox) {
      return layout.mapbox.style === colors.mapbox;
    }
    return true;
  }

  function applyThemeToggleLabels(theme, language) {
    const selected = THEMES.has(theme) ? theme : "light";
    const lang = SUPPORTED.has(language) ? language : "es";
    const next = nextTheme(selected);
    const label =
      selected === "dark"
        ? lang === "es"
          ? "Modo oscuro"
          : "Dark mode"
        : lang === "es"
          ? "Modo claro"
          : "Light mode";
    const accessibleLabel =
      selected === "dark"
        ? lang === "es"
          ? "Cambiar a modo claro"
          : "Switch to light mode"
        : lang === "es"
          ? "Cambiar a modo oscuro"
          : "Switch to dark mode";

    document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
      button.dataset.themeTarget = next;
      button.dataset.themeState = selected;
      button.setAttribute("aria-label", accessibleLabel);
      button.setAttribute("title", accessibleLabel);
      button.setAttribute("aria-pressed", selected === "dark" ? "true" : "false");
    });

    document.querySelectorAll("[data-theme-label]").forEach((labelNode) => {
      if (labelNode && labelNode.textContent !== label) {
        labelNode.textContent = label;
      }
    });
  }

  function applySelectTranslations(language) {
    const fromIndex = language === "es" ? 1 : 0;
    const toIndex = language === "es" ? 0 : 1;
    document
      .querySelectorAll(
        ".Select-value-label, .Select-placeholder, .Select-option, .VirtualizedSelectOption, .dash-dropdown-value"
      )
      .forEach((node) => {
        const cleanText = node.textContent.trim();
        const match = LABELS.find((pair) => pair[fromIndex] === cleanText);
        if (match && node.textContent !== match[toIndex]) {
          node.textContent = match[toIndex];
        }
      });
  }
})();
