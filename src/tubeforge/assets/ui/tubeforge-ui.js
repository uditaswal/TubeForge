/*
  TubeForge shared UI behaviour. Plain JavaScript, no framework, no build step.
  Every behaviour is switched on by a data attribute in the HTML, so pages never need custom wiring:

    data-nav-open                 button that opens the mobile navigation drawer
    data-nav-close                button (or backdrop) that closes it
    data-dialog-open="<id>"       button that opens <dialog id="<id>"> as a modal
    data-dialog-close             button inside a dialog that closes it
    data-copy="<text>"            button that copies <text>; its label changes to "Copied" for 1.5 s

  Add new behaviours here (one function each) and document the attribute above and in design/DESIGN.md.
*/
(function () {
  "use strict";

  function setNav(open) {
    var nav = document.querySelector("[data-nav]");
    var backdrop = document.querySelector("[data-nav-close].tf-nav-backdrop");
    if (!nav) return;
    nav.dataset.open = open ? "true" : "false";
    if (backdrop) backdrop.hidden = !open;
    document.querySelectorAll("[data-nav-open]").forEach(function (b) {
      b.setAttribute("aria-expanded", open ? "true" : "false");
    });
    if (open) {
      var first = nav.querySelector("a, button");
      if (first) first.focus();
    }
  }

  function copyText(button) {
    var text = button.getAttribute("data-copy");
    var label = button.textContent;
    var done = function () {
      button.textContent = "Copied";
      setTimeout(function () { button.textContent = label; }, 1500);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, function () { window.prompt("Copy this:", text); });
    } else {
      window.prompt("Copy this:", text);
    }
  }

  document.addEventListener("click", function (event) {
    var target = event.target.closest("[data-nav-open],[data-nav-close],[data-dialog-open],[data-dialog-close],[data-copy]");
    if (!target) return;
    if (target.hasAttribute("data-nav-open")) setNav(true);
    else if (target.hasAttribute("data-nav-close")) setNav(false);
    else if (target.hasAttribute("data-dialog-open")) {
      var dialog = document.getElementById(target.getAttribute("data-dialog-open"));
      if (dialog && typeof dialog.showModal === "function") dialog.showModal();
    } else if (target.hasAttribute("data-dialog-close")) {
      var parent = target.closest("dialog");
      if (parent) parent.close(target.value || "");
    } else if (target.hasAttribute("data-copy")) copyText(target);
  });

  document.addEventListener("keydown", function (event) {
    var nav = document.querySelector("[data-nav][data-open='true']");
    if (event.key === "Escape" && nav) {
      setNav(false);
      var opener = document.querySelector("[data-nav-open]");
      if (opener) opener.focus();
    }
  });
})();
