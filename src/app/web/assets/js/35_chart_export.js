(function (window, document) {
  const app = (window.RainbowLens = window.RainbowLens || {});

  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-chart-export]");
    if (!button) {
      return;
    }
    event.preventDefault();
    void downloadChart(button);
  });

  async function downloadChart(button) {
    if (button.disabled || button.getAttribute("aria-busy") === "true") {
      return;
    }

    const targetId = button.dataset.chartExportTarget;
    const wrapper = targetId ? document.getElementById(targetId) : null;
    const graph = wrapper
      ? wrapper.querySelector(".js-plotly-plot") || (wrapper.matches(".js-plotly-plot") ? wrapper : null)
      : null;
    const error = findErrorStatus(button, targetId);
    setErrorVisibility(error, false);

    if (!graph || !hasVisibleData(graph) || !window.Plotly || typeof window.Plotly.downloadImage !== "function") {
      setErrorVisibility(error, true);
      return;
    }

    const meta = graph.layout && graph.layout.meta && typeof graph.layout.meta === "object"
      ? graph.layout.meta
      : {};
    const format = String(meta.export_format || button.dataset.exportFormat || "png").toLowerCase();
    const filename = safeFilename(meta.export_filename || `rainbowlens-datahub_${targetId || "grafico"}`, format);
    const options = {
      format,
      filename,
      width: positiveInteger(meta.export_width || button.dataset.exportWidth, 1600),
      height: positiveInteger(meta.export_height || button.dataset.exportHeight, 900),
      scale: positiveNumber(meta.export_scale || button.dataset.exportScale, 2),
    };
    const theme = app.state && typeof app.state.currentTheme === "function"
      ? app.state.currentTheme()
      : document.documentElement && document.documentElement.dataset.theme === "dark"
        ? "dark"
        : "light";

    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    try {
      await downloadPlotlyImage(graph, meta, options, theme);
    } catch (_errorReason) {
      setErrorVisibility(error, true);
    } finally {
      button.disabled = false;
      button.removeAttribute("aria-busy");
    }
  }

  async function downloadPlotlyImage(graph, meta, options, theme) {
    if (typeof window.Plotly.newPlot !== "function"
      || typeof document.createElement !== "function"
      || !document.body
      || !app.theme
      || typeof app.theme.colorsForTheme !== "function") {
      await window.Plotly.downloadImage(graph, options);
      return;
    }

    const exportGraph = document.createElement("div");
    exportGraph.setAttribute("aria-hidden", "true");
    exportGraph.style.position = "fixed";
    exportGraph.style.inset = "auto auto 200vh 200vw";
    exportGraph.style.width = `${options.width}px`;
    exportGraph.style.height = `${options.height}px`;
    document.body.insertAdjacentElement("beforeend", exportGraph);

    const currentLayout = deepClone(graph.layout || {});
    if (meta.export_title) {
      currentLayout.title = Object.assign({}, currentLayout.title, {text: meta.export_title});
    }
    const exportData = deepClone(graph.data || []);
    const colors = app.theme.colorsForTheme(theme);
    const currentMargin = currentLayout.margin || {};
    const annotations = Array.isArray(currentLayout.annotations)
      ? currentLayout.annotations.map((annotation) => themedAnnotation(annotation, colors))
      : [];
    if (meta.export_source) {
      annotations.push({
        text: String(meta.export_source),
        x: 0,
        y: -0.28,
        xref: "paper",
        yref: "paper",
        xanchor: "left",
        yanchor: "top",
        align: "left",
        showarrow: false,
        font: {size: 11, color: colors.muted},
      });
    }
    const showExportLegend = meta.export_showlegend === true;
    const minimumBottomMargin = showExportLegend ? 190 : meta.export_source ? 115 : 75;
    const exportLayout = Object.assign({}, currentLayout, {
      autosize: false,
      width: options.width,
      height: options.height,
      paper_bgcolor: colors.paper,
      plot_bgcolor: colors.plot,
      font: Object.assign({}, currentLayout.font || {}, {color: colors.font}),
      title: themedTitle(currentLayout.title, colors),
      margin: Object.assign({}, currentMargin, {
        b: Math.max(Number(currentMargin.b) || 0, minimumBottomMargin),
      }),
      showlegend: showExportLegend ? true : currentLayout.showlegend,
      legend: themedLegend(currentLayout.legend, meta, colors, showExportLegend),
      hoverlabel: Object.assign({}, currentLayout.hoverlabel || {}, {
        bgcolor: colors.paper,
        bordercolor: colors.axis,
        font: Object.assign({}, (currentLayout.hoverlabel || {}).font || {}, {color: colors.font}),
      }),
      annotations,
    });
    applyLayoutTheme(exportLayout, colors);
    applyTraceTheme(exportData, colors);
    applyMapRanking(exportData, exportLayout, meta, colors);

    try {
      await window.Plotly.newPlot(exportGraph, exportData, exportLayout, {
        staticPlot: true,
        responsive: false,
        displayModeBar: false,
      });
      await window.Plotly.downloadImage(exportGraph, options);
    } finally {
      if (typeof window.Plotly.purge === "function") {
        window.Plotly.purge(exportGraph);
      }
      exportGraph.remove();
    }
  }

  function themedTitle(title, colors) {
    if (typeof title === "string") {
      return {text: title, font: {color: colors.font}};
    }
    return Object.assign({}, title || {}, {
      font: Object.assign({}, (title || {}).font || {}, {color: colors.font}),
    });
  }

  function themedLegend(legend, meta, colors, forceBottomLegend) {
    const themed = Object.assign({}, legend || {}, {
      bgcolor: colors.legend,
      bordercolor: colors.axis,
      font: Object.assign({}, (legend || {}).font || {}, {color: colors.font}),
      title: Object.assign({}, (legend || {}).title || {}, {
        font: Object.assign({}, ((legend || {}).title || {}).font || {}, {color: colors.font}),
      }),
    });
    if (!forceBottomLegend) {
      return themed;
    }
    return Object.assign(themed, {
      orientation: "h",
      x: 0.5,
      xanchor: "center",
      y: -0.13,
      yanchor: "top",
      title: Object.assign({}, themed.title, {text: String(meta.export_legend_title || "")}),
    });
  }

  function themedAnnotation(annotation, colors) {
    return Object.assign({}, annotation || {}, {
      font: Object.assign({}, (annotation || {}).font || {}, {color: colors.font}),
    });
  }

  function applyLayoutTheme(layout, colors) {
    Object.keys(layout).forEach((key) => {
      if (/^[xyz]axis\d*$/.test(key)) {
        layout[key] = Object.assign({}, layout[key] || {}, {
          color: colors.axis,
          gridcolor: colors.grid,
          linecolor: colors.axis,
          tickfont: Object.assign({}, (layout[key] || {}).tickfont || {}, {color: colors.axis}),
          title: themedTitle((layout[key] || {}).title, colors),
          zerolinecolor: colors.grid,
        });
      }
      if (/^coloraxis\d*$/.test(key)) {
        layout[key] = Object.assign({}, layout[key] || {}, {
          colorbar: themedColorbar((layout[key] || {}).colorbar, colors),
        });
      }
    });
    if (layout.geo) {
      layout.geo = Object.assign({}, layout.geo, {
        bgcolor: colors.geoBg,
        landcolor: colors.geoLand,
        oceancolor: colors.geoOcean,
        coastlinecolor: colors.geoCoast,
      });
    }
    if (layout.mapbox) {
      layout.mapbox = Object.assign({}, layout.mapbox, {style: colors.mapbox});
    }
  }

  function applyTraceTheme(data, colors) {
    data.forEach((trace) => {
      if (trace.colorbar) {
        trace.colorbar = themedColorbar(trace.colorbar, colors);
      }
      if (trace.marker && trace.marker.colorbar) {
        trace.marker.colorbar = themedColorbar(trace.marker.colorbar, colors);
      }
    });
  }

  function applyMapRanking(data, layout, meta, colors) {
    if (!Array.isArray(meta.export_map_ranking) || meta.export_map_ranking.length === 0) {
      return;
    }
    const rows = meta.export_map_ranking.filter((item) => item && item.country_name);
    if (rows.length === 0) {
      return;
    }
    if (layout.geo) {
      layout.geo = Object.assign({}, layout.geo, {domain: {x: [0, 0.7], y: [0, 1]}});
    }
    data.push({
      type: "table",
      domain: {x: [0.76, 1], y: [0, 1]},
      columnwidth: [25, 150, 58],
      header: {
        values: ["#", `<b>${String(meta.export_country_label || "")}</b>`, `<b>${String(meta.export_score_label || "")}</b>`],
        align: ["right", "left", "right"],
        fill: {color: colors.grid},
        font: {color: colors.font, size: 13},
        height: 26,
        line: {color: colors.axis},
      },
      cells: {
        values: [
          rows.map((_item, index) => index + 1),
          rows.map((item) => String(item.country_name)),
          rows.map((item) => `${Number(item.score).toFixed(2).replace(/\.00$/, "")}%`),
        ],
        align: ["right", "left", "right"],
        fill: {color: colors.paper},
        font: {color: colors.font, size: 12},
        height: 18,
        line: {color: colors.grid},
      },
    });
    const existingTitleText = typeof layout.title === "string"
      ? layout.title
      : layout.title && layout.title.text;
    if (!String(existingTitleText || "").trim()) {
      layout.title = themedTitle(
        `<b>RainbowLens DataHub</b><br><sup>${String(meta.export_map_title || "")}</sup>`,
        colors
      );
    }
    layout.annotations = Array.isArray(layout.annotations) ? layout.annotations : [];
    layout.annotations.push({
      text: `<b>${String(meta.export_ranking_title || "")}</b>`,
      x: 0.88,
      y: 1,
      xref: "paper",
      yref: "paper",
      xanchor: "center",
      // Ancla el borde inferior sobre la tabla, con independencia de la altura exportada.
      yanchor: "bottom",
      yshift: 12,
      showarrow: false,
      font: {size: 16, color: colors.font},
    });
    layout.margin = Object.assign({}, layout.margin || {}, {
      l: Math.max(Number((layout.margin || {}).l) || 0, 55),
      r: Math.max(Number((layout.margin || {}).r) || 0, 42),
      t: Math.max(Number((layout.margin || {}).t) || 0, 112),
    });
  }

  function themedColorbar(colorbar, colors) {
    return Object.assign({}, colorbar || {}, {
      outlinecolor: colors.axis,
      tickcolor: colors.axis,
      tickfont: Object.assign({}, (colorbar || {}).tickfont || {}, {color: colors.axis}),
      title: themedTitle((colorbar || {}).title, colors),
    });
  }

  function deepClone(value) {
    if (typeof window.structuredClone === "function") {
      return window.structuredClone(value);
    }
    return JSON.parse(JSON.stringify(value));
  }

  function hasVisibleData(graph) {
    return Array.isArray(graph.data) && graph.data.some((trace) => trace && trace.visible !== false);
  }

  function findErrorStatus(button, targetId) {
    const control = button.parentElement;
    const localError = control && targetId
      ? control.querySelector(`[data-chart-export-error="${targetId}"]`)
      : null;
    if (localError) {
      return localError;
    }
    const panel = button.closest(".stats-panel");
    return panel && targetId
      ? panel.querySelector(`[data-chart-export-error="${targetId}"]`)
      : null;
  }

  function setErrorVisibility(error, visible) {
    if (error) {
      error.hidden = !visible;
    }
  }

  function safeFilename(value, format) {
    const withoutExtension = String(value || "")
      .replace(new RegExp(`\\.${format}$`, "i"), "")
      .replace(/[^a-zA-Z0-9_-]+/g, "-")
      .replace(/^-+|-+$/g, "");
    return withoutExtension || "rainbowlens-datahub_grafico";
  }

  function positiveInteger(value, fallback) {
    const parsed = Number.parseInt(value, 10);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
  }

  function positiveNumber(value, fallback) {
    const parsed = Number(value);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
  }

  app.chartExport = {
    downloadChart,
  };
})(window, document);
