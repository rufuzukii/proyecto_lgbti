(function (window, document) {
  const app = (window.RainbowLens = window.RainbowLens || {});
  let refreshPending = false;

  function enhanceFields(root) {
    const scope = root && root.querySelectorAll ? root : document;
    scope.querySelectorAll("input, select, textarea").forEach((field) => {
      if (!field.id && !field.getAttribute("name")) {
        const fieldId = uniqueFieldId(field);
        field.id = fieldId;
        field.setAttribute("name", fieldId);
      }

      if (field.classList.contains("dash-dropdown-focus-target")) {
        field.setAttribute("autocomplete", "off");
      }

      if (!hasAccessibleLabel(field)) {
        addInternalAccessibleName(field);
      }
    });
  }

  function uniqueFieldId(field) {
    const dropdownOwner = field.classList.contains("dash-dropdown-focus-target")
      ? field.closest(".dash-dropdown-wrapper")?.querySelector(".dash-dropdown[id]")
      : null;
    const owner = dropdownOwner || field.closest("[id]");
    const ownerKey = safeKey(owner && owner.id ? owner.id : "dash-field");
    const suffix = field.classList.contains("dash-range-slider-min-input")
      ? "minimum"
      : field.classList.contains("dash-range-slider-max-input")
        ? "maximum"
        : field.classList.contains("dash-dropdown-focus-target")
          ? "focus-target"
          : `input-${fieldIndex(field) + 1}`;
    const base = `${ownerKey}-${suffix}`;
    let candidate = base;
    let duplicate = 2;
    while (document.getElementById(candidate) && document.getElementById(candidate) !== field) {
      candidate = `${base}-${duplicate}`;
      duplicate += 1;
    }
    return candidate;
  }

  function fieldIndex(field) {
    const owner = field.closest("[id]") || field.parentElement;
    if (!owner) {
      return 0;
    }
    return Array.from(owner.querySelectorAll("input, select, textarea")).indexOf(field);
  }

  function safeKey(value) {
    const clean = String(value || "dash-field")
      .replace(/[^A-Za-z0-9_-]+/g, "-")
      .replace(/^-+|-+$/g, "");
    return clean || "dash-field";
  }

  function hasAccessibleLabel(field) {
    if (field.getAttribute("aria-label") || field.getAttribute("aria-labelledby")) {
      return true;
    }
    if (field.closest("label")) {
      return true;
    }
    return Array.from(document.querySelectorAll("label[for]")).some(
      (label) => label.getAttribute("for") === field.id
    );
  }

  function addInternalAccessibleName(field) {
    const labels = internalLabelText(field);
    field.setAttribute("data-i18n-aria-label-es", labels.es);
    field.setAttribute("data-i18n-aria-label-en", labels.en);
    field.setAttribute("aria-label", currentLanguage() === "en" ? labels.en : labels.es);
  }

  function internalLabelText(field) {
    if (field.classList.contains("dash-range-slider-min-input")) {
      return { es: "Valor mínimo del rango", en: "Minimum range value" };
    }
    if (field.classList.contains("dash-range-slider-max-input")) {
      return { es: "Valor máximo del rango", en: "Maximum range value" };
    }
    const owner = field.closest(".dash-dropdown-wrapper");
    const button = owner && owner.querySelector(".dash-dropdown[id]");
    const visibleLabel = button && Array.from(document.querySelectorAll("label[for]")).find(
      (label) => label.getAttribute("for") === button.id
    );
    const translatedLabel = visibleLabel && (
      visibleLabel.matches("[data-i18n-es][data-i18n-en]")
        ? visibleLabel
        : visibleLabel.querySelector("[data-i18n-es][data-i18n-en]")
    );
    const fallbackText = String(
      (visibleLabel && visibleLabel.textContent) ||
      (button && button.getAttribute("aria-label")) ||
      (button && button.id) ||
      "Control"
    ).trim();
    const spanishText = String(
      (translatedLabel && translatedLabel.getAttribute("data-i18n-es")) || fallbackText
    ).trim();
    const englishText = String(
      (translatedLabel && translatedLabel.getAttribute("data-i18n-en")) || fallbackText
    ).trim();
    return {
      es: `${spanishText} (control auxiliar)`,
      en: `${englishText} (auxiliary control)`,
    };
  }

  function currentLanguage() {
    return document.documentElement.lang === "en" ? "en" : "es";
  }

  function scheduleEnhancement() {
    if (refreshPending) {
      return;
    }
    refreshPending = true;
    window.requestAnimationFrame(() => {
      refreshPending = false;
      enhanceFields(document);
    });
  }

  const observer = new MutationObserver(scheduleEnhancement);
  observer.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["aria-label", "id", "name"],
    childList: true,
    subtree: true,
  });
  document.addEventListener("DOMContentLoaded", scheduleEnhancement);
  scheduleEnhancement();

  app.formAccessibility = { enhanceFields };
})(window, document);
