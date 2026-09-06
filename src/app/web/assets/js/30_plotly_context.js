(function (window, document) {
  const app = (window.RainbowLens = window.RainbowLens || {});
  const observed = new WeakSet();
  const pending = new WeakSet();
  const canvas = document.createElement("canvas");
  const context = canvas.getContext("2d");
  const resizeObserver = new ResizeObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.target.isConnected) schedule(entry.target);
      else resizeObserver.unobserve(entry.target);
    });
  });

  function escape(text) {
    return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  function wrap(text, width, font) {
    context.font = font;
    const lines = [];
    let line = "";
    String(text || "").split(/\s+/).forEach((word) => {
      if (line && context.measureText(`${line} ${word}`).width > width) {
        lines.push(escape(line));
        line = word;
      } else {
        line = line ? `${line} ${word}` : word;
      }
    });
    if (line) lines.push(escape(line));
    return lines;
  }

  function schedule(graph) {
    if (pending.has(graph)) return;
    pending.add(graph);
    window.requestAnimationFrame(async () => {
      try {
        if (!graph.isConnected || !graph._fullLayout || !window.Plotly) return;
        const meta = graph.layout.meta || {};
        if (!meta.context_title) return;
        const width = graph.clientWidth - 32;
        if (width < 100) return;
        const family = graph._fullLayout.font.family;
        const title = wrap(meta.context_title, width, `bold 18px ${family}`);
        const subtitle = wrap(meta.context_subtitle, width, `12px ${family}`);
        const text = `<b>${title.join("<br>")}</b><br><sup>${subtitle.join("<br>")}</sup>`;
        const top = 40 + title.length * 23 + subtitle.length * 18;
        if (graph.layout.title.text === text && graph.layout.margin.t === top) return;
        await window.Plotly.relayout(graph, {"title.text": text, "margin.t": top});
      } catch (error) {
        // Navigating away can remove the plot while Plotly finishes a resize.
        if (graph.isConnected) throw error;
      } finally {
        pending.delete(graph);
      }
    });
  }

  function observe() {
    document.querySelectorAll(".js-plotly-plot").forEach((graph) => {
      if (!graph._fullLayout || !graph.layout.meta?.context_title) return;
      if (!observed.has(graph)) {
        observed.add(graph);
        resizeObserver.observe(graph);
        graph.on("plotly_afterplot", () => schedule(graph));
        graph.on("plotly_purge", () => resizeObserver.unobserve(graph));
      }
      schedule(graph);
    });
  }

  app.charts = {observe};
})(window, document);
