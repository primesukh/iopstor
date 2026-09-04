/* Admin progressive enhancement: auto slug, inline media upload, block editor.
   No framework, no build step. Every part is a no-op when its hook is absent, and the
   plain form underneath (textarea named "blocks", plain selects) still works without JS. */
(function () {
  "use strict";

  var el = function (tag, attrs, kids) {
    var n = document.createElement(tag);
    for (var k in attrs || {}) { if (k === "text") { n.textContent = attrs[k]; } else { n.setAttribute(k, attrs[k]); } }
    (kids || []).forEach(function (c) { n.appendChild(c); });
    return n;
  };
  var btn = function (label, title, onclick) {
    var b = el("button", { type: "button", "class": "secondary tiny", title: title || label, text: label });
    b.addEventListener("click", onclick);
    return b;
  };
  var csrf = function () { var i = document.querySelector('input[name="csrf"]'); return i ? i.value : ""; };

  // ---- paste ----------------------------------------------------------------
  /* Editors draft in Word or Google Docs and paste the result in. The old handler forced every
     paste through insertText, which threw away the headings and lists — the whole reason they
     drafted there. Keep the structure, drop the vendor noise: an allowlist of tags, and only
     href/src/alt survive. This is a quality filter, not a security boundary — block HTML is
     still trusted-staff-only on the server (blocks.py). */
  var PASTE_OK = { P: 1, BR: 1, H2: 1, H3: 1, H4: 1, UL: 1, OL: 1, LI: 1, STRONG: 1, EM: 1, U: 1, A: 1, S: 1,
                   BLOCKQUOTE: 1, TABLE: 1, THEAD: 1, TBODY: 1, TR: 1, TH: 1, TD: 1, IMG: 1, HR: 1, CODE: 1, PRE: 1 };
  var PASTE_AS = { B: "STRONG", I: "EM", DIV: "P", H1: "H2", H5: "H4", H6: "H4",  // h1 is the page title's alone
                   STRIKE: "S", DEL: "S" };
  var PASTE_DROP = { SCRIPT: 1, STYLE: 1, HEAD: 1, META: 1, LINK: 1, TITLE: 1, OBJECT: 1, IFRAME: 1, NOSCRIPT: 1, SVG: 1 };
  var PASTE_ATTR = { href: 1, src: 1, alt: 1 };

  function cleanPaste(root, d) {
    Array.prototype.slice.call(root.children).forEach(function (node) {
      var tag = node.tagName;
      if (PASTE_DROP[tag]) { node.remove(); return; }   // remove outright: unwrapping would spill source as text
      cleanPaste(node, d);                              // depth first, so children are settled before the parent moves
      var want = PASTE_AS[tag] || (PASTE_OK[tag] ? tag : "");
      if (!want) {                                      // unwrap: keep the words, lose the wrapper
        while (node.firstChild) node.parentNode.insertBefore(node.firstChild, node);
        node.remove();
        return;
      }
      var keep = {};
      Array.prototype.slice.call(node.attributes).forEach(function (a) {
        if (PASTE_ATTR[a.name]) keep[a.name] = a.value;
        node.removeAttribute(a.name);
      });
      if (want !== tag) {
        var swap = d.createElement(want);
        while (node.firstChild) swap.appendChild(node.firstChild);
        node.parentNode.replaceChild(swap, node);
        node = swap;
      }
      for (var k in keep) node.setAttribute(k, keep[k]);
    });
  }

  function clipboard(e) { return e.clipboardData || (e.target.ownerDocument.defaultView || window).clipboardData; }

  function richPaste(e) {             // prose: keep headings, lists, links, tables
    var d = e.target.ownerDocument, cb = clipboard(e), html = cb.getData("text/html");
    e.preventDefault();
    if (!html) return d.execCommand("insertText", false, cb.getData("text/plain"));
    var holder = d.createElement("div");
    holder.innerHTML = html.replace(/<!--[\s\S]*?-->/g, "");   // Word hides half its markup in conditional comments
    cleanPaste(holder, d);
    d.execCommand("insertHTML", false, holder.innerHTML);
  }

  function plainPaste(e) {            // a heading or a button label cannot hold markup
    var d = e.target.ownerDocument;
    e.preventDefault();
    d.execCommand("insertText", false, clipboard(e).getData("text/plain"));
  }

  // ---- slug -----------------------------------------------------------------
  // mirrors iopstor/db.py slugify(): strip accents, lowercase, non-alphanumerics -> "-"
  function slugify(text) {
    return text.normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase()
               .replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  }

  function initSlug() {
    var title = document.getElementById("post-title"), slug = document.getElementById("post-slug");
    if (!title || !slug) return;
    var saved = slug.value, unlocked = false;
    title.addEventListener("input", function () {
      if (!saved && !unlocked) slug.value = slugify(title.value);
    });
    slug.parentNode.appendChild(btn("Edit", "Change the web address", function () {
      if (saved && !confirm("Changing the web address breaks any existing link to this page. Continue?")) return;
      unlocked = true;
      slug.readOnly = false;
      slug.focus();
    }));
  }

  // ---- media ----------------------------------------------------------------
  var MEDIA = [];            // {id, url, filename, mime, alt}
  var pickers = [];          // so a new upload appears in every picker at once; detached ones unregister themselves

  function mediaById(id) {
    for (var i = 0; i < MEDIA.length; i++) if (String(MEDIA[i].id) === String(id)) return MEDIA[i];
    return null;
  }

  function upload(file, alt, done, fail) {
    var body = new FormData();
    body.append("csrf", csrf());
    body.append("file", file);
    if (alt) body.append("alt", alt);
    fetch("/admin/media/upload", { method: "POST", body: body, credentials: "same-origin" })
      .then(function (r) { return r.json().then(function (j) { return r.ok ? j : Promise.reject(j.error || r.statusText); }); })
      .then(function (m) {
        MEDIA.unshift(m);
        pickers.slice().forEach(function (fn) { fn(); });
        done(m);
      })
      .catch(function (e) { fail(String(e)); });
  }

  /* One media widget: preview + "choose existing" select + upload straight from here.
     `get`/`set` read and write whatever holds the value (a form <select> or a block field). */
  function mediaWidget(get, set, imagesOnly) {
    var sel = el("select"), thumb = el("span", { "class": "media-thumb" }),
        file = el("input", { type: "file", accept: imagesOnly ? "image/*" : "image/*,application/pdf" }),
        note = el("small", { "class": "media-note" });

    function refresh() {
      if (sel.dataset.live && !sel.isConnected) {   // detached by a redraw: unregister rather than pile up
        var at = pickers.indexOf(refresh);
        if (at > -1) pickers.splice(at, 1);
        return;
      }
      sel.dataset.live = "1";
      var cur = get();
      sel.innerHTML = "";
      sel.appendChild(el("option", { value: "", text: "— none —" }));
      MEDIA.forEach(function (m) {
        if (imagesOnly && m.mime && m.mime.indexOf("image/") !== 0) return;
        sel.appendChild(el("option", { value: m.id, text: "#" + m.id + " " + m.filename }));
      });
      sel.value = cur == null ? "" : String(cur);
      var m = mediaById(cur);
      thumb.innerHTML = "";
      if (m && m.mime && m.mime.indexOf("image/") === 0) thumb.appendChild(el("img", { src: m.url, alt: m.alt || "" }));
      else if (m) thumb.appendChild(el("span", { text: m.filename }));
    }

    sel.addEventListener("change", function () { set(sel.value); refresh(); });
    file.addEventListener("change", function () {
      if (!file.files.length) return;
      note.textContent = "Uploading…";
      upload(file.files[0], "", function (m) { note.textContent = ""; set(String(m.id)); refresh(); file.value = ""; },
             function (err) { note.textContent = err; file.value = ""; });
    });
    pickers.push(refresh);
    refresh();
    return el("span", { "class": "media-field" }, [thumb, sel, file, note]);
  }

  // Upgrade the plain <select data-media> fields (featured image, per-type media fields).
  function initMediaSelects() {
    Array.prototype.forEach.call(document.querySelectorAll("select[data-media]"), function (s) {
      var hidden = el("input", { type: "hidden", name: s.name });
      hidden.value = s.value;
      s.parentNode.insertBefore(hidden, s);
      var imagesOnly = s.getAttribute("data-media") === "images";
      s.parentNode.insertBefore(mediaWidget(function () { return hidden.value; },
                                           function (v) { hidden.value = v; }, imagesOnly), s);
      s.remove();
    });
  }

  // ---- rich text ------------------------------------------------------------
  // ponytail: document.execCommand rich text — deprecated but universally implemented, and 40 lines
  // against a bundled editor. Swap for a real editor if a browser drops it.
  var RT_BUTTONS = [["B", "bold", "Bold"], ["I", "italic", "Italic"], ["H2", "formatBlock:<h2>", "Heading"],
                    ["H3", "formatBlock:<h3>", "Sub-heading"], ["¶", "formatBlock:<p>", "Normal text"],
                    ["• list", "insertUnorderedList", "Bulleted list"], ["1. list", "insertOrderedList", "Numbered list"],
                    ["link", "createLink", "Add a link"], ["clear", "removeFormat", "Remove formatting"]];

  function richText(value, onChange) {
    var body = el("div", { "class": "rt-body", contenteditable: "true" });
    var raw = el("textarea", { "class": "code rt-raw", hidden: "hidden", style: "min-height:8rem" });
    body.innerHTML = value || "";
    raw.value = value || "";

    var bar = el("div", { "class": "rt-toolbar" });
    RT_BUTTONS.forEach(function (b) {
      bar.appendChild(btn(b[0], b[2], function () {
        var cmd = b[1].split(":");
        body.focus();
        if (cmd[0] === "createLink") {
          var url = prompt("Link address", "https://");
          if (url) document.execCommand("createLink", false, url);
        } else {
          document.execCommand(cmd[0], false, cmd[1] || null);
        }
        onChange(body.innerHTML);
      }));
    });
    var toggle = btn("HTML", "Edit the raw HTML", function () {
      if (raw.hidden) { raw.value = body.innerHTML; raw.hidden = false; body.hidden = true; }
      else { body.innerHTML = raw.value; onChange(raw.value); raw.hidden = true; body.hidden = false; }
    });
    toggle.classList.add("rt-toggle");
    bar.appendChild(toggle);

    body.addEventListener("input", function () { onChange(body.innerHTML); });
    raw.addEventListener("input", function () { onChange(raw.value); });
    body.addEventListener("paste", richPaste);
    return el("div", { "class": "rt" }, [bar, body, raw]);
  }

  // ---- block editor ---------------------------------------------------------
  var SPEC = null;  // {blocks: {type: [required, optional]}, ui: {widgets, items, labels, kinds}, media, post_types}

  function widgetFor(type, field) {
    return SPEC.ui.widgets[type + "." + field] || SPEC.ui.widgets[field] || "text";
  }
  var BLOCK_NAMES = { cta: "CTA", faq: "FAQ", embed_html: "Embed HTML", rich_text: "Rich text" };
  function nameFor(type) {
    var n = SPEC && SPEC.ui.names && SPEC.ui.names[type];
    return (n && n[1]) || BLOCK_NAMES[type] || (type.charAt(0).toUpperCase() + type.slice(1)).replace(/_/g, " ");
  }
  function labelFor(field) {
    return SPEC.ui.labels[field] || (field.charAt(0).toUpperCase() + field.slice(1)).replace(/_/g, " ");
  }
  function fieldsOf(type) {
    var spec = SPEC.blocks[type] || [[], []];
    return spec[0].map(function (f) { return { key: f, required: true }; })
      .concat(spec[1].map(function (f) { return { key: f, required: false }; }));
  }

  // One input for data[key]. `data` is mutated in place, so keys the editor does not render survive.
  function fieldInput(type, key, data) {
    var widget = widgetFor(type, key), set = function (v) { data[key] = v; };
    if (widget === "media") return mediaWidget(function () { return data[key]; }, set, true);
    if (widget === "richtext") return richText(data[key] || "", set);
    if (widget === "checkbox") {
      var c = el("input", { type: "checkbox" });
      c.checked = !!data[key];
      c.addEventListener("change", function () { data[key] = c.checked; });
      return c;
    }
    var input;
    if (widget === "textarea" || widget === "code") {
      input = el("textarea", widget === "code" ? { "class": "code" } : {});
    } else if (widget === "post_type" || widget === "kind") {
      input = el("select");
      input.appendChild(el("option", { value: "", text: "— choose —" }));
      (widget === "kind" ? SPEC.ui.kinds : SPEC.post_types).forEach(function (o) {
        input.appendChild(el("option", { value: o, text: o }));
      });
    } else {
      input = el("input", { type: widget === "number" ? "number" : widget === "url" ? "text" : "text" });
    }
    input.value = data[key] == null ? "" : data[key];
    input.addEventListener("input", function () { set(widget === "number" ? (input.value === "" ? null : Number(input.value)) : input.value); });
    input.addEventListener("change", function () { set(widget === "number" ? (input.value === "" ? null : Number(input.value)) : input.value); });
    return input;
  }

  function labelled(text, required, node) {
    return el("label", {}, [document.createTextNode(text + (required ? " *" : "")), node]);
  }

  // items / images / rows: a list of {subfield: value} rows
  function repeater(type, key, data) {
    var subs = SPEC.ui.items[type] || [];
    if (!Array.isArray(data[key])) data[key] = [];
    var list = el("div", { "class": "rep" });

    function draw() {
      list.innerHTML = "";
      data[key].forEach(function (row, i) {
        var cells = subs.map(function (s) { return labelled(labelFor(s), false, fieldInput(type, s, row)); });
        var controls = el("span", { "class": "rep-controls" }, [
          btn("↑", "Move up", function () { if (i) { data[key].splice(i - 1, 0, data[key].splice(i, 1)[0]); draw(); } }),
          btn("↓", "Move down", function () { if (i < data[key].length - 1) { data[key].splice(i + 1, 0, data[key].splice(i, 1)[0]); draw(); } }),
          btn("✕", "Remove", function () { data[key].splice(i, 1); draw(); })
        ]);
        list.appendChild(el("div", { "class": "rep-row" }, cells.concat([controls])));
      });
      list.appendChild(btn("+ Add " + labelFor(key).toLowerCase().replace(/s$/, ""), "Add a row", function () {
        var row = {};
        subs.forEach(function (s) { row[s] = ""; });
        data[key].push(row);
        draw();
      }));
    }
    draw();
    return el("div", {}, [el("strong", { text: labelFor(key) }), list]);
  }

  function blockCard(block, i, blocks, redraw) {
    var head = el("div", { "class": "blk-head" }, [
      el("strong", { text: nameFor(block.type) }),
      el("span", { "class": "spacer" }),
      btn("↑", "Move up", function () { if (i) { blocks.splice(i - 1, 0, blocks.splice(i, 1)[0]); redraw(); } }),
      btn("↓", "Move down", function () { if (i < blocks.length - 1) { blocks.splice(i + 1, 0, blocks.splice(i, 1)[0]); redraw(); } }),
      btn("✕", "Remove this section", function () { if (confirm("Remove this " + nameFor(block.type) + " section?")) { blocks.splice(i, 1); redraw(); } })
    ]);
    if (!block.data || typeof block.data !== "object") block.data = {};
    var body = el("div", { "class": "blk-fields" });
    if (!SPEC.blocks[block.type]) {
      body.appendChild(el("p", { "class": "muted", text: "Unknown block type — edit it under “Advanced — edit as JSON”." }));
    } else {
      fieldsOf(block.type).forEach(function (f) {
        if (SPEC.ui.items[block.type] && (f.key === "items" || f.key === "images" || f.key === "rows")) {
          body.appendChild(repeater(block.type, f.key, block.data));
        } else {
          body.appendChild(labelled(labelFor(f.key), f.required, fieldInput(block.type, f.key, block.data)));
        }
      });
    }
    return el("div", { "class": "blk" }, [head, body]);
  }

  // ---- shared model ---------------------------------------------------------
  /* One array, three editors. fieldInput() mutates block objects in place, so the canvas, the
     settings panel and the JSON textarea all point at the same objects — there is no sync layer.
     The one dangerous move is REPLACING the array; setBlocks() is the only place that happens. */
  var MODEL = [], AREA = null, dirty = false;
  var redrawForm = function () {};

  function setBlocks(next) {
    MODEL = Array.isArray(next) ? next : [];
    redrawForm();
    canvasFull();
  }
  function markDirty() { dirty = true; }

  // An empty paragraph is the editor waiting for you, not content. Drop it on save — but keep
  // one that holds only a picture, a rule or a table, which has no text and is still real.
  function written(b) {
    if (b.type !== "rich_text") return true;
    var html = b.data && b.data.html || "";
    return !!html.replace(/<[^>]*>/g, "").replace(/&nbsp;|\u00a0/g, " ").trim() || /<(img|hr|table)\b/i.test(html);
  }
  function seedFor(type) {
    return JSON.parse(JSON.stringify((SPEC.ui.seed && SPEC.ui.seed[type]) || {}));  // never hand out the shared seed
  }

  // ---- the visual canvas ----------------------------------------------------
  /* The iframe holds a real server render (POST /admin/canvas) of the blocks currently in memory,
     so what an editor sees is exactly what render_blocks() will publish. Same origin, so we drive
     contentDocument directly. Typing never re-renders; a structural change swaps ONE <section>. */
  var FRAME = null, selected = -1, panel = null, tokens = {};

  function cdoc() { return FRAME && FRAME.contentDocument; }

  function ask(key, extra, done) {
    var body = new FormData(), title = document.getElementById("post-title"),
        excerpt = document.querySelector('textarea[name="excerpt"]');
    body.append("csrf", csrf());
    body.append("blocks", JSON.stringify(MODEL));
    body.append("title", title ? title.value : "");
    body.append("excerpt", excerpt ? excerpt.value : "");
    for (var k in extra || {}) body.append(k, extra[k]);
    var mine = tokens[key] = (tokens[key] || 0) + 1;
    fetch("/admin/canvas", { method: "POST", body: body, credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.text() : Promise.reject(r.statusText); })
      .then(function (html) { if (tokens[key] === mine) done(html); })   // a newer request already won
      .catch(function () {});
  }

  function fragment(d, html) {
    var holder = d.createElement("div");
    holder.innerHTML = html;
    return holder.firstElementChild;
  }

  var focusOnLoad = -1;

  function canvasFull() {
    if (!FRAME) return;
    if (VIEW === "preview") return renderPreview();   // whatever changed, preview is what is on screen
    ask("full", {}, function (html) {
      FRAME.onload = function () {
        FRAME.onload = null;
        wireDoc();
        if (focusOnLoad > -1) { focusBlock(focusOnLoad); focusOnLoad = -1; }
        syncBar();                       // the old caret died with the old document; say so
      };
      FRAME.srcdoc = html;
    });
  }

  function canvasBlock(i) {           // one block's data changed in the settings panel
    var d = cdoc();
    if (!d || !MODEL[i]) return;
    ask("b" + i, { i: i }, function (html) {
      var node = d.querySelector('[data-b="' + i + '"]'), fresh = fragment(d, html);
      if (!node || !fresh) return canvasFull();
      node.replaceWith(fresh);
      fresh.setAttribute("data-b", i);   // the fragment is rendered alone, so it comes back as 0
      wireBlock(fresh);
      paint();
      bars();
      syncBar();                         // replaceWith just threw the remembered caret away
    });
  }

  function canvasInsert(i, focus) {   // MODEL already holds the new block at i
    var d = cdoc();
    if (!d) return canvasFull();
    ask("b" + i, { i: i }, function (html) {
      var main = d.getElementById("main"), at = d.querySelectorAll("[data-b]")[i], fresh = fragment(d, html);
      if (!main || !fresh) return canvasFull();
      main.insertBefore(fresh, at || null);
      renumber();
      wireBlock(fresh);
      bars();
      if (focus) focusBlock(i); else select(i);
      fresh.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  }

  function renumber() {
    var d = cdoc();
    if (d) Array.prototype.forEach.call(d.querySelectorAll("[data-b]"), function (n, i) { n.setAttribute("data-b", String(i)); });
  }

  /* The gaps between sections are where a document keeps typing. Clicking one drops in an empty
     paragraph and puts the caret in it; "/" inside that paragraph reaches every section type.
     One mechanic instead of two, and it means there is never nowhere to type. */
  function addBar(d, i) {
    var b = d.createElement("button");
    b.type = "button";
    b.textContent = "Type here, or press / for a section";
    b.title = "Write here";
    b.addEventListener("click", function (e) { e.preventDefault(); e.stopPropagation(); addParagraph(i); });
    var w = d.createElement("div");
    w.className = "iop-add";
    w.appendChild(b);
    return w;
  }

  function addParagraph(at) {
    MODEL.splice(at, 0, { type: "rich_text", data: { html: "" } });
    redrawForm();
    markDirty();
    canvasInsert(at, true);
  }

  function focusBlock(i) {
    var d = cdoc(), f = d && d.querySelector('[data-b="' + i + '"] [data-f]');
    if (!f) return;
    f.focus();
    var r = d.createRange(), sel = d.defaultView.getSelection();
    r.selectNodeContents(f);
    r.collapse(true);
    sel.removeAllRanges();
    sel.addRange(r);
    select(i);
  }

  function bars() {                   // the "+" strips live between blocks; rebuild after any move
    var d = cdoc();
    if (!d) return;
    var main = d.getElementById("main");
    if (!main) return;
    Array.prototype.forEach.call(d.querySelectorAll(".iop-add"), function (n) { n.remove(); });
    var list = d.querySelectorAll("[data-b]");
    for (var i = 0; i <= list.length; i++) main.insertBefore(addBar(d, i), list[i] || null);
  }

  // ---- editing on the page --------------------------------------------------
  function setEditable(f, rich) {
    if (rich) { f.contentEditable = "true"; return; }
    f.contentEditable = "plaintext-only";
    if (f.contentEditable !== "plaintext-only") {   // engine without it: emulate the half that matters
      f.contentEditable = "true";
      f.addEventListener("keydown", function (e) { if (e.key === "Enter") e.preventDefault(); });
    }
  }

  // Which object does this field write into — the block's data, or one repeater row?
  function dataFor(node, f) {
    var b = MODEL[+node.getAttribute("data-b")];
    if (!b || !b.data) return null;
    var row = f.closest("[data-r]");
    if (!row || row === f) return b.data;
    var arr = b.data[row.getAttribute("data-r")];
    return Array.isArray(arr) ? arr[+row.getAttribute("data-i")] : null;
  }

  function bindField(node, f) {
    var rich = f.hasAttribute("data-rich"), key = f.getAttribute("data-f");
    setEditable(f, rich);
    f.addEventListener("input", function () {
      var target = dataFor(node, f);
      if (!target) return;
      target[key] = rich ? f.innerHTML : f.innerText;
      markDirty();
    });
    f.addEventListener("focus", function () { select(+node.getAttribute("data-b")); });
    f.addEventListener("paste", rich ? richPaste : plainPaste);
    if (rich) bindSlash(node, f);
  }

  function moveBlock(dir, i) {
    var to = i + dir, d = cdoc();
    if (to < 0 || to >= MODEL.length) return;
    MODEL.splice(to, 0, MODEL.splice(i, 1)[0]);
    if (d) {
      var nodes = d.querySelectorAll("[data-b]"), node = nodes[i], ref = nodes[to];
      if (node && ref) ref.parentNode.insertBefore(node, dir > 0 ? ref.nextSibling : ref);
      renumber();
      bars();
    }
    redrawForm();
    markDirty();
    select(to);
  }

  function dupBlock(i) {
    MODEL.splice(i + 1, 0, JSON.parse(JSON.stringify(MODEL[i])));
    redrawForm();
    markDirty();
    canvasInsert(i + 1);
  }

  function delBlock(i) {
    if (!confirm("Remove this " + nameFor(MODEL[i].type) + " section?")) return;
    MODEL.splice(i, 1);
    var d = cdoc(), node = d && d.querySelector('[data-b="' + i + '"]');
    if (node) node.remove();
    renumber();
    bars();
    redrawForm();
    markDirty();
    select(-1);
  }

  function blockBar(d, node) {
    var bar = d.createElement("div");
    bar.className = "iop-bar";
    var at = function () { return +node.getAttribute("data-b"); };
    function push(label, title, fn, cls) {
      var x = d.createElement("button");
      x.type = "button";
      x.title = title;
      x.textContent = label;
      if (cls) x.className = cls;
      x.addEventListener("click", function (e) { e.preventDefault(); e.stopPropagation(); fn(at()); });
      bar.appendChild(x);
    }
    var name = d.createElement("span");
    name.className = "iop-name";
    name.textContent = nameFor((MODEL[at()] || {}).type || "");
    bar.appendChild(name);
    var grab = d.createElement("button");
    grab.type = "button";
    grab.className = "iop-grab";
    grab.title = "Drag to move this section";
    grab.textContent = "⠿";
    bar.appendChild(grab);
    push("↑", "Move up", function (i) { moveBlock(-1, i); });
    push("↓", "Move down", function (i) { moveBlock(1, i); });
    push("⧉", "Make a copy", dupBlock);
    push("⚙", "Pictures, links and settings", select);
    push("✕", "Remove this section", delBlock, "iop-del");
    return bar;
  }

  function wireBlock(node) {
    var d = node.ownerDocument, old = node.querySelector(":scope > .iop-bar");
    if (old) old.remove();
    // a floating toolbar over every paragraph would destroy the document feel; sections keep theirs
    if (((MODEL[+node.getAttribute("data-b")] || {}).type) !== "rich_text") node.appendChild(blockBar(d, node));
    Array.prototype.forEach.call(node.querySelectorAll("[data-f]"), function (f) { bindField(node, f); });
    node.addEventListener("mousedown", function () { select(+node.getAttribute("data-b")); });
  }

  function wireDoc() {
    var d = cdoc();
    if (!d) return;
    // the canvas is a real page: stop it behaving like one (contact_form would post a live lead)
    d.addEventListener("submit", function (e) { e.preventDefault(); }, true);
    d.addEventListener("click", function (e) {
      var hit = e.target.closest && e.target.closest("a,button");
      if (hit && !hit.closest(".iop-bar") && !hit.closest(".iop-add")) e.preventDefault();
    }, true);
    d.addEventListener("scroll", closeSlash, true);
    Array.prototype.forEach.call(d.querySelectorAll("details"), function (x) { x.open = true; });  // FAQ answers stay open to edit
    d.addEventListener("selectionchange", rememberSelection);
    Array.prototype.forEach.call(d.querySelectorAll("[data-b]"), wireBlock);
    bars();
    paint();
    var Sortable = d.defaultView && d.defaultView.Sortable;
    if (Sortable) {
      Sortable.create(d.getElementById("main"), {
        draggable: "[data-b]", handle: ".iop-grab", animation: 140, ghostClass: "iop-ghost", chosenClass: "iop-drag",
        onEnd: function (e) {
          var from = +e.item.getAttribute("data-b"),
              to = Array.prototype.indexOf.call(d.querySelectorAll("[data-b]"), e.item);
          if (to < 0 || to === from) return;
          MODEL.splice(to, 0, MODEL.splice(from, 1)[0]);
          renumber();
          bars();
          redrawForm();
          markDirty();
          select(to);
        }
      });
    }
  }

  // ---- selection + the settings panel ---------------------------------------
  function paint() {
    var d = cdoc();
    if (d) Array.prototype.forEach.call(d.querySelectorAll("[data-b]"), function (n) {
      n.classList.toggle("iop-sel", +n.getAttribute("data-b") === selected);
    });
  }

  function select(i) {
    if (i === selected) return;   // every mousedown lands here; only rebuild the panel on a real change
    selected = i;
    paint();
    showPanel(i);
  }

  function showPanel(i) {
    if (!panel) return;
    panel.innerHTML = "";
    if (!MODEL[i]) {
      panel.appendChild(el("p", { "class": "muted", text: "Click a section on the page to change its pictures, links and settings." }));
      return;
    }
    // the settings panel IS the form editor's card — every widget reused, nothing reimplemented
    panel.appendChild(blockCard(MODEL[i], i, MODEL, function () { redrawForm(); canvasFull(); select(-1); }));
  }

  // ---- the section picker ---------------------------------------------------
  function chooser(title, items, pick) {
    var search = el("input", { type: "search", placeholder: "Search…" }), grid = el("div", { "class": "iop-grid" });
    function draw() {
      var q = search.value.toLowerCase();
      grid.innerHTML = "";
      items.filter(function (it) { return !q || (it.label + " " + it.text).toLowerCase().indexOf(q) > -1; }).forEach(function (it) {
        var card = el("button", { type: "button", "class": "iop-pick" }, [
          el("span", { "class": "iop-icon", text: it.icon || "▦" }),
          el("strong", { text: it.label }),
          el("small", { text: it.text })
        ]);
        card.addEventListener("click", function () { close(); pick(it.key); });
        grid.appendChild(card);
      });
      if (!grid.children.length) grid.appendChild(el("p", { "class": "muted", text: "Nothing matches that." }));
    }
    function esc(e) { if (e.key === "Escape") close(); }
    function close() { document.removeEventListener("keydown", esc); box.remove(); }
    search.addEventListener("input", draw);
    var box = el("div", { "class": "iop-modal" }, [
      el("div", { "class": "iop-modal-in" }, [
        el("div", { "class": "toolbar" }, [el("strong", { text: title }), el("span", { "class": "spacer" }), btn("✕", "Close", close)]),
        search, grid
      ])
    ]);
    box.addEventListener("click", function (e) { if (e.target === box) close(); });
    document.addEventListener("keydown", esc);
    document.body.appendChild(box);
    draw();
    search.focus();
  }

  function openInserter(at) {
    var types = (SPEC.ui.order || []).filter(function (t) { return SPEC.blocks[t]; });
    Object.keys(SPEC.blocks).forEach(function (t) { if (types.indexOf(t) < 0) types.push(t); });
    chooser("Add a section", types.map(function (t) {
      var n = (SPEC.ui.names && SPEC.ui.names[t]) || [];
      return { key: t, icon: n[0], label: nameFor(t), text: n[2] || "" };
    }), function (t) {
      MODEL.splice(at, 0, { type: t, data: seedFor(t) });
      redrawForm();
      markDirty();
      canvasInsert(at);
    });
  }

  // Ready-made layouts are offered, never imposed: they live in the Insert menu, not in the way.
  function openLayouts() {
    chooser("Start from a layout", (SPEC.layouts || []).map(function (pair) {
      return { key: pair[0], icon: "▤", label: pair[0], text: pair[1].map(nameFor).join(" · ") };
    }), function (name) {
      var pair = (SPEC.layouts || []).filter(function (x) { return x[0] === name; })[0];
      if (!pair) return;
      markDirty();
      setBlocks(pair[1].map(function (t) { return { type: t, data: seedFor(t) }; }));
    });
  }

  // ---- the document toolbar -------------------------------------------------
  /* Lives in the admin page (so it uses admin.css) but every command runs against the CANVAS
     document. Clicking a button moves focus out of the iframe, so the caret is remembered on
     every selection change and put back before the command runs. */
  var savedRange = null, savedField = null, syncBar = function () {};

  function fire(f) {
    var W = f.ownerDocument.defaultView;
    f.dispatchEvent(new (W.Event || Event)("input", { bubbles: true }));
  }

  function rememberSelection() {
    var d = cdoc();
    if (!d) return;
    var sel = d.defaultView.getSelection();
    if (!sel || !sel.rangeCount) return;
    var r = sel.getRangeAt(0), host = r.startContainer;
    host = host.nodeType === 1 ? host : host.parentNode;
    var f = host && host.closest && host.closest("[data-f]");
    if (!f) return;
    savedRange = r.cloneRange();
    savedField = f;
    syncBar();
  }

  /* Is the remembered caret still commandable? isConnected is not enough: a node from a replaced
     srcdoc stays "connected" to its own dead document, and handing that range to the live document's
     selection throws. It has to be in the canvas document we are about to run the command against.
     ponytail: a re-render (canvasBlock/canvasFull) throws the node away and the toolbar goes dead
     until the editor clicks back into the canvas — it says so rather than failing quietly. Re-derive
     the field from its block index + field key if that click ever costs more than it saves. */
  function liveField() {
    var d = cdoc();
    return d && savedRange && savedField && d.contains(savedField) ? savedField : null;
  }

  function restoreSelection() {
    var d = cdoc();
    if (!liveField()) return false;
    savedField.focus();
    var sel = d.defaultView.getSelection();
    sel.removeAllRanges();
    sel.addRange(savedRange);
    return true;
  }

  /* The block element the caret sits in, bounded by the field. sel="…" asks for the nearest
     matching ancestor instead. Returns the field itself only when the text really has no wrapper.

     The descent matters: at a block boundary — the caret at the end of a line, which is where it
     is after you type — Gecko reports the range's container as the editing HOST, not the block.
     Taken at face value that makes quote-off undetectable (closest("blockquote") from the host is
     null) and reads alignment off the wrong element. Resolve through startOffset first. */
  function caretBlock(sel) {
    if (!liveField()) return null;
    var n = savedRange.startContainer;
    if (n === savedField && n.childNodes.length) {
      n = n.childNodes[Math.min(savedRange.startOffset, n.childNodes.length - 1)];
    }
    n = n.nodeType === 1 ? n : n.parentNode;
    if (!n || !savedField.contains(n)) return null;
    if (sel) { var hit = n.closest(sel); return hit && savedField.contains(hit) ? hit : null; }
    while (n !== savedField && n.parentNode !== savedField) n = n.parentNode;
    return n;
  }

  var BLOCK_CMD = /^(justify|formatBlock|outdent|indent)/;

  function exec(cmd, val) {
    var d = cdoc();
    if (!d || !restoreSelection()) return;
    // Bare text straight in the field leaves the browser styling the contenteditable host, whose
    // attributes the innerHTML write-back drops on the floor. Give a block command a block first.
    if (BLOCK_CMD.test(cmd) && caretBlock() === savedField) {
      d.execCommand("formatBlock", false, "<p>");
      rememberSelection();
    }
    // Justify has to win against site.css: styleWithCSS off emits a presentational align="" that
    // ranks below author styles, so a centred section simply ignores it.
    d.execCommand("styleWithCSS", false, /^(foreColor|hiliteColor|justify)/.test(cmd));
    d.execCommand(cmd, false, val == null ? null : val);
    if (savedField) fire(savedField);
    rememberSelection();
  }

  function sectionItems() {
    var types = (SPEC.ui.order || []).filter(function (t) { return SPEC.blocks[t]; });
    Object.keys(SPEC.blocks).forEach(function (t) { if (types.indexOf(t) < 0) types.push(t); });
    return types.filter(function (t) { return t !== "rich_text"; }).map(function (t) {
      var n = (SPEC.ui.names && SPEC.ui.names[t]) || [];
      return { key: t, icon: n[0], label: nameFor(t), text: n[2] || "" };
    });
  }

  // A picture in the flow, uploaded on the spot. media_alt() cannot reach inside rich_text HTML,
  // so the alt text has to be asked for here or it never gets written at all.
  function altPrompt(src) {
    var host = document.getElementById("doc-toolbar");
    if (!host) return;
    var input = el("input", { type: "text", placeholder: "Describe this picture for screen readers (recommended)" });
    function close() { row.remove(); }
    function save() {
      var d = cdoc(), img = d && d.querySelector('img[src="' + src.replace(/"/g, '&quot;') + '"]');
      if (img && input.value.trim()) {
        img.setAttribute("alt", input.value.trim());
        var f = img.closest("[data-f]");
        if (f) fire(f);
      }
      close();
    }
    var row = el("div", { "class": "tb-alt" }, [input, btn("Save", "Save the description", save), btn("Skip", "Leave it blank", close)]);
    host.appendChild(row);
    input.focus();
    input.addEventListener("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); save(); } });
  }

  function buildToolbar() {
    var bar = document.getElementById("doc-toolbar");
    if (!bar) return;
    function hold(x) { x.addEventListener("mousedown", function (e) { e.preventDefault(); }); return x; }
    function b(label, title, fn, cls) {
      var x = el("button", { type: "button", "class": "tb" + (cls ? " " + cls : ""), title: title, text: label });
      hold(x);
      x.addEventListener("click", function (e) { e.preventDefault(); fn(); });
      return x;
    }
    function group(kids) { return el("span", { "class": "tb-group" }, kids); }

    var style = el("select", { "class": "tb-style", title: "Text style" });
    // Shown when the caret is in a block this list has no name for — a blockquote, a bare text node.
    // It has to be a real selectable value, not a coerced "p": pretending the caret is already on
    // Normal text means picking Normal text changes nothing and raises no change event.
    style.appendChild(el("option", { value: "", text: "\u2014", hidden: "hidden" }));
    // No Heading 1: post.html already emits the page title as the page's only <h1>.
    [["p", "Normal text"], ["h2", "Heading"], ["h3", "Sub-heading"], ["h4", "Small heading"]]
      .forEach(function (o) { style.appendChild(el("option", { value: o[0], text: o[1] })); });
    // No hold() here: cancelling mousedown on a <select> suppresses the native popup, and the caret
    // is replayed from savedRange anyway. Nor does mousedown touch selectedIndex: from Firefox 137
    // the dropdown is DOM-rendered, so clicking an option fires a SECOND mousedown that bubbles to
    // the select — anything that resets the value there wipes the pick before change reads it.
    style.addEventListener("blur", function () { syncBar(); });   // dismissed without picking: show the caret's style again
    style.addEventListener("change", function () {
      if (style.value) exec("formatBlock", "<" + style.value + ">");
    });

    var bold = b("B", "Bold", function () { exec("bold"); }, "tb-b"),
        ital = b("I", "Italic", function () { exec("italic"); }, "tb-i"),
        und = b("U", "Underline", function () { exec("underline"); }, "tb-u"),
        strike = b("S", "Strikethrough", function () { exec("strikeThrough"); }, "tb-s");

    var file = el("input", { type: "file", accept: "image/*", style: "display:none" });
    var note = el("small", { "class": "tb-note" });
    file.addEventListener("change", function () {
      if (!file.files.length) return;
      note.textContent = "Uploading…";
      upload(file.files[0], "", function (m) {
        note.textContent = "";
        exec("insertHTML", '<img src="' + m.url + '" alt="">');
        altPrompt(m.url);
        file.value = "";
      }, function (err) { note.textContent = err; file.value = ""; });
    });

    function insertTable() {
      var spec = prompt("How many rows and columns?", "3 x 2");
      var m = spec && /(\d+)\s*[x×]\s*(\d+)/i.exec(spec);
      if (!m) return;
      var rows = Math.max(1, Math.min(+m[1], 50)), cols = Math.max(1, Math.min(+m[2], 12)), html = "<table><tbody>";
      for (var r = 0; r < rows; r++) {
        html += "<tr>";
        for (var c = 0; c < cols; c++) html += (r ? "<td>&nbsp;</td>" : "<th>&nbsp;</th>");
        html += "</tr>";
      }
      exec("insertHTML", html + "</tbody></table><p><br></p>");
    }

    function colour(cmd, title, initial) {
      var i = el("input", { type: "color", "class": "tb-colour", title: title, value: initial });
      i.addEventListener("input", function () { exec(cmd, i.value); });   // no hold(): it would block the picker
      return i;
    }

    function insertSection() {
      var at = selected > -1 ? selected + 1 : MODEL.length;
      chooser("Insert", sectionItems().concat([{ key: "__layout", icon: "▤", label: "Start from a layout…",
                                                 text: "Replace the page with a ready-made set of sections." }]), function (t) {
        if (t === "__layout") return openLayouts();
        MODEL.splice(at, 0, { type: t, data: seedFor(t) });
        redrawForm();
        markDirty();
        canvasInsert(at);
      });
    }

    bar.appendChild(group([b("↶", "Undo", function () { exec("undo"); }), b("↷", "Redo", function () { exec("redo"); })]));
    bar.appendChild(group([style]));
    bar.appendChild(group([bold, ital, und, strike, b("Tx", "Remove formatting", function () { exec("removeFormat"); })]));
    // formatBlock only ever wraps, so quote needs its own way back out: outdent is what unwraps a
    // blockquote in both engines.
    var quote = b("❝", "Quote", function () {
      if (caretBlock("blockquote")) exec("outdent"); else exec("formatBlock", "<blockquote>");
    });
    bar.appendChild(group([b("•", "Bulleted list", function () { exec("insertUnorderedList"); }),
                           b("1.", "Numbered list", function () { exec("insertOrderedList"); }),
                           quote,
                           b("—", "Divider", function () { exec("insertHTML", "<hr><p><br></p>"); })]));
    bar.appendChild(group([b("🔗", "Add a link", function () { var u = prompt("Link address", "https://"); if (u) exec("createLink", u); }),
                           b("🖼", "Insert a picture", function () { file.click(); }),
                           b("▦", "Insert a table", insertTable),
                           b("</>", "Embed code from another service", function () {
                             var h = prompt("Paste the embed code (YouTube, Google Maps, …)");
                             if (h) exec("insertHTML", h);
                           })]));
    var align = { left: b("⇤", "Align left", function () { exec("justifyLeft"); }),
                  center: b("↔", "Centre", function () { exec("justifyCenter"); }),
                  right: b("⇥", "Align right", function () { exec("justifyRight"); }) };
    bar.appendChild(group([align.left, align.center, align.right,
                           colour("foreColor", "Text colour", "#1f2937"),
                           colour("hiliteColor", "Highlight", "#fef08a")]));
    bar.appendChild(group([b("+ Section", "Insert a designed section", insertSection, "tb-wide")]));
    bar.appendChild(file);
    bar.appendChild(note);

    var HINT = document.getElementById("pane-hint"), HINT_ON = HINT && HINT.innerHTML;

    syncBar = function () {                       // reflect the caret, the way a real toolbar does
      var d = cdoc();
      if (!d) return;
      // A command needs a caret in a rich field. Without one execCommand does nothing, so the
      // toolbar must go dead rather than paint a state it cannot deliver — a control that silently
      // snaps back to "Normal text" is worse than one that is visibly switched off.
      var live = !!(liveField() && savedField.hasAttribute("data-rich"));
      bar.classList.toggle("tb-off", !live);
      [style, bold, ital, und, strike, quote, align.left, align.center, align.right]
        .forEach(function (x) { x.disabled = !live; });
      if (HINT) HINT.innerHTML = live ? HINT_ON : "Click in the page to start editing.";
      if (!live) return;
      try {
        bold.classList.toggle("on", d.queryCommandState("bold"));
        ital.classList.toggle("on", d.queryCommandState("italic"));
        und.classList.toggle("on", d.queryCommandState("underline"));
        strike.classList.toggle("on", d.queryCommandState("strikeThrough"));
        quote.classList.toggle("on", !!caretBlock("blockquote"));
        // a lit button is what tells the editor a second click switches it back off
        var line = caretBlock(), at = line ? d.defaultView.getComputedStyle(line).textAlign : "";
        if (at === "start" || at === "justify") at = "left";
        Object.keys(align).forEach(function (k) { align[k].classList.toggle("on", k === at); });
        var blk = (d.queryCommandValue("formatBlock") || "").toLowerCase();
        style.value = ["p", "h2", "h3", "h4"].indexOf(blk) > -1 ? blk : "";
      } catch (e) { /* no selection in the canvas yet */ }
    };
  }

  // ---- "/" inserts a section at the caret ------------------------------------
  var slashBox = null, slashOff = null;

  function closeSlash() {
    if (slashOff) { slashOff(); slashOff = null; }
    if (slashBox) { slashBox.remove(); slashBox = null; }
  }

  function lineOf(container, f) {               // the block-level line the caret sits on
    var n = container.nodeType === 1 ? container : container.parentNode;
    while (n && n !== f && n.parentNode !== f) n = n.parentNode;
    return n === f ? f : n;
  }

  function splitAt(node, f, line, type) {
    var i = +node.getAttribute("data-b"), before = [], after = [], seen = false;
    Array.prototype.forEach.call(f.childNodes, function (n) {
      if (n === line) { seen = true; return; }
      (seen ? after : before).push(n);
    });
    function html(list) {
      var box = f.ownerDocument.createElement("div");
      list.forEach(function (n) { box.appendChild(n.cloneNode(true)); });
      return box.innerHTML;
    }
    var head = line === f ? "" : html(before), tail = line === f ? "" : html(after);
    var ins = [{ type: type, data: seedFor(type) }, { type: "rich_text", data: { html: tail } }];
    if (head) {
      MODEL[i].data.html = head;
      MODEL.splice.apply(MODEL, [i + 1, 0].concat(ins));
      focusOnLoad = i + 2;
    } else {                                     // the "/" line was the whole paragraph: replace it
      MODEL.splice.apply(MODEL, [i, 1].concat(ins));
      focusOnLoad = i + 1;
    }
    redrawForm();
    markDirty();
    canvasFull();
  }

  function openSlash(node, f, line) {
    closeSlash();
    var d = f.ownerDocument, rect = line.getBoundingClientRect(), fr = FRAME.getBoundingClientRect();
    var list = el("div", { "class": "iop-slash" });
    slashBox = list;
    list.style.top = (window.scrollY + fr.top + rect.bottom + 6) + "px";
    list.style.left = (window.scrollX + fr.left + rect.left) + "px";

    var items = sectionItems(), shown = items;
    function draw() {
      var q = (line.textContent || "").replace(/^\//, "").trim().toLowerCase();
      shown = items.filter(function (it) { return !q || (it.label + " " + it.text).toLowerCase().indexOf(q) > -1; });
      list.innerHTML = "";
      shown.slice(0, 8).forEach(function (it, n) {
        var row = el("button", { type: "button", "class": "iop-slash-row" + (n ? "" : " on") }, [
          el("span", { "class": "iop-icon", text: it.icon || "▦" }), el("strong", { text: it.label })
        ]);
        row.addEventListener("mousedown", function (e) { e.preventDefault(); });
        row.addEventListener("click", function () { pick(it.key); });
        list.appendChild(row);
      });
      if (!shown.length) list.appendChild(el("p", { "class": "muted", text: "Nothing matches." }));
    }
    function pick(type) { closeSlash(); splitAt(node, f, line, type); }
    function key(e) {
      if (!slashBox) return;
      if (e.key === "Escape") { closeSlash(); return; }
      if (e.key === "Enter" && shown.length) { e.preventDefault(); pick(shown[0].key); return; }
      setTimeout(function () {                    // let the keystroke land in the line first
        if (!slashBox) return;
        if ((line.textContent || "").charAt(0) !== "/") { closeSlash(); return; }
        draw();
      }, 0);
    }
    d.addEventListener("keydown", key);
    slashOff = function () { d.removeEventListener("keydown", key); };
    document.body.appendChild(list);
    draw();
  }

  function bindSlash(node, f) {
    f.addEventListener("keyup", function (e) {
      if (e.key !== "/" || slashBox) return;
      var d = f.ownerDocument, sel = d.defaultView.getSelection();
      if (!sel || !sel.rangeCount) return;
      var line = lineOf(sel.getRangeAt(0).startContainer, f);
      if (!line || (line.textContent || "").trim() !== "/") return;   // only on an otherwise empty line
      openSlash(node, f, line);
    });
  }

  // ---- preview: the page exactly as a visitor gets it ------------------------
  /* The editing canvas is honest about the content but says nothing about the header, the footer,
     the breadcrumbs or the social card — and it adds outlines and placeholders a visitor never
     sees. Preview swaps the same iframe for a real render of post.html + base.html, built by the
     server from the form as it stands. A draft cannot be seen any other way: db.live() gates every
     public lookup on status='published'. */
  var VIEW = "edit", DEVICE = 1440;

  function previewUrl(part) {
    return "/admin/preview?type=" + encodeURIComponent(SPEC.type || "page") +
           (SPEC.pk ? "&pk=" + SPEC.pk : "") + (part ? "&part=" + part : "");
  }

  // The whole form, so the server can run it through the same _form_body() that Save uses.
  function formBody() {
    var form = document.getElementById("post-form"), body = new FormData(form);
    body.set("blocks", JSON.stringify(MODEL.filter(written)));   // the textarea is only written on submit
    return body;
  }

  function askPreview(part, done) {
    var key = "pv" + (part || ""), mine = tokens[key] = (tokens[key] || 0) + 1;
    fetch(previewUrl(part), { method: "POST", body: formBody(), credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.text() : Promise.reject(r.statusText); })
      .then(function (html) { if (tokens[key] === mine) done(html); })   // a newer request already won
      .catch(function () {});
  }

  function renderPreview() {
    if (!FRAME || VIEW !== "preview") return;
    askPreview("", function (html) {
      FRAME.onload = function () { FRAME.onload = null; wirePreview(); };
      FRAME.srcdoc = html;
    });
    var card = document.getElementById("seo-card");
    if (card) askPreview("card", function (html) { card.innerHTML = html; });
  }

  function wirePreview() {
    var d = cdoc();
    if (!d) return;
    d.addEventListener("submit", function (e) { e.preventDefault(); }, true);   // no real leads from a preview
    d.addEventListener("click", function (e) {
      var a = e.target.closest && e.target.closest("a");
      if (!a) return;
      e.preventDefault();                       // navigating would replace the preview with a real page
      var href = a.getAttribute("href") || "";
      if (href && href.charAt(0) !== "#") window.open(href, "_blank", "noopener");
    }, true);
  }

  /* The iframe IS the viewport, so the site's own breakpoints answer honestly. Show a device width
     by rendering at that width and scaling down to the pane; the height is divided by the same
     factor so the scaled result fills the pane exactly instead of leaving a gap. */
  function fitPreview() {
    var wrap = document.getElementById("canvas-wrap");
    if (!FRAME || !wrap) return;
    if (VIEW !== "preview") {
      FRAME.style.width = FRAME.style.height = FRAME.style.transform = "";
      wrap.style.height = "";
      return;
    }
    var pane = wrap.clientWidth, k = Math.min(1, pane / DEVICE), h = Math.round(window.innerHeight * 0.76);
    FRAME.style.width = DEVICE + "px";
    FRAME.style.height = Math.round(h / k) + "px";
    FRAME.style.transformOrigin = "top left";
    FRAME.style.transform = "scale(" + k + ")";
    wrap.style.height = h + "px";
  }

  function setView(v) {
    VIEW = v;
    closeSlash();
    ["doc-toolbar", "pane-hint"].forEach(function (id) {
      var n = document.getElementById(id);
      if (n) n.hidden = v !== "edit";
    });
    ["pv-device", "seo-card"].forEach(function (id) {
      var n = document.getElementById(id);
      if (n) n.hidden = v !== "preview";
    });
    Array.prototype.forEach.call(document.querySelectorAll("#view-mode button"), function (b) {
      b.classList.toggle("on", b.getAttribute("data-view") === v);
    });
    fitPreview();
    if (v === "preview") {
      renderPreview();
    } else {
      focusOnLoad = -1;      // coming back from preview should not yank the caret to the top
      canvasFull();
    }
  }

  function initPreview() {
    var mode = document.getElementById("view-mode"), dev = document.getElementById("pv-device");
    if (!mode) return;
    Array.prototype.forEach.call(mode.querySelectorAll("button"), function (b) {
      b.addEventListener("click", function () { setView(b.getAttribute("data-view")); });
    });
    if (dev) Array.prototype.forEach.call(dev.querySelectorAll("button"), function (b) {
      b.addEventListener("click", function () {
        DEVICE = +b.getAttribute("data-w");
        Array.prototype.forEach.call(dev.querySelectorAll("button"), function (x) { x.classList.toggle("on", x === b); });
        fitPreview();
      });
    });
    window.addEventListener("resize", fitPreview);
  }

  // ---- tabs -----------------------------------------------------------------
  function initTabs() {
    var tabs = document.getElementById("content-tabs");
    if (!tabs) return;
    var panes = { visual: document.getElementById("pane-visual"), form: document.getElementById("pane-form"), json: document.getElementById("pane-json") };
    function show(want) {
      Array.prototype.forEach.call(tabs.querySelectorAll("button"), function (x) { x.classList.toggle("on", x.getAttribute("data-tab") === want); });
      for (var k in panes) if (panes[k]) panes[k].hidden = k !== want;
      if (want === "json" && AREA) AREA.value = JSON.stringify(MODEL, null, 2);
    }
    Array.prototype.forEach.call(tabs.querySelectorAll("button"), function (b) {
      b.addEventListener("click", function () { show(b.getAttribute("data-tab")); });
    });
    tabs.hidden = false;
    show("visual");
    return show;
  }

  // ---- wiring ---------------------------------------------------------------
  function initBlocks() {
    var mount = document.getElementById("blocks-editor"),
        data = document.getElementById("editor-data"),
        form = document.getElementById("post-form");
    AREA = document.querySelector('textarea[name="blocks"]');
    if (!mount || !data || !AREA || !form) return;
    SPEC = JSON.parse(data.textContent);
    MEDIA = SPEC.media || [];
    FRAME = document.getElementById("canvas");
    panel = document.getElementById("block-settings");
    initMediaSelects();
    buildToolbar();
    initPreview();
    var show = initTabs();

    var parsed;
    try { parsed = JSON.parse(AREA.value || "[]"); } catch (e) { parsed = null; }
    if (!Array.isArray(parsed)) {   // unparseable JSON from a rejected save: leave the textarea in charge
      mount.appendChild(el("p", { "class": "error", text: "The saved content is not valid JSON — fix it under Advanced." }));
      if (show) show("json");
      return;
    }
    MODEL = parsed;
    if (!MODEL.length) MODEL = [{ type: "rich_text", data: { html: "" } }];   // open with a caret, not a dialog

    var list = el("div");
    redrawForm = function () {
      list.innerHTML = "";
      if (!MODEL.length) list.appendChild(el("p", { "class": "muted", text: "No sections yet — add one below." }));
      MODEL.forEach(function (b, i) { list.appendChild(blockCard(b, i, MODEL, function () { redrawForm(); canvasFull(); })); });
    };
    redrawForm();
    mount.appendChild(list);
    mount.appendChild(el("div", { "class": "toolbar" }, [btn("+ Add a section", "Choose a section to add", function () { openInserter(MODEL.length); })]));

    if (panel) {
      // fieldInput() mutates in place and reports nothing, so watch the panel for any activity
      // and redraw the one block it belongs to. Cheaper than threading a callback through every widget.
      var pending = null;
      var schedule = function () {
        clearTimeout(pending);
        pending = setTimeout(function () { if (selected > -1) canvasBlock(selected); }, 250);
        markDirty();
      };
      ["input", "change", "click"].forEach(function (ev) { panel.addEventListener(ev, schedule); });
      showPanel(-1);
    }

    focusOnLoad = 0;   // land the caret in the document, the way Docs does
    canvasFull();

    // The Advanced panel edits the same data. Hand-edited JSON is read back on blur, so whichever
    // side was touched last wins instead of being silently overwritten on save.
    AREA.addEventListener("change", function () {
      var next;
      try { next = JSON.parse(AREA.value || "[]"); } catch (e) { next = null; }
      if (!Array.isArray(next)) { alert("That is not a valid list of blocks — the editor is unchanged."); return; }
      markDirty();
      setBlocks(next);
    });
    document.addEventListener("input", function (e) {   // the title feeds the canvas page head
      if (e.target.id !== "post-title" && e.target.name !== "excerpt") return;
      markDirty();
      var d = cdoc(), head = d && d.querySelector(e.target.id === "post-title" ? ".page-title" : ".page-head .lead");
      if (head) head.textContent = e.target.value || (e.target.id === "post-title" ? "Untitled page" : "");
    });
    form.addEventListener("submit", function () {
      dirty = false;
      AREA.value = JSON.stringify(MODEL.filter(written), null, 2);
    });
    var pvPending = null;
    ["input", "change"].forEach(function (ev) {      // while Preview is up, keep it a step behind your typing
      form.addEventListener(ev, function () {
        if (VIEW !== "preview") return;
        clearTimeout(pvPending);
        pvPending = setTimeout(renderPreview, 500);
      });
    });
    window.addEventListener("beforeunload", function (e) { if (dirty) { e.preventDefault(); e.returnValue = ""; } });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initSlug();
    initBlocks();
  });
})();
