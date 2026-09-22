/* Admin progressive enhancement: auto slug, inline media upload, the document editor.
   No framework, no build step. Every part is a no-op when its hook is absent, and the
   plain form underneath (the Advanced textarea named "blocks", plain selects) still works without JS. */
(function () {
  "use strict";

  /* The highlighted row in an .iop-slash list. Shared by the terms picker and the "/" section menu,
     which draw the same markup: .iop-slash-row rather than list.children, because the "/" menu can
     also be holding a "Nothing matches" paragraph. */
  function moveRow(list, step) {
    var rows = list && list.querySelectorAll(".iop-slash-row"), at = -1, i;
    if (!rows || !rows.length) return;
    for (i = 0; i < rows.length; i++) if (rows[i].classList.contains("on")) at = i;
    if (at > -1) rows[at].classList.remove("on");
    rows[Math.max(0, Math.min(rows.length - 1, at + step))].classList.add("on");
  }

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

    input.addEventListener("input", draw);
    input.addEventListener("blur", close);
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter") {
        e.preventDefault();          // unconditional: this input is inside #post-form, so Enter would save the post
        if (list) list.querySelector(".on").click();
      } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        moveRow(list, e.key === "ArrowDown" ? 1 : -1);
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

  /* A per-type field of type "kv" -- a list of {k, v} rows. The rows ARE the repeater the
     spec_table block already uses: SPEC.ui.items["spec_table"] is ["k", "v"] and the labels are
     already Label and Value, so passing that type in gets the whole widget for nothing. The value
     reaches the server the same way a media field's does -- through the hidden input that was
     already in the form, written on submit. */
  function initMetaRows(form) {
    Array.prototype.forEach.call(document.querySelectorAll("[data-kv]"), function (box) {
      var hidden = form.elements[box.getAttribute("data-kv")], model = { rows: [] };
      try { model.rows = JSON.parse(hidden.value || "[]"); } catch (e) { model.rows = []; }
      if (!Array.isArray(model.rows)) model.rows = [];
      box.appendChild(repeater("spec_table", "rows", model));
      form.addEventListener("submit", function () {
        hidden.value = JSON.stringify(model.rows.filter(function (r) { return (r.k || "").trim(); }));
      });
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
  var REPEATERS = ["items", "images", "rows", "cols"];   // blocks.py REPEATERS
  function fieldsOf(type) {
    var spec = SPEC.blocks[type] || [[], []];
    var fields = spec[0].map(function (f) { return { key: f, required: true }; })
      .concat(spec[1].map(function (f) { return { key: f, required: false }; }));
    // A repeater is as tall as it has rows, so anything declared after it — a Numbers section's
    // effect, a Cards heading — sat below six rows of fields and was never found. Rows go last.
    return fields.filter(function (f) { return REPEATERS.indexOf(f.key) < 0; })
      .concat(fields.filter(function (f) { return REPEATERS.indexOf(f.key) >= 0; }));
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
    } else if (widget === "choice") {
      // options are [value, label] pairs in EDITOR["choices"][key], so the empty one reads "None"
      input = el("select");
      (SPEC.ui.choices[key] || []).forEach(function (o) {
        input.appendChild(el("option", { value: o[0], text: o[1] }));
      });
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

  /* Alignment belongs to every section, so it is not a field in BLOCKS: one control here covers all
     of them, and any type added later. "" removes the key rather than writing an empty string, so a
     section nobody aligned stays byte-identical in the saved JSON.
     ponytail: a rich_text section has no ⚙ bar (wireBlock skips it), so this is out of reach there —
     its text still aligns per paragraph from the document toolbar. If that gap is felt, the smallest
     fix is the same two controls in the doc toolbar, acting on `selected`. */
  var ALIGNMENTS = [["", "Default"], ["left", "Left"], ["center", "Centre"], ["right", "Right"]];

  function alignPick(label, key, data) {
    var s = el("select", { title: label });
    ALIGNMENTS.forEach(function (o) { s.appendChild(el("option", { value: o[0], text: o[1] })); });
    s.value = data[key] || "";
    s.addEventListener("change", function () {
      if (s.value) data[key] = s.value; else delete data[key];
    });
    return labelled(label, false, s);
  }

  /* Width is one key holding either a named step or a number of pixels, so the select and the number
     box both write data.width and each clears the other. "Custom" is only ever shown while a number
     is in play — picking it is meaningless, so it is disabled. */
  var WIDTHS = [["", "Default"], ["wide", "Wide"], ["full", "Full width"]];

  /* The band a section sits on. Same shape as alignPick: picking the blank option deletes the key,
     so an untouched section stays byte-identical in the saved JSON. */
  var TONES = [["", "Page background"], ["grey", "Light grey"], ["dark", "Dark"], ["blue", "Blue"]];

  /* How much air the section keeps, and only ever less than the design's own -- adding space is a
     Spacer, which is a thing you can drag. Same shape as tonePick: the blank option deletes the key.
     Values mirror blocks.py PADS by hand, like ALIGNMENTS/WIDTHS/TONES above; a test compares them. */
  var PADS = [["", "Default"], ["none", "None"], ["small", "Small"], ["medium", "Medium"]];
  function padPick(data) {
    var sel = el("select", { title: "Space above and below the section" });
    PADS.forEach(function (p) { sel.appendChild(el("option", {value: p[0], text: p[1]})); });
    sel.value = data.pad || "";
    sel.addEventListener("change", function () {
      if (sel.value) data.pad = sel.value; else delete data.pad;
    });
    return labelled("Spacing", false, sel);
  }
  function tonePick(data) {
    var sel = el("select");
    TONES.forEach(function (t) { sel.appendChild(el("option", {value: t[0], text: t[1]})); });
    sel.value = data.tone || "";
    sel.addEventListener("change", function () {
      if (sel.value) data.tone = sel.value; else delete data.tone;
    });
    return labelled("Background", false, sel);
  }

  function widthPick(data) {
    var s = el("select", { title: "How wide the section's content is" }),
        n = el("input", { type: "number", "class": "wid-px", min: "1", max: "4000", step: "10", placeholder: "px" });
    WIDTHS.forEach(function (o) { s.appendChild(el("option", { value: o[0], text: o[1] })); });
    s.appendChild(el("option", { value: "custom", text: "Custom", disabled: "disabled" }));
    function show() {
      var v = String(data.width == null ? "" : data.width);
      s.value = /^\d+$/.test(v) ? "custom" : (v === "wide" || v === "full" ? v : "");
      n.value = /^\d+$/.test(v) ? v : "";
    }
    function set(v) {
      if (v) data.width = v; else delete data.width;
      show();
    }
    s.addEventListener("change", function () { set(s.value === "custom" ? "" : s.value); });
    n.addEventListener("change", function () { set(n.value && +n.value > 0 ? String(Math.round(+n.value)) : ""); });
    show();
    return labelled("Width", false, el("span", { "class": "wid" }, [s, n]));
  }

  // The fields of one section — what ⚙ opens. Words on the page are edited on the page; this is
  // for the rest: alignment, pictures, links, choices, and the rows of a Cards / FAQ / Numbers section.
  function blockFields(block) {
    if (!block.data || typeof block.data !== "object") block.data = {};
    var body = el("div", { "class": "blk-fields" });
    if (!SPEC.blocks[block.type]) {
      body.appendChild(el("p", { "class": "muted", text: "Unknown section type — edit it under Advanced." }));
    } else {
      body.appendChild(alignPick("Align the content", "align", block.data));
      body.appendChild(alignPick("Align the section", "align_box", block.data));
      body.appendChild(tonePick(block.data));
      body.appendChild(widthPick(block.data));
      // not on a spacer: its Height is its spacing, and two controls on one gap is the trap
      if (block.type !== "spacer") body.appendChild(padPick(block.data));
      fieldsOf(block.type).forEach(function (f) {
        // a rich_text section IS its html, edited on the page; a second document editor in a 23rem
        // popover is a trap, so the panel here is layout only
        if (block.type === "rich_text" && f.key === "html") return;
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
  function markDirty() { dirty = true; stampIds(MODEL); reconcileOut(); nudgeSave(); }
  /* A discrete action, as opposed to typing: put a boundary on the undo stack so this and the
     click before it are two steps rather than one. Typing deliberately does NOT call this --
     it coalesces by the manager's captureTimeout, the way Quill's own history always did. */
  function markStep() { step(); markDirty(); }

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

  /* ---- the shared document ---------------------------------------------------------------------
     Everybody with this page open types into ONE document, and the paragraph is the whole point:
     two people in the same sentence keep both sets of words, because a paragraph is a Y.Text -- a
     text CRDT -- and not a string. A string is last-writer-wins however it is transported, which is
     the thing this run of changes exists to stop.

     MODEL stays the plain array everything else reads and writes (the thirteen markDirty() sites,
     the six canvas paths, prune(), the Advanced textarea). The shared document is kept beside it:

        markDirty()     -> reconcileOut()   MODEL into Y, matching blocks by data._id
        YB.observeDeep  -> reconcileIn()    Y back into MODEL, then the smallest repaint that shows it

     Reconciling, rather than rewriting those thirteen sites to speak Yjs, is both the smaller change
     and the safer one: every one of them already performs its own surgical canvas patch
     (canvasInsert, node.remove() + renumber, insertBefore), and a diff by _id recovers exactly that
     intent -- insert, delete, reorder, set -- instead of expressing it twice in two vocabularies.

     TWO KEYS TRAVEL WITH A BLOCK, in data, so they ride posts.blocks and post_drafts.blocks and are
     listed in blocks.py _NON_TEXT_KEYS (or a uuid would turn up in llms-full.txt and admin search):

       _id    names a section for as long as it exists. data-b is a POSITION and renumber() rewrites
              it on every insert, so "block 3" means different sections to two browsers; every merge
              decision here needs a name that does not move.
       _rich  is the Quill gate's verdict, decided once and stored. quillKeeps() is a pure function of
              a block's HTML, so two peers agree -- until one of them types. If A's editing changed the
              markup and B loaded afterwards, B could decide differently and build a Y.Text where A has
              a string: two shapes for one block, which no amount of merging repairs. It is the kind of
              fault that passes a two-browser test and fails with the third, so it is content, not a
              calculation, and only the elected writer ever computes it (see mountQuill). */

  var Y = null, YDOC = null, YB = null;        // the Yjs module, the shared document, its blocks array
  var YORIGIN = { mine: 1 };                   // our own transactions, recognised when they echo back
  var UNDO = null;                             // Y.UndoManager over YB -- one undo for the whole page
  /* Ours too, but NOT an edit anybody made: seeding the document and repairing a double-seed.
     A separate origin rather than UNDO.clear(), and the difference is not cosmetic -- the seed is
     on a four-second timer, so clearing was a wipe of whatever the editor had done in those four
     seconds. Measured: a section moved at 4.0s left an empty undo stack. reconcileIn skips this
     the same way it skips YORIGIN (both are us); trackedOrigins deliberately does not list it. */
  var YSEED = { seed: 1 };
  /* Quill keeps no history of its own: the Y.UndoManager owns it, which is what y-quill expects
     when a Y.Text is the source of truth. maxStack 0 leaves Quill's own Ctrl+Z bindings in place
     and permanently empty, so they are inert rather than fighting ours. This also removes two
     faults nobody had reported: Quill's default userOnly:false recorded a PEER's delta on your
     stack, so undo could revert a colleague's sentence and the binding broadcast the revert; and
     mountQuill's seeding paste was recorded too, so undoing far enough emptied the block. */
  var HISTORY_OFF = { maxStack: 0, userOnly: true };
  var SCALARS = {};                            // blocks.py _NON_TEXT_KEYS: never a text type
  var BINDS = [];                              // live QuillBindings, destroyed when the canvas is replaced
  var WAITING = [];                            // editors mounted before the shared text existed
  var viewChanged = function () {};            // late-bound by initCollab: tell peers who can write
  var shareOut = function () {};               // late-bound by initCollab: put a delta on the wire
  var canWrite = function () { return true; }; // single player is always the writer
  var sharedChanged = function () {};          // late-bound by initAutosave: a peer typed; the writer saves
  var touched = function () {};                // late-bound by initAutosave: this section is my work

  function uid() {
    return (window.crypto && crypto.randomUUID) ? crypto.randomUUID()
         : "b" + Date.now().toString(36) + Math.random().toString(36).slice(2, 10);
  }
  function idOf(b) { return b && b.data && b.data._id; }
  // The SECTION an editor sees, for a field that may be nested one level inside a columns block.
  // The activity log lists top-level sections, so crediting a nested block would name nothing.
  function rootIdOf(path) { return idOf(MODEL[+String(path).split(".")[0]]); }

  /* Which keys become a shared text type: a string that is not one of blocks.py's non-text keys is
     prose somebody types, and everything else is a setting, a media id or a whitelisted token -- a
     value, not a sentence. `html` is the exception in both directions. On a block Quill drives it is
     a Y.Text owned end to end by y-quill; on a block Quill refused it stays a plain string, because
     splicing two people's edits into one HTML string can interleave inside a tag and publish broken
     markup. That second case is why those sections say so on hover. */
  function isProse(key, val, data) {
    if (typeof val !== "string") return false;
    if (key === "html") return !!(data && data._rich);
    return !SCALARS[key];
  }

  // Every block has an _id before it can be shared. Minting is separate from the gate above because
  // this is cheap and pure and runs on every change, and the gate needs a Quill in a document.
  function stampIds(list) {
    (list || []).forEach(function (b) {
      if (!b || !b.data) return;
      if (!b.data._id) b.data._id = uid();
      if (b.type === "columns" && Array.isArray(b.data.cols)) b.data.cols.forEach(stampIds);
    });
  }

  function eachBlock(list, fn) {
    (list || []).forEach(function (b) {
      fn(b);
      if (b && b.type === "columns" && b.data && Array.isArray(b.data.cols)) b.data.cols.forEach(function (c) { eachBlock(c, fn); });
    });
  }

  function pathOfId(id, list, prefix) {
    var found = null;
    (list || MODEL).forEach(function (b, i) {
      if (found) return;
      var p = (prefix == null ? "" : prefix + ".") + i;
      if (idOf(b) === id) { found = p; return; }
      if (b.type === "columns" && b.data && Array.isArray(b.data.cols))
        b.data.cols.forEach(function (col, c) { if (!found) found = pathOfId(id, col, p + "." + c); });
    });
    return found;
  }

  function mapById(id, yarr) {
    yarr = yarr || YB;
    if (!yarr) return null;
    for (var i = 0; i < yarr.length; i++) {
      var m = yarr.get(i), data = m.get("data");
      if (data && data.get("_id") === id) return m;
      var cols = data && data.get("cols");
      if (cols && cols.length !== undefined) for (var c = 0; c < cols.length; c++) {
        var hit = mapById(id, cols.get(c));
        if (hit) return hit;
      }
    }
    return null;
  }

  // ---- MODEL -> Y -----------------------------------------------------------
  /* The smallest edit that turns this text into that one: keep the common prefix and suffix, replace
     what is between them. Not a real diff, and it does not need to be -- a caret only ever edits in
     one place, and two carets in one field are what the CRDT underneath is for. */
  function spliceText(yt, want) {
    var has = yt.toString();
    if (has === want) return;
    var n = Math.min(has.length, want.length), a = 0, b = 0;
    while (a < n && has.charAt(a) === want.charAt(a)) a += 1;
    while (b < n - a && has.charAt(has.length - 1 - b) === want.charAt(want.length - 1 - b)) b += 1;
    if (has.length - a - b > 0) yt.delete(a, has.length - a - b);
    if (want.length - a - b > 0) yt.insert(a, want.slice(a, want.length - b));
  }

  function yData(ym, data) {
    Object.keys(data).forEach(function (k) {
      var v = data[k];
      if (k === "cols" && Array.isArray(v)) {
        if (!(ym.get("cols") instanceof Y.Array)) ym.set("cols", new Y.Array());
        var ya = ym.get("cols");
        while (ya.length > v.length) ya.delete(ya.length - 1, 1);
        v.forEach(function (col, i) {
          if (i >= ya.length) ya.insert(ya.length, [new Y.Array()]);   // attached by the insert itself
          yList(ya.get(i), col);
        });
        return;
      }
      if (isProse(k, v, data)) {
        // y-quill owns a rich block's html end to end -- it holds a Quill delta, not the HTML string
        // this key carries in MODEL, so writing MODEL's value here would push markup in as literal text.
        if (k === "html") return;
        var yt = ym.get(k);
        if (yt instanceof Y.Text) return spliceText(yt, v);
        var t = new Y.Text();
        ym.set(k, t);
        if (v) t.insert(0, v);
        return;
      }
      var cur = ym.get(k);
      if (v && typeof v === "object") {
        // ponytail: a repeater (faq items, cards, spec rows) rides as one value, so two people in two
        // different rows of ONE block still lose a side. Per-row ids and a nested Y.Array is the
        // upgrade; focus-wins below stops it happening under a caret in the meantime.
        if (JSON.stringify(cur) !== JSON.stringify(v)) ym.set(k, JSON.parse(JSON.stringify(v)));
      } else if (cur !== v) ym.set(k, v);
    });
    ym.forEach(function (v, k) { if (!(k in data)) ym.delete(k); });
  }

  /* Attach first, fill second, all the way down. Yjs refuses to read a type that is not yet in a
     document -- "Add Yjs type to a document before reading data" -- so building a block whole and
     then inserting it throws the moment yData looks at a nested column. */
  function yBlock(yarr, at, b) {
    var m = new Y.Map();
    yarr.insert(at, [m]);
    m.set("type", b.type);
    m.set("data", new Y.Map());
    yData(m.get("data"), b.data || {});
  }

  function yList(yarr, list) {
    var want = list.map(idOf), i, j;
    for (i = yarr.length - 1; i >= 0; i -= 1) {
      var d = yarr.get(i).get("data");
      if (want.indexOf(d && d.get("_id")) < 0) yarr.delete(i, 1);
    }
    for (i = 0; i < list.length; i += 1) {
      var at = -1;
      for (j = i; j < yarr.length; j += 1) {
        var dd = yarr.get(j).get("data");
        if (dd && dd.get("_id") === want[i]) { at = j; break; }
      }
      // ponytail: a move is a delete and a fresh insert, because Y.Array has no move and one Y.Map
      // cannot be integrated twice -- so a peer typing into the moved block as it moves loses that
      // sentence. y-utility's move, or a position CRDT, is the upgrade.
      if (at !== i) {
        if (at > i) yarr.delete(at, 1);
        yBlock(yarr, i, list[i]);
        continue;
      }
      var m = yarr.get(i);
      if (m.get("type") !== list[i].type) m.set("type", list[i].type);
      yData(m.get("data"), list[i].data || {});
    }
  }

  /* "A new thing just happened." Called by the handful of discrete structural actions -- not by
     typing, which is meant to coalesce. Without it, two clicks a moment apart merge into one undo
     step; with it, they never do. It cannot split what one reconcileOut tick already merged (two
     actions inside the same 120ms window reach Y as a single transaction), which is a real limit
     and the reason the harness asserts step COUNTS and not just contents. */
  function step() { if (UNDO) UNDO.stopCapturing(); }

  function canUndo() { return !!(UNDO && UNDO.canUndo()); }
  function canRedo() { return !!(UNDO && UNDO.canRedo()); }
  /* The repaint comes free: an undo transaction carries the UndoManager as its origin, which is not
     YORIGIN, so reconcileIn does not skip it -- it takes the same shape branch a peer's structural
     edit takes, MODEL = fromY() and a full canvas render. Nothing here has to know about painting.
     sharedChanged() is the autosave's "the document moved even though MODEL may not have": an undo
     that lands back on the last-saved blocks would otherwise write nothing, and post_drafts.state
     would keep the ops we just undid -- which initShared lets win on the next load. */
  function undo() { if (canUndo()) { UNDO.undo(); sharedChanged(); } }
  function redo() { if (canRedo()) { UNDO.redo(); sharedChanged(); } }

  var outPending = null;
  function reconcileOut() {
    if (!YDOC) return;
    // Per keystroke this is a full walk of the document; per broadcast tick it is free. The tick is
    // also what keeps a fast typist inside the channel's events-per-second budget.
    clearTimeout(outPending);
    outPending = setTimeout(function () {
      YDOC.transact(function () { yList(YB, MODEL); }, YORIGIN);
    }, 120);
  }

  // ---- Y -> MODEL -----------------------------------------------------------
  /* The shared document as plain blocks. Y.Text.toJSON() is the PLAIN TEXT -- a Quill delta's
     formatting is not in the string -- so a rich block's html is taken from MODEL, which
     mountQuill()'s text-change mirror keeps current whoever did the typing. */
  function fromY() {
    var out = YB.toJSON(), mine = {};
    eachBlock(MODEL, function (b) { if (idOf(b)) mine[idOf(b)] = b; });
    eachBlock(out, function (b) {
      var was = b && b.data && mine[b.data._id];
      if (!b || !b.data || !b.data._rich) return;
      if (was) return void (b.data.html = was.data.html);
      /* Not in MODEL, so there is no mirror to read the formatting off -- which is exactly what
         undoing a DELETE looks like: the block is back in the document and gone from here. Falling
         through would leave b.data.html as Y.Text.toJSON(), the bare words, so undoing the deletion
         of a formatted paragraph would quietly return it as plain text. converter() is the offscreen
         Quill kept so a delta renders byte-identically to a mounted editor; mirrorProse already
         reads a peer's words through it, and this is the same question asked about our own. */
      var yt = ytextAt(b.data._id), conv = yt && converter();
      if (!conv) return;
      conv.setContents(yt.toDelta(), "silent");
      b.data.html = semantic(conv);
    });
    return out;
  }

  /* The Y.Text for a block's html, by _id, wherever it sits (a column nests one level). */
  function ytextAt(id) {
    var found = null;
    function walk(arr) {
      for (var i = 0; i < arr.length && !found; i += 1) {
        var m = arr.get(i), d = m && m.get && m.get("data");
        if (!d || !d.get) continue;
        if (d.get("_id") === id) { var h = d.get("html"); if (h && h.toDelta) found = h; return; }
        var cols = d.get("cols");
        if (cols && cols.length) for (var c = 0; c < cols.length && !found; c += 1) walk(cols.get(c));
      }
    }
    walk(YB);
    return found;
  }

  /* Focus wins. A remote value landing in the field somebody is typing in would replace it mid-word,
     which is worse than the editor before any of this: there, the loser at least kept typing into
     their own copy until the next save. So a change that touches the block the caret is in is held,
     and applied when the caret leaves. One rule, and it covers all three things that are not a
     shared text type: a legacy section's html, a repeater's rows, and the settings in the panel. */
  var held = [];
  function caretIn(id) {
    var d = cdoc(), a = d && d.activeElement, n = a && a.closest && a.closest("[data-b]");
    return !!n && idOf(blockAt(n.getAttribute("data-b"))) === id;
  }
  function later(id, fn) { if (caretIn(id)) held.push([id, fn]); else fn(); }
  function flushHeld() {
    var q = held;
    held = [];
    q.forEach(function (x) { later(x[0], x[1]); });
  }

  /* ---- a peer's prose, when no editor is mounted to receive it ---------------------------------
     A rich paragraph is the one field MODEL cannot read out of the shared document. A Y.Text holds a
     Quill delta and toString() is only the plain words, so html has always been mirrored back by a
     mounted Quill's text-change (mountQuill) -- which is why the loop above used to skip the key.

     That leaves a hole exactly where it is most visible. In Preview there is no Quill at all:
     canvasFull() short-circuits to renderPreview() and never wires the document. So a peer's typing
     reached the shared document, the roster and the markers, and never reached MODEL -- and MODEL is
     what Preview renders (formBody) and what Publish submits. The words were simply missing from the
     preview, and publishing from there sent the page an edit behind. #68 saw half of this and took
     the writer's job away from a previewing browser so it could not SAVE a stale draft; it could
     still show one, and Publish was never gated that way at all.

     So when nothing owns the field, convert it with a Quill of our own. Not a hand-written
     delta-to-HTML renderer: the output has to be byte-identical to the mounted editor's or the two
     paths would disagree about the same paragraph, so it is the same vendored Quill, the same
     QUILL_FORMATS and the same semantic(). */
  var convQ = null;
  function converter() {
    if (convQ) return convQ;
    var Q = window.Quill;                 // the PARENT's copy (post_form.html), not quillCtor()'s
    if (!Q) return null;                  // no room on this page, so no peer and nothing to convert
    var box = document.createElement("div");
    // Offscreen rather than hidden: display:none is a container Quill has never been measured in,
    // and this one has to behave exactly like the mounted editors.
    box.style.cssText = "position:fixed;left:-99999px;top:0;width:640px;height:1px;overflow:hidden";
    box.setAttribute("aria-hidden", "true");
    document.body.appendChild(box);
    convQ = new (withSize(Q))(box, { formats: QUILL_FORMATS, modules: { toolbar: false, history: HISTORY_OFF } });
    return convQ;
  }

  function mirrorProse(b, path, yt) {
    var d = cdoc(), f = d && d.querySelector('[data-b="' + path + '"] [data-f="html"]');
    // A mounted editor owns this field: y-quill applied the delta into it with both carets intact
    // and its text-change already wrote MODEL. __quill is set before the binding is, so a field still
    // waiting in the bind queue counts as owned too -- which is what makes this safe during a repaint.
    if (quillOf(f)) return;
    var conv = converter();
    if (!conv) return;
    conv.setContents(yt.toDelta(), "silent");   // silent: receiving is not an edit
    b.data.html = semantic(conv);
    // No markDirty(): this is somebody else's edit arriving, not one of ours to stamp and rebroadcast.
    // canvasBlock() is right in both views: a preview document has no [data-b] to replace, so it
    // falls through to canvasFull(), which is itself the "render the preview" path. Same repaint
    // every other field already takes.
    canvasBlock(path);
  }

  function reconcileIn(events, tx) {
    if (!YB || tx.origin === YORIGIN || tx.origin === YSEED) return;   // our own writes, echoing back
    var shape = false, blocks = {}, texts = {};
    events.forEach(function (e) {
      if (e.target instanceof Y.Array) { shape = true; return; }
      if (e.target instanceof Y.Text) {
        // A rich block's html is y-quill's: it applies the delta into Quill itself, both carets intact,
        // and that is the whole reason the editor moved to Quill before this change could be made.
        var key = e.path[e.path.length - 1], owner = e.target.parent;
        var tid = owner && owner.get && owner.get("_id");
        // html is no longer excluded: mirrorProse() decides, per field, whether an editor already
        // took it (the common case, and free) or whether nobody did and MODEL has to be caught up.
        if (tid) texts[tid + " " + key] = 1;
        return;
      }
      var g = e.target.get, id = g && (e.target.get("_id") || (e.target.get("data") && e.target.get("data").get("_id")));
      if (id) blocks[id] = 1; else shape = true;
    });
    // ponytail: a section added, removed or moved by somebody else repaints the whole canvas, which
    // costs the local caret. Typing never comes through here -- y-quill applies that straight into
    // Quill -- so the common case is unaffected; dispatching a structural delta to canvasInsert /
    // delBlock / moveBlock by _id is the upgrade when this proves annoying in real use.
    if (shape) { MODEL = fromY(); return canvasFull(); }
    Object.keys(texts).forEach(function (k) {
      var sp = k.indexOf(" "), id = k.slice(0, sp), key = k.slice(sp + 1);
      later(id, function () {
        var p = pathOfId(id), b = p && blockAt(p), m = mapById(id);
        if (!b || !m) return;
        var yt = m.get("data").get(key);
        if (!(yt instanceof Y.Text)) return;
        if (key === "html") return mirrorProse(b, p, yt);
        b.data[key] = yt.toString();
        var d = cdoc(), f = d && d.querySelector('[data-b="' + p + '"] [data-f="' + key + '"]');
        // innerText, not textContent, and symmetric with what bindField() reads back. These fields
        // are contentEditable="plaintext-only", so Enter makes a <br>; textContent would write a bare
        // "\n" that innerText reads back with the break collapsed, and the next local keystroke
        // would splice the peer's line break away again -- on every keystroke, until somebody stopped.
        if (f && f.closest("[data-b]").getAttribute("data-b") === p) f.innerText = b.data[key];
        else canvasBlock(p);
      });
    });
    Object.keys(blocks).forEach(function (id) {
      later(id, function () {
        var p = pathOfId(id), b = p && blockAt(p), m = mapById(id);
        if (!b || !m) return;
        var keep = b.data._rich ? b.data.html : null;
        b.type = m.get("type");
        b.data = m.get("data").toJSON();
        if (keep !== null) b.data.html = keep;
        canvasBlock(p);
      });
    });
  }

  /* One document, however many people opened it. Two editors who each seeded a fresh Y.Doc from the
     same blocks would hand Yjs two independent histories to merge, and every section would appear
     twice -- so the stored state is loaded when there is one, and seeded only when there is not. */
  function initShared(state) {
    if (!window.IOPY) return;                      // the module did not load: single-player, as before
    Y = window.IOPY.Y;
    YDOC = new Y.Doc();
    YB = YDOC.getArray("blocks");
    /* Attached before anything below can return, and that ordering is the whole lesson: everything
       after this point has an early exit in it, and while this line sat at the END of the function a
       page with a stored state -- which is every page after its first save -- returned before
       `update` was ever hooked up. Not one keystroke was broadcast to anybody. Nothing threw: the
       editor worked, the draft saved, the peer markers moved, and the words stayed in the browser.
       Safe this early because shareOut is a no-op until initCollab has a channel, which is also why
       loading the state below cannot put the whole document on the wire. */
    YDOC.on("update", function (delta, origin) { shareOut(delta, origin); });
    if (state) { try { Y.applyUpdate(YDOC, b64bytes(state)); } catch (e) { say("stored state unreadable: " + e.message); } }
    // After the state, not before: loading it is not somebody else's edit arriving, and reconcileIn
    // would answer it with a full repaint of a canvas that does not exist yet.
    YB.observeDeep(reconcileIn);
    /* One undo for the whole page, and it has to belong to the DOCUMENT rather than to an editor.
       Quill's history lives on a Quill instance: it dies on every repaint, it has never heard of
       sections, and with its default userOnly:false it records a peer's delta and lets you revert
       THAT -- broadcast to everyone, because the binding writes the inverse straight back into the
       Y.Text. A Y.UndoManager is scoped to YB, so it survives repaints and covers structure and
       prose alike (both live in this one document), and `trackedOrigins` means it only ever pops
       ops that were ours. A colleague's sentence is not on this stack and cannot be.
       Constructed AFTER applyUpdate on purpose: loading the stored state is not an edit, and a
       manager built before it would open with the whole page as its first undo step.
       captureTimeout is Quill's `delay` in a different hat -- continuous typing coalesces into one
       step, which is the behaviour this editor already had. It does NOT separate discrete actions,
       because reconcileOut's debounce makes transactions timer ticks rather than actions; step()
       below is what puts a boundary where the action actually is. */
    UNDO = new Y.UndoManager(YB, { trackedOrigins: new Set([YORIGIN]), captureTimeout: 500 });
    // The buttons' only rule is whether there is anything on the stacks, so they have to be
    // repainted when the stacks move -- including while somebody types, which no other event here
    // would tell the toolbar about.
    UNDO.on("stack-item-added", function () { syncBar(); });
    UNDO.on("stack-item-popped", function () { syncBar(); });
    if (YB.length) return void (MODEL = fromY());   // the stored document wins over what this page drew
    /* No stored document. Seeding one from `blocks` is only safe if NOBODY ELSE already has one:
       two browsers that each seed give Yjs two independent histories of the same page, and merging
       them shows every section twice. (Seen for real, and it is not a rare race -- with no stored
       state, which is every page load before 0010 is applied, it happens every single time.) So the
       seed waits until the roster says we are alone; if a peer is here, their state arrives on our
       join and this becomes a no-op. The timeout is the backstop for a peer that never answers --
       an editor with a document nobody is sharing beats an editor with no document at all. */
    if (!(SPEC.rt && SPEC.rt.room) || !window.supabase) return seedDoc();
    setTimeout(seedDoc, 4000);
  }

  /* Bind this editor to the shared paragraph -- the line that makes two people in one sentence keep
     both sets of words. The Y.Text holds a Quill DELTA, not HTML (Y.Text.toJSON() is the plain text;
     the formatting lives in the delta), so it is filled from an editor that already has the content,
     and filled BEFORE the binding: QuillBinding's constructor ends in setContents(type.toDelta()),
     so binding an empty one would empty the page.
     Binding also repairs a stale mirror for free -- that setContents is the shared truth arriving --
     which is what makes coming back from Preview safe. */
  function shareQuill(node, f, q, key) {
    if (!YDOC || key !== "html" || !window.IOPY) return;
    var id = idOf(blockAt(node.getAttribute("data-b")));
    if (!id) return;
    WAITING.push({ id: id, q: q, key: key });
    shareWaiting();
  }

  /* A QUEUE, and not a decision taken once at mount time, because at mount time the answer is very
     often "not yet" -- and the cost of treating that as "never" is silent and total. canvasFull()'s
     onload runs wireDoc() before initCollab() has a channel, so canWrite() is false for every editor
     on the page's first paint; the shared text is never created, nothing binds, and from then on
     typing reaches MODEL and stops there. It does not throw and it does not warn: reconcileOut skips
     a rich block's html by design (y-quill owns it), so the words simply never leave the browser.
     Seen for real -- a stored draft whose html read "Prime Testing  is available only monday to
     Friday" beside a shared text that still read "Prime Test".

     So a mount that cannot bind waits, and every event that could change the answer drains the
     queue: the document arriving, a peer's update, the roster settling, the channel subscribing. */
  function shareWaiting() {
    if (!YDOC || !window.IOPY) return;
    for (var i = WAITING.length - 1; i >= 0; i -= 1) {
      var w = WAITING[i], m = mapById(w.id), data = m && m.get("data");
      if (!data) continue;                         // the document itself has not arrived yet
      if (!(data.get(w.key) instanceof Y.Text)) {
        if (!canWrite()) continue;                 // somebody else is the one to create it
        // The shared text holds a Quill DELTA, so it is filled from the editor that already has the
        // content -- and filled before anything binds, because QuillBinding's constructor ends in
        // setContents(type.toDelta()) and binding an empty one would empty the page.
        YDOC.transact(function () {
          var t = new Y.Text();
          data.set(w.key, t);
          t.applyDelta(w.q.getContents().ops);
        }, YORIGIN);
      }
      var yt = data.get(w.key);
      if (!(yt instanceof Y.Text)) continue;
      WAITING.splice(i, 1);
      bindQuill(yt, w.q);
    }
  }

  function bindQuill(yt, q) {
    /* Sweep the dead first. canvasBlock() replaces ONE section's node without going through
       wireDoc(), so that block's old binding is left observing the shared text and feeding a delta
       into an editor whose DOM is gone -- and that editor's own observer then writes it back. Two
       bindings on one text is a loop, not a leak. */
    for (var i = BINDS.length - 1; i >= 0; i -= 1) {
      var old = BINDS[i];
      if (old.quill && old.quill.root && old.quill.root.isConnected) continue;
      try { old.destroy(); } catch (e) { /* already gone */ }
      BINDS.splice(i, 1);
    }
    BINDS.push(new window.IOPY.QuillBinding(yt, q));
  }

  // Idempotent by design: called from the roster, from a timeout and from the single-player path,
  // and whichever arrives first makes the others do nothing.
  function seedDoc() {
    if (!YDOC || YB.length) return;
    stampIds(MODEL);
    // YSEED, not YORIGIN: writing the page into the document for the first time is not an edit,
    // and it must not land on the undo stack -- undo on a freshly opened page would empty it.
    YDOC.transact(function () { yList(YB, MODEL); }, YSEED);
    say("seeded the shared document from this page's sections.");
    shareWaiting();
  }

  /* The repair for the race the seed guard cannot close: two browsers loading in the same instant
     both see an empty roster and both seed. One _id must name one section, so a later copy of a name
     we already have is deleted. Cheap, because it only runs when a peer's update actually arrives. */
  function dedupe() {
    if (!YDOC) return;
    var seen = {}, dead = [];
    for (var i = 0; i < YB.length; i += 1) {
      var d = YB.get(i).get("data"), id = d && d.get("_id");
      if (!id) continue;
      if (seen[id]) dead.push(i); else seen[id] = 1;
    }
    if (!dead.length) return;
    say("removed " + dead.length + " duplicated section(s): two browsers had seeded this page.");
    YDOC.transact(function () {
      for (var k = dead.length - 1; k >= 0; k -= 1) YB.delete(dead[k], 1);
    }, YSEED);                // a repair, not an edit -- and undoing it would put the twins back
    MODEL = fromY();
    canvasFull();
  }

  function b64bytes(s) {
    var bin = atob(s), out = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i += 1) out[i] = bin.charCodeAt(i);
    return out;
  }
  function bytesB64(u8) {
    var s = "", i;
    for (i = 0; i < u8.length; i += 1) s += String.fromCharCode(u8[i]);
    return btoa(s);
  }
  function yState() { return YDOC ? bytesB64(Y.encodeStateAsUpdate(YDOC)) : ""; }

  function seedFor(type) {
    return JSON.parse(JSON.stringify((SPEC.ui.seed && SPEC.ui.seed[type]) || {}));  // never hand out the shared seed
  }

  // ---- saving itself --------------------------------------------------------
  /* The page writes itself to a working draft every second and a half. Nothing here touches the
     published content: that moves only when somebody presses the button, which is why the button
     says Publish on a live page.

     Reassigned by initAutosave(), a no-op until then and on a post that has not been created yet --
     markDirty() runs during the first render, before there is anywhere to save to. Same late-binding
     shape as syncBar() and paintPeers(). */
  var nudgeSave = function () {};

  function initAutosave(form) {
    var box = document.getElementById("ed-saved"), pk = SPEC.pk;
    if (!pk) return;                       // a new post has no row to hang a draft on until it is created
    var timer = null, inFlight = 0, savedAt = 0, sent = null,
        // Each section THIS person has touched, and what it looked like the moment they first
        // touched it. Both halves matter. Which sections, because everybody holds the same document
        // now and a plain before/after would credit the whole room's writing to whoever saved last.
        // And FROM WHEN, because a baseline taken at page load spans everything a peer did to that
        // section in the meantime -- a real entry read "WAS <p></p> NOW <the whole sentence>" for
        // somebody who had added one word to what a colleague wrote while they had the page open.
        // Quill is what can tell local from remote: text-change reports source "user" for input and
        // the binding object for a delta y-quill just applied from a peer.
        mine = {}, shared = false,
        idle = null;

    function show(text, bad) {
      if (!box) return;
      box.className = bad ? "ed-saved bad" : "ed-saved";
      box.textContent = text;
    }
    function showAge() {
      if (!savedAt) return;
      var mins = Math.round((Date.now() - savedAt) / 60000);
      show(mins < 1 ? "Saved just now" : mins === 1 ? "Saved a minute ago" : "Saved " + mins + " minutes ago");
    }
    setInterval(showAge, 30000);           // so "just now" stops claiming to be just now

    /* What the draft stores, and it is NOT pruned. prune() drops an empty paragraph and rebuilds a
       columns block as a fresh object -- so a block an editor still has the caret in loses its _id,
       every section after it answers to a different one, and a remote edit would be applied to the
       wrong section on the next load. The draft is the live document, empty paragraphs and all;
       Publish still prunes, because that is where "an empty paragraph is the caret waiting for you,
       not content" is true. */
    function saveable() { return JSON.stringify(MODEL); }

    /* This person's sitting, as a [before, after] pair: ONLY the sections they touched, each against
       what it looked like when they first touched it.

       Both sides are built here, from one ordered list, because the two halves have to describe the
       same document -- sending a whole-page `was` beside a narrowed `now` is what made an entry claim
       a colleague's sentence. Sections nobody here touched are left out of both sides rather than
       repeated on each: the payload is smaller, and _section_rows() on the server names a row by its
       section TYPE rather than by its position, so dropping them costs no context. */
    function sitting(now) {
      if (!YDOC) return [was, now];        // single player: the whole document IS their work
      var fresh = {}, order = [], seen = {}, wasOut = [], nowOut = [];
      JSON.parse(now).forEach(function (b) {
        var id = idOf(b);
        if (id) { fresh[id] = b; if (!seen[id]) { seen[id] = 1; order.push(id); } }
      });
      // a section they deleted is in `mine` but no longer on screen, and has to keep its place
      Object.keys(mine).forEach(function (id) { if (!seen[id]) { seen[id] = 1; order.push(id); } });
      order.forEach(function (id) {
        if (!mine[id]) return;                       // somebody else's: silent on both sides
        wasOut.push(mine[id]);                       // as it was when I first put a hand on it
        if (fresh[id]) nowOut.push(fresh[id]);       // still here; absent = I removed it
      });
      return [JSON.stringify(wasOut), JSON.stringify(nowOut)];
    }

    function body(now, close) {
      var f = new FormData();
      f.append("csrf", csrf());
      // The document half is the ELECTED WRITER'S only: every peer holds the same document, so thirty
      // editors would otherwise be thirty writes of the same bytes. The sitting half below is every
      // peer's own, which is what keeps the activity log per person. The server tests for the field
      // being present, not for it being truthy.
      if (canWrite()) { f.append("blocks", now); f.append("state", yState()); }
      var pair = sitting(now);
      f.append("was", pair[0]);
      f.append("now", pair[1]);
      if (close) f.append("close", "1");
      return f;
    }

    function save() {
      var now = saveable();
      // `shared` is the other reason to write: a peer typed, so the document moved even though this
      // copy of the blocks did not -- the encoded state has to catch up or a reload would lose it.
      if (now === sent && !shared) return;   // the title moved, not the page
      shared = false;
      sent = now;
      var mine = ++inFlight;
      show("Saving…");
      fetch("/admin/posts/" + pk + "/draft", { method: "POST", body: body(now), credentials: "same-origin" })
        .then(function (r) {
          // ui_required redirects a finished session to the login page and fetch() follows it, so a
          // dead session arrives as 200 HTML. Say "sign in again", never parse it as JSON.
          if (r.redirected) throw new Error("your sign-in has ended — open this page again in a new tab");
          return r.json().then(function (j) { return r.ok ? j : Promise.reject(new Error(j.error || "could not save")); });
        })
        .then(function (j) {
          if (mine !== inFlight) return;   // a newer save already answered
          /* The server tolerates the working-draft tables not existing yet, because the editor has
             to run before that migration is applied -- but it says so, and so do we. Reporting
             "Saved just now" over work with nowhere to go is how typing appears to vanish on the
             next reload: the page is served the PUBLISHED version back, because there is no draft.
             No table names on an editor's screen; the console gets the developer half. */
          if (j && j.stored === false) {
            sent = null;
            say("the working-draft tables are missing -- apply migrations/0010_working_draft.sql. Nothing is being saved.");
            return show("Not saved — this site is not set up to keep drafts yet. Tell a developer.", true);
          }
          savedAt = Date.now();
          dirty = false;                   // it is safe to leave: the work is on the server
          showAge();
        })
        .catch(function (e) {
          if (mine !== inFlight) return;
          sent = null;                     // so the next keystroke tries again rather than seeing no change
          show("Not saved — " + e.message, true);
        });
    }

    // Somebody else typed. Nothing of mine changed, so this is not my sitting and dirty stays as it
    // was -- but if I am the writer, the draft on the server is now behind and only I can move it.
    sharedChanged = function () { if (canWrite()) { shared = true; clearTimeout(timer); timer = setTimeout(save, 1500); } };
    /* The snapshot lives HERE rather than at the call sites, because the one call that matters most
       is a deletion: the section has to be captured while it is still in MODEL. Called once per
       section per sitting -- after that the baseline is fixed, which is the whole point. */
    touched = function (id) {
      if (!id || mine[id]) return;
      var p = pathOfId(id), b = p && blockAt(p);
      mine[id] = b ? JSON.parse(JSON.stringify(b)) : { type: "rich_text", data: { _id: id } };
    };

    nudgeSave = function () {
      clearTimeout(timer);
      timer = setTimeout(save, 1500);
      clearTimeout(idle);
      // Fifteen minutes after the last change, this sitting is over: close the session so the
      // activity log gets its entry without waiting for the tab to be shut.
      // Fifteen minutes with no activity is the only thing that ENDS a sitting. Leaving the page
      // does not: see the pagehide handler.
      idle = setTimeout(function () { closeSession(true); }, 15 * 60 * 1000);
    };

    /* `end` is what separates "I am leaving the page" from "this sitting is over", and they are not
       the same thing. A reload or a trip to another screen used to close the sitting outright, so one
       person doing twenty minutes' work across three visits got three entries instead of the one the
       client asked for ("no activity for 15 mins"). Now leaving only FLUSHES what is pending; the
       sitting is closed by the idle timer above, or by flush_sessions()' backstop when the next
       person touches the page -- which is also what records a tab that was closed and never came
       back. touch_session() merges each visit into the open session, so the entry covers all of it. */
    function closeSession(end) {
      clearTimeout(timer);
      var now = saveable(), pair = sitting(now);
      if (pair[0] === pair[1]) return;     // opened the page and read it: not a sitting to write up

      if (!navigator.sendBeacon) { fetch("/admin/posts/" + pk + "/draft", { method: "POST", body: body(now, end), credentials: "same-origin", keepalive: true }).catch(function () {}); return; }
      // sendBeacon, not fetch: an ordinary request is cancelled when the page goes away. FormData
      // and not JSON because ui_required reads the csrf field out of request.form.
      navigator.sendBeacon("/admin/posts/" + pk + "/draft", body(now, end));
    }
    window.addEventListener("pagehide", function () { closeSession(false); });

    // The button tells the truth about what pressing it does, and the status dropdown can change
    // that without a reload.
    var status = form.querySelector('select[name="status"]'), publish = document.getElementById("ed-publish");
    if (status && publish) status.addEventListener("change", function () {
      publish.textContent = status.value === "published" ? "Publish" : "Save";
    });
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
    // the canvas needs the content type to know whether this page draws its own title above the
    // sections (blocks.owns_head): a blog post and a case study always do, everything else only
    // when no Hero or Columns section opens the page.
    body.append("type", SPEC.type || "");
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
    // Coalesced, not immediate: this is the one funnel every repaint reaches -- a peer's keystroke,
    // dedupe(), setBlocks(), the structural branch -- and a preview render is a whole page off the
    // database. setView() calls renderPreview() directly, so ENTERING preview is still instant.
    if (VIEW === "preview") return previewSoon();   // whatever changed, preview is what is on screen
    /* srcdoc hands back a document scrolled to the top and nothing else puts it back, so every
       structural change threw the editor to the top of the page -- inserting a section, deleting
       one, a peer's edit. It was invisible on a block WITH a field, because focusBlock() then
       focuses one and the browser scrolls it into view; a divider, a spacer and an embed have no
       field to focus, so there it is the whole story (measured: 1694 -> 0 on a page eight
       paragraphs long). Read now, not in onload: by then the old document is gone. Only from the
       edit canvas -- the preview is a different page, with a header above the body, so its offset
       means nothing here. `pvUp` is exactly that question and renderPreview() already asks it. */
    var old = !pvUp && cdoc(), y = old ? old.defaultView.scrollY : 0;
    pvUp = false;                      // the frame is about to hold the edit canvas, not a preview
    ask("full", {}, function (html) {
      FRAME.onload = function () {
        FRAME.onload = null;
        wireDoc();
        // before focusBlock: a caret that is off screen after this still wins, by scrolling itself in
        if (y) { var w = cdoc(); if (w) w.defaultView.scrollTo(0, y); }
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
    // A preview document carries no [data-b] -- render_blocks() hands it _no_fe -- so the surgery
    // below can never find its node and the callback always fell through to canvasFull(). The !d
    // guard does not catch it, because the preview iframe has a perfectly good document, so every
    // peer keystroke bought a /admin/canvas round trip purely to discard it: ~6.6 a second.
    if (VIEW === "preview") return canvasFull();
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
    markStep();                    // mints the _id, so the section has a name to be touched by
    touched(rootIdOf(at));
    canvasInsert(at, true);
  }

  function focusBlock(path) {
    var d = cdoc(), node = d && d.querySelector('[data-b="' + path + '"]');
    var f = node && Array.prototype.filter.call(node.querySelectorAll("[data-f]"), function (x) {
      return x.closest("[data-b]") === node;      // not a nested block's first field
    })[0];
    if (!f) return select(path);      // a divider, or a fresh columns block: no field of its own
    /* Quill mounts div.ql-editor INSIDE [data-f], so the field itself is never contenteditable and
       never focusable -- f.focus() is a no-op and a range at (f, 0) sits outside the editable, which
       is why the caret had to be placed with the mouse before anything could be typed. */
    var q = quillOf(f);
    if (q) { q.focus(); q.setSelection(0, 0); return select(path); }
    f.focus();
    var r = d.createRange(), sel = d.defaultView.getSelection();
    r.selectNodeContents(f);
    r.collapse(true);
    sel.removeAllRanges();
    sel.addRange(r);
    select(path);
  }

  /* Reassigned by initCollab(); a no-op when collaboration is off, or before the socket is up.
     Same late-binding trick as syncBar() below, and for the same reason: canvasFull() is async, so
     anything that touches the canvas document has to tolerate being called before it exists. */
  var paintPeers = function () {};

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
    paintPeers();   // the one place every re-render path passes through, and renumber() has already run
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

  /* ---- Quill, on the blocks it can hold without losing anything ---------------
     Prose is edited by Quill so that two people can later type in the same paragraph and keep both
     sets of words -- a plain HTML string is last-writer-wins however it is transported, and only a
     real text CRDT fixes that. Quill is the binding a CRDT needs.

     It does NOT take every block, and the rule is measured rather than guessed. Quill silently drops
     what it has no blot for, and on this site's own content that was 7 of 24 rich_text blocks:
     <dl>/<dt>/<dd> on NAS and Contact Us, <div>/<span> on About Us, <table> on NAS and Testing, and
     -- the dangerous one -- the Home page, which loses six CLASSES and not a single tag, so a
     "does it contain a table?" check would wave it straight through and the first save would strip
     the page's styling. So the gate is per block and empirical: paste it into a throwaway Quill,
     read it back, and refuse if any tag or class went missing. Those blocks keep the editor they
     have always had -- except where the section was never prose at all, which is the real cure and
     has now happened three times: 0011 made Home's panel `points` and NAS's feature list
     `definitions`, and 0017 made the About Us founder pair `people`. Four refusals are left. */
  var QUILL_FORMATS = ["bold", "italic", "underline", "strike", "link", "header", "list",
                       "blockquote", "align", "color", "background", "image", "size"];

  /* Quill ships a size format and it was simply out of reach: its style attributor is built with
     `whitelist:["10px","18px","32px"]`, and none of TEXT_SIZES is in that list, so every rem size
     was dropped on the next keystroke. The whitelist is a property on a singleton, so widening it
     is the whole registration. A STYLE attributor, not the class one, on purpose: it emits
     style="font-size:…", which is exactly the span the legacy execCommand path already produces,
     so the two paths keep agreeing about the same paragraph and quillKeeps()'s marks() -- which
     compares tags and classes -- is untouched by any of this.
     Called for EVERY Quill constructor, because there are two: the canvas iframe's and the
     parent's offscreen converter(). One registered and not the other means a peer's paragraph
     renders one way in the editor and another way through the converter, which is the same class
     of fault as two copies of Yjs. Memoised on the constructor itself rather than in a module
     variable, since the iframe's Q is a different object after every full repaint. */
  function withSize(Q) {
    if (!Q || Q.__iopSize) return Q;
    try {
      var SizeStyle = Q.import("attributors/style/size");
      SizeStyle.whitelist = TEXT_SIZES.map(function (o) { return o[0]; })
                                      .filter(function (v) { return v !== "normal"; });
      Q.register(SizeStyle, true);
      Q.__iopSize = 1;
    } catch (e) { /* an older bundle without the attributor: Size stays as it was */ }
    return Q;
  }

  function quillCtor() { var w = FRAME && FRAME.contentWindow; return w && w.Quill; }
  function quillOf(f) { return f && f.__quill ? f.__quill : null; }

  function semantic(q) {
    /* getSemanticHTML(), never root.innerHTML: innerHTML wraps every list in <ol> with
       <li data-list="bullet"> plus injected <span class="ql-ui">, and the public page loads no Quill
       CSS -- so every bulleted list on the live site would render numbered.
       Then undo the &nbsp;: getSemanticHTML does replaceAll(" ", "&nbsp;") on EVERY text leaf
       (verified in the vendored build, not in the docs). Left alone, _html_md()'s unescape() puts
       U+00A0 through the .md twins and the public page never wraps. A real non-breaking space is
       emitted as the character, not the entity, so this does not touch one. */
    return semanticPart(q, 0, q.getLength());
  }

  // The same, over one stretch of the document: getSemanticHTML(index, length) is the real signature
  // in the vendored build, and splitAt() needs the half of a paragraph that is staying behind.
  function semanticPart(q, i, n) { return q.getSemanticHTML(i, n).replace(/&nbsp;/g, " "); }

  // Quill rewrites <b> as <strong> and <i> as <em>, which _html_md() has always treated as the same
  // thing. Without this the gate refuses a block for a difference nobody can see.
  var SAME_TAG = { b: "strong", i: "em" };

  function marks(html) {                 // every tag and class the markup carries, as one flat list
    var out = [], seen = {};
    (html.match(/<([a-zA-Z][\w-]*)/g) || []).forEach(function (m) {
      var t = m.slice(1).toLowerCase();
      t = SAME_TAG[t] || t;
      if (!seen["<" + t]) { seen["<" + t] = 1; out.push("<" + t); }
    });
    (html.match(/class="([^"]*)"/g) || []).forEach(function (m) {
      m.slice(7, -1).split(/\s+/).forEach(function (c) {
        if (c && !seen["." + c]) { seen["." + c] = 1; out.push("." + c); }
      });
    });
    return out;
  }

  function quillKeeps(Q, d, html) {
    if (!html) return true;              // an empty paragraph is what Quill is for
    var probe = d.createElement("div");
    probe.style.cssText = "position:absolute;left:-9999px;top:0";
    d.body.appendChild(probe);
    try {
      var q = new (withSize(Q))(probe, { formats: QUILL_FORMATS, modules: { toolbar: false, history: HISTORY_OFF } });
      q.clipboard.dangerouslyPasteHTML(html, "silent");
      var after = marks(semantic(q));
      // A no-loss test, not an equality test: Quill wrapping a bare text node in <p> is fine, and
      // losing <dl> or class="eyebrow" is not.
      return marks(html).every(function (m) { return after.indexOf(m) > -1; });
    } catch (e) {
      return false;                      // it threw on this markup: that is a refusal too
    } finally {
      if (probe.parentNode) probe.parentNode.removeChild(probe);
    }
  }

  function mountQuill(node, f, key) {
    var Q = quillCtor(), d = f.ownerDocument, target = dataFor(node, f);
    if (!Q || !target) return false;
    /* The verdict is READ here, never worked out here. mountQuill runs once per peer per repaint, so
       a "compute it if it is missing" fallback is the per-peer gate all over again: three browsers
       opening one page would all reach it at once and could disagree. Only the elected writer
       decides, once, and the answer is then content that travels with the block -- and a block with
       no verdict yet is treated as legacy until the writer's document arrives and repaints. */
    if (target._rich === undefined) {
      if (!canWrite()) { node.setAttribute("data-legacy", "1"); return false; }
      target._rich = quillKeeps(Q, d, target[key] || "");
      markDirty();
    }
    if (!target._rich) {
      // Said on the block, not the field: [data-f]::after is the peer label, and anything put INSIDE
      // a [data-f] is copied into MODEL by the legacy input handler and published.
      node.setAttribute("data-legacy", "1");
      return false;
    }
    var q = new (withSize(Q))(f, { formats: QUILL_FORMATS, modules: { toolbar: false, history: HISTORY_OFF } });
    q.clipboard.dangerouslyPasteHTML(target[key] || "", "silent");   // silent: mounting is not an edit
    f.__quill = q;
    shareQuill(node, f, q, key);
    q.on("text-change", function (delta, old, source) {
      var t = dataFor(node, f);
      if (!t) return;
      t[key] = semantic(q);
      // Quill's own normalising is not somebody typing, and neither is a delta y-quill just applied
      // from a peer -- it passes the binding as the source, so anything but "user" came from elsewhere.
      if (source !== "user") return sharedChanged();
      touched(rootIdOf(node.getAttribute("data-b")));
      markDirty();
      // The "/" inserter. The legacy path gets it from bindSlash()'s keyup, but Quill owns the
      // keyboard, so the hook is the content itself: a line that now reads exactly "/" opens the
      // chooser, on the line's own DOM node, which is what openSlash() measures and rewrites.
      if (slashBox) return;
      var r = q.getSelection(), ln = r && q.getLine(r.index)[0];
      if (ln && ln.domNode && (ln.domNode.textContent || "").trim() === "/") openSlash(node, f, ln.domNode);
    });
    // rememberSelection() already sets savedField/savedRange from the document's own
    // selectionchange -- the caret is inside f, so its closest("[data-f]") is still f. This handler
    // only does the two things that are not selection state.
    q.on("selection-change", function (range) {
      if (!range) return;
      select(node.getAttribute("data-b"));
      syncBar();
    });
    return true;
  }

  function bindField(node, f) {
    var rich = f.hasAttribute("data-rich"), key = f.getAttribute("data-f");
    if (rich && mountQuill(node, f, key)) return;   // Quill drives this one end to end
    setEditable(f, rich);
    f.addEventListener("input", function () {
      var target = dataFor(node, f);
      if (!target) return;
      target[key] = rich ? f.innerHTML : f.innerText;
      touched(rootIdOf(node.getAttribute("data-b")));
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
    touched(rootIdOf(path));
    r.arr.splice(to, 0, r.arr.splice(r.i, 1)[0]);
    var box = d && boxFor(path);
    if (box) {
      var nodes = blocksIn(box), node = nodes[r.i], ref = nodes[to];
      if (node && ref) ref.parentNode.insertBefore(node, dir > 0 ? ref.nextSibling : ref);
      renumber();
      bars();
    }
    markStep();
    select(siblingPath(path, to));
  }

  function dupBlock(path) {
    closePanel();
    var r = listAt(path);
    if (!r.arr) return;
    var copy = JSON.parse(JSON.stringify(r.arr[r.i]));
    // A copy is a different section, so it gets a different name. Sharing one _id with the original
    // makes the two indistinguishable to every merge decision below.
    eachBlock([copy], function (b) { if (b && b.data) delete b.data._id; });
    r.arr.splice(r.i + 1, 0, copy);
    markStep();
    touched(rootIdOf(siblingPath(path, r.i + 1)));
    canvasInsert(siblingPath(path, r.i + 1));
  }

  function delBlock(path) {
    closePanel();
    var r = listAt(path);
    if (!r.arr || !r.arr[r.i]) return;
    if (!confirm("Remove this " + nameFor(r.arr[r.i].type) + " section?")) return;
    touched(rootIdOf(path));        // while it is still here: the snapshot IS what was removed
    r.arr.splice(r.i, 1);
    var d = cdoc(), node = d && d.querySelector('[data-b="' + path + '"]');
    if (node) node.remove();
    renumber();
    bars();
    markStep();
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
    // Typed sections carry it too: it is the only way to reach their alignment and width, and it is
    // one bar per block of writing, not one per paragraph. It hangs off the <section>, outside the
    // [data-f] editable, so nothing it adds can reach the saved HTML.
    node.appendChild(blockBar(d, node));
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
    // Once per document rather than once per element, and once per document is also once per full
    // repaint -- srcdoc hands back a brand-new document each time, so this never stacks up.
    d.addEventListener("keydown", undoKey);
    // The document this canvas held is gone; its bindings still observe Y types and would apply
    // deltas into dead Quill instances for the life of the tab.
    BINDS.splice(0).forEach(function (b) { try { b.destroy(); } catch (e) { /* already gone */ } });
    WAITING.length = 0;                                    // those editors are gone with the document
    d.addEventListener("focusout", flushHeld);             // the caret left: apply what was held back
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
        markStep();
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

    /* fieldInput() mutates in place and reports nothing, so watch the popover for any activity
       and redraw the one block it belongs to. Cheaper than threading a callback through every widget.

       `click` is in the list for the panel's BUTTONS -- a repeater's + Add and its ✕, the media
       browser -- which mutate data and fire nothing else. It must NOT fire for a click on a form
       control: that click changes nothing by itself, and on a <select> it is the click that OPENS
       the native dropdown. The repaint 250ms later replaces the section under it (canvasBlock ->
       node.replaceWith), the popover is repositioned, and the menu is dismissed before anybody can
       pick anything -- reported as "it kind of refreshes and the dropdown closes". Measured with
       the real editor: opening a <select> cost one /admin/canvas round trip that nothing asked for.
       Every one of these controls announces a real change through input or change, so nothing is
       lost by ignoring their clicks. */
    var pending = null;
    ["input", "change", "click"].forEach(function (ev) {
      box.addEventListener(ev, function (e) {
        if (ev === "click" && /^(SELECT|OPTION|INPUT|TEXTAREA|LABEL)$/.test(e.target.tagName)) return;
        clearTimeout(pending);
        pending = setTimeout(function () { if (panelAt) canvasBlock(panelAt); }, 250);
        if (ev === "input") markDirty(); else markStep();   // picking from a list is an action; typing in the box is not
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
      markStep();
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
      markStep();
      setBlocks(pair[1].map(function (t) { return { type: t, data: seedFor(t) }; }));
    });
  }

  // ---- the document toolbar -------------------------------------------------
  /* Lives in the admin page (so it uses admin.css) but every command runs against the CANVAS
     document. Clicking a button moves focus out of the iframe, so the caret is remembered on
     every selection change and put back before the command runs. */
  var savedRange = null, savedField = null, syncBar = function () {};

  /* Undo and redo, from wherever they are asked for -- the two buttons and the two keyboard
     listeners all land here. syncBar() afterwards because the stacks have just moved and the
     buttons' only rule is whether there is anything left on them. */
  function doUndo() { undo(); syncBar(); }
  function doRedo() { redo(); syncBar(); }

  /* Ctrl/Cmd+Z, Ctrl/Cmd+Shift+Z, and Ctrl+Y for the Windows habit -- the three Quill itself binds,
     so nobody has to learn a new one. Returns true when it handled the key.
     This has to be attached to BOTH documents: the canvas is an iframe, so a key pressed while
     editing never reaches the parent, and one pressed in the right-hand panel never reaches the
     canvas. keydown also runs before Quill's own beforeinput interceptor, so preventDefault() here
     wins even where Quill still has a binding registered. */
  function undoKey(e) {
    if (!(e.ctrlKey || e.metaKey) || e.altKey) return false;
    var k = (e.key || "").toLowerCase();
    if (k !== "z" && k !== "y") return false;
    e.preventDefault();
    if (k === "y" || e.shiftKey) doRedo(); else doUndo();
    return true;
  }

  /* An ordinary form control has its own undo and people rely on it -- taking Ctrl+Z away from the
     title or the slug to add it to the page would be a trade nobody asked for. The canvas has no
     such fields: everything there is a contenteditable whose history now belongs to the document. */
  function typingInAField(d) {
    var a = d && d.activeElement;
    return !!(a && /^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName));
  }

  function fire(f) {
    var W = f.ownerDocument.defaultView;
    f.dispatchEvent(new (W.Event || Event)("input", { bubbles: true }));
  }

  var sendWhere = function () {};   // reassigned by initCollab(), like paintPeers()

  function rememberSelection() {
    var d = cdoc();
    if (!d) return;
    /* selectionchange stopped meaning "the person at this keyboard moved their caret". y-quill
       applies a peer's words by mutating the canvas DOM, and that fires it too -- so without this
       the editor would record a caret it does not have, broadcast "I am typing here" for a field
       nobody is in, and ask a Quill that has no selection to describe one. The iframe keeps its own
       activeElement when focus moves to the toolbar in the parent document, so a toolbar click is
       still a caret in the canvas and the bar stays live. */
    var here = d.activeElement;
    if (!here || !here.closest || !here.closest("[data-f]")) return;
    var sel = d.defaultView.getSelection();
    if (!sel || !sel.rangeCount) return;
    var r = sel.getRangeAt(0), host = r.startContainer;
    host = host.nodeType === 1 ? host : host.parentNode;
    var f = host && host.closest && host.closest("[data-f]");
    if (!f) return;
    savedRange = r.cloneRange();
    savedField = f;
    syncBar();
    sendWhere(f);   // no-op unless a channel is up; throttled inside, selectionchange is very chatty
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
  /* Clear any inline size across the WHOLE line the caret is in, in a Quill field. q.format() would
     only reach the selection; a heading has to lose the size everywhere along it or the part the
     caret happened to cover is the only part that recovers. */
  function clearSizeOnLine() {
    var q = qHere();
    if (!q) return;
    var at = q.getSelection();
    if (!at) return;
    var pair = q.getLine(at.index), blot = pair && pair[0], off = pair && pair[1];
    if (!blot) return;
    var start = at.index - off;
    q.formatText(start, blot.length(), "size", false, "user");
    syncBar();
  }

  function setSize(css) {
    var d = cdoc(), q = qHere();
    /* Quill owns the field: use its own format. Not qfmt(), which TOGGLES when the caret is already
       in the value asked for -- right for a B button, wrong for a dropdown, where picking "Large"
       must mean Large and never "not Large". With nothing selected Quill keeps this as the pending
       format and the next words typed come out at that size, which is what bold and italic here
       already do. */
    if (q) {
      q.focus();
      if (!q.getSelection()) return;         // focus() landed no caret: do nothing rather than throw
      q.format("size", css === "normal" ? false : css, "user");
      return syncBar();
    }
    /* exec, NOT execLine. execLine widens a COLLAPSED caret to the whole line -- and to the whole
       field when the content has no block wrapper, because caretBlock() returns the field itself
       there. That widening was the reported bug: the surgery below used to collapse savedRange (a
       live Range whose boundaries sit inside the <font> whose children are being moved out), and
       nothing re-recorded it, so the SECOND pick -- "Large was too much, try Larger" -- found a
       collapsed range and resized the lot. execCommand with a collapsed caret already styles what
       gets typed next, so dropping execLine also makes this path agree with the Quill one above. */
    exec("fontSize", "7");
    if (!d || !savedField) return;
    var first = null, last = null;
    Array.prototype.forEach.call(savedField.querySelectorAll('font[size="7"]'), function (f) {
      var box = d.createElement("span");
      if (css === "normal") box = d.createDocumentFragment();
      else box.style.fontSize = css;
      while (f.firstChild) {
        last = f.firstChild;
        if (!first) first = last;
        box.appendChild(f.firstChild);
      }
      f.parentNode.replaceChild(box, f);
    });
    // Keep the words selected across the surgery. Without this the highlight vanishes the instant
    // the size lands, and the next pick has nothing to work on -- which is the whole bug, not a
    // cosmetic detail. Set before normalize(): the browser carries a live selection through a
    // merge, and rememberSelection() afterwards stores wherever it ended up.
    if (first && last) {
      var r = d.createRange();
      r.setStartBefore(first);
      r.setEndAfter(last);
      var sel = d.getSelection();
      sel.removeAllRanges();
      sel.addRange(r);
    }
    savedField.normalize();
    rememberSelection();
    fire(savedField);
    syncBar();
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

  /* One toolbar, two engines. Half a page can be on each at once -- Quill where it round-trips
     cleanly, the original contenteditable where it does not -- so every command tries Quill first
     and falls back to execCommand. `qfmt` with no value toggles, which is what a B or I button
     wants; an explicit value sets. Returns false when the caret is not in a Quill field, which is
     what makes `if (!qfmt(...)) exec(...)` read the way it does. */
  function qHere() { return quillOf(liveField()); }

  function qfmt(name, value) {
    var q = qHere();
    if (!q) return false;
    q.focus();
    var at = q.getSelection();
    if (!at) return false;             // focus() did not land a caret: do nothing rather than throw
    var now = q.getFormat(at);
    q.format(name, value === undefined ? !now[name] : (now[name] === value ? false : value), "user");
    syncBar();
    return true;
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
    /* Controls that build markup Quill has no blot for. The gate that let Quill take a block in the
       first place is precisely "it contains none of this", so they are switched off while the caret
       is in a Quill field rather than inserting something the next keystroke would silently drop.
       Sections that need a table or an embed keep the original editor, and keep these. */
    var proseOnly = [], undoBtn = null, redoBtn = null;
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
       thinks in H-tags. H1 is offered but is not the default for a reason: the page already has
       exactly one <h1> -- its title, or the Hero's heading when the Hero is what opens the page --
       so an H1 in body text is a second one. Use H2 to open a section. */
    HEAD_LEVELS.forEach(function (o) { style.appendChild(el("option", { value: o[0], text: o[1] })); });
    // No hold() here: cancelling mousedown on a <select> suppresses the native popup, and the caret
    // is replayed from savedRange anyway. Nor does mousedown touch selectedIndex: from Firefox 137
    // the dropdown is DOM-rendered, so clicking an option fires a SECOND mousedown that bubbles to
    // the select — anything that resets the value there wipes the pick before change reads it.
    style.addEventListener("blur", function () { syncBar(); });   // dismissed without picking: show the caret's style again
    style.addEventListener("change", function () {
      if (!style.value) return;
      // Quill's header format is a number, or false for body text.
      var lvl = style.value === "p" ? false : +style.value.slice(1);
      if (!qfmt("header", lvl)) return applyLevel(style.value);
      /* The Quill half of applyLevel's rule, which until Size worked in a Quill field had nothing
         to do. applyLevel strips inline sizes when a line becomes a heading, for the reason its
         comment gives -- the level IS the size, and with Size disabled on headings a leftover span
         is a dead end with no way back out of it from the toolbar. qfmt() returns true here, so
         applyLevel never runs on this path and the rule has to be applied to the line directly. */
      if (lvl) clearSizeOnLine();
    });

    var size = el("select", { "class": "tb-style tb-size", title: "Text size" });
    size.appendChild(el("option", { value: "", text: "Size", hidden: "hidden" }));
    TEXT_SIZES.forEach(function (o) { size.appendChild(el("option", { value: o[0], text: o[1] })); });
    size.addEventListener("blur", function () { syncBar(); });
    size.addEventListener("change", function () {
      if (size.value) setSize(size.value);
    });

    var bold = b("B", "Bold", function () { if (!qfmt("bold")) exec("bold"); }, "tb-b"),
        ital = b("I", "Italic", function () { if (!qfmt("italic")) exec("italic"); }, "tb-i"),
        und = b("U", "Underline", function () { if (!qfmt("underline")) exec("underline"); }, "tb-u"),
        strike = b("S", "Strikethrough", function () { if (!qfmt("strike")) exec("strikeThrough"); }, "tb-s");

    function colour(cmd, title, initial) {
      var i = el("input", { type: "color", "class": "tb-colour", title: title, value: initial });
      i.addEventListener("input", function () {          // no hold(): it would block the picker
        if (!qfmt(cmd === "foreColor" ? "color" : "background", i.value)) exec(cmd, i.value);
      });
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
        markStep();
        canvasInsert(at);
      });
    }

    /* One undo for the whole page, so these are NOT the caret's business -- they step the shared
       document back whether you are in a paragraph, in a settings box or nowhere at all. They keep
       `free`, which is what leaves them out of `cmds` and therefore out of syncBar's "is the caret
       in a rich field" rule; their own rule is simply whether there is anything to undo. Before
       this they were free AND unruled, so the control looked live in every state including the two
       where it was a guaranteed no-op. */
    undoBtn = b("↶", "Undo (Ctrl+Z)", doUndo, "", true);
    redoBtn = b("↷", "Redo (Ctrl+Shift+Z)", doRedo, "", true);
    bar.appendChild(group([undoBtn, redoBtn]));
    bar.appendChild(group([style, size]));
    bar.appendChild(group([bold, ital, und, strike, b("Tx", "Remove formatting", function () {
      var q = qHere();
      if (!q) return exec("removeFormat");
      var r = q.getSelection(true);
      if (r) q.removeFormat(r.index, r.length, "user");
    })]));
    // formatBlock only ever wraps, so quote needs its own way back out: outdent is what unwraps a
    // blockquote in both engines.
    var quote = b("❝", "Quote", function () {
      if (qfmt("blockquote")) return;
      if (caretBlock("blockquote")) exec("outdent"); else exec("formatBlock", "<blockquote>");
    });
    var divider = b("—", "Divider", function () { exec("insertHTML", "<hr><p><br></p>"); });
    proseOnly.push(divider);
    bar.appendChild(group([b("•", "Bulleted list", function () { if (!qfmt("list", "bullet")) exec("insertUnorderedList"); }),
                           b("1.", "Numbered list", function () { if (!qfmt("list", "ordered")) exec("insertOrderedList"); }),
                           quote,
                           divider]));
    var inserts = [b("🖼", "Insert a picture", pictureDialog),
                   b("▦", "Insert a table", tableDialog),
                   b("</>", "Embed code from another service", embedDialog)];
    inserts.forEach(function (x) { proseOnly.push(x); });
    bar.appendChild(group([b("🔗", "Add a link", function () {
      var q = qHere();
      if (!q) return docLink();
      var r = q.getSelection(true);
      if (!r || !r.length) return alert("Select the words you want to link first.");
      var url = prompt("Link address", q.getFormat(r).link || "https://");
      if (url !== null) q.format("link", url || false, "user");
    })].concat(inserts)));
    // Quill's align is an attribute with no value for left, which is also how site.css reads it.
    var align = { left: b("⇤", "Align left", function () { if (!qfmt("align", false)) exec("justifyLeft"); }),
                  center: b("↔", "Centre", function () { if (!qfmt("align", "center")) exec("justifyCenter"); }),
                  right: b("⇥", "Align right", function () { if (!qfmt("align", "right")) exec("justifyRight"); }) };
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
      /* Read the caret WITHOUT focusing. q.getFormat() with no argument means
         getFormat(this.getSelection(true)) -- which focuses the editor and returns null when the
         canvas document does not have focus, and getFormat then reads .index off that null and
         throws. Painting a toolbar must never move the caret, and it must survive being asked while
         the caret is somewhere else entirely: selectionchange fires in the canvas whenever y-quill
         applies a peer's words, and at that moment the person typing may be in the title field, in
         another pane, or in another window. A Quill field with no caret in it is simply not live. */
      var q = qHere(), qat = q && q.getSelection();
      if (q && !qat) live = false;
      bar.classList.toggle("tb-off", !live);
      cmds.concat([style]).forEach(function (x) { x.disabled = !live; });
      // ...and undo/redo answer to the document, not the caret. This is the whole of their rule.
      if (undoBtn) undoBtn.disabled = !canUndo();
      if (redoBtn) redoBtn.disabled = !canRedo();
      proseOnly.forEach(function (x) { x.disabled = !live || !!q; });
      // Size belongs to body text. A heading's size IS its level, so offering both there invites an
      // H2 that looks like an H4 — the outline Google reads and the one a reader sees disagreeing.
      // It is NO LONGER off in a Quill field: Quill has a size format after all (withSize()), and
      // "a rem size is an inline style Quill has no format for" was true only of its default
      // whitelist. That clause disabled the control on every block Quill accepted, which is most
      // of them, and is what "I can't change the size of normal text" was.
      /* In a Quill field this test is inert and that is not an oversight: Quill mounts its own
         div.ql-editor inside [data-f], so caretBlock() -- which walks up to the child of
         savedField -- returns that DIV and never the h2 inside it. The Quill branch below applies
         the same rule from now.header instead. Two places, one policy; leave both. */
      size.disabled = !live || /^H[1-6]$/.test((caretBlock() || {}).tagName || "");
      if (HINT) HINT.innerHTML = live ? HINT_ON : "Click in the page to start editing.";
      if (!live) return;
      if (q) {                                    // Quill knows its own state; queryCommandState does not
        var now = q.getFormat(qat);
        bold.classList.toggle("on", !!now.bold);
        ital.classList.toggle("on", !!now.italic);
        und.classList.toggle("on", !!now.underline);
        strike.classList.toggle("on", !!now.strike);
        quote.classList.toggle("on", !!now.blockquote);
        Object.keys(align).forEach(function (k) {
          align[k].classList.toggle("on", k === (now.align || "left"));
        });
        style.value = now.header ? "h" + now.header : "p";
        // This branch returns, so the legacy size.value line below is never reached from here --
        // without this the control would show the last thing the caret met in a legacy block.
        size.value = now.size || "normal";
        size.disabled = !!now.header;        // the heading rule, from Quill rather than the DOM
        return;
      }
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
    var path = node.getAttribute("data-b"), r = listAt(path), q = quillOf(f), head = "", tail = "";
    if (q) {
      /* The DOM walk below cannot see this one: Quill's lines live inside div.ql-editor, not as
         children of the field, so `line` was never found and every "/" landed in the insert-after
         branch with the whole editor cloned into data.html. Both halves go through Quill instead --
         the tail because root.innerHTML would publish <span class="ql-ui"> and render a bulleted
         list numbered (see semantic()), and the head because yData() refuses to write `html` on a
         prose block and the binding's setContents() would put the "/" line straight back on the
         repaint. Deleting it here travels: through the binding into the Y.Text, and back into MODEL
         by mountQuill's own text-change mirror. */
      var sel = q.getSelection(), pair = sel && q.getLine(sel.index);
      var blot = (pair && pair[0]) || quillCtor().find(line);
      var at = blot ? q.getIndex(blot) : 0, end = at + (blot ? blot.length() : 0);
      if (end < q.getLength()) tail = semanticPart(q, end, q.getLength() - end);
      // "api", not "user": the text-change mirror writes MODEL before it looks at the source, and
      // the early return there keeps our own delete from re-opening the "/" menu.
      if (at) { q.deleteText(at, q.getLength() - at, "api"); head = semantic(q); }
    } else {
      var before = [], after = [], seen = false;
      Array.prototype.forEach.call(f.childNodes, function (n) {
        if (n === line) { seen = true; return; }
        (seen ? after : before).push(n);
      });
      var html = function (list) {
        var box = f.ownerDocument.createElement("div");
        list.forEach(function (n) { box.appendChild(n.cloneNode(true)); });
        return box.innerHTML;
      };
      head = line === f ? "" : html(before);
      tail = line === f ? "" : html(after);
    }
    var ins = [{ type: type, data: seedFor(type) }];
    // On the page the trailing paragraph is where you carry on writing, so it always goes in. In a
    // column it would just be an empty box under the thing you placed, so it goes in only when the
    // split actually left text behind. The caret then lands on the section itself.
    if (tail || !isNested(path)) ins.push({ type: "rich_text", data: { html: tail } });
    if (!r.arr) return;
    touched(rootIdOf(path));                     // the paragraph being split is changed either way
    // The caret goes into the section just placed, not into the paragraph under it: you asked for a
    // Hero, so the next thing you type is its heading. The trailing paragraph is still there to
    // carry on in. A column has no trailing paragraph and already did this; now the two agree.
    if (head) {
      r.arr[r.i].data.html = head;
      r.arr.splice.apply(r.arr, [r.i + 1, 0].concat(ins));
      focusOnLoad = siblingPath(path, r.i + 1);
    } else {                                     // the "/" line was the whole paragraph: replace it
      r.arr.splice.apply(r.arr, [r.i, 1].concat(ins));
      focusOnLoad = siblingPath(path, r.i);
    }
    markStep();                                 // mints an _id for each section just inserted
    ins.forEach(function (_, n) { touched(rootIdOf(siblingPath(path, r.i + (head ? 1 : 0) + n))); });
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
    function stop(e) { e.preventDefault(); e.stopPropagation(); }
    function key(e) {
      if (!slashBox) return;
      if (e.key === "Escape") { stop(e); closeSlash(); return; }
      if (e.key === "ArrowDown" || e.key === "ArrowUp") { stop(e); moveRow(list, e.key === "ArrowDown" ? 1 : -1); return; }
      // .on rather than shown[0], so the arrows above decide what Enter takes
      if (e.key === "Enter" && shown.length) { stop(e); list.querySelector(".iop-slash-row.on").click(); return; }
      setTimeout(function () {                    // let the keystroke land in the line first
        if (!slashBox) return;
        if ((line.textContent || "").charAt(0) !== "/") { closeSlash(); return; }
        draw();
      }, 0);
    }
    /* Capture, and stopPropagation on the four keys the menu owns. Quill's Keyboard listens on its
       own div.ql-editor, which is closer to the target than this document -- in the bubble phase
       handleEnter had already inserted a newline by the time preventDefault() ran here, so Enter
       split the paragraph instead of choosing from the menu. Everything else still falls through,
       which is what types the filter. Nothing else on THIS document wants those four: undoKey is the
       only other keydown listener here and it is ctrl/meta-only, and the two Escape handlers
       (panelKey, modal's esc) are on the PARENT document, which an event inside the iframe never
       reached in the first place. */
    d.addEventListener("keydown", key, true);
    slashOff = function () { d.removeEventListener("keydown", key, true); };
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
  /* VIEW is edit-or-preview and nothing else: twelve reads of it mean exactly that, and three
     are collaboration rather than rendering (peer markers, `edit:` on the wire, canWrite()).
     Which HALF of Preview is on screen -- the page, or the search and share cards -- is a
     sub-state, so all twelve keep their meaning and only the rendering below branches. */
  var VIEW = "edit", DEVICE = 1440, PVPART = "page";

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

  /* Preview repaints by replacing #main, not by reassigning srcdoc, and that is the difference
     between "live" and "unusable". fitPreview() makes the iframe its own scroll container, so
     navigating it -- which `srcdoc =` does, even to identical HTML -- throws the reader back to the
     top of the page. A colleague typing is ~6.6 updates a second, so the page was snatched away
     roughly that often and the words underneath were never the point.

     base.html wraps every page in <main id="main">, exactly as canvas.html does, so the same surgery
     the edit canvas has always used on one section (canvasBlock's node.replaceWith) works here on
     the whole body. The document survives, so the scroll offset is never lost rather than saved and
     restored, there is no blank-then-repaint flash, and wirePreview()'s listeners -- bound to the
     document, in the capture phase -- go on working. Measured in a real browser before being relied
     on: 600px stays 600px across two swaps and a listener still fires, where `srcdoc =` gives 0.

     srcdoc remains the path for the first paint and for entering Preview, which is where the head,
     the header, the nav and the footer are rebuilt. # ponytail: between those they are not, so a
     Settings or Menus change made in another tab shows on the next Edit/Preview switch. The page
     editor cannot change either, which is why this is a ceiling and not a bug. */
  /* pvUp is what says the iframe is ALREADY showing a previewed page, and it is not optional:
     canvas.html has a <main id="main"> of its own, so entering Preview -- when the frame still holds
     the edit canvas -- would otherwise graft the previewed body into the canvas document and leave
     the editor's chrome wrapped around it. First render loads, every render after that swaps. */
  var pvUp = false, pvLast = null;
  function renderPreview() {
    if (!FRAME || VIEW !== "preview") return;
    // Each half fetches only itself. Both are a full _form_body() + _preview_post() + build_meta()
    // on the server and the page one is 8-11 Supabase round trips, so doing both on every beat --
    // which is what this did -- was paying twice to show one thing.
    if (PVPART === "seo") {
      var c = document.getElementById("seo-card");
      if (c) askPreview("card", function (html) { if (c.innerHTML !== html) c.innerHTML = html; });
      return;
    }
    askPreview("", function (html) {
      var d = pvUp && cdoc(), was = d && d.getElementById("main"),
          now = was && new DOMParser().parseFromString(html, "text/html").getElementById("main");
      if (now) {
        // Nothing visible changed -- a peer editing a block that renders the same, or any of the
        // repaints that are not about the page body. Left alone this still rebuilt the document.
        if (now.innerHTML === pvLast) return;
        pvLast = now.innerHTML;
        return was.replaceWith(d.importNode(now, true));
      }
      FRAME.onload = function () {
        FRAME.onload = null;
        wirePreview();
        // Seeded from the same parser the swap branch compares against, never from the live
        // document: a browser reserialises what it parsed (a paragraph the markup left open, an
        // attribute quoted the other way) and the two spellings would make the next render look
        // like a change. Both sides of the === now come out of one serialiser.
        var m = new DOMParser().parseFromString(html, "text/html").getElementById("main");
        pvUp = true;
        pvLast = m ? m.innerHTML : null;
      };
      FRAME.srcdoc = html;
    });
  }

  // One beat for every preview repaint, local or remote. It was already here at 500ms but wired
  // only to the form's own input/change events and shut inside initBlocks(), so a peer's edit went
  // straight to renderPreview() -- one full page render, 8-11 Supabase round trips, per update.
  var pvPending = null;
  function previewSoon() {
    clearTimeout(pvPending);
    pvPending = setTimeout(function () { pvPending = null; renderPreview(); }, 500);
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
    // ...and not while the cards are the pane: #canvas-wrap is hidden, so clientWidth is 0 and the
    // scale would come out 0. pvParts() always runs BEFORE this, so by the time we measure on the
    // way back the wrap is visible again.
    if (VIEW !== "preview" || PVPART === "seo") {
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

  /* Which of Preview's two halves is showing. ALWAYS called before fitPreview(), never after:
     with #canvas-wrap hidden its clientWidth is 0, fitPreview() computes scale(0), and the frame
     comes back invisible. setView() already used that order for the toolbar; this keeps it. */
  function pvParts() {
    var seo = VIEW === "preview" && PVPART === "seo",
        wrap = document.getElementById("canvas-wrap"),
        card = document.getElementById("seo-card"),
        dev = document.getElementById("pv-device");
    if (wrap) wrap.hidden = seo;        // hidden, not emptied: cdoc() must keep answering, or the
    if (card) card.hidden = !seo;       // presence and canWrite() paths work against nothing
    if (dev) dev.hidden = VIEW !== "preview";
    Array.prototype.forEach.call(document.querySelectorAll("#pv-device button"), function (b) {
      b.classList.toggle("on", b.hasAttribute("data-pv") ? seo : (!seo && +b.getAttribute("data-w") === DEVICE));
    });
  }

  function setView(v) {
    VIEW = v;
    closeSlash();
    ["doc-toolbar", "pane-hint"].forEach(function (id) {
      var n = document.getElementById(id);
      if (n) n.hidden = v !== "edit";
    });
    pvParts();
    Array.prototype.forEach.call(document.querySelectorAll("#view-mode button"), function (b) {
      b.classList.toggle("on", b.getAttribute("data-view") === v);
    });
    fitPreview();
    viewChanged();     // previewing means this browser can no longer be the one that saves
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
        var was = PVPART;
        if (b.hasAttribute("data-pv")) PVPART = "seo";
        else { PVPART = "page"; DEVICE = +b.getAttribute("data-w"); }
        pvParts();          // unhide first, then measure -- see the comment on pvParts()
        fitPreview();
        // A width change only rescales what is already there; swapping halves needs the other one
        // fetched, and the page may have gone stale while the cards were up.
        if (PVPART !== was) renderPreview();
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
    initMetaRows(form);
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
    (SPEC.ui.scalars || []).forEach(function (k) { SCALARS[k] = 1; });
    initShared(SPEC.state);   // before initAutosave: its baseline has to carry the ids this mints

    focusOnLoad = "0";   // land the caret in the document, the way Docs does
    canvasFull();
    initAutosave(form);
    initCollab();   // canvasFull() is async, so the first paint comes through bars(), not from here

    // Advanced is the same data as JSON. The textarea is written when the panel opens (and on
    // submit); a hand edit is read back on blur, so whichever side was touched last wins.
    if (advanced) advanced.addEventListener("toggle", function () {
      if (advanced.open) AREA.value = JSON.stringify(MODEL, null, 2);
    });
    AREA.addEventListener("change", function () {
      var next;
      try { next = JSON.parse(AREA.value || "[]"); } catch (e) { next = null; }
      if (!Array.isArray(next)) { alert("That is not a valid list of blocks — the editor is unchanged."); return; }
      markStep();
      setBlocks(next);
    });
    // The other half of the shortcut: the panel, the toolbar, anywhere outside the canvas iframe.
    document.addEventListener("keydown", function (e) { if (!typingInAField(document)) undoKey(e); });
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
    ["input", "change"].forEach(function (ev) {      // while Preview is up, keep it a step behind your typing
      form.addEventListener(ev, function () {
        if (VIEW === "preview") previewSoon();      // the same beat a peer's edits are on
      });
    });
    // Still worth asking on a new post, which has no draft to fall back on, and on the rare window
    // between a keystroke and its autosave. A saved draft clears `dirty`, so this no longer fires
    // for work that is safely on the server.
    window.addEventListener("beforeunload", function (e) { if (dirty) { e.preventDefault(); e.returnValue = ""; } });
  }

  // ---- working at the same time ---------------------------------------------
  /* Every state this feature can be in says so once, in the console. It is off far more often than it
     is broken -- unset in tests, unset before the migration, unset in production until the tunnel
     routes /realtime/ -- and telling those apart from the page was impossible without it. */
  function say(msg) { if (window.console) console.info("[iopstor] editor presence: " + msg); }

  /* Who else has this page open, and roughly where they are. Presence only: nothing here changes a
     block, and nobody's typing reaches anybody else yet -- that is the shared-document work.

     The socket lives in THIS document, not in the canvas iframe (unlike Sortable, which has to bind
     to elements in there). Markers are painted into the iframe's DOM from out here, which is what
     admin.js already does everywhere else via cdoc().

     Off, silently, when the post has no id yet or when the library did not load -- both are the same
     single-player editor that existed before. There is no environment switch any more: the channel
     comes back through this app, so there is nothing to configure and nothing to leave unset. */
  function initCollab() {
    var rt = SPEC.rt || {};
    /* Silence was the wrong default here: "off" and "broken" looked identical from the page, and the
       first real setup spent a round trip finding out which it was. One console line, only when
       something is missing, naming the thing that is missing. */
    if (!rt.room) return say("this page has no id yet, so there is nobody to share it with until it is saved once.");
    if (!window.supabase) return say("the realtime library did not load (static/vendor/supabase.js).");

    say("joining " + rt.room + " as " + rt.me.name);
    var client = null, token = null;
    var chan = null, peers = {}, spot = {}, mine = { path: null, bid: null, field: null, sig: sig(), at: 0 };
    var roster = document.getElementById("ed-peers");

    /* MODEL's shape as a string. data-b is POSITIONAL and renumber() rewrites it on every insert,
       move and delete -- so the moment one editor adds a section, my "2" is their "3" and a marker
       drawn at their path would sit on the wrong block. Comparing shape lets a marker be drawn only
       while both sides are looking at the same document, and hidden (not moved) when they are not.
       ponytail: goes away entirely once the document itself is shared; then there is one shape. */
    function sig() {
      var out = [];
      (function walk(list) {
        (list || []).forEach(function (b) {
          out.push(b.type);
          if (b.type === "columns" && b.data && b.data.cols) b.data.cols.forEach(walk);
        });
      })(MODEL);
      return out.join(",");
    }

    function initials(name) {
      var bits = String(name || "?").trim().split(/\s+/);
      return ((bits[0] || "?")[0] + (bits.length > 1 ? bits[bits.length - 1][0] : "")).toUpperCase();
    }

    function drawRoster() {
      if (!roster) return;
      var list = Object.keys(peers).map(function (k) { return peers[k]; });
      roster.textContent = "";
      list.slice(0, 4).forEach(function (p) {
        var a = el("span", { "class": "ed-peer", title: p.name + " has this page open" });
        a.style.background = p.colour;
        a.textContent = initials(p.name);
        roster.appendChild(a);
      });
      if (list.length > 4) roster.appendChild(el("span", { "class": "ed-peer more", text: "+" + (list.length - 4) }));
    }

    /* Markers are attributes and a pseudo-element, never injected nodes: bindField()'s input handler
       copies a field's innerHTML straight into MODEL, so anything appended inside a [data-f] would be
       saved into the published page. The block edge is an inset box-shadow because hover and
       selection both use outline, and an inset shadow adds no layout box and fights neither. */
    paintPeers = function () {
      var d = cdoc();
      if (!d) return;
      Array.prototype.forEach.call(d.querySelectorAll("[data-peer],[data-peer-at]"), function (n) {
        n.removeAttribute("data-peer");
        n.removeAttribute("data-peer-at");
        n.style.removeProperty("--peer");
      });
      if (VIEW === "preview") return;   // a different document entirely; no [data-b] to mark
      Object.keys(peers).forEach(function (k) {
        var p = peers[k], w = spot[k];
        // With one shared document there is one shape, so a name resolves wherever the section has
        // moved to. sig is the fallback for a peer that has not sent a name yet.
        var at = w && w.bid ? pathOfId(w.bid) : (w && w.sig === mine.sig ? w.path : null);
        if (!w || !at) return;
        var block = d.querySelector('[data-b="' + at + '"]');
        if (!block) return;
        block.setAttribute("data-peer-at", "1");
        block.style.setProperty("--peer", p.colour);
        var f = w.field && block.querySelector('[data-f="' + w.field + '"]');
        if (f && f.closest("[data-b]") === block) {
          f.setAttribute("data-peer", p.name + " is typing here");
          f.style.setProperty("--peer", p.colour);
        }
      });
    };

    /* Two signals, two transports, and the split is the instance's limit rather than tidiness.
       presence.track() is rationed to roughly FIVE EVENTS A MINUTE per client here: one per caret
       move earned "Client presence rate limit exceeded" on the sixth and the server closed the
       channel, so the page went dead the moment anybody typed -- and CLOSED is not a retry trigger,
       so it stayed dead. Measured against this Supabase: six tracks three seconds apart were
       refused; 160 broadcasts at four a second were all delivered and the channel never moved. So
       presence carries WHO IS HERE and is sent once per join, and where the caret is goes over
       broadcast, which is the budget built for it. */
    var pending = null;
    /* `chan` exists the moment channel() is called, but it cannot carry anything until the socket is
       OPEN *and* the channel has joined -- and in that window chan.send() does NOT throw: supabase-js
       quietly falls back to POSTing /realtime/v1/api/broadcast over REST. Against Supabase directly
       that worked, which is why nothing ever noticed; through our proxy that path is
       /admin/realtime/v1/api/broadcast, which Flask 404s, and the symptom is the worst kind --
       messages "sent", roster empty, no error anywhere.

       Both halves are needed and the second is easy to miss: LongPoll reports OPEN as soon as its
       first poll returns, which is before the join reply arrives. This is the library's own canPush()
       -- `socket.isConnected() && isJoined()` -- written against the public channel state enum rather
       than reaching into channelAdapter for it. */
    function canSend() { return !!(chan && chan.state === "joined" && client && client.realtime.isConnected()); }

    function beam() {
      if (!canSend()) return;
      mine.sig = sig();
      chan.send({ type: "broadcast", event: "where",
                  payload: { id: rt.me.id, path: mine.path, bid: mine.bid, field: mine.field,
                             sig: mine.sig, edit: VIEW !== "preview",
                             stamp: (stampBox() || {}).value || "", panel: panelSig() } });
    }
    function nudge() {                       // selectionchange fires on every caret move
      clearTimeout(pending);
      pending = setTimeout(beam, 250);
    }

    /* ---- the document on the wire -------------------------------------------------------------
       Base64 in a broadcast payload on the channel #65 already opened. No new server: y-websocket
       and y-webrtc both want one, and gunicorn runs sync workers that cannot hold a socket. */
    var outbox = [], flushing = null;
    // Nothing is spliced until the send is actually going to happen: an un-OPEN socket leaves the
    // deltas in the outbox to go out merged with the next batch, rather than dropping them into the
    // REST fallback described above. Called again on SUBSCRIBED so a typist who stopped mid-connect
    // does not have their last batch wait for the next keystroke.
    function flushOutbox() {
      flushing = null;
      if (!canSend() || !outbox.length) return;
      chan.send({ type: "broadcast", event: "doc",
                  payload: { id: rt.me.id, u: bytesB64(Y.mergeUpdates(outbox.splice(0))) } });
    }
    shareOut = function (delta, origin) {
      if (!chan || origin === "remote") return;   // what a peer just sent us is not ours to send back
      outbox.push(delta);
      if (flushing) return;
      // doc.on("update") fires once per transaction, and a fast typist is eight to ten a second
      // against a channel budget counted in events per second. One merged delta per tick instead.
      flushing = setTimeout(flushOutbox, 150);
    };

    function hearDoc(msg) {
      var m = msg && msg.payload;
      if (!m || !m.u || m.id === rt.me.id || !YDOC) return;
      try { Y.applyUpdate(YDOC, b64bytes(m.u), "remote"); }
      catch (e) { return say("could not apply an update from " + m.id + " -- " + e.message); }
      dedupe();
      shareWaiting();
    }

    /* A newcomer is caught up by a PEER, not by the server. The stored state is behind by the save
       debounce plus whatever is in flight, so a newcomer who loads it and then receives the next
       delta has Yjs hold that delta as pending -- its base is missing -- and those words never
       appear at all. Proved rather than assumed: applying a bare delta to a fresh document yields
       an empty document, silently. applyUpdate is idempotent, so a redundant one costs nothing. */
    function beamState(fresh) {
      // Anyone holding a document answers, not only the writer: the writer is elected by lowest id
      // and that can be the NEWCOMER, who has nothing to send. applyUpdate is idempotent, so two
      // peers answering costs one extra message and nothing else.
      if (!canSend() || !YDOC || !YB.length) return;
      // Realtime reports our OWN arrival as a join. Without this the writer encodes and broadcasts
      // the whole document to an empty room every time it opens the page.
      if (!fresh.some(function (x) { return x && x.id && x.id !== rt.me.id; })) return;
      chan.send({ type: "broadcast", event: "doc",
                  payload: { id: rt.me.id, u: bytesB64(Y.encodeStateAsUpdate(YDOC)) } });
    }

    /* Everybody holds the same document, so everybody would otherwise save it. The lowest presence
       id writes, and the election re-runs whenever the roster moves.

       Preview disqualifies you, and that is not tidiness. Preview replaces the canvas, so there are
       no Quill instances -- and a rich paragraph's HTML is derived from a Quill, not from the shared
       text (a Y.Text holds a delta; its toJSON is the plain words). A previewing writer would keep
       saving a draft that is quietly behind whoever is typing. It rides the `where` broadcast rather
       than presence because presence is rationed to about five events a minute on this instance and
       a preview toggle is a click. */
    canWrite = function () {
      if (!chan || VIEW === "preview") return false;
      var low = rt.me.id;
      Object.keys(peers).forEach(function (id) {
        if (spot[id] && spot[id].edit === false) return;
        if (id < low) low = id;
      });
      return low === rt.me.id;
    };

    viewChanged = function () { beam(); sharedChanged(); };

    /* After somebody publishes, every other tab still carries the version stamp its form was drawn
       with, so the next Publish trips #64's guard -- over page content that is now IDENTICAL, because
       there is only one document. So peers tell each other their stamp, and a later one is adopted.

       Only when the rest of the form matches, and that condition is the whole point. The panel on the
       right -- title, web address, status, summary, SEO -- is deliberately NOT shared, so #64's guard
       is still the only thing standing between two people who both retitled the page. Adopting a
       stamp over a panel that differs would turn a refusal into a silent overwrite. Matching panels
       mean the only thing that moved was the shared document, and that is exactly the false alarm. */
    function stampBox() { return document.querySelector('#post-form input[name="updated_at"]'); }
    // Cached: this is read on every caret move of every peer, and walking a form with a long SEO
    // panel each time is real work for an answer that only changes when somebody edits the panel.
    var panelWas = null;
    function panelSig() {
      var form = document.getElementById("post-form");
      if (!form || !window.FormData) return null;
      if (panelWas !== null) return panelWas;
      var out = [];
      new FormData(form).forEach(function (v, k) {
        if (k !== "blocks" && k !== "csrf" && k !== "updated_at") out.push(k + "\u0000" + v);
      });
      return (panelWas = out.join("\u0001"));
    }
    var pform = document.getElementById("post-form");
    if (pform) ["input", "change"].forEach(function (ev) {
      pform.addEventListener(ev, function () { panelWas = null; });
    });

    function hearStamp(w) {
      var box = stampBox();
      if (!YDOC || !box || !w.stamp || w.panel == null) return;
      if (w.stamp <= box.value || w.panel !== panelSig()) return;
      box.value = w.stamp;   // said once per stamp, not once per caret move of every peer
      say("adopted a newer version stamp from " + w.id + ": the page content is the same document.");
    }

    sendWhere = function (f) {
      var block = f && f.closest && f.closest("[data-b]");
      mine.path = block ? block.getAttribute("data-b") : null;
      // The NAME of the section, not only its position: data-b is rewritten by renumber() on every
      // insert, so a marker drawn from a path that has since moved sits on the wrong section.
      mine.bid = block ? idOf(blockAt(mine.path)) : null;
      mine.field = f ? f.getAttribute("data-f") : null;
      mine.at = Date.now();
      nudge();
    };

    /* Nothing in the editor says "I stopped editing": there is no blur handler on a field, and
       clicking the title or the settings panel leaves the last caret position standing. So it ages
       out on its own rather than lingering on a section nobody is in. */
    setInterval(function () {
      if (mine.path && Date.now() - mine.at > 60000) { mine.path = mine.field = null; beam(); }
    }, 20000);

    function readRoster() {
      var state = chan.presenceState(), next = {};
      Object.keys(state).forEach(function (key) {
        var m = state[key][0];
        if (m && m.id && m.id !== rt.me.id) next[m.id] = m;
      });
      peers = next;
      Object.keys(spot).forEach(function (id) { if (!peers[id]) delete spot[id]; });
      drawRoster();
      paintPeers();
      // Nobody else is here, so seeding cannot collide with anybody else's document. With a peer
      // present we wait instead: their state arrives on our join.
      if (!Object.keys(peers).length) seedDoc();
      shareWaiting();          // the roster decides who creates a shared text, so it just changed
      // The writer may have just left, or just arrived. Whoever it is now owes the server a save.
      sharedChanged();
    }

    /* Positions are kept apart from the roster on purpose: a broadcast that arrives before the
       presence sync would otherwise be dropped, and a latecomer has heard nobody's last position at
       all -- which is why every peer re-sends theirs whenever somebody joins. */
    function hearWhere(msg) {
      var w = msg && msg.payload;
      if (!w || !w.id || w.id === rt.me.id) return;
      spot[w.id] = w;
      hearStamp(w);
      paintPeers();
    }

    /* The client is built around a token GETTER, not a token, and that is the whole reason presence
       works at all. supabase-js re-authorises the socket by itself -- on connect, on reconnect and
       on every heartbeat -- and when it does it ignores whatever realtime.setAuth() was handed and
       calls its own accessToken callback instead. That callback defaults to the GoTrue session, and
       this client has none: the token comes from /admin/rt-token, not from a sign-in in the page. So
       it fell back to the ANON key, pushed that to the already-joined channel, Realtime re-ran the
       policy as `anon` against a policy written `to authenticated`, and closed the channel a tenth
       of a second after it opened. The console read "channel SUBSCRIBED" then "channel CLOSED", the
       roster stayed empty, and every layer underneath tested green. Proved by A/B against the live
       instance: with the getter, two peers see each other and hold for a minute; without it, the
       first peer is gone before the second one arrives. setAuth() stays so the first join does not
       wait on the callback's promise, and the client is built here rather than above because a null
       token makes supabase-js fall back to the anon key again. */
    /* The channel comes back through our own server, not from Supabase directly: Supabase is LAN-only
       in production and Flask is the only exposed service, exactly as it is for every picture. That
       means longpoll rather than a websocket, because a gthread worker can proxy request/response and
       cannot hold a socket.

       Nothing here is hand-written protocol: supabase-js ships a complete LongPoll transport, it is
       simply not reachable through createClient's options (longPollFallbackMs is dropped by
       _initializeOptions), so it is fetched off the socket and handed back in as `transport`. Three
       things that are load-bearing and were each verified against the vendored 2.116.0 bundle before
       being relied on, because this is minified internals and a vendor bump could move any of them:
         - the class lives at realtime.socketAdapter.SOCKET.getLongPollTransport(), one level deeper
           than it looks; socketAdapter itself does not have it
         - passing it as `transport` makes the socket choose its JSON encoder by itself -- the default
           vsn=2.0.0 binary serializer cannot ride inside a JSON longpoll envelope
         - the base URL is turned into the poll URL by the library: `<origin>/admin` becomes
           /admin/realtime/v1/websocket and LongPoll rewrites that to /admin/realtime/v1/longpoll
       If a future bundle moves getLongPollTransport, the fallback is vsn:"1.0.0" plus
       replaceTransport(), which binds the JSON serializer explicitly and reaches the same place.

       location.origin, not a URL from the server: it is the only value certain to match the origin
       the session cookie was set on. Against a SITE_URL of localhost, a browser sitting on 127.0.0.1
       would send every poll cross-origin, with no cookie, and be refused. */
    function join(t) {
      token = t;
      if (!client) {
        var base = location.origin + "/admin";
        var probe = window.supabase.createClient(base, rt.key);
        var LongPoll = probe.realtime.socketAdapter.socket.getLongPollTransport();
        client = window.supabase.createClient(base, rt.key, {
          accessToken: function () { return Promise.resolve(token); },
          // csrf rides the query string on every poll and every send, because ui_required's usual
          // form field cannot reach a JSON-bodied Phoenix POST. eventsPerSecond travels the same way.
          realtime: { transport: LongPoll, params: { eventsPerSecond: 5, csrf: csrf() } }
        });
      }
      client.realtime.setAuth(token);
      chan = client.channel(rt.room, { config: { private: true, presence: { key: rt.me.id } } });
      chan.on("presence", { event: "sync" }, readRoster)
          .on("presence", { event: "join" }, function (p) {
            readRoster();
            beam();                    // a latecomer has heard nobody's position, or whether they can write
            beamState((p && p.newPresences) || []);
          })
          .on("presence", { event: "leave" }, readRoster)
          .on("broadcast", { event: "where" }, hearWhere)
          .on("broadcast", { event: "doc" }, hearDoc)
          .subscribe(function (status, err) {
            say("channel " + status + (err ? " -- " + err.message : ""));
            // The one presence event of the session: who I am. Everything else rides broadcast.
            if (status === "SUBSCRIBED") {
              tries = 0;
              shareWaiting();   // canWrite() was false until this moment: there was no channel
              flushOutbox();    // and canSend() was false, so anything typed while connecting waited
              return chan.track({ id: rt.me.id, name: rt.me.name, colour: rt.me.colour });
            }
            // CHANNEL_ERROR is what an expired JWT looks like from here. _session_token() only
            // refreshes AFTER expiry, so reacting to the error is the only schedule that can be
            // honoured -- asking early would hand back the same dying token.
            if (status === "CHANNEL_ERROR" || status === "TIMED_OUT") retry();
            // A CLOSED we did not ask for is the server hanging up -- a restarted realtime
            // container, a changed policy, a limit tripped -- and it used to be the end of
            // collaboration for the life of the tab. `closing` is what separates that from the
            // close removeChannel() makes on the way to a retry, which must not re-arm the retry.
            if (status === "CLOSED" && !closing) retry();
          });
    }

    /* Backs off and then gives up, and this shape is load-bearing rather than tidy: the first version
       retried a flat two seconds forever and, with the realtime service refusing the socket, every
       open editor quietly fetched /admin/rt-token every two seconds for as long as the tab was open.
       An UNASKED-FOR close does reconnect now, but the close this function makes itself does not --
       that distinction is the `closing` flag, and getting it wrong is what made the first version
       re-arm its own retry and never terminate even once the socket was fine. */
    var tries = 0, retrying = false, closing = false;
    function retry() {
      if (retrying) return;
      if (tries >= 5) return say("giving up after " + tries + " attempts; reload the page to try again.");
      retrying = true;
      var wait = Math.min(2000 * Math.pow(2, tries), 30000);
      tries += 1;
      say("retrying in " + Math.round(wait / 1000) + "s (attempt " + tries + " of 5)");
      setTimeout(function () {
        fetch("/admin/rt-token", { credentials: "same-origin" }).then(function (r) {
          // ui_required redirects a finished session to the login page and fetch follows it, so a
          // dead session arrives as 200 HTML, never 401. Stop rather than hammer it forever.
          if (r.redirected) throw new Error("signed out");
          return r.json();
        }).then(function (j) {
          retrying = false;
          if (!j.token) return say("no token: the session has ended, so sign in again.");
          if (client && chan) { closing = true; client.removeChannel(chan); chan = null; closing = false; }
          join(j.token);
        }).catch(function () { retrying = false; tries = 5; say("cannot reach the server; presence is off until you reload."); });
      }, wait);
    }

    fetch("/admin/rt-token", { credentials: "same-origin" })
      .then(function (r) { return r.redirected ? null : r.json(); })
      .then(function (j) {
        if (j && j.token) return join(j.token);
        say(j ? "the server sent no token, so presence is off." : "the session has ended; sign in again.");
      })
      .catch(function (e) { say("could not ask the server for a token -- " + e.message); });

    // Realtime expires presence server-side when the socket drops, so this only makes it prompt.
    window.addEventListener("beforeunload", function () { if (chan) chan.untrack(); });
  }

  // ---- the warranty form ----------------------------------------------------
  /* Validation messages belong on the field they are about, in the browser's own bubble, not in a
     banner at the top of a page the form is scrolled below. Same setCustomValidity idiom initSlug()
     uses for a taken web address: the browser blocks Save and says why, at the input.
     The dates are checked here so that mistake never costs a round trip; a serial already on file
     cannot be (it would mean shipping every serial to the page), so the server sends its refusal
     back in data-refused and this pops it. */
  /* --- the menus screen: drag to reorder, and a button to add a row -------------------------- */
  /* The level is a <select> in the markup, not a checkbox, so the three getlist()s on the server
     stay the same length whatever is ticked. Everything here is enhancement: without JS you can
     still edit and re-level the rows you have, just not reorder or add one. */
  function initMenus() {
    var form = document.getElementById("menus-form");
    if (!form) return;
    var rows = document.getElementById("menu-rows");
    if (window.Sortable) Sortable.create(rows, {draggable: ".menu-row", handle: ".grip", ghostClass: "iop-ghost"});
    rows.addEventListener("click", function (e) {
      var del = e.target.closest(".row-del");
      if (del) del.closest(".menu-row").remove();
    });
    rows.addEventListener("change", function (e) {
      if (e.target.name === "level") e.target.closest(".menu-row").classList.toggle("is-child", e.target.value === "1");
    });
    var add = document.getElementById("menu-add");
    if (add) add.addEventListener("click", function () {
      var row = rows.firstElementChild;
      var fresh;
      if (row) {
        fresh = row.cloneNode(true);
        fresh.classList.remove("is-child");
        fresh.querySelectorAll("input").forEach(function (i) { i.value = ""; });
        fresh.querySelector("select").value = "0";
      } else {
        fresh = el("div", {class: "menu-row"}, [
          el("span", {class: "grip", text: "\u2807"}),
          el("input", {name: "label", placeholder: "Label"}),
          el("input", {name: "url", placeholder: "/where-it-goes", class: "mono"}),
          el("select", {name: "level"}, [el("option", {value: "0", text: "Top level"}),
                                         el("option", {value: "1", text: "Under the one above"})]),
          el("button", {type: "button", class: "secondary row-del", text: "\u2715"})]);
      }
      rows.appendChild(fresh);
      fresh.querySelector("input").focus();
    });
  }

  function initWarranty() {
    var form = document.getElementById("warranty-form");
    if (!form) return;
    var buy = form.elements.purchase_date, exp = form.elements.expiry_date,
        field = form.elements[form.getAttribute("data-refused-field")],
        refused = form.getAttribute("data-refused");

    function checkDates() {
      // no purchase date means nothing to compare against, so any expiry is allowed -- the same arm
      // the warranties_expiry_after_purchase constraint has. ISO dates compare as dates.
      exp.setCustomValidity(buy.value && exp.value && exp.value < buy.value
        ? "Warranty expiry cannot be before the purchase date (" + buy.value + ")." : "");
    }
    buy.addEventListener("input", checkDates);
    exp.addEventListener("input", checkDates);
    checkDates();   // a refused save comes back with both dates still in the fields

    if (refused && field) {
      field.setCustomValidity(refused);
      // one edit clears it -- only the server can tell whether it is fixed. checkDates() runs after,
      // so clearing a stale date refusal cannot also clear a date pair that is still wrong.
      field.addEventListener("input", function () { field.setCustomValidity(""); checkDates(); });
      if (field.reportValidity) field.reportValidity();   // show it now, focused and scrolled to
    }
  }

  /* Media grid selection. The screen works without this: every tile carries a real checkbox, and a
     plain click is a link to ?pick=, which the server answers with that file's panel open and its box
     already ticked -- so one click selects one file with JavaScript off. What this adds is the two
     modifier clicks a list of files is expected to have, anywhere on the tile rather than only on the
     small box: ctrl/cmd to add one to the selection, shift to take the whole run since the last one.
     Both have to stop the link, or the page navigates away from the selection just made. */
  function initMediaBulk() {
    var grid = document.querySelector(".tiles-m");
    if (!grid) return;
    var boxes = Array.prototype.slice.call(grid.querySelectorAll(".m-pick")), last = -1;
    boxes.forEach(function (b, i) { if (b.checked) last = i; });   // the ?pick=ed tile is the anchor

    grid.addEventListener("click", function (e) {
      var tile = e.target.closest && e.target.closest(".m-tile");
      if (!tile) return;
      var box = tile.querySelector(".m-pick"), at = boxes.indexOf(box), onBox = e.target === box;
      if (!onBox && !e.target.closest(".m-open")) return;   // the tile's own border: not a click on anything

      if (e.shiftKey && last > -1 && last !== at) {
        if (!onBox) e.preventDefault();
        for (var i = Math.min(last, at); i <= Math.max(last, at); i++) boxes[i].checked = true;
      } else if (e.ctrlKey || e.metaKey || e.shiftKey) {
        if (!onBox) { e.preventDefault(); box.checked = !box.checked; }
        last = at;
      } else {
        last = at;   // a plain click: the link navigates, or the box has toggled itself. Neither is ours
      }
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initSlug();
    initTerms();
    initWarranty();
    initMenus();
    initBlocks();
    initMediaBulk();
  });
})();
