/* The public site's only script, and it exists for exactly one thing: the sliding row of
   testimonials. Everything else on this site is server-rendered HTML and CSS, and stays that way.

   The row already works without this file. `.pl-rail .cards` is a native scroll container with
   scroll-snap (site.css), so the wheel, a trackpad and a finger on a phone all move it on a page
   served with scripts blocked. What this adds is the drift, the arrows, the dots and click-drag --
   which is why post_list.html renders .rail-nav with `hidden` and this is what takes it off. No
   script, no dead buttons.

   ponytail: no module, no build, no framework. One IIFE, no globals. */
(function () {
  var STEP_MS = 5000;   // how long a card sits before the row drifts on
  var HOLD_MS = 10000;  // how long a click or a drag holds the drift off afterwards
  var still = matchMedia('(prefers-reduced-motion: reduce)');

  document.querySelectorAll('.pl-rail').forEach(function (sec) {
    var rail = sec.querySelector('.cards');
    var nav = sec.querySelector('.rail-nav');
    var dots = sec.querySelector('.rail-dots');
    var prev = sec.querySelector('[data-rail="-1"]');
    var next = sec.querySelector('[data-rail="1"]');
    if (!rail || !nav || !rail.firstElementChild) return;

    // Measured, never assumed: the card width comes from CSS (min(340px,82vw)) and the gap from the
    // flex gap, so both change with the viewport and neither is a number this file may hard-code.
    function step() {
      var card = rail.firstElementChild;
      return card.getBoundingClientRect().width + parseFloat(getComputedStyle(rail).columnGap || 0);
    }
    function stops() {
      // how many start positions the row really has -- NOT one per card. Once the last card is
      // flush with the right edge there is nothing further to scroll to, so a row of eight cards
      // showing three at a time has six stops, not eight.
      return Math.max(0, Math.ceil((rail.scrollWidth - rail.clientWidth) / step() - 0.01)) + 1;
    }
    function at() { return Math.min(Math.round(rail.scrollLeft / step()), stops() - 1); }

    function buildDots() {
      var n = stops(), now = at();
      // Nothing to drive: two testimonials fit the row at 1440, and a dead arrow either side of a
      // single dot says "this is broken" rather than "this is all of them". Re-checked on resize,
      // because the same two cards DO overflow a phone.
      nav.hidden = n <= 1;
      if (n <= 1) return;
      if (dots.children.length !== n) {
        dots.textContent = '';
        for (var i = 0; i < n; i++) {
          var b = document.createElement('button');
          b.type = 'button';
          b.className = 'rail-dot';
          b.setAttribute('aria-label', 'Testimonials ' + (i + 1) + ' of ' + n);
          dots.appendChild(b);
        }
      }
      mark(now);
    }
    function mark(i) {
      for (var d = 0; d < dots.children.length; d++) {
        dots.children[d].setAttribute('aria-current', d === i ? 'true' : 'false');
      }
      if (prev) prev.disabled = i <= 0;
      if (next) next.disabled = i >= stops() - 1;
    }
    function go(i, smooth) {
      rail.scrollTo({ left: i * step(), behavior: smooth && !still.matches ? 'smooth' : 'auto' });
    }

    // --- the drift ------------------------------------------------------------------------------
    // Paused while the pointer is over the row or the keyboard is inside it, and held off for a
    // while after anybody moves it by hand: drifting out from under somebody mid-read is the thing
    // that makes carousels hated.
    var held = 0, hover = false;
    function hold() { held = Date.now() + HOLD_MS; }
    var timer = still.matches ? 0 : setInterval(function () {
      if (hover || Date.now() < held || document.hidden) return;
      var i = at();
      go(i >= stops() - 1 ? 0 : i + 1, true);
    }, STEP_MS);
    still.addEventListener('change', function (e) {
      if (e.matches && timer) { clearInterval(timer); timer = 0; }
    });

    sec.addEventListener('pointerenter', function () { hover = true; });
    sec.addEventListener('pointerleave', function () { hover = false; });
    sec.addEventListener('focusin', function () { hover = true; });
    sec.addEventListener('focusout', function () { hover = false; });

    nav.addEventListener('click', function (e) {
      var arrow = e.target.closest('.rail-arrow'), dot = e.target.closest('.rail-dot');
      if (arrow) { hold(); go(at() + Number(arrow.dataset.rail), true); }
      else if (dot) { hold(); go([].indexOf.call(dots.children, dot), true); }
    });

    // --- click-drag -----------------------------------------------------------------------------
    // Snap has to come off for the duration or the row fights the hand on every pixel, and goes
    // back on at the end so releasing settles onto a card.
    var from = 0, left = 0, dragging = false;
    rail.addEventListener('pointerdown', function (e) {
      if (e.pointerType === 'touch') return;   // touch scrolling is the browser's job, and better
      dragging = true; from = e.clientX; left = rail.scrollLeft;
      rail.style.scrollSnapType = 'none';
      // only while the hand is down: a testimonial is meant to be selectable and copyable, but a
      // drag that paints the quote blue on the way past looks like something went wrong.
      rail.style.userSelect = 'none';
      rail.setPointerCapture(e.pointerId);
    });
    rail.addEventListener('pointermove', function (e) {
      if (dragging) { rail.scrollLeft = left - (e.clientX - from); }
    });
    ['pointerup', 'pointercancel'].forEach(function (ev) {
      rail.addEventListener(ev, function () {
        if (!dragging) return;
        dragging = false; hold();
        rail.style.scrollSnapType = '';
        rail.style.userSelect = '';
      });
    });

    // --- keeping the dots honest ------------------------------------------------------------
    var queued = false;
    rail.addEventListener('scroll', function () {
      if (queued) return;
      queued = true;
      requestAnimationFrame(function () { queued = false; mark(at()); });
    });
    addEventListener('resize', buildDots);
    buildDots();
  });
})();
