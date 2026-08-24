(function (window, document) {
  "use strict";

  let lastDialogTrigger = null;

  function currentLanguage() {
    const app = window.RainbowLens || {};
    return app.state && typeof app.state.currentLanguage === "function"
      ? app.state.currentLanguage()
      : "es";
  }

  function prepareDeletionForm(dialog) {
    const language = currentLanguage();
    const languageField = dialog.querySelector("#privacy-delete-language");
    const phraseField = dialog.querySelector("#privacy-delete-phrase");
    if (languageField) {
      languageField.value = language;
    }
    if (phraseField) {
      phraseField.placeholder = language === "en" ? "DELETE MY ACCOUNT" : "ELIMINAR MI CUENTA";
    }
    syncConfirmationValue(dialog);
  }

  function syncConfirmationValue(root) {
    const checkbox = root.querySelector("#privacy-confirm-checklist input[type='checkbox']");
    const hidden = root.querySelector("#privacy-confirm-value");
    if (hidden) {
      hidden.value = checkbox && checkbox.checked ? "yes" : "";
    }
  }

  function openDialog(dialog, trigger) {
    if (!dialog || typeof dialog.showModal !== "function" || dialog.open) {
      return;
    }
    lastDialogTrigger = trigger || document.activeElement;
    prepareDeletionForm(dialog);
    dialog.showModal();
    const firstField = dialog.querySelector("#privacy-delete-email");
    if (firstField) {
      window.setTimeout(function () {
        firstField.focus();
      }, 0);
    }
  }

  function closeDialog(dialog) {
    if (!dialog || typeof dialog.close !== "function" || !dialog.open) {
      return;
    }
    dialog.close();
    if (lastDialogTrigger && typeof lastDialogTrigger.focus === "function") {
      lastDialogTrigger.focus();
    }
    lastDialogTrigger = null;
  }

  function initializeDialogs() {
    document.querySelectorAll("[data-privacy-dialog]").forEach(function (dialog) {
      prepareDeletionForm(dialog);
      if (dialog.dataset.autoOpen === "true" && !dialog.dataset.autoOpened) {
        dialog.dataset.autoOpened = "true";
        openDialog(dialog, document.querySelector("[data-privacy-dialog-open]"));
      }
    });
  }

  function clearDeletedAccountState() {
    if (!document.querySelector("[data-privacy-account-deleted='true']")) {
      return;
    }
    try {
      Object.keys(window.localStorage).forEach(function (key) {
        if (key.indexOf("rainbowlens-") === 0) {
          window.localStorage.removeItem(key);
        }
      });
    } catch (_error) {
      // Storage can be unavailable in privacy-restricted contexts.
    }
  }

  document.addEventListener("click", function (event) {
    const opener = event.target.closest("[data-privacy-dialog-open]");
    if (opener) {
      openDialog(document.getElementById(opener.dataset.privacyDialogOpen), opener);
      return;
    }
    const closer = event.target.closest("[data-privacy-dialog-close]");
    if (closer) {
      closeDialog(closer.closest("dialog"));
    }
  });

  document.addEventListener("cancel", function (event) {
    if (event.target.matches("[data-privacy-dialog]")) {
      event.preventDefault();
      closeDialog(event.target);
    }
  });

  document.addEventListener("change", function (event) {
    if (event.target.closest("#privacy-confirm-checklist")) {
      syncConfirmationValue(event.target.closest("dialog") || document);
    }
  });

  function initialize() {
    clearDeletedAccountState();
    initializeDialogs();
  }

  const observer = new MutationObserver(initialize);
  observer.observe(document.documentElement, { childList: true, subtree: true });
  document.addEventListener("DOMContentLoaded", initialize);
  initialize();
})(window, document);
