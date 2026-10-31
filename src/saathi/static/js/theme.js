// @ts-check
// Light is the default theme (easier to read outdoors). A person's choice is kept in this browser;
// without one, the system setting decides. A classic script in <head>, so the theme is set before
// the first paint. Pages on the same origin (the demo's two frames) follow each other through the
// `storage` event.
(() => {
  const KEY = "saathi-theme";
  const root = document.documentElement;
  const dark = window.matchMedia("(prefers-color-scheme: dark)");

  /** @returns {"light" | "dark" | null} */
  function stored() {
    try {
      const value = localStorage.getItem(KEY);
      return value === "light" || value === "dark" ? value : null;
    } catch {
      return null; // private window or blocked storage: the system setting applies
    }
  }

  /** @param {"light" | "dark"} theme */
  function apply(theme) {
    root.dataset.theme = theme;
    for (const button of document.querySelectorAll("[data-theme-toggle]")) {
      button.setAttribute("aria-pressed", String(theme === "dark"));
    }
  }

  /** @returns {"light" | "dark"} */
  const current = () => stored() ?? (dark.matches ? "dark" : "light");

  root.dataset.theme = current();
  if (window.parent !== window) root.classList.add("in-frame");
  dark.addEventListener("change", () => apply(current()));
  window.addEventListener("storage", (event) => {
    if (event.key === KEY) apply(current());
  });

  document.addEventListener("DOMContentLoaded", () => {
    for (const button of document.querySelectorAll("[data-theme-toggle]")) {
      const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      svg.setAttribute("viewBox", "0 0 24 24");
      svg.setAttribute("class", "icon");
      svg.setAttribute("aria-hidden", "true");
      svg.innerHTML =
        '<circle cx="12" cy="12" r="8.5" fill="none" stroke="currentColor" stroke-width="2"/>' +
        '<path d="M12 3.5a8.5 8.5 0 0 0 0 17z" fill="currentColor"/>';
      button.append(svg);
      button.addEventListener("click", () => {
        const next = root.dataset.theme === "dark" ? "light" : "dark";
        try {
          localStorage.setItem(KEY, next);
        } catch {
          // The choice still applies to this page view.
        }
        apply(next);
      });
    }
    apply(current());
  });
})();
