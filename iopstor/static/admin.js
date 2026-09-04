/* Admin progressive enhancement: auto slug, inline media upload, the document editor.
   No framework, no build step. Every part is a no-op when its hook is absent, and the
   plain form underneath (the Advanced textarea named "blocks", plain selects) still works without JS. */
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
  var PASTE_OK = { P: 1, BR: 1, H2: 1, H3: 1, H4: 1, H5: 1, H6: 1, UL: 1, OL: 1, LI: 1, STRONG: 1, EM: 1, U: 1, A: 1, S: 1,
                   BLOCKQUOTE: 1, TABLE: 1, THEAD: 1, TBODY: 1, TR: 1, TH: 1, TD: 1, IMG: 1, HR: 1, CODE: 1, PRE: 1 };
  // H1 is still demoted on the way in: a pasted Word or Docs file always carries its title as an
  // H1, and the page already has one. The toolbar can still set H1 deliberately.
  var PASTE_AS = { B: "STRONG", I: "EM", DIV: "P", H1: "H2", STRIKE: "S", DEL: "S" };
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

  // mirrors iopstor/db.py unique_slug(): base if nobody holds it, else base + three random letters.
  // Memoised per base, so the address does not reshuffle under you on the next keystroke.
  var LETTERS = "abcdefghijklmnopqrstuvwxyz";
  function freeSlug(base, taken, seen) {
    if (!seen[base]) {
      var s = base;
      while (taken.indexOf(s) > -1) {
        s = base + "-";
        for (var i = 0; i < 3; i++) s += LETTERS[Math.floor(Math.random() * 26)];
      }
      seen[base] = s;
    }
    return seen[base];
  }

  function initSlug() {
    var title = document.getElementById("post-title"), slug = document.getElementById("post-slug");
    if (!title || !slug) return;
    var saved = slug.value, unlocked = false,
        hint = document.getElementById("slug-hint"),
        madeFrom = hint ? hint.textContent : "",
        seen = {},
        // ponytail: a page-load snapshot of this type's slugs. A post created in another tab meanwhile
        // still lands on apply_post(), which resolves it the same way on create.
        taken = (slug.getAttribute("data-taken") || "").split(" ").filter(Boolean);

    function check() {
      var v = slugify(slug.value),
          clash = !!v && taken.indexOf(v) > -1,
          fromTitle = slugify(title.value),
          suffixed = !clash && !!v && !saved && !unlocked && v !== fromTitle;   // the title's address was taken
      if (hint) {
        hint.textContent = clash ? "That address is already used \u2014 try \u201c" + freeSlug(v, taken, seen) + "\u201d."
                         : suffixed ? "\u201c" + fromTitle + "\u201d is already used, so this page is at \u201c" + v + "\u201d."
                         : madeFrom;
        hint.className = clash ? "slug-taken" : "";
      }
      // ponytail: a readonly input is barred from constraint validation, so this only blocks Save once
      // Edit has unlocked the field. The message above shows either way.
      slug.setCustomValidity(clash ? "This web address is already used. Pick another one." : "");
    }

    title.addEventListener("input", function () {
      // A new post takes the first free address outright — nobody should be stopped from writing a
      // page because someone else used the title. A deliberate rename (below) still gets the warning.
      if (!saved && !unlocked) slug.value = freeSlug(slugify(title.value), taken, seen);
      check();
    });
    slug.addEventListener("input", check);
    slug.parentNode.appendChild(btn("Edit", "Change the web address", function () {
      if (saved && !confirm("Changing the web address breaks any existing link to this page. Continue?")) return;
      unlocked = true;
      slug.readOnly = false;
      slug.focus();
    }));
    check();   // a rejected save comes back with the clashing slug already in the field
  }

  // ---- categories and tags --------------------------------------------------
  /* Each .term-pick is a checkbox list from the server; this swaps it for a search box and chips.
     Everything it matches against is already in data-all, so there is no request anywhere in here.
     A chip is either an existing term (hidden "terms" = its id, what the form has always posted) or
     one you just named (hidden "new_terms" = "taxonomy:Name"), which _save() turns into a real term. */
  function termPick(box) {
    // ponytail: a page-load snapshot of this taxonomy's terms, like initSlug()'s. A term added in
    // another tab meanwhile is not offered, but naming it still lands on db.ensure_term(), which
    // reuses it rather than making a second one.
    var all = JSON.parse(box.getAttribute("data-all") || "[]"), tax = box.getAttribute("data-tax"),
        picked = [], list = null, boxes = box.querySelector(".term-boxes");

    Array.prototype.forEach.call(box.querySelectorAll('input[name="terms"]:checked'), function (c) {
      var name = c.parentNode.textContent.trim();
      picked.push({ id: Number(c.value), name: name });
    });
    if (boxes) boxes.remove();          // JS is up: the plain checkboxes are the fallback, not a duplicate

    var chips = el("div", { "class": "chips" }),
        input = el("input", { type: "text", "class": "term-input", autocomplete: "off", id: "tp-" + tax,
                              placeholder: "Search or type a new one…" });
    box.querySelector("label").htmlFor = input.id;   // the taxonomy name was a label with nothing to label
    box.appendChild(chips);
    box.appendChild(input);

    function drawChips() {
      chips.innerHTML = "";
      picked.forEach(function (t, n) {
        var chip = el("span", { "class": "pill chip" + (t.id ? "" : " new"), title: t.id ? "" : "New — created when you save" }, [
          el("span", { text: t.name }),
          el("input", { type: "hidden", name: t.id ? "terms" : "new_terms", value: t.id ? String(t.id) : tax + ":" + t.name })
        ]);
        chip.appendChild(btn("×", "Remove " + t.name, function () { picked.splice(n, 1); drawChips(); }));
        chips.appendChild(chip);
      });
    }

    function has(slug) { return picked.some(function (t) { return slugify(t.name) === slug; }); }

    function add(t) { picked.push(t); input.value = ""; drawChips(); close(); }

    function close() { if (list) { list.remove(); list = null; } }

    function draw() {
      close();
      var q = input.value.trim(), slug = slugify(q);
      if (!q) return;
      var hits = all.filter(function (t) { return t.name.toLowerCase().indexOf(q.toLowerCase()) > -1 && !has(slugify(t.name)); }).slice(0, 8),
          // Matched by slug, like the server: typing "All-Flash" when "all flash" exists offers that
          // term rather than proposing a near-duplicate.
          known = has(slug) || all.some(function (t) { return slugify(t.name) === slug; });
      list = el("div", { "class": "iop-slash" });
      hits.forEach(function (t, n) { list.appendChild(row(t.name, n === 0, function () { add({ id: t.id, name: t.name }); })); });
      if (!known) list.appendChild(row("Create “" + q + "”", !hits.length, function () { add({ id: null, name: q }); }));
      if (list.children.length) box.appendChild(list); else close();
    }

    function row(text, on, onclick) {
      var r = el("button", { type: "button", "class": "iop-slash-row" + (on ? " on" : "") }, [el("strong", { text: text })]);
      r.addEventListener("mousedown", function (e) { e.preventDefault(); });   // clicking a row must not blur the input
      r.addEventListener("click", onclick);
      return r;
    }

    function move(step) {
      if (!list) return;
      var rows = list.children, at = -1, i;
      for (i = 0; i < rows.length; i++) if (rows[i].classList.contains("on")) at = i;
      if (at > -1) rows[at].classList.remove("on");
      rows[Math.max(0, Math.min(rows.length - 1, at + step))].classList.add("on");
    }

    input.addEventListener("input", draw);
    input.addEventListener("blur", close);
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter") {
        e.preventDefault();          // unconditional: this input is inside #post-form, so Enter would save the post
        if (list) list.querySelector(".on").click();
      } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        move(e.key === "ArrowDown" ? 1 : -1);
      } else if (e.key === "Escape") {
        close();
      } else if (e.key === "Backspace" && !input.value && picked.length) {
        picked.pop();
        drawChips();
      }
    });
    drawChips();
  }

  function initTerms() {
    Array.prototype.forEach.call(document.querySelectorAll(".term-pick"), termPick);
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
     `get`/`set` read and write whatever holds the value (a form <select> or a block field).
     `only` is a mime prefix ("image/", "application/pdf") that narrows both the list and the
     file picker; "" or omitted offers everything the server accepts. */
  function mediaWidget(get, set, only) {
    var sel = el("select"), thumb = el("span", { "class": "media-thumb" }),
        file = el("input", { type: "file", accept: only === "image/" ? "image/*" : (only || "image/*,application/pdf") }),
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
        if (only && m.mime && m.mime.indexOf(only) !== 0) return;
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
      var only = s.getAttribute("data-media") === "images" ? "image/" : "";
      s.parentNode.insertBefore(mediaWidget(function () { return hidden.value; },
                                           function (v) { hidden.value = v; }, only), s);
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
    /* This body lives in the ADMIN document, so a dialog input really does take its selection away
       (the canvas toolbar gets away with it only because its caret is in another document). Stash
       the range on the toolbar's mousedown, which fires before focus moves, and replay it after. */
    var rng = null;
    bar.addEventListener("mousedown", function () {
      var sel = document.getSelection();
      if (sel.rangeCount && body.contains(sel.getRangeAt(0).commonAncestorContainer)) rng = sel.getRangeAt(0).cloneRange();
      else rng = null;
    });
    function replay(r) {
      body.focus();
      if (!r) return;
      var sel = document.getSelection();
      sel.removeAllRanges();
      sel.addRange(r);
    }
    function rtLink() {
      var n = rng && rng.commonAncestorContainer, a = null;
      if (n) { n = n.nodeType === 1 ? n : n.parentNode; a = n.closest("a"); }
      if (a && !body.contains(a)) a = null;
      linkDialog({ url: a ? a.getAttribute("href") : "",
                   text: a ? a.textContent : (rng ? rng.toString() : ""),
                   blank: !!(a && a.getAttribute("target") === "_blank") },
        function (html) { replay(a ? rangeOn(a) : rng); document.execCommand("insertHTML", false, html); onChange(body.innerHTML); },
        a && function () { replay(rangeOn(a)); document.execCommand("unlink", false, null); onChange(body.innerHTML); });
    }
    RT_BUTTONS.forEach(function (b) {
      bar.appendChild(btn(b[0], b[2], function () {
        var cmd = b[1].split(":");
        if (cmd[0] === "createLink") return rtLink();
        body.focus();
        document.execCommand(cmd[0], false, cmd[1] || null);
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

  // ---- a section's fields ---------------------------------------------------
  var SPEC = null;  // {blocks: {type: [required, optional]}, ui: {widgets, items, labels, kinds}, media, post_types}

  function widgetFor(type, field) {
    return SPEC.ui.widgets[type + "." + field] || SPEC.ui.widgets[field] || "text";
  }
  var HEAD_LEVELS = [["p", "Normal text"], ["h1", "H1 \u2014 Page title"], ["h2", "H2 \u2014 Heading"],
                     ["h3", "H3 \u2014 Sub-heading"], ["h4", "H4 \u2014 Small heading"],
                     ["h5", "H5 \u2014 Smaller"], ["h6", "H6 \u2014 Smallest"]];
  var HEAD_TAGS = HEAD_LEVELS.map(function (o) { return o[0]; });
  /* Size is separate from level on purpose: a level says what a line *is* (and Google reads it),
     a size only says how big it looks. Values are absolute rem, so a size inside a size does not
     compound. "normal" removes the wrapper instead of writing one, which is a true reset. */
  var TEXT_SIZES = [["0.875rem", "Small"], ["normal", "Normal"], ["1.25rem", "Large"],
                    ["1.5rem", "Larger"], ["2rem", "Huge"]];
  var BLOCK_NAMES = { cta: "CTA", faq: "FAQ", embed_html: "Embed HTML", rich_text: "Rich text" };
  var NEVER_NESTED = ["columns", "hero"];   // mirrors blocks.py; a column holds sections, not a grid or the page H1
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
    if (widget === "media") return mediaWidget(function () { return data[key]; }, set, "image/");
    if (widget === "pdf") return mediaWidget(function () { return data[key]; }, set, "application/pdf");
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

  /* items / images / rows: a list of {subfield: value} rows. `make` and `cells` are the two things a
     columns block needs different — its rows are arrays of blocks, not rows of fields — and the ↑ ↓ ✕
     splice loop is worth having in one place rather than two. */
  function repeater(type, key, data, make, cells) {
    var subs = SPEC.ui.items[type] || [];
    if (!Array.isArray(data[key])) data[key] = [];
    var list = el("div", { "class": "rep" });

    function draw() {
      list.innerHTML = "";
      data[key].forEach(function (row, i) {
        var cells_ = cells ? cells(row, i) : subs.map(function (s) { return labelled(labelFor(s), false, fieldInput(type, s, row)); });
        var controls = el("span", { "class": "rep-controls" }, [
          btn("↑", "Move up", function () { if (i) { data[key].splice(i - 1, 0, data[key].splice(i, 1)[0]); draw(); } }),
          btn("↓", "Move down", function () { if (i < data[key].length - 1) { data[key].splice(i + 1, 0, data[key].splice(i, 1)[0]); draw(); } }),
          btn("✕", "Remove", function () {   // a row that is itself a list (a column) takes sections with it
            if (Array.isArray(data[key][i]) && data[key][i].length &&
                !confirm("Remove this column and everything in it?")) return;
            data[key].splice(i, 1);
            draw();
          })
        ]);
        list.appendChild(el("div", { "class": "rep-row" }, cells_.concat([controls])));
      });
      list.appendChild(btn("+ Add " + labelFor(key).toLowerCase().replace(/s$/, ""), "Add a row", function () {
        var row = {};
        subs.forEach(function (s) { row[s] = ""; });
        data[key].push(make ? make() : row);
        draw();
      }));
    }
    draw();
    return el("div", {}, [el("strong", { text: labelFor(key) }), list]);
  }

  // The fields of one section — what ⚙ opens. Words on the page are edited on the page; this is
  // for the rest: pictures, links, choices, and the rows of a Cards / FAQ / Numbers section.
  function blockFields(block) {
    if (!block.data || typeof block.data !== "object") block.data = {};
    var body = el("div", { "class": "blk-fields" });
    if (!SPEC.blocks[block.type]) {
      body.appendChild(el("p", { "class": "muted", text: "Unknown section type — edit it under Advanced." }));
    } else {
      fieldsOf(block.type).forEach(function (f) {
        if (f.key === "cols") {
          // the sections inside a column are edited on the page; the panel only adds, moves and removes
          body.appendChild(repeater(block.type, "cols", block.data,
            function () { return []; },
            function (col, i) {
              return [el("span", { text: "Column " + (i + 1) + " \u2014 " +
                                        col.length + " section" + (col.length === 1 ? "" : "s") })];
            }));
        } else if (SPEC.ui.items[block.type] && (f.key === "items" || f.key === "images" || f.key === "rows")) {
          body.appendChild(repeater(block.type, f.key, block.data));
        } else {
          body.appendChild(labelled(labelFor(f.key), f.required, fieldInput(block.type, f.key, block.data)));
        }
      });
    }
    return body;
  }

  // ---- shared model ---------------------------------------------------------
  /* One array, two views and a textarea. fieldInput() mutates block objects in place, so the canvas,
     the settings popover and the Advanced textarea all point at the same objects — there is no sync
     layer. The one dangerous move is REPLACING the array; setBlocks() is the only place that happens. */
  var MODEL = [], AREA = null, dirty = false;

  /* A block's address is a dotted PATH, not an index: "3" is a top-level block, "3.1.0" is block 3's
     column 1, first block. Parts alternate block/column, so the count is always odd. Everything that
     used to parse +getAttribute("data-b") goes through these three instead. */
  function listAt(path) {                 // {arr, i} — the array a path lives in, and where in it
    var p = String(path).split("."), arr = MODEL;
    while (p.length > 2) {
      var b = arr[+p.shift()], c = +p.shift();
      arr = b && b.data && b.data.cols && b.data.cols[c];
      if (!Array.isArray(arr)) return { arr: null, i: -1 };
    }
    return { arr: arr, i: +p[0] };
  }
  function blockAt(path) { var r = listAt(path); return r.arr ? r.arr[r.i] : null; }
  function siblingPath(path, n) { var p = String(path).split("."); p[p.length - 1] = n; return p.join("."); }
  function isNested(path) { return String(path).split(".").length > 1; }

  function setBlocks(next) {
    closePanel();
    MODEL = Array.isArray(next) ? next : [];
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
  // written(), applied all the way down. Returns new arrays: a rejected save must not eat the empty
  // paragraph an editor still has the caret in.
  function prune(list) {
    return list.filter(written).map(function (b) {
      if (b.type !== "columns" || !b.data || !Array.isArray(b.data.cols)) return b;
      var data = {};
      for (var k in b.data) data[k] = b.data[k];
      data.cols = b.data.cols.map(prune);
      return { type: b.type, data: data };
    });
  }

  function seedFor(type) {
    return JSON.parse(JSON.stringify((SPEC.ui.seed && SPEC.ui.seed[type]) || {}));  // never hand out the shared seed
  }

  // ---- the visual canvas ----------------------------------------------------
  /* The iframe holds a real server render (POST /admin/canvas) of the blocks currently in memory,
     so what an editor sees is exactly what render_blocks() will publish. Same origin, so we drive
     contentDocument directly. Typing never re-renders; a structural change swaps ONE <section>. */
  var FRAME = null, selected = null, tokens = {};

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

  var focusOnLoad = null;

  function canvasFull() {
    if (!FRAME) return;
    if (VIEW === "preview") return renderPreview();   // whatever changed, preview is what is on screen
    ask("full", {}, function (html) {
      FRAME.onload = function () {
        FRAME.onload = null;
        wireDoc();
        if (focusOnLoad) { focusBlock(focusOnLoad); focusOnLoad = null; }
        syncBar();                       // the old caret died with the old document; say so
      };
      FRAME.srcdoc = html;
    });
  }

  /* Blocks live in containers: #main, or one [data-col] of a columns block. These four are the
     bridge between a container in the canvas document and the array it stands for in MODEL. */
  function blocksIn(box) {                // the blocks this container owns, in document order
    return Array.prototype.filter.call(box.querySelectorAll("[data-b]"), function (n) {
      return n.parentNode.closest("[data-col],#main") === box;
    });
  }
  function boxFor(path) {                 // #main, or the [data-col] that holds this path
    var d = cdoc(), p = String(path).split(".");
    if (!d) return null;
    if (p.length === 1) return d.getElementById("main");
    var owner = d.querySelector('[data-b="' + p.slice(0, -2).join(".") + '"]');
    return owner && owner.querySelector('[data-col="' + p[p.length - 2] + '"]');
  }
  function pathIn(box, i) {               // the path a block at index i of this container would have
    if (box.id === "main") return String(i);
    return box.closest("[data-b]").getAttribute("data-b") + "." + box.getAttribute("data-col") + "." + i;
  }
  function listIn(box) {                  // the MODEL array this container stands for
    if (box.id === "main") return MODEL;
    var owner = blockAt(box.closest("[data-b]").getAttribute("data-b"));
    return owner && owner.data && owner.data.cols && owner.data.cols[+box.getAttribute("data-col")];
  }

  function canvasBlock(path) {        // one block's data changed in its settings popover
    var d = cdoc();
    if (!d || !blockAt(path)) return;
    ask("b" + path, { p: path }, function (html) {
      var node = d.querySelector('[data-b="' + path + '"]'), fresh = fragment(d, html);
      if (!node || !fresh) return canvasFull();
      node.replaceWith(fresh);           // the server rendered it at its own path, so no renumbering
      wireTree(fresh);
      paint();
      bars();
      syncBar();                         // replaceWith just threw the remembered caret away
    });
  }

  function canvasInsert(path, focus) {   // MODEL already holds the new block at this path
    var d = cdoc();
    if (!d) return canvasFull();
    ask("b" + path, { p: path }, function (html) {
      var box = boxFor(path), fresh = fragment(d, html);
      if (!box || !fresh) return canvasFull();
      box.insertBefore(fresh, blocksIn(box)[+String(path).split(".").pop()] || null);
      renumber();
      wireTree(fresh);
      bars();
      if (focus) focusBlock(path); else select(path);
      fresh.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  }

  /* Document order alone no longer gives the numbering: a column's blocks sit inside their parent,
     so renumbering has to descend container by container instead of over one flat NodeList. */
  function renumber(box, prefix) {
    var d = cdoc();
    if (!d) return;
    box = box || d.getElementById("main");
    if (!box) return;
    blocksIn(box).forEach(function (node, i) {
      var p = prefix == null ? String(i) : prefix + "." + i;
      node.setAttribute("data-b", p);
      Array.prototype.forEach.call(node.querySelectorAll("[data-col]"), function (c) {
        if (c.closest("[data-b]") === node) renumber(c, p + "." + c.getAttribute("data-col"));
      });
    });
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
    var r = listAt(at);
    if (!r.arr) return;
    r.arr.splice(r.i, 0, { type: "rich_text", data: { html: "" } });
    markDirty();
    canvasInsert(at, true);
  }

  function focusBlock(path) {
    var d = cdoc(), node = d && d.querySelector('[data-b="' + path + '"]');
    var f = node && Array.prototype.filter.call(node.querySelectorAll("[data-f]"), function (x) {
      return x.closest("[data-b]") === node;      // not a nested block's first field
    })[0];
    if (!f) return;
    f.focus();
    var r = d.createRange(), sel = d.defaultView.getSelection();
    r.selectNodeContents(f);
    r.collapse(true);
    sel.removeAllRanges();
    sel.addRange(r);
    select(path);
  }

  function bars() {                   // the "+" strips live between blocks; rebuild after any move
    var d = cdoc();
    if (!d) return;
    var main = d.getElementById("main");
    if (!main) return;
    Array.prototype.forEach.call(d.querySelectorAll(".iop-add"), function (n) { n.remove(); });
    // every container, so an empty column is a place to type rather than a dead box
    [main].concat(Array.prototype.slice.call(d.querySelectorAll("[data-col]"))).forEach(function (box) {
      var list = blocksIn(box);
      for (var i = 0; i <= list.length; i++) box.insertBefore(addBar(d, pathIn(box, i)), list[i] || null);
    });
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
    var b = blockAt(node.getAttribute("data-b"));
    if (!b || !b.data) return null;
    var row = f.closest("[data-r]");
    if (!row || row === f || row.closest("[data-b]") !== node) return b.data;
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
    f.addEventListener("focus", function () { select(node.getAttribute("data-b")); });
    f.addEventListener("paste", rich ? richPaste : plainPaste);
    if (rich) bindSlash(node, f);
  }

  // ↑ ↓ move within the block's own container: out of a column is a drag, not a button press
  function moveBlock(dir, path) {
    var r = listAt(path), to = r.i + dir, d = cdoc();
    if (!r.arr || to < 0 || to >= r.arr.length) return;
    closePanel();
    r.arr.splice(to, 0, r.arr.splice(r.i, 1)[0]);
    var box = d && boxFor(path);
    if (box) {
      var nodes = blocksIn(box), node = nodes[r.i], ref = nodes[to];
      if (node && ref) ref.parentNode.insertBefore(node, dir > 0 ? ref.nextSibling : ref);
      renumber();
      bars();
    }
    markDirty();
    select(siblingPath(path, to));
  }

  function dupBlock(path) {
    closePanel();
    var r = listAt(path);
    if (!r.arr) return;
    r.arr.splice(r.i + 1, 0, JSON.parse(JSON.stringify(r.arr[r.i])));
    markDirty();
    canvasInsert(siblingPath(path, r.i + 1));
  }

  function delBlock(path) {
    closePanel();
    var r = listAt(path);
    if (!r.arr || !r.arr[r.i]) return;
    if (!confirm("Remove this " + nameFor(r.arr[r.i].type) + " section?")) return;
    r.arr.splice(r.i, 1);
    var d = cdoc(), node = d && d.querySelector('[data-b="' + path + '"]');
    if (node) node.remove();
    renumber();
    bars();
    markDirty();
    select(null);
  }

  function blockBar(d, node) {
    var bar = d.createElement("div");
    bar.className = "iop-bar";
    var at = function () { return node.getAttribute("data-b"); };
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
    name.textContent = nameFor((blockAt(at()) || {}).type || "");
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
    push("⚙", "Pictures, links and settings", function (i) { select(i); openPanel(i); });
    push("✕", "Remove this section", delBlock, "iop-del");
    return bar;
  }

  function wireBlock(node) {
    var d = node.ownerDocument, old = node.querySelector(":scope > .iop-bar");
    if (old) old.remove();
    // a floating toolbar over every paragraph would destroy the document feel; sections keep theirs
    if (((blockAt(node.getAttribute("data-b")) || {}).type) !== "rich_text") node.appendChild(blockBar(d, node));
    // only this block's own fields and clicks: a Columns block must not claim its children's
    Array.prototype.forEach.call(node.querySelectorAll("[data-f]"), function (f) {
      if (f.closest("[data-b]") === node) bindField(node, f);
    });
    node.addEventListener("mousedown", function (e) {
      if (e.target.closest("[data-b]") === node) select(node.getAttribute("data-b"));
    });
  }

  // a fresh fragment can carry nested blocks and their own drop containers
  function wireTree(node) {
    wireBlock(node);
    Array.prototype.forEach.call(node.querySelectorAll("[data-b]"), wireBlock);
    Array.prototype.forEach.call(node.querySelectorAll("[data-col]"), sortable);
  }

  /* Drag a column edge to resize it. Widths live in a <colgroup> built on the first drag, in
     percentages so the table still reflows on a phone, and the two columns either side of the edge
     trade width so the table itself never changes size. site.css switches a table to
     table-layout:fixed only once it has a colgroup, so nothing anyone typed before this existed
     changes shape.
     ponytail: uniform tables only — colspan and ragged rows are ignored. tableHtml() never emits
     either; a pasted table that has them resizes oddly rather than breaking. */
  var GRIP = 6, MIN_COL = 4;                     // px either side of the edge; smallest column, in %

  function colgroupFor(table, cols) {
    var g = table.querySelector(":scope > colgroup");
    if (g && g.children.length === cols) return g;
    if (g) g.remove();
    var d = table.ownerDocument, row = table.rows[0], full = table.getBoundingClientRect().width;
    g = d.createElement("colgroup");
    for (var i = 0; i < cols; i++) {
      var c = d.createElement("col");
      c.style.width = (row.cells[i].getBoundingClientRect().width / full * 100).toFixed(3) + "%";
      g.appendChild(c);
    }
    table.insertBefore(g, table.firstChild);     // a colgroup has to come before thead/tbody
    return g;
  }

  function startColDrag(e) {
    var cell = e.target.closest && e.target.closest("td,th");
    if (!cell || !cell.closest("[data-rich]")) return;
    var row = cell.parentNode, at = cell.cellIndex;
    if (at < 0 || at >= row.cells.length - 1) return;            // the last edge is the table's own
    if (e.clientX < cell.getBoundingClientRect().right - GRIP) return;
    var table = cell.closest("table"), field = cell.closest("[data-f]"), d = cell.ownerDocument;
    if (!table || !field) return;
    var g = colgroupFor(table, row.cells.length),
        a = g.children[at], b = g.children[at + 1],
        full = table.getBoundingClientRect().width,
        aw = parseFloat(a.style.width), bw = parseFloat(b.style.width), x0 = e.clientX;
    e.preventDefault();                          // otherwise the contenteditable starts selecting text
    function move(ev) {
      var by = Math.max(MIN_COL - aw, Math.min((ev.clientX - x0) / full * 100, bw - MIN_COL));
      a.style.width = (aw + by).toFixed(3) + "%";
      b.style.width = (bw - by).toFixed(3) + "%";
    }
    function stop() {
      d.removeEventListener("mousemove", move);
      d.removeEventListener("mouseup", stop);
      table.classList.remove("iop-resizing");
      fire(field);                               // the new HTML goes back into MODEL like any edit
    }
    table.classList.add("iop-resizing");
    d.addEventListener("mousemove", move);
    d.addEventListener("mouseup", stop);
  }

  function wireDoc() {
    var d = cdoc();
    if (!d) return;
    d.addEventListener("mousedown", startColDrag, true);   // before the caret lands in the cell
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
    sortable(d.getElementById("main"));
    Array.prototype.forEach.call(d.querySelectorAll("[data-col]"), sortable);
  }

  /* One Sortable per container, all in the same group, so a section drags between the page and any
     column. oldIndex/newIndex count the .iop-add strips too, so the destination is read back out of
     the DOM the way it always was — and the source path off the item, before renumber() rewrites it. */
  function sortable(box) {
    var Sortable = box && box.ownerDocument.defaultView && box.ownerDocument.defaultView.Sortable;
    if (!Sortable) return;
    Sortable.create(box, {
      draggable: "[data-b]", handle: ".iop-grab", animation: 140, ghostClass: "iop-ghost", chosenClass: "iop-drag",
      group: { name: "iop", put: function (to, from, item) {
        // blocks.py NEVER_NESTED rejects these on save too; this is so the drop never looks legal
        return to.el.id === "main" ||
               NEVER_NESTED.indexOf((blockAt(item.getAttribute("data-b")) || {}).type) < 0;
      } },
      onEnd: function (e) {
        var src = listAt(e.item.getAttribute("data-b")), dst = listIn(e.to), to = blocksIn(e.to).indexOf(e.item);
        if (!src.arr || !dst || to < 0) return canvasFull();
        dst.splice(to, 0, src.arr.splice(src.i, 1)[0]);
        renumber();
        bars();
        markDirty();
        select(e.item.getAttribute("data-b"));
      }
    });
  }

  // ---- selection + the section's settings popover ---------------------------
  function paint() {
    var d = cdoc();
    if (d) Array.prototype.forEach.call(d.querySelectorAll("[data-b]"), function (n) {
      n.classList.toggle("iop-sel", n.getAttribute("data-b") === selected);
    });
  }

  function select(path) {
    if (path === selected) return;   // every mousedown lands here; only repaint on a real change
    selected = path;
    paint();
  }

  /* A section's pictures, links and settings belong to the section, not to a card parked in the
     sidebar — ⚙ on its own toolbar opens them over it. The popover has to live in the ADMIN
     document (blockFields builds nodes with el(), mediaWidget and richText, all parent-document),
     so it is positioned over the iframe from two rects, the way openSlash() already does it. */
  var panelBox = null, panelAt = null, panelPlace = null;

  function closePanel() {
    if (!panelBox) return;
    document.removeEventListener("keydown", panelKey);
    document.removeEventListener("mousedown", panelAway);
    window.removeEventListener("resize", panelPlace);
    window.removeEventListener("scroll", panelPlace, true);
    var d = cdoc();
    if (d) { d.removeEventListener("scroll", panelPlace, true); d.removeEventListener("mousedown", panelAway); }
    panelBox.remove();
    panelBox = null;
    panelAt = null;
    panelPlace = null;
  }

  function panelKey(e) { if (e.key === "Escape") closePanel(); }
  function panelAway(e) {
    // a section's own bar is exempt: closing on its mousedown would undo the ⚙ toggle a moment later
    var bar = e.target.closest && e.target.closest(".iop-bar");
    if (panelBox && !bar && !panelBox.contains(e.target)) closePanel();
  }

  function openPanel(path) {
    var d = cdoc(), node = d && d.querySelector('[data-b="' + path + '"]'), block = blockAt(path);
    if (panelAt === path) return closePanel();    // ⚙ again on the same section shuts it
    closePanel();
    if (!node || !block) return;
    var box = el("div", { "class": "iop-panel" });
    panelBox = box;
    panelAt = path;
    box.appendChild(el("div", { "class": "toolbar" }, [
      el("strong", { text: nameFor(block.type) }),
      el("span", { "class": "spacer" }),
      btn("✕", "Close", closePanel)
    ]));
    box.appendChild(blockFields(block));

    // fieldInput() mutates in place and reports nothing, so watch the popover for any activity
    // and redraw the one block it belongs to. Cheaper than threading a callback through every widget.
    var pending = null;
    ["input", "change", "click"].forEach(function (ev) {
      box.addEventListener(ev, function () {
        clearTimeout(pending);
        pending = setTimeout(function () { if (panelAt) canvasBlock(panelAt); }, 250);
        markDirty();
      });
    });

    panelPlace = function () {
      var live = cdoc(), n = live && live.querySelector('[data-b="' + panelAt + '"]');
      if (!n) return closePanel();
      var r = n.getBoundingClientRect(), fr = FRAME.getBoundingClientRect(), pad = 8;
      // clamp into the window: a section at the far right or scrolled half off must stay reachable
      var top = Math.min(Math.max(fr.top + r.top + 40, pad), window.innerHeight - box.offsetHeight - pad),
          left = Math.min(Math.max(fr.left + r.left + 24, pad), window.innerWidth - box.offsetWidth - pad);
      box.style.top = Math.max(top, pad) + "px";
      box.style.left = Math.max(left, pad) + "px";
    };

    document.body.appendChild(box);
    panelPlace();
    document.addEventListener("keydown", panelKey);
    document.addEventListener("mousedown", panelAway);
    window.addEventListener("resize", panelPlace);
    window.addEventListener("scroll", panelPlace, true);
    d.addEventListener("scroll", panelPlace, true);   // the canvas scrolls inside itself (#canvas is 76vh)
    d.addEventListener("mousedown", panelAway);       // iframe clicks never reach the admin document
  }

  // ---- dialogs ----------------------------------------------------------------
  /* One overlay behind every dialog: the section picker and the toolbar's link, picture, table and
     embed boxes. It mounts on document.body — deliberately OUTSIDE #post-form, so Enter in a field
     cannot submit the post and the form's own preview debounce never sees the typing. Esc, the
     ✕ and a click on the backdrop all close it. Returns close(). */
  function modal(title, kids, wide) {
    function esc(e) { if (e.key === "Escape") close(); }
    function close() { document.removeEventListener("keydown", esc); box.remove(); }
    var card = el("div", { "class": "iop-modal-in" + (wide ? "" : " iop-modal-sm") },
      [el("div", { "class": "toolbar" }, [el("strong", { text: title }), el("span", { "class": "spacer" }),
                                          btn("✕", "Close", function () { close(); })])].concat(kids));
    var box = el("div", { "class": "iop-modal" }, [card]);
    box.addEventListener("click", function (e) { if (e.target === box) close(); });
    document.addEventListener("keydown", esc);
    document.body.appendChild(box);
    return close;
  }

  // btn() is the small secondary one; a dialog's confirming button is the accent-filled default.
  function primary(label, fn) {
    var x = el("button", { type: "button", text: label });
    x.addEventListener("click", fn);
    return x;
  }

  function foot(kids) {
    return el("div", { "class": "toolbar iop-foot" }, [el("span", { "class": "spacer" })].concat(kids));
  }

  function onEnter(input, fn) {
    input.addEventListener("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); fn(); } });
  }

  function rangeOn(node) {                       // a range covering one whole element
    var r = node.ownerDocument.createRange();
    r.selectNode(node);
    return r;
  }

  /* A scheme allowlist, not a javascript: blocklist — data: URLs script just as happily. A bare
     domain gets https://, because that is what an editor actually types into a link box. */
  function safeUrl(u) {
    u = (u || "").trim();
    var bare = u.replace(/[\s\u0000-\u001f]/g, "");
    if (!u) return "";
    if (/^(https?|mailto|tel):/i.test(bare)) return u;
    if (/^[/#?]/.test(u)) return u;                      // same-site path, anchor, query
    if (/^[a-z][a-z0-9+.-]*:/i.test(bare)) return "";    // any other scheme: refuse
    return "https://" + u;
  }

  /* The link box, shared by the document toolbar and the rich-text widget in a section's settings.
     They differ only in which document their caret lives in, so the caller says what to prefill from
     and what to do with the finished anchor. `remove` is null when there is no link to take off. */
  function linkDialog(cur, save, remove) {
    var url = el("input", { type: "text", placeholder: "example.com/page  ·  /about  ·  mailto:sales@…" }),
        text = el("input", { type: "text", placeholder: "The words the reader clicks" }),
        blank = el("input", { type: "checkbox" }),
        why = el("small", { "class": "iop-why" });
    url.value = cur.url || "";
    text.value = cur.text || "";
    blank.checked = !!cur.blank;

    function apply() {
      var href = safeUrl(url.value);
      if (!href) {
        why.textContent = url.value.trim() ? "That web address is not allowed." : "Enter a web address.";
        url.focus();
        return;
      }
      var a = document.createElement("a");       // built as a node, so the browser does the escaping
      a.setAttribute("href", href);
      a.textContent = text.value.trim() || href;
      if (blank.checked) { a.setAttribute("target", "_blank"); a.setAttribute("rel", "noopener"); }
      close();
      save(a.outerHTML);
    }
    onEnter(url, apply);
    onEnter(text, apply);

    var bottom = foot([btn("Cancel", "Close without changing anything", function () { close(); }),
                       primary(remove ? "Save" : "Insert", apply)]);
    // Remove sits at the far left, away from Save: it is the one button that throws something away
    if (remove) bottom.insertBefore(btn("Remove link", "Take the link off these words",
                                        function () { close(); remove(); }), bottom.firstChild);

    var close = modal(remove ? "Edit link" : "Add a link", [
      labelled("Web address", true, url), why,
      labelled("Link text", false, text),
      el("div", { "class": "iop-check" }, [
        el("label", { "class": "inline" }, [blank, document.createTextNode(" Open in a new tab")])
      ]),
      bottom
    ]);
    url.focus();
    url.select();
  }

  /* A picture in the flow. mediaWidget() is the same picker as every other image field on the form,
     so an editor can reuse a library image here instead of only ever uploading a new one.
     media_alt() cannot reach inside rich_text HTML, which is why the alt text is asked for here. */
  function pictureDialog() {
    var id = "", alt = el("input", { type: "text", placeholder: "What is in the picture?" }),
        why = el("small", { "class": "iop-why" });
    var widget = mediaWidget(function () { return id; }, function (v) {
      id = v;
      var m = mediaById(v);
      if (m && m.alt && !alt.value.trim()) alt.value = m.alt;
      why.textContent = "";
    }, "image/");

    function apply() {
      var m = mediaById(id);
      if (!m) { why.textContent = "Choose a picture first."; return; }
      var img = document.createElement("img");
      img.setAttribute("src", m.url);
      img.setAttribute("alt", alt.value.trim());
      close();
      exec("insertHTML", img.outerHTML);
    }
    onEnter(alt, apply);

    var close = modal("Insert a picture", [
      labelled("Picture", true, widget), why,
      labelled("Alt text", false, alt),
      el("small", { text: "A short description for blind visitors — Google reads it too." }),
      foot([btn("Cancel", "Close without inserting", function () { close(); }), primary("Insert", apply)])
    ]);
  }

  var GRID_R = 8, GRID_C = 10, MAX_R = 50, MAX_C = 12;

  function tableHtml(rows, cols, head) {
    function row(tag) { return "<tr>" + Array(cols + 1).join("<" + tag + ">&nbsp;</" + tag + ">") + "</tr>"; }
    var html = "<table>", body = head ? rows - 1 : rows;
    if (head) html += "<thead>" + row("th") + "</thead>";
    if (body > 0) {                              // a one-row table that is all header has no tbody
      html += "<tbody>";
      for (var i = 0; i < body; i++) html += row("td");
      html += "</tbody>";
    }
    return html + "</table><p><br></p>";         // somewhere to type once the table is in
  }

  /* Drag out the size the way Word and Docs do. The grid is the pointer affordance; the two number
     boxes beside it are the keyboard path and the only way to ask for more than the grid shows, so
     the grid itself is hidden from screen readers rather than read out as eighty empty cells. */
  function tableDialog() {
    var rows = 3, cols = 3, cells = [],
        grid = el("div", { "class": "tb-grid", "aria-hidden": "true" }),
        out = el("strong"),
        rowIn = el("input", { type: "number", min: "1", max: String(MAX_R), value: "3" }),
        colIn = el("input", { type: "number", min: "1", max: String(MAX_C), value: "3" }),
        head = el("input", { type: "checkbox" });
    head.checked = true;

    for (var y = 1; y <= GRID_R; y++) {
      for (var x = 1; x <= GRID_C; x++) {
        var cell = el("span", { "class": "tb-cell", "data-r": String(y), "data-c": String(x) });
        cells.push(cell);
        grid.appendChild(cell);
      }
    }
    function clamp(n, max) { return Math.max(1, Math.min(Math.floor(n) || 1, max)); }
    function paint() {
      cells.forEach(function (n) {
        n.classList.toggle("on", +n.getAttribute("data-r") <= rows && +n.getAttribute("data-c") <= cols);
      });
      out.textContent = cols + " × " + rows;
    }
    function set(r, c) {
      rows = clamp(r, MAX_R);
      cols = clamp(c, MAX_C);
      rowIn.value = rows;
      colIn.value = cols;
      paint();
    }
    function apply() { close(); exec("insertHTML", tableHtml(rows, cols, head.checked)); }

    grid.addEventListener("mousemove", function (e) {      // one listener, eighty cells
      var t = e.target.closest(".tb-cell");
      if (t) set(+t.getAttribute("data-r"), +t.getAttribute("data-c"));
    });
    grid.addEventListener("click", function (e) { if (e.target.closest(".tb-cell")) apply(); });
    // typing repaints but does not rewrite the box mid-keystroke; the value is normalised on change
    rowIn.addEventListener("input", function () { rows = clamp(+rowIn.value, MAX_R); paint(); });
    colIn.addEventListener("input", function () { cols = clamp(+colIn.value, MAX_C); paint(); });
    rowIn.addEventListener("change", function () { set(+rowIn.value, cols); });
    colIn.addEventListener("change", function () { set(rows, +colIn.value); });
    onEnter(rowIn, apply);
    onEnter(colIn, apply);

    var close = modal("Insert a table", [
      grid, el("p", { "class": "tb-dims-line" }, [out]),
      el("div", { "class": "tb-dims" }, [labelled("Rows", false, rowIn), labelled("Columns", false, colIn)]),
      el("div", { "class": "iop-check" }, [
        el("label", { "class": "inline" }, [head, document.createTextNode(" First row is a header")])
      ]),
      foot([btn("Cancel", "Close without inserting", function () { close(); }), primary("Insert", apply)])
    ]);
    paint();
  }

  /* The snippet goes in exactly as pasted. Block HTML is trusted-staff-only on the server and the
     embed_html block already takes raw markup; filtering here alone would make the two disagree. */
  function embedDialog() {
    var box = el("textarea", { "class": "code", style: "min-height:9rem",
                               placeholder: '<iframe src="https://www.youtube.com/embed/…" …></iframe>' }),
        why = el("small", { "class": "iop-why" });
    function apply() {
      var html = box.value.trim();
      if (!html) { why.textContent = "Paste the code first."; box.focus(); return; }
      close();
      exec("insertHTML", html);
    }
    var close = modal("Embed code from another service", [
      labelled("Embed code", true, box), why,
      el("small", { text: "The share or embed snippet from YouTube, Google Maps, a form or a calendar." }),
      foot([btn("Cancel", "Close without inserting", function () { close(); }), primary("Insert", apply)])
    ]);
    box.focus();
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
    search.addEventListener("input", draw);
    var close = modal(title, [search, grid], true);
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

  /* The element the caret is actually in. At a block boundary — the caret at the end of a line,
     which is where it is after you type — Gecko names the range's container as the *parent* (the
     block, or the editing host) with an offset, not the node you are standing in. Walking up from
     that misses everything below it: quote-off goes undetectable, alignment reads off the wrong
     element, an inline size is invisible. Resolve through startOffset before walking anywhere. */
  // ponytail: a mixed selection reports the size at its start; showing "several" would need the end
  // walked too, for a case an editor hits rarely.
  function caretNode() {
    var n = savedRange.startContainer, off = savedRange.startOffset, atEnd;
    while (n.nodeType === 1 && n.childNodes.length) {   // all the way down, not one level: a
      atEnd = off >= n.childNodes.length;               // selection CONTAINING a span resolves to
      n = atEnd ? n.lastChild : n.childNodes[off];      // the block, and the span's size is below it
      off = atEnd && n.childNodes ? n.childNodes.length : 0;
    }
    return n.nodeType === 1 ? n : n.parentNode;
  }

  /* The block element the caret sits in, bounded by the field. sel="…" asks for the nearest
     matching ancestor instead. Returns the field itself only when the text really has no wrapper. */
  function caretBlock(sel) {
    if (!liveField()) return null;
    var n = caretNode();
    if (!n || !savedField.contains(n)) return null;
    if (sel) { var hit = n.closest(sel); return hit && savedField.contains(hit) ? hit : null; }
    while (n !== savedField && n.parentNode !== savedField) n = n.parentNode;
    return n;
  }

  var BLOCK_CMD = /^(justify|formatBlock|outdent|indent)/;

  /* Gecko ignores styleWithCSS for fontSize and always emits <font size>, an obsolete tag the paste
     filter strips on the next round trip. So run the command with a marker size — which also clears
     any size already inside the selection — and swap the tags it produced for a real CSS size, or
     for nothing at all when the editor asked for Normal. */
  function setSize(css) {
    var d = cdoc();
    execLine("fontSize", "7");
    if (!d || !savedField) return;
    Array.prototype.forEach.call(savedField.querySelectorAll('font[size="7"]'), function (f) {
      var box = d.createElement("span");
      if (css === "normal") box = d.createDocumentFragment();
      else box.style.fontSize = css;
      while (f.firstChild) box.appendChild(f.firstChild);
      f.parentNode.replaceChild(box, f);
    });
    savedField.normalize();
    fire(savedField);
  }

  // the inline size covering the caret, if the toolbar put one there
  function caretSize() {
    if (!liveField()) return "";
    var n = caretNode();
    while (n && n !== savedField) {
      if (n.style && n.style.fontSize) return n.style.fontSize;
      n = n.parentNode;
    }
    return "";
  }

  /* Setting a heading clears any inline size inside the line. The level IS the size — an H2 left
     wearing a "Huge" span renders like nothing in the outline, and because the size control is
     disabled on headings there would be no way back out of it from the toolbar. Normal text keeps
     its size: p + a size is the whole point of the size control. */
  function applyLevel(tag) {
    exec("formatBlock", "<" + tag + ">");
    var line = /^h[1-6]$/.test(tag) && caretBlock();
    if (!line || line === savedField) return;
    var sized = [].slice.call(line.querySelectorAll('[style*="font-size"]'));
    if (line.style && line.style.fontSize) sized.push(line);
    sized.forEach(function (n) {
      n.style.fontSize = "";
      if (!n.getAttribute("style")) n.removeAttribute("style");
      if (n.tagName === "SPAN" && !n.attributes.length) {      // nothing left to carry: unwrap it
        while (n.firstChild) n.parentNode.insertBefore(n.firstChild, n);
        n.remove();
      }
    });
    if (!sized.length) return;
    line.normalize();
    fire(savedField);
    rememberSelection();
  }

  function execLine(cmd, val) {
    var d = cdoc();
    if (!d || !restoreSelection()) return;
    if (savedRange.collapsed) {
      var line = caretBlock();
      if (line) { var r = d.createRange(); r.selectNodeContents(line); savedRange = r; }
    }
    exec(cmd, val);
  }

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

  function sectionItems(nested) {
    var types = (SPEC.ui.order || []).filter(function (t) { return SPEC.blocks[t]; });
    Object.keys(SPEC.blocks).forEach(function (t) { if (types.indexOf(t) < 0) types.push(t); });
    // rich_text is what you get by just typing; inside a column the two never-nested types go too
    return types.filter(function (t) { return t !== "rich_text" && !(nested && NEVER_NESTED.indexOf(t) > -1); }).map(function (t) {
      var n = (SPEC.ui.names && SPEC.ui.names[t]) || [];
      return { key: t, icon: n[0], label: nameFor(t), text: n[2] || "" };
    });
  }

  /* The document toolbar's own link box: the caret lives in the canvas, so the anchor is found
     through caretBlock() and the result goes back through exec(), which replays savedRange. Editing
     an existing link means pointing savedRange at the whole anchor first — the same trick execLine()
     uses to turn a collapsed caret into a whole line. */
  function docLink() {
    var a = caretBlock("a");
    linkDialog({ url: a ? a.getAttribute("href") : "",
                 text: a ? a.textContent : (savedRange ? savedRange.toString() : ""),
                 blank: !!(a && a.getAttribute("target") === "_blank") },
      function (html) { if (a) savedRange = rangeOn(a); exec("insertHTML", html); },
      a && function () { savedRange = rangeOn(a); exec("unlink"); });
  }

  function buildToolbar() {
    var bar = document.getElementById("doc-toolbar");
    if (!bar) return;
    function hold(x) { x.addEventListener("mousedown", function (e) { e.preventDefault(); }); return x; }
    /* Every control that needs a caret in a rich field registers itself here, so syncBar() cannot
       drift out of step with the buttons the way a hand-written list did: Tx, the lists, the divider,
       the four insert buttons and the colour swatches were all left enabled and silently doing
       nothing. `free` opts out the three that genuinely need no caret. */
    var cmds = [];
    function b(label, title, fn, cls, free) {
      var x = el("button", { type: "button", "class": "tb" + (cls ? " " + cls : ""), title: title, text: label });
      hold(x);
      x.addEventListener("click", function (e) { e.preventDefault(); fn(); });
      if (!free) cmds.push(x);
      return x;
    }
    function group(kids) { return el("span", { "class": "tb-group" }, kids); }

    var style = el("select", { "class": "tb-style", title: "Text style" });
    // Shown when the caret is in a block this list has no name for — a blockquote, a bare text node.
    // It has to be a real selectable value, not a coerced "p": pretending the caret is already on
    // Normal text means picking Normal text changes nothing and raises no change event.
    style.appendChild(el("option", { value: "", text: "\u2014", hidden: "hidden" }));
    /* All six levels, named as well as numbered so the list reads to an editor and to anyone who
       thinks in H-tags. H1 is offered but is not the default for a reason: post.html already emits
       the page title as the page's only <h1> (a hero block emits its own), so an H1 in body text is
       a second one on the page. Use H2 to open a section. */
    HEAD_LEVELS.forEach(function (o) { style.appendChild(el("option", { value: o[0], text: o[1] })); });
    // No hold() here: cancelling mousedown on a <select> suppresses the native popup, and the caret
    // is replayed from savedRange anyway. Nor does mousedown touch selectedIndex: from Firefox 137
    // the dropdown is DOM-rendered, so clicking an option fires a SECOND mousedown that bubbles to
    // the select — anything that resets the value there wipes the pick before change reads it.
    style.addEventListener("blur", function () { syncBar(); });   // dismissed without picking: show the caret's style again
    style.addEventListener("change", function () {
      if (style.value) applyLevel(style.value);
    });

    var size = el("select", { "class": "tb-style tb-size", title: "Text size" });
    size.appendChild(el("option", { value: "", text: "Size", hidden: "hidden" }));
    TEXT_SIZES.forEach(function (o) { size.appendChild(el("option", { value: o[0], text: o[1] })); });
    size.addEventListener("blur", function () { syncBar(); });
    size.addEventListener("change", function () {
      if (size.value) setSize(size.value);
    });

    var bold = b("B", "Bold", function () { exec("bold"); }, "tb-b"),
        ital = b("I", "Italic", function () { exec("italic"); }, "tb-i"),
        und = b("U", "Underline", function () { exec("underline"); }, "tb-u"),
        strike = b("S", "Strikethrough", function () { exec("strikeThrough"); }, "tb-s");

    function colour(cmd, title, initial) {
      var i = el("input", { type: "color", "class": "tb-colour", title: title, value: initial });
      i.addEventListener("input", function () { exec(cmd, i.value); });   // no hold(): it would block the picker
      cmds.push(i);
      return i;
    }

    function insertSection() {
      var cur = selected && listAt(selected);   // a path left over from a setBlocks() falls back to the end
      var at = cur && cur.arr ? siblingPath(selected, cur.i + 1) : String(MODEL.length), nested = isNested(at);
      var extra = nested ? [] : [{ key: "__layout", icon: "▤", label: "Start from a layout…",
                                   text: "Replace the page with a ready-made set of sections." }];
      chooser("Insert", sectionItems(nested).concat(extra), function (t) {
        if (t === "__layout") return openLayouts();
        var r = listAt(at);
        if (!r.arr) return;
        r.arr.splice(r.i, 0, { type: t, data: seedFor(t) });
        markDirty();
        canvasInsert(at);
      });
    }

    bar.appendChild(group([b("↶", "Undo", function () { exec("undo"); }, "", true),
                           b("↷", "Redo", function () { exec("redo"); }, "", true)]));
    bar.appendChild(group([style, size]));
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
    bar.appendChild(group([b("🔗", "Add a link", docLink),
                           b("🖼", "Insert a picture", pictureDialog),
                           b("▦", "Insert a table", tableDialog),
                           b("</>", "Embed code from another service", embedDialog)]));
    var align = { left: b("⇤", "Align left", function () { exec("justifyLeft"); }),
                  center: b("↔", "Centre", function () { exec("justifyCenter"); }),
                  right: b("⇥", "Align right", function () { exec("justifyRight"); }) };
    bar.appendChild(group([align.left, align.center, align.right,
                           colour("foreColor", "Text colour", "#1f2937"),
                           colour("hiliteColor", "Highlight", "#fef08a")]));
    bar.appendChild(group([b("+ Section", "Insert a designed section", insertSection, "tb-wide", true)]));

    var HINT = document.getElementById("pane-hint"), HINT_ON = HINT && HINT.innerHTML;

    syncBar = function () {                       // reflect the caret, the way a real toolbar does
      var d = cdoc();
      if (!d) return;
      // A command needs a caret in a rich field. Without one execCommand does nothing, so the
      // toolbar must go dead rather than paint a state it cannot deliver — a control that silently
      // snaps back to "Normal text" is worse than one that is visibly switched off.
      var live = !!(liveField() && savedField.hasAttribute("data-rich"));
      bar.classList.toggle("tb-off", !live);
      cmds.concat([style]).forEach(function (x) { x.disabled = !live; });
      // Size belongs to body text. A heading's size IS its level, so offering both there invites an
      // H2 that looks like an H4 — the outline Google reads and the one a reader sees disagreeing.
      size.disabled = !live || /^H[1-6]$/.test((caretBlock() || {}).tagName || "");
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
        style.value = HEAD_TAGS.indexOf(blk) > -1 ? blk : "";
        var px = caretSize();
        size.value = TEXT_SIZES.some(function (o) { return o[0] === px; }) ? px : (px ? "" : "normal");
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
    var path = node.getAttribute("data-b"), r = listAt(path), before = [], after = [], seen = false;
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
    if (!r.arr) return;
    if (head) {
      r.arr[r.i].data.html = head;
      r.arr.splice.apply(r.arr, [r.i + 1, 0].concat(ins));
      focusOnLoad = siblingPath(path, r.i + 2);
    } else {                                     // the "/" line was the whole paragraph: replace it
      r.arr.splice.apply(r.arr, [r.i, 1].concat(ins));
      focusOnLoad = siblingPath(path, r.i + 1);
    }
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

    var items = sectionItems(isNested(node.getAttribute("data-b"))), shown = items;
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
    FRAME.style.height = wrap.style.height = wrap.style.flex = "";   // measure the layout, not the last fit
    if (VIEW !== "preview") {
      FRAME.style.width = FRAME.style.transform = "";
      return;
    }
    // Preview is the whole screen: from where the frame starts down to the bottom of the window,
    // taken out of the flex flow so the search and share cards under it cannot squeeze it — the
    // column scrolls to reach them instead.
    var top = Math.max(wrap.getBoundingClientRect().top, 0),
        h = Math.max(window.innerHeight - top - 16, 288),
        pane = wrap.clientWidth, k = Math.min(1, pane / DEVICE);
    FRAME.style.width = DEVICE + "px";
    FRAME.style.height = Math.round(h / k) + "px";
    FRAME.style.transformOrigin = "top left";
    FRAME.style.transform = "scale(" + k + ")";
    wrap.style.flex = "none";
    wrap.style.height = h + "px";                  // the unscaled frame must not stretch the wrap
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
      focusOnLoad = null;    // coming back from preview should not yank the caret to the top
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

  // ---- wiring ---------------------------------------------------------------
  function initBlocks() {
    var data = document.getElementById("editor-data"),
        form = document.getElementById("post-form"),
        advanced = document.getElementById("advanced");
    AREA = document.querySelector('textarea[name="blocks"]');
    if (!data || !AREA || !form) return;
    SPEC = JSON.parse(data.textContent);
    MEDIA = SPEC.media || [];
    FRAME = document.getElementById("canvas");
    initMediaSelects();
    buildToolbar();
    initPreview();

    var parsed;
    try { parsed = JSON.parse(AREA.value || "[]"); } catch (e) { parsed = null; }
    if (!Array.isArray(parsed)) {   // unparseable JSON from a rejected save: leave the textarea in charge
      AREA.parentNode.insertBefore(el("p", { "class": "error", text: "The saved content is not valid JSON — fix it here." }), AREA);
      if (advanced) advanced.open = true;
      return;
    }
    MODEL = parsed;
    if (!MODEL.length) MODEL = [{ type: "rich_text", data: { html: "" } }];   // open with a caret, not a dialog

    focusOnLoad = "0";   // land the caret in the document, the way Docs does
    canvasFull();

    // Advanced is the same data as JSON. The textarea is written when the panel opens (and on
    // submit); a hand edit is read back on blur, so whichever side was touched last wins.
    if (advanced) advanced.addEventListener("toggle", function () {
      if (advanced.open) AREA.value = JSON.stringify(MODEL, null, 2);
    });
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
      AREA.value = JSON.stringify(prune(MODEL), null, 2);
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
    initTerms();
    initBlocks();
  });
})();
