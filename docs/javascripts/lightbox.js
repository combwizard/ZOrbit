/* Click a picture in the docs or the blog to see it larger. A click anywhere, the close button or Esc closes it.
   On a phone it shows the picture at its own size and you pan across it, with the close button staying put. Only pictures that would show bigger are offered: one already shown at its full size is left alone, and so is
   one inside a link (the link wins). A picture can opt out with {data-no-zoom} (attr_list). The page keeps its
   scroll position, and focus goes back to the picture. Styles are in stylesheets/extra.css (zo-lightbox). */
(function () {
  "use strict";

  var box = null, opener = null;

  function inPage(img) {
    return !!img.closest(".md-content .md-typeset") && !img.closest("a, .zo-lightbox") && !img.hasAttribute("data-no-zoom");
  }

  /* Whether the picture is shown smaller than it is, so enlarging it shows something. */
  function worthIt(img) {
    return img.naturalWidth > img.clientWidth + 16 || img.naturalHeight > img.clientHeight + 16;
  }

  function mark(img) {
    if (!inPage(img) || !worthIt(img)) return;
    img.classList.add("zo-zoomable");
    img.tabIndex = 0;
    img.setAttribute("role", "button");
    img.setAttribute("aria-haspopup", "dialog");
    img.title = "Click to enlarge";
  }

  function markAll() {
    document.querySelectorAll(".md-content .md-typeset img").forEach(function (img) {
      if (img.complete) mark(img);
      else img.addEventListener("load", function () { mark(img); }, { once: true });
    });
  }

  function close() {
    if (!box) return;
    var gone = box;
    box = null;
    document.documentElement.classList.remove("zo-lightbox-open");
    gone.classList.remove("on");
    setTimeout(function () { gone.remove(); }, 200);
    if (opener && document.contains(opener)) opener.focus({ preventScroll: true });
    opener = null;
  }

  function open(img) {
    close();
    opener = img;
    var alt = img.getAttribute("alt") || "";
    box = document.createElement("div");
    box.className = "zo-lightbox";
    box.setAttribute("role", "dialog");
    box.setAttribute("aria-modal", "true");
    box.setAttribute("aria-label", alt || "Enlarged picture");

    var fig = document.createElement("figure");
    var big = document.createElement("img");
    big.src = img.currentSrc || img.src;
    big.alt = alt;
    fig.appendChild(big);
    if (alt) {
      var cap = document.createElement("figcaption");
      cap.textContent = alt;
      fig.appendChild(cap);
    }

    var x = document.createElement("button");
    x.type = "button";
    x.className = "zo-lightbox-x";
    x.setAttribute("aria-label", "Close");
    x.innerHTML = '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>';

    /* The picture scrolls in its own layer. The close button stays outside it, so panning never moves it. */
    var pan = document.createElement("div");
    pan.className = "zo-lightbox-pan";
    pan.appendChild(fig);

    box.append(pan, x);
    box.addEventListener("click", close);
    document.body.appendChild(box);
    document.documentElement.classList.add("zo-lightbox-open");
    void box.offsetWidth;                                           // lay it out at opacity 0 first, so it fades in
    box.classList.add("on");
    x.focus({ preventScroll: true });
  }

  document.addEventListener("click", function (e) {
    var img = e.target;
    if (img && img.classList && img.classList.contains("zo-zoomable") && e.button === 0) open(img);
  });

  document.addEventListener("keydown", function (e) {
    if (box) {
      if (e.key === "Escape") { e.preventDefault(); close(); }
      else if (e.key === "Tab") e.preventDefault();                 // the close button is the only stop
      return;
    }
    var img = e.target;
    if ((e.key === "Enter" || e.key === " ") && img && img.classList && img.classList.contains("zo-zoomable")) {
      e.preventDefault();
      open(img);
    }
  });

  /* Material's instant navigation swaps the page without a reload: mark the new page's pictures, drop an open one. */
  if (window.document$ && window.document$.subscribe) {
    window.document$.subscribe(function () { close(); markAll(); });
  } else if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", markAll);
  } else {
    markAll();
  }
})();
