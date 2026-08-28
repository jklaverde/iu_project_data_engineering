// Shared chrome behavior for every docs/*.html page: sidebar filter + scroll-spy.
// Page-specific rendering (containers.html's D3 diagrams/charts) lives in its own
// script, loaded alongside this one.
(function () {
  "use strict";

  // ---- sidebar filter ----
  // Filters <a data-name="..."> links inside #tocNav [data-group] blocks (hiding a
  // group entirely once none of its links match), and — if present on the page —
  // <details class="incident" data-name="..."> entries anywhere in <main>, so the
  // same search box can narrow both the nav and a long troubleshooting-style log.
  const input = document.getElementById("filterInput");
  if (input) {
    const groups = document.querySelectorAll("#tocNav [data-group]");
    const incidents = document.querySelectorAll("details.incident[data-name]");
    // Generic third case: any row/card outside the sidebar marked data-name
    // (e.g. reference.html's file table rows) filters the same way, and its
    // parent [data-filter-group] (e.g. a <tbody> per directory) hides itself
    // once nothing inside it still matches.
    const filterRows = document.querySelectorAll("main [data-name]:not(#tocNav *):not(details.incident)");
    const filterGroups = document.querySelectorAll("[data-filter-group]");
    input.addEventListener("input", function () {
      const q = input.value.trim().toLowerCase();
      groups.forEach((group) => {
        const links = group.querySelectorAll("a");
        let anyVisible = false;
        links.forEach((a) => {
          const match = !q || a.getAttribute("data-name").toLowerCase().indexOf(q) !== -1;
          a.classList.toggle("toc-hidden", !match);
          if (match) anyVisible = true;
        });
        group.classList.toggle("toc-hidden", !anyVisible);
      });
      incidents.forEach((el) => {
        const match = !q || el.getAttribute("data-name").toLowerCase().indexOf(q) !== -1;
        el.classList.toggle("toc-hidden", !match);
        if (match && q) el.open = true;
      });
      filterRows.forEach((el) => {
        const match = !q || el.getAttribute("data-name").toLowerCase().indexOf(q) !== -1;
        el.classList.toggle("toc-hidden", !match);
      });
      filterGroups.forEach((group) => {
        const anyVisible = !!group.querySelector("[data-name]:not(.toc-hidden)");
        group.classList.toggle("toc-hidden", !anyVisible);
      });
    });
  }

  // ---- scroll-spy ----
  const navLinks = Array.prototype.slice.call(document.querySelectorAll("#tocNav a"));
  const linkById = {};
  navLinks.forEach((a) => {
    const href = a.getAttribute("href") || "";
    if (href.charAt(0) === "#") linkById[href.slice(1)] = a;
  });
  const targets = Object.keys(linkById).map((id) => document.getElementById(id)).filter(Boolean);
  if ("IntersectionObserver" in window && targets.length) {
    let current = null;
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            if (current) current.classList.remove("active");
            current = linkById[entry.target.id];
            if (current) current.classList.add("active");
          }
        });
      },
      { rootMargin: "-15% 0px -70% 0px", threshold: 0 }
    );
    targets.forEach((t) => observer.observe(t));
  }

  // ---- flash + jump to a card/section by id (used by cross-links between pages) ----
  window.docsFlash = function (id) {
    const el = document.getElementById(id);
    if (!el) return;
    el.classList.add("flash");
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    setTimeout(() => el.classList.remove("flash"), 1600);
  };
  if (window.location.hash) {
    const id = window.location.hash.slice(1);
    window.addEventListener("load", () => {
      const el = document.getElementById(id);
      if (el && el.tagName === "DETAILS") el.open = true;
      window.docsFlash(id);
    });
  }
})();
