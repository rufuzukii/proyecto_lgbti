(function (window, document) {
  const app = (window.RainbowLens = window.RainbowLens || {});

  function syncActiveStates(root) {
    findControls(root).forEach((control) => {
      control.querySelectorAll(".stats-segmented-label").forEach((label) => {
        label.classList.remove("is-active", "active");
        label.removeAttribute("aria-pressed");
      });

      control.querySelectorAll(".dash-options-list-option").forEach((option) => {
        const input = option.querySelector(".stats-segmented-input");
        setActiveOption(option, Boolean(input && input.checked));
      });
    });
  }

  function setActiveOption(option, active) {
    option.classList.toggle("is-active", active);
    option.classList.toggle("active", active);
    option.setAttribute("aria-pressed", active ? "true" : "false");
  }

  function findControls(root) {
    const scope = root && root.querySelectorAll ? root : document;
    const controls = [];
    if (scope.matches && scope.matches(".stats-segmented-control")) {
      controls.push(scope);
    }
    scope.querySelectorAll(".stats-segmented-control").forEach((control) => {
      controls.push(control);
    });
    return controls;
  }

  app.segmentedControls = {
    syncActiveStates,
  };
})(window, document);
