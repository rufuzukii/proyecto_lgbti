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
    const filename = safeFilename(meta.export_filename || `rainbow-lens_${targetId || "grafico"}`, format);
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
      await window.Plotly.downloadImage(graph, options);
    } catch (_errorReason) {
      setErrorVisibility(error, true);
    } finally {
      button.disabled = false;
      button.removeAttribute("aria-busy");
    }
  }

  function hasVisibleData(graph) {
    return Array.isArray(graph.data) && graph.data.some((trace) => trace && trace.visible !== false);
  }

  function findErrorStatus(button, targetId) {
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
    return withoutExtension || "rainbow-lens_grafico";
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
