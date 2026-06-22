(function () {
  const LANGUAGE_KEY = "rainbowlens-language";
  const THEME_KEY = "rainbowlens-theme";
  const SUPPORTED = new Set(["es", "en"]);
  const THEMES = new Set(["light", "dark"]);

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

    restylePlotly(selected);
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
    }
  });

  document.addEventListener("DOMContentLoaded", () => {
    applyLanguage(currentLanguage());
    applyTheme(currentTheme());
  });

  const observer = new MutationObserver(() => {
    applyLanguage(currentLanguage());
    applyTheme(currentTheme());
  });
  observer.observe(document.documentElement, { childList: true, subtree: true });
  applyTheme(currentTheme());

  function restylePlotly(theme) {
    if (!window.Plotly) {
      return;
    }

    const dark = theme === "dark";
    const layout = {
      paper_bgcolor: dark ? "#111827" : "#ffffff",
      plot_bgcolor: dark ? "#111827" : "#ffffff",
      "font.color": dark ? "#f7f9fc" : "#252a31",
      "xaxis.color": dark ? "#aeb8c7" : "#252a31",
      "yaxis.color": dark ? "#aeb8c7" : "#252a31",
      "xaxis.gridcolor": dark ? "#2d3748" : "#e5e9eb",
      "yaxis.gridcolor": dark ? "#2d3748" : "#e5e9eb",
      "geo.bgcolor": dark ? "#111827" : "#ffffff",
      "geo.landcolor": dark ? "#1a2232" : "#edf1f4",
      "geo.oceancolor": dark ? "#0a0e17" : "#dcebf2",
      "geo.coastlinecolor": dark ? "#536176" : "#b9c0ca",
      "mapbox.style": dark ? "carto-darkmatter" : "open-street-map",
    };

    document.querySelectorAll(".js-plotly-plot").forEach((graph) => {
      if (graph.dataset.themeApplied === theme) {
        return;
      }
      graph.dataset.themeApplied = theme;
      window.Plotly.relayout(graph, layout).catch(() => {});
    });
  }
})();
