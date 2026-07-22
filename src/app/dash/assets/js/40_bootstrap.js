(function (window, document) {
  const app = (window.RainbowLens = window.RainbowLens || {});
  const state = app.state;

  document.addEventListener("click", (event) => {
    const navigationToggle = event.target.closest("[data-nav-menu-toggle]");
    if (navigationToggle) {
      toggleNavigation(navigationToggle);
      return;
    }

    const languageButton = event.target.closest("[data-language-toggle]");
    if (languageButton) {
      const dashLanguageToggle = document.getElementById("app-language-toggle");
      if (dashLanguageToggle) {
        dashLanguageToggle.click();
      } else {
        app.i18n.setLanguage(state.nextLanguage(state.currentLanguage()));
      }
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

    const navigationLink = event.target.closest(".nav-menu a");
    if (navigationLink) {
      closeNavigation(navigationLink.closest(".navbar"));
      return;
    }

    const openNavigation = document.querySelector(".navbar.is-menu-open");
    if (openNavigation && !openNavigation.contains(event.target)) {
      closeNavigation(openNavigation);
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
    closeNavigation(document.querySelector(".navbar.is-menu-open"));
    const uploadDismiss = document.querySelector("[data-upload-dismiss]");
    if (uploadDismiss) {
      uploadDismiss.click();
    }
  });

  document.addEventListener("DOMContentLoaded", () => {
    app.i18n.applyLanguage(state.currentLanguage());
    app.theme.applyTheme(state.currentTheme());
    app.segmentedControls.syncActiveStates();
    observeLazyImages(document);
  });

  const lazyImageObserver = "IntersectionObserver" in window
    ? new IntersectionObserver((entries, imageObserver) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) {
            return;
          }
          loadLazyImage(entry.target);
          imageObserver.unobserve(entry.target);
        });
      }, { rootMargin: "240px 0px" })
    : null;

  let pendingRefresh = null;
  let pendingRefreshTargets = emptyRefreshTargets();
  const observer = new MutationObserver((mutations) => {
    const targets = refreshTargetsFromMutations(mutations);
    if (targets.language) {
      app.i18n.applyLanguage(state.currentLanguage());
      targets.language = false;
      targets.themeControls = false;
    } else if (targets.themeControls) {
      app.theme.applyToggleLabels(state.currentTheme(), state.currentLanguage());
      targets.themeControls = false;
    }
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
  observer.observe(document.documentElement, {
    childList: true,
    subtree: true,
    characterData: true,
    attributes: true,
    attributeFilter: ["data-i18n-es", "data-i18n-en"],
  });

  app.i18n.applyLanguage(state.currentLanguage());
  app.theme.applyTheme(state.currentTheme());

  const compactNavigation = window.matchMedia("(max-width: 1199px)");
  const handleNavigationBreakpoint = (event) => {
    if (!event.matches) {
      closeNavigation(document.querySelector(".navbar.is-menu-open"));
    }
  };
  if (typeof compactNavigation.addEventListener === "function") {
    compactNavigation.addEventListener("change", handleNavigationBreakpoint);
  } else if (typeof compactNavigation.addListener === "function") {
    compactNavigation.addListener(handleNavigationBreakpoint);
  }

  function emptyRefreshTargets() {
    return {
      language: false,
      segmentedControls: false,
      plotly: false,
      themeControls: false,
    };
  }

  function mergeRefreshTargets(first, second) {
    return {
      language: first.language || second.language,
      segmentedControls: first.segmentedControls || second.segmentedControls,
      plotly: first.plotly || second.plotly,
      themeControls: first.themeControls || second.themeControls,
    };
  }

  function hasRefreshTarget(targets) {
    return targets.language || targets.segmentedControls || targets.plotly || targets.themeControls;
  }

  function refreshTargetsFromMutations(mutations) {
    const targets = emptyRefreshTargets();
    mutations.forEach((mutation) => {
      if (mutation.type === "characterData") {
        const parent = mutation.target && mutation.target.parentElement;
        targets.language =
          targets.language ||
          Boolean(parent && parent.matches("[data-i18n-es][data-i18n-en]"));
        return;
      }
      if (mutation.type === "attributes") {
        const target = mutation.target;
        targets.language =
          targets.language ||
          Boolean(target && target.matches && target.matches("[data-i18n-es][data-i18n-en]"));
        return;
      }
      mutation.addedNodes.forEach((node) => {
        if (!isElementNode(node)) {
          return;
        }
        observeLazyImages(node);
        targets.language =
          targets.language || nodeOrDescendantMatches(node, "[data-i18n-es][data-i18n-en]");
        targets.segmentedControls =
          targets.segmentedControls ||
          nodeOrDescendantMatches(node, ".stats-segmented-input, .dash-options-list-option");
        targets.plotly =
          targets.plotly ||
          nodeOrDescendantMatches(node, ".js-plotly-plot") ||
          Boolean(node.closest && node.closest(".js-plotly-plot"));
        targets.themeControls =
          targets.themeControls ||
          nodeOrDescendantMatches(node, "[data-theme-toggle], [data-theme-option], [data-theme-label]");
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

  function observeLazyImages(root) {
    const images = [];
    if (root.matches && root.matches("img[data-lazy-src]")) {
      images.push(root);
    }
    if (root.querySelectorAll) {
      images.push(...root.querySelectorAll("img[data-lazy-src]"));
    }
    images.forEach((image) => {
      if (image.dataset.lazyObserved === "true" || !image.dataset.lazySrc) {
        return;
      }
      image.dataset.lazyObserved = "true";
      if (lazyImageObserver) {
        lazyImageObserver.observe(image);
      } else {
        loadLazyImage(image);
      }
    });
  }

  function loadLazyImage(image) {
    const source = image.dataset.lazySrc;
    if (!source) {
      return;
    }
    const figure = image.closest(".report-figure");
    const fallback = figure && figure.querySelector(".report-figure-load-error");
    image.hidden = false;
    if (fallback) {
      fallback.hidden = true;
    }
    image.addEventListener("load", () => {
      image.hidden = false;
      image.classList.add("is-loaded");
      image.removeAttribute("data-lazy-src");
      if (fallback) {
        fallback.hidden = true;
      }
    }, { once: true });
    image.addEventListener("error", () => {
      image.hidden = true;
      if (fallback) {
        fallback.hidden = false;
      }
    }, { once: true });
    image.src = source;
  }

  function clearUploadFileInput() {
    const upload = document.getElementById("upload-csv");
    const input = upload ? upload.querySelector("input[type='file']") : null;
    if (input) {
      input.value = "";
    }
  }

  function toggleNavigation(button) {
    const navigation = button.closest(".navbar");
    if (!navigation) {
      return;
    }
    setNavigationState(navigation, !navigation.classList.contains("is-menu-open"));
  }

  function closeNavigation(navigation) {
    if (navigation) {
      setNavigationState(navigation, false);
    }
  }

  function setNavigationState(navigation, isOpen) {
    navigation.classList.toggle("is-menu-open", isOpen);
    const button = navigation.querySelector("[data-nav-menu-toggle]");
    if (!button) {
      return;
    }
    button.setAttribute("aria-expanded", String(isOpen));
    const english = state.currentLanguage() === "en";
    button.setAttribute(
      "aria-label",
      isOpen ? (english ? "Close menu" : "Cerrar menú") : (english ? "Open menu" : "Abrir menú")
    );
  }
})(window, document);
