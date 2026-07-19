(function (window, document) {
  const app = (window.RainbowLens = window.RainbowLens || {});
  const state = app.state;

  document.addEventListener("click", (event) => {
    const languageButton = event.target.closest("[data-language-toggle]");
    if (languageButton) {
      app.i18n.setLanguage(state.nextLanguage(state.currentLanguage()));
      return;
    }

    const themeButton = event.target.closest("[data-theme-option]");
    if (themeButton) {
      app.theme.setTheme(themeButton.dataset.themeOption);
      return;
    }

    const themeToggle = event.target.closest("[data-theme-toggle]");
    if (themeToggle) {
      app.theme.setTheme(themeToggle.dataset.themeTarget || state.nextTheme(state.currentTheme()));
      return;
    }

    const uploadDismiss = event.target.closest("[data-upload-dismiss]");
    if (uploadDismiss) {
      clearUploadFileInput();
      return;
    }
  });

  document.addEventListener("change", (event) => {
    if (event.target && event.target.matches(".stats-segmented-input")) {
      app.segmentedControls.syncActiveStates();
    }
  });

  document.addEventListener("submit", (event) => {
    const form = event.target.closest("[data-admin-import-form]");
    if (!form) {
      return;
    }
    const submitter = event.submitter;
    if (!submitter || submitter.name !== "action" || submitter.value !== "insert") {
      return;
    }
    const modalId = form.dataset.loadingModal;
    const modal = modalId ? document.getElementById(modalId) : null;
    if (modal) {
      modal.classList.remove("is-hidden");
      app.i18n.applyLanguage(state.currentLanguage());
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") {
      return;
    }
    const uploadDismiss = document.querySelector("[data-upload-dismiss]");
    if (uploadDismiss) {
      uploadDismiss.click();
    }
  });

  document.addEventListener("DOMContentLoaded", () => {
    app.i18n.applyLanguage(state.currentLanguage());
    app.theme.applyTheme(state.currentTheme());
    app.segmentedControls.syncActiveStates();
  });

  let pendingRefresh = null;
  let pendingRefreshTargets = emptyRefreshTargets();
  const observer = new MutationObserver((mutations) => {
    const targets = refreshTargetsFromMutations(mutations);
    if (!hasRefreshTarget(targets)) {
      return;
    }
    pendingRefreshTargets = mergeRefreshTargets(pendingRefreshTargets, targets);
    if (pendingRefresh !== null) {
      return;
    }
    pendingRefresh = window.setTimeout(() => {
      const targetsToApply = pendingRefreshTargets;
      pendingRefresh = null;
      pendingRefreshTargets = emptyRefreshTargets();
      if (targetsToApply.language) {
        app.i18n.applyLanguage(state.currentLanguage());
      }
      if (targetsToApply.segmentedControls) {
        app.segmentedControls.syncActiveStates();
      }
      if (targetsToApply.plotly) {
        app.theme.restylePlotly(state.currentTheme(), 0);
      }
    }, 80);
  });
  observer.observe(document.documentElement, { childList: true, subtree: true });

  app.theme.applyTheme(state.currentTheme());

  function emptyRefreshTargets() {
    return {
      language: false,
      segmentedControls: false,
      plotly: false,
    };
  }

  function mergeRefreshTargets(first, second) {
    return {
      language: first.language || second.language,
      segmentedControls: first.segmentedControls || second.segmentedControls,
      plotly: first.plotly || second.plotly,
    };
  }

  function hasRefreshTarget(targets) {
    return targets.language || targets.segmentedControls || targets.plotly;
  }

  function refreshTargetsFromMutations(mutations) {
    const targets = emptyRefreshTargets();
    mutations.forEach((mutation) => {
      mutation.addedNodes.forEach((node) => {
        if (!isElementNode(node)) {
          return;
        }
        targets.language =
          targets.language || nodeOrDescendantMatches(node, "[data-i18n-es][data-i18n-en]");
        targets.segmentedControls =
          targets.segmentedControls ||
          nodeOrDescendantMatches(node, ".stats-segmented-input, .dash-options-list-option");
        targets.plotly =
          targets.plotly ||
          nodeOrDescendantMatches(node, ".js-plotly-plot") ||
          Boolean(node.closest && node.closest(".js-plotly-plot"));
      });
    });
    return targets;
  }

  function isElementNode(node) {
    return node && node.nodeType === 1;
  }

  function nodeOrDescendantMatches(node, selector) {
    return node.matches(selector) || Boolean(node.querySelector(selector));
  }

  function clearUploadFileInput() {
    const upload = document.getElementById("upload-csv");
    const input = upload ? upload.querySelector("input[type='file']") : null;
    if (input) {
      input.value = "";
    }
  }
})(window, document);
