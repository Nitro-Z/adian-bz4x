// v2 only: poster style for the result cards (step 3).
// - Bigger titles with a green marker, a big outlined card number (01, 02 ...) in the corner.
// - Each time a card becomes the active one: its blocks rise in one by one, bars grow, and the key numbers
//   (score, savings, side big numbers) count up from 0. Only transform/opacity animations, so the
//   layout and fitCards() zoom are not affected. Waits until the verdict reveal (v2-reveal.js) has closed.
// Kept in its own file so advisor.html can be re-synced from the live site and only needs this <script>.
(function () {
  var reduce = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
  var css = document.createElement('style');
  css.textContent = [
    // card numbers (only visible cards are counted)
    '#view3 .result-grid{counter-reset:rc}',
    '#view3 .result-grid>.result-card:not(.hidden){counter-increment:rc}',
    '.carousel>.result-card::after{content:counter(rc,decimal-leading-zero);position:absolute;top:6px;right:18px;z-index:0;pointer-events:none;',
    ' font-family:"Archivo Black",sans-serif;font-size:4.6rem;line-height:1;color:transparent;-webkit-text-stroke:2px #141B2D;opacity:.13}',
    '.carousel>.result-card.persona-card::after{-webkit-text-stroke-color:#27F550;opacity:.3}',
    // titles: bigger, green marker under the words
    // green bar UNDER the words (not across them)
    '.carousel .section-title{display:table;font-size:1.9rem;line-height:1.25;letter-spacing:0;margin-bottom:1rem;padding-bottom:.18em;',
    ' background:linear-gradient(#27F550,#27F550) left bottom/100% .16em no-repeat}',
    '.carousel .persona-card .section-title{background-image:linear-gradient(rgba(39,245,80,.6),rgba(39,245,80,.6))}',
    '.carousel .verdict-title{font-size:2.9rem;line-height:1.1;letter-spacing:0}',
    '.carousel .score-head b{font-family:"Archivo Black",sans-serif;font-weight:400;font-size:3rem}',
    '.carousel #savingsLine b{font-family:"Archivo Black",sans-serif;font-weight:400;font-size:1.35em}',
    '.carousel .side .big-num{font-family:"Archivo Black",sans-serif;font-weight:400;font-size:2.3rem}',
    '.carousel .side h4{font-size:1.05rem;letter-spacing:.02em}',
    // entrance
    '@keyframes v2up{from{opacity:0;transform:translateY(26px)}to{opacity:1;transform:none}}',
    '@keyframes v2grow{from{transform:scaleX(0)}to{transform:scaleX(1)}}',
    '.v2-enter>.card-body>*,.v2-enter>.side>*{animation:v2up .6s cubic-bezier(.2,.8,.2,1) both}',
    '.v2-enter .sr-bar i,.v2-enter .bar-container>div{transform-origin:left;animation:v2grow .9s cubic-bezier(.2,.8,.2,1) .35s both}',
    '@media (prefers-reduced-motion:reduce){.v2-enter *{animation:none!important}}'
  ].join('\n');
  document.head.appendChild(css);
  if (!document.querySelector('link[href*="Archivo+Black"]')) {
    var f = document.createElement('link'); f.rel = 'stylesheet';
    f.href = 'https://fonts.googleapis.com/css2?family=Archivo+Black&display=swap'; document.head.appendChild(f);
  }

  // count a number inside an element up from 0, keeping its prefix/suffix and format ("NT$ 1,260", "78", "2.4")
  function countUp(el) {
    if (reduce || el.dataset.v2counting) return;
    var final = el.textContent, m = final.match(/\d[\d,]*(\.\d+)?/);
    if (!m) return;
    var to = parseFloat(m[0].replace(/,/g, '')), dec = m[1] ? m[1].length - 1 : 0, comma = m[0].indexOf(',') >= 0;
    if (!(to > 0)) return;
    var pre = final.slice(0, m.index), post = final.slice(m.index + m[0].length), t0 = performance.now();
    el.dataset.v2counting = '1';
    (function step(now) {
      var p = Math.min(1, (now - t0) / 1000), v = to * (1 - Math.pow(1 - p, 3));
      var s = dec ? v.toFixed(dec) : String(Math.round(v));
      if (comma) s = Number(s).toLocaleString('en-US', { minimumFractionDigits: dec, maximumFractionDigits: dec });
      el.textContent = p < 1 ? pre + s + post : final;
      if (p < 1) requestAnimationFrame(step); else delete el.dataset.v2counting;
    })(t0);
  }

  function enter(card) {
    if (!card) return;
    card.classList.remove('v2-enter'); void card.offsetWidth; card.classList.add('v2-enter');
    var kids = [].slice.call(card.querySelectorAll(':scope > .card-body > *, :scope > .side > *'));
    kids.forEach(function (k, i) { k.style.animationDelay = (0.06 + i * 0.07).toFixed(2) + 's'; });
    card.querySelectorAll('.score-head b, .sr-val, #savingsLine b, .side .big-num').forEach(countUp);
    clearTimeout(card._v2t);
    card._v2t = setTimeout(function () { card.classList.remove('v2-enter'); kids.forEach(function (k) { k.style.animationDelay = ''; }); }, 2200);
  }

  // watch which card is active (layoutCarousel() sets data-pos="active")
  var last = null;
  function check() {
    var a = document.querySelector('#view3 .result-grid > .result-card[data-pos="active"]');
    if (!a || a === last || document.getElementById('view3').classList.contains('hidden')) return;
    if (document.getElementById('v2reveal')) { setTimeout(check, 200); return; }   // after the verdict reveal
    last = a; enter(a);
  }
  function start() {
    var grid = document.querySelector('#view3 .result-grid');
    if (!grid) return;
    new MutationObserver(function () { requestAnimationFrame(check); })
      .observe(grid, { subtree: true, attributes: true, attributeFilter: ['data-pos'] });
    new MutationObserver(function () { if (document.getElementById('view3').classList.contains('hidden')) last = null; else requestAnimationFrame(check); })
      .observe(document.getElementById('view3'), { attributes: true, attributeFilter: ['class'] });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
