// v2 only: the verdict "reveal" moment. When the chat finishes, a full-screen poster flips in:
// a giant verdict, the score counting up, and 阿電 popping in and saying the score (congratulations only
// when the result is good), then 「接下來是你的詳細分析」. When 阿電 has finished (or on click / any key)
// the poster slides away and the guided tour of the result cards starts.
// Kept in its own file so advisor.html can be re-synced from the live site and only needs this <script>.
(function () {
  var COLORS = { '很適合': '#27F550', '適合但有一個障礙': '#FFD84D', '現在不建議': '#FF7A59', '座位不夠': '#67E8F9' };
  var LINES = { '很適合': ['很', '適合'], '適合但有一個障礙': ['適合，', '差一點'], '現在不建議': ['現在', '先不換'], '座位不夠': ['座位', '不夠'] };
  var reduce = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;

  // what 阿電 says on the poster: the score, then a line that fits the result (no congratulations when it does not fit)
  function sayLines(verdict, score) {
    var s = '你的轉電適配度是 ' + score + ' 分。';
    var mid = {
      '很適合': '恭喜你！電動車很適合你的生活。',
      '適合但有一個障礙': '已經很接近了，只差一個地方要注意。',
      '現在不建議': '老實說，現在還不是換電動車最好的時機。',
      '座位不夠': ''
    }[verdict];
    if (verdict === '座位不夠') s = '你常要坐六個人以上，bZ4X 只有五人座，座位會不夠。';
    return s + (mid || '') + '接下來是你的詳細分析。';
  }

  var css = document.createElement('style');
  css.textContent = [
    '#v2reveal{position:fixed;inset:0;z-index:9999;display:flex;align-items:center;padding:0 clamp(16px,6vw,96px);',
    ' background:radial-gradient(rgba(20,27,45,.13) 1.4px,transparent 1.6px) 0 0/22px 22px,var(--rv,#27F550);',
    ' border:3px solid #141B2D;clip-path:inset(0 0 100% 0);transition:clip-path .55s cubic-bezier(.7,0,.2,1);cursor:pointer;overflow:hidden}',
    '#v2reveal.show{clip-path:inset(0 0 0 0)}',
    '#v2reveal.hide{clip-path:inset(100% 0 0 0)}',
    '#v2reveal .grid{width:100%;display:grid;grid-template-columns:minmax(0,1.05fr) minmax(0,1fr);gap:clamp(16px,4vw,64px);align-items:center}',
    '#v2reveal .k{display:inline-flex;align-items:center;gap:12px;font-weight:900;font-size:clamp(1.1rem,2vw,1.6rem);background:#fff;border:3px solid #141B2D;',
    ' border-radius:999px;padding:6px 18px 6px 6px;box-shadow:4px 4px 0 #141B2D}',
    '#v2reveal .k b{background:#141B2D;color:var(--rv);padding:4px 14px;border-radius:999px;font-family:"Archivo Black",sans-serif;font-weight:400}',
    // the verdict: white letters, thick ink outline and a hard shadow, so it jumps off the colour
    '#v2reveal h2{font-weight:900;font-size:clamp(3.4rem,min(11vw,21vh),14rem);white-space:nowrap;line-height:1.02;letter-spacing:0;margin:.12em 0 0;color:#fff;',
    ' -webkit-text-stroke:.035em #141B2D;paint-order:stroke fill;text-shadow:.06em .06em 0 #141B2D}',
    '#v2reveal h2 span{display:block;overflow:hidden;padding:0 .1em .1em 0}',
    '#v2reveal h2 i{display:inline-block;font-style:normal;transform:translateY(110%);transition:transform .8s cubic-bezier(.2,.8,.2,1)}',
    '#v2reveal.show h2 i{transform:none}#v2reveal.show h2 span+span i{transition-delay:.12s}',
    '#v2reveal .score{display:inline-flex;align-items:baseline;gap:14px;margin-top:28px;background:#141B2D;color:var(--rv);border-radius:20px;',
    ' padding:10px 24px 14px;box-shadow:6px 6px 0 rgba(20,27,45,.35);transform:scale(.6) rotate(-4deg);opacity:0;',
    ' transition:transform .6s cubic-bezier(.3,1.6,.5,1) .45s,opacity .3s ease .45s}',
    '#v2reveal.show .score{transform:rotate(-2deg);opacity:1}',
    '#v2reveal .score b{font-family:"Archivo Black",sans-serif;font-weight:400;font-size:clamp(3rem,8vw,6.5rem);line-height:1}',
    '#v2reveal .score small{font-size:clamp(1rem,1.8vw,1.4rem);font-weight:900;color:#fff}',
    // 阿電 in the middle of the right half, a slowly turning sunburst behind, the speech bubble above
    '#v2reveal .who{position:relative;display:flex;flex-direction:column;align-items:center;gap:22px}',
    '#v2reveal .burst{position:absolute;left:50%;top:62%;width:min(46vw,72vh);aspect-ratio:1;transform:translate(-50%,-50%);border-radius:50%;z-index:0;',
    ' background:repeating-conic-gradient(rgba(255,255,255,.38) 0 10deg,transparent 10deg 20deg);',
    ' -webkit-mask:radial-gradient(closest-side,#000 55%,transparent);mask:radial-gradient(closest-side,#000 55%,transparent);animation:v2spin 24s linear infinite}',
    '@keyframes v2spin{to{transform:translate(-50%,-50%) rotate(360deg)}}',
    '#v2reveal .say{position:relative;z-index:1;max-width:30em;background:#fff;border:3px solid #141B2D;border-radius:22px;box-shadow:6px 6px 0 #141B2D;padding:16px 22px;',
    ' font-weight:900;font-size:clamp(1.05rem,1.6vw,1.4rem);line-height:1.6;color:#141B2D;opacity:0;transform:translateY(16px) scale(.9);',
    ' transition:opacity .4s ease .9s,transform .5s cubic-bezier(.3,1.6,.5,1) .9s}',
    '#v2reveal .say::after{content:"";position:absolute;left:50%;bottom:-14px;width:22px;height:22px;background:#fff;border-right:3px solid #141B2D;',
    ' border-bottom:3px solid #141B2D;transform:translateX(-50%) rotate(45deg)}',
    '#v2reveal.show .say{opacity:1;transform:none}',
    '#v2reveal .ava{position:relative;z-index:1;width:clamp(240px,min(32vw,52vh),520px);filter:drop-shadow(8px 10px 0 rgba(20,27,45,.9));',
    ' transform:translateY(130%) scale(.6) rotate(-10deg);transition:transform .8s cubic-bezier(.3,1.7,.5,1) .3s}',
    '#v2reveal.show .ava{transform:none}',
    '#v2reveal .ava svg,#v2reveal .ava img{width:100%;height:auto;display:block}',
    '#v2reveal .tap{position:absolute;left:clamp(16px,6vw,96px);bottom:22px;font-weight:900;font-size:.95rem;background:#fff;border:2px solid #141B2D;',
    ' border-radius:999px;padding:4px 14px}',
    '@media (max-width:760px){#v2reveal .grid{grid-template-columns:1fr}#v2reveal h2{font-size:22vw}#v2reveal .ava{width:46vw}#v2reveal .burst{width:90vw}}',
    '@media (prefers-reduced-motion:reduce){#v2reveal,#v2reveal *{transition:none!important;animation:none!important}}'
  ].join('\n');
  document.head.appendChild(css);
  if (!document.querySelector('link[href*="Archivo+Black"]')) {
    var f = document.createElement('link'); f.rel = 'stylesheet';
    f.href = 'https://fonts.googleapis.com/css2?family=Archivo+Black&display=swap'; document.head.appendChild(f);
  }

  function countUp(el, to) {
    if (reduce) { el.textContent = to; return; }
    var t0 = performance.now();
    (function step(now) { var p = Math.min(1, (now - t0) / 1200), e = 1 - Math.pow(1 - p, 3);
      el.textContent = Math.round(to * e); if (p < 1) requestAnimationFrame(step); })(t0);
  }
  var sleep = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };

  // show the poster; resolves when it has closed (after 阿電's lines, or on click)
  function show(verdict, score) {
    return new Promise(function (done) {
      var old = document.getElementById('v2reveal'); if (old) old.remove();
      var el = document.createElement('div'); el.id = 'v2reveal';
      el.style.setProperty('--rv', COLORS[verdict] || '#27F550');
      var L = LINES[verdict] || [verdict], text = sayLines(verdict, score);
      el.innerHTML = '<div class="grid"><div>' +
        '<p class="k"><b>RESULT</b>阿電的誠實結論</p>' +
        '<h2>' + L.map(function (s) { return '<span><i>' + s + '</i></span>'; }).join('') + '</h2>' +
        (verdict === '座位不夠' ? '' : '<p class="score"><b>0</b><small>／100　轉電適配度</small></p>') +
        '</div><div class="who"><span class="burst"></span><p class="say"></p>' +
        '<div class="ava" id="v2revealAva"><img src="assets/adian.svg?v=20261013s" alt=""></div></div></div>' +
        '<p class="tap">點一下，直接看分析 →</p>';
      document.body.appendChild(el);

      var main = (typeof avatar !== 'undefined') ? avatar : null, prevMirror = main ? main.mirror : null, closed = false;
      var close = function () {
        if (closed) return; closed = true;
        removeEventListener('keydown', onKey);
        if (main && main.setMirror) main.setMirror(prevMirror || null);
        el.classList.add('hide');
        setTimeout(function () { el.remove(); done(); }, 600);
      };
      var onKey = function () { skip(); };
      var skip = function () { try { if (typeof stopSpeaking === 'function') stopSpeaking(); } catch (e) { /* ignore */ } close(); };
      el.addEventListener('click', skip); addEventListener('keydown', onKey);

      // the poster's 阿電 copies the talking mouth of the main 阿電 (same lip-sync)
      var avaBox = el.querySelector('#v2revealAva');
      var mounted = window.AdianAvatar ? AdianAvatar.mount(avaBox, { src: 'assets/adian-rig.svg?v=20261013s', size: avaBox.clientWidth || 380 })
        .then(function (a) { a.setVoiceEnabled(false); a.setMood('happy'); if (main && main.setMirror) main.setMirror(a); return a; })
        .catch(function () { return null; }) : Promise.resolve(null);

      requestAnimationFrame(function () { requestAnimationFrame(function () {
        el.classList.add('show');
        var b = el.querySelector('.score b'); if (b) setTimeout(function () { countUp(b, score); }, 350);
      }); });

      var t0 = performance.now();
      mounted.then(function () { return sleep(1100); }).then(function () {
        if (closed) return;
        var say = el.querySelector('.say');
        say.textContent = text;
        var spoken = main && main.speak ? main.speak(text) : sleep(4500);
        return Promise.race([spoken, sleep(25000)]);
      }).then(function () { return sleep(Math.max(600, 4200 - (performance.now() - t0))); })   // at least ~4 s on screen
        .then(close, close);
    });
  }

  // hook the end of the chat: finishChat() is a global function declaration in advisor.html.
  // Its built-in tour start (setTimeout(autoTour)) is held back until the poster has closed.
  if (typeof window.finishChat === 'function') {
    var orig = window.finishChat;
    window.finishChat = function () {
      var realAuto = window.autoTour;
      window.autoTour = function () {};
      var r;
      try { r = orig.apply(this, arguments); } finally { setTimeout(function () { window.autoTour = realAuto; }, 300); }
      revealed = true;
      var verdict = (typeof tour !== 'undefined' && tour.verdict) || '';
      var score = 0; try { score = evScore().S; } catch (e) { /* ignore */ }
      // after the poster: start the guided tour (autoTour() itself skips it if the visitor already browsed the cards)
      show(verdict, score).then(function () { setTimeout(function () { try { realAuto(); } catch (e) { /* ignore */ } }, 200); });
      return r;
    };
  }
  // after the poster has said the verdict and the score, the tour's first card should not repeat them
  var revealed = false;
  if (typeof window.tourSteps === 'function') {
    var origSteps = window.tourSteps;
    window.tourSteps = function () {
      var steps = origSteps.apply(this, arguments);
      if (revealed && steps.length) {
        steps[0].text = steps[0].text
          .replace(/^結論：你很適合，轉電適配度 \d+ 分！/, '')                       // 很適合
          .replace(/^結論：你很適合，\d+ 分，只差一點：/, '要注意的一點是：')          // 適合但有一個障礙
          .replace(/^老實說，現在還不建議，你的轉電適配度是 \d+ 分，主要是/, '主要原因是')  // 現在不建議
          .replace(/^老實說，現在不建議。/, '')                                       // 現在不建議（充電一票否決）
          .replace(/^結論：你常要坐六人以上，bZ4X 只有五人座，硬換反而不方便。/, '');  // 座位不夠
      }
      return steps;
    };
  }
  window.v2Reveal = show;
})();
