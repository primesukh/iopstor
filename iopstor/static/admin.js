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
  // ponytail: refresh hooks are appended, never pruned — detached ones bail out on isConnected.
  // Grows with every redraw; give widgets a real teardown only if a page ever holds hundreds of blocks.
  var pickers = [];          // so a new upload appears in every picker at once

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
        pickers.forEach(function (fn) { fn(); });
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
      if (sel.dataset.live && !sel.isConnected) return;  // row was redrawn; this widget is detached
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
    body.addEventListener("paste", function (e) {   // strip Word/Docs markup
      e.preventDefault();
      document.execCommand("insertText", false, (e.clipboardData || window.clipboardData).getData("text/plain"));
    });
    return el("div", { "class": "rt" }, [bar, body, raw]);
  }

  // ---- block editor ---------------------------------------------------------
  var SPEC = null;  // {blocks: {type: [required, optional]}, ui: {widgets, items, labels, kinds}, media, post_types}

  function widgetFor(type, field) {
    return SPEC.ui.widgets[type + "." + field] || SPEC.ui.widgets[field] || "text";
  }
  var BLOCK_NAMES = { cta: "CTA", faq: "FAQ", embed_html: "Embed HTML", rich_text: "Rich text" };
  function nameFor(type) {
    return BLOCK_NAMES[type] || (type.charAt(0).toUpperCase() + type.slice(1)).replace(/_/g, " ");
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

  function initBlocks() {
    var mount = document.getElementById("blocks-editor"),
        data = document.getElementById("editor-data"),
        area = document.querySelector('textarea[name="blocks"]'),
        form = document.getElementById("post-form");
    if (!mount || !data || !area || !form) return;
    SPEC = JSON.parse(data.textContent);
    MEDIA = SPEC.media || [];
    initMediaSelects();

    var blocks;
    try { blocks = JSON.parse(area.value || "[]"); } catch (e) { blocks = null; }
    if (!Array.isArray(blocks)) {   // unparseable JSON from a rejected save: leave the textarea in charge
      mount.appendChild(el("p", { "class": "error", text: "The saved content is not valid JSON — fix it under “Advanced — edit as JSON” below." }));
      document.getElementById("blocks-json").open = true;
      return;
    }

    var list = el("div");
    function redraw() {
      list.innerHTML = "";
      if (!blocks.length) list.appendChild(el("p", { "class": "muted", text: "No sections yet — add one below." }));
      blocks.forEach(function (b, i) { list.appendChild(blockCard(b, i, blocks, redraw)); });
    }

    var adder = el("select");
    adder.appendChild(el("option", { value: "", text: "+ Add a section…" }));
    Object.keys(SPEC.blocks).forEach(function (t) { adder.appendChild(el("option", { value: t, text: nameFor(t) })); });
    adder.addEventListener("change", function () {
      if (!adder.value) return;
      blocks.push({ type: adder.value, data: {} });
      adder.value = "";
      redraw();
    });

    redraw();
    mount.appendChild(list);
    mount.appendChild(el("div", { "class": "toolbar" }, [adder]));

    // The Advanced panel edits the same data. Hand-edited JSON is read back into the editor on
    // blur, so whichever side was touched last wins instead of being silently overwritten on save.
    area.addEventListener("change", function () {
      var parsed;
      try { parsed = JSON.parse(area.value || "[]"); } catch (e) { parsed = null; }
      if (!Array.isArray(parsed)) { alert("That is not a valid list of blocks — the editor above is unchanged."); return; }
      blocks = parsed;
      redraw();
    });
    form.addEventListener("submit", function () { area.value = JSON.stringify(blocks, null, 2); });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initSlug();
    initBlocks();
  });
})();
