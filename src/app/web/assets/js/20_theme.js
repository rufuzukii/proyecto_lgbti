(function (window, document) {
  const app = (window.RainbowLens = window.RainbowLens || {});
  const config = app.config;
  const state = app.state;

  function applyTheme(theme) {
    const selected = state.isSupportedTheme(theme) ? theme : "light";
    document.documentElement.dataset.theme = selected;
    document.documentElement.style.colorScheme = selected;
    if (document.body) {
      document.body.dataset.theme = selected;
    }

    document.querySelectorAll("[data-theme-option]").forEach((button) => {
      const isActive = button.dataset.themeOption === selected;
      button.classList.toggle("is-active", isActive);
      button.setAttribute("aria-pressed", isActive ? "true" : "false");
    });

    applyToggleLabels(selected, state.currentLanguage());
    restylePlotly(selected, 0);
  }

  function setTheme(theme) {
    const selected = state.isSupportedTheme(theme) ? theme : "light";
    try {
      window.localStorage.setItem(config.THEME_KEY, selected);
    } catch (_error) {
      /* The explicit selection still applies for this session. */
    }
    applyTheme(selected);
  }

  function applyToggleLabels(theme, language) {
    const selected = state.isSupportedTheme(theme) ? theme : "light";
    const lang = state.isSupportedLanguage(language) ? language : "es";
    const next = state.nextTheme(selected);
    const labels = selected === "dark"
      ? { es: "Modo oscuro", en: "Dark mode" }
      : { es: "Modo claro", en: "Light mode" };
    const label = labels[lang];
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
      if (labelNode.dataset.i18nEs !== labels.es) {
        labelNode.dataset.i18nEs = labels.es;
      }
      if (labelNode.dataset.i18nEn !== labels.en) {
        labelNode.dataset.i18nEn = labels.en;
      }
      if (app.i18n && app.i18n.setTextNodeValue) {
        app.i18n.setTextNodeValue(labelNode, label);
      }
    });
  }

  function restylePlotly(theme, attempt) {
    if (!window.Plotly) {
      if (attempt < 12) {
        window.setTimeout(() => restylePlotly(theme, attempt + 1), 120);
      }
      return;
    }

    const colors = colorsForTheme(theme);
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
      if (!isPlotlyInitialized(graph)) {
        return;
      }
      bindPlotlyThemeEvents(graph);
      if (isPlotlyThemeApplied(graph, colors)) {
        graph.dataset.themeApplied = theme;
        return;
      }
      graph.dataset.themeApplied = theme;
      window.Plotly.relayout(graph, layout).catch(() => {});
    });
  }

  function colorsForTheme(theme) {
    const dark = theme === "dark";
    return {
      paper: dark ? "#111827" : "#ffffff",
      plot: dark ? "#111827" : "#ffffff",
      font: dark ? "#f7f9fc" : "#252a31",
      axis: dark ? "#aeb8c7" : "#252a31",
      grid: dark ? "#2d3748" : "#e5e9eb",
      muted: dark ? "#c4cede" : "#475569",
      legend: dark ? "rgba(17,24,39,0.94)" : "rgba(255,255,255,0.94)",
      geoBg: dark ? "#111827" : "#ffffff",
      geoLand: dark ? "#1a2232" : "#edf1f4",
      geoOcean: "#dcebf2",
      geoCoast: dark ? "#536176" : "#b9c0ca",
      mapbox: dark ? "carto-darkmatter" : "open-street-map",
    };
  }

  function isPlotlyInitialized(graph) {
    return Boolean(
      graph &&
      graph.isConnected &&
      graph._fullLayout &&
      Array.isArray(graph.data) &&
      graph.data.length > 0 &&
      typeof graph.on === "function"
    );
  }

  function bindPlotlyThemeEvents(graph) {
    if (!graph || graph.dataset.themeEventsBound === "true" || typeof graph.on !== "function") {
      return;
    }
    graph.dataset.themeEventsBound = "true";
    graph.on("plotly_afterplot", () => {
      window.requestAnimationFrame(() => restylePlotly(state.currentTheme(), 0));
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

  app.theme = {
    applyTheme,
    applyToggleLabels,
    colorsForTheme,
    restylePlotly,
    setTheme,
  };
})(window, document);
