/*
  Guide-only behaviour (not used by dashboard pages):
    - under every [data-example], add a collapsed "Show recipe" block with its HTML and a "Copy recipe" button
    - mark the sidebar link for the section in view with aria-current="page"
  You should not need to edit this file to add a component; see design/DESIGN.md.
*/
(function () {
  "use strict";

  function dedent(text) {
    var lines = text.replace(/^\n+|\s+$/g, "").split("\n");
    var indents = lines.filter(function (l) { return l.trim(); }).map(function (l) { return l.match(/^ */)[0].length; });
    var cut = indents.length ? Math.min.apply(null, indents) : 0;
    return lines.map(function (l) { return l.slice(cut); }).join("\n");
  }

  document.querySelectorAll("[data-example]").forEach(function (example) {
    var code = dedent(example.innerHTML);
    var wrap = document.createElement("details");
    wrap.className = "grid min-w-0 gap-2";
    var summary = document.createElement("summary");
    summary.className = "inline-flex h-8 w-fit cursor-pointer items-center rounded-md px-3 text-sm font-medium text-tf-muted hover:bg-tf-raised hover:text-tf-text";
    summary.textContent = "Show recipe";
    var bar = document.createElement("div");
    bar.className = "mt-2 flex justify-end";
    var copy = document.createElement("button");
    copy.type = "button";
    copy.className = "inline-flex h-8 items-center gap-2 rounded-md border border-tf-line-strong bg-tf-raised px-3 text-sm font-medium text-tf-text hover:border-tf-muted";
    copy.textContent = "Copy recipe";
    copy.setAttribute("data-copy", code);
    bar.append(copy);
    var pre = document.createElement("pre");
    pre.className = "tf-mono mt-2 max-h-80 overflow-auto rounded-md border border-tf-line bg-tf-input p-4 text-xs text-tf-muted";
    pre.textContent = code;
    wrap.append(summary, bar, pre);
    example.after(wrap);
  });

  var links = Array.prototype.slice.call(document.querySelectorAll("[data-nav] a[href^='#']"));
  var byId = {};
  links.forEach(function (a) { byId[a.getAttribute("href").slice(1)] = a; });
  if ("IntersectionObserver" in window) {
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting || !byId[entry.target.id]) return;
        links.forEach(function (a) { a.removeAttribute("aria-current"); });
        byId[entry.target.id].setAttribute("aria-current", "page");
      });
    }, { rootMargin: "-20% 0px -70% 0px" });
    document.querySelectorAll("section[data-component]").forEach(function (s) { observer.observe(s); });
  }
})();
