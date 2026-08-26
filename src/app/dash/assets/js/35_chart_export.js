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

    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    try {
      await downloadPlotlyImage(graph, meta, options);
    } catch (_errorReason) {
      setErrorVisibility(error, true);
    } finally {
      button.disabled = false;
      button.removeAttribute("aria-busy");
    }
  }

  async function downloadPlotlyImage(graph, meta, options) {
    if (meta.export_showlegend !== true
      || typeof window.Plotly.newPlot !== "function"
      || typeof document.createElement !== "function"
      || !document.body) {
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

    const currentLayout = graph.layout || {};
    const currentMargin = currentLayout.margin || {};
    const annotations = Array.isArray(currentLayout.annotations)
      ? currentLayout.annotations.slice()
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
        font: {size: 11, color: "#475569"},
      });
    }
    const exportLayout = Object.assign({}, currentLayout, {
      autosize: false,
      width: options.width,
      height: options.height,
      paper_bgcolor: "#ffffff",
      plot_bgcolor: "#ffffff",
      font: Object.assign({}, currentLayout.font || {}, {color: "#1f2937"}),
      margin: Object.assign({}, currentMargin, {bottom: Math.max(Number(currentMargin.b) || 0, 190)}),
      showlegend: true,
      legend: Object.assign({}, currentLayout.legend || {}, {
        orientation: "h",
        x: 0.5,
        xanchor: "center",
        y: -0.13,
        yanchor: "top",
        title: {text: String(meta.export_legend_title || "")},
      }),
      annotations,
    });

    try {
      await window.Plotly.newPlot(exportGraph, graph.data, exportLayout, {
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
