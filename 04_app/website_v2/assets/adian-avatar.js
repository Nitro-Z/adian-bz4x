/*
 * adian-avatar.js — animated, talking 阿電 (Adian) mascot.
 * Plain ES2017, no dependencies. Exposes window.AdianAvatar.
 *
 *   const av = await AdianAvatar.mount(el, { src: 'assets/adian-rig.svg', size: 220 });
 *   av.setMood('idle' | 'happy' | 'thinking' | 'talking' | 'sorry');
 *   await av.speak('嗨！我是阿電', { rate: 1, pitch: 1.1 });
 *   av.stopSpeaking();
 *   av.setVoiceEnabled(false);   // muted: mouth still animates for an estimated duration
 *   AdianAvatar.voiceSupported   // boolean
 */
(function () {
  'use strict';

  var MOODS = ['idle', 'happy', 'thinking', 'talking', 'sorry'];
  var MOUTHS = ['mouth', 'mouth-half', 'mouth-open', 'mouth-o', 'mouth-flat'];

  // Per-mood pose. Brow/cheek transforms are CSS (transform-box: fill-box, origin: center).
  var POSES = {
    idle:     { mouth: 'mouth', dimples: 1, pupil: [0, 0], cheeks: 1,
                browL: '', browR: '', cheekScale: 1 },
    happy:    { mouth: 'mouth', dimples: 1, pupil: [0, -1], cheeks: 1,
                browL: 'translate(0px,-4px) rotate(-4deg)', browR: 'translate(0px,-4px) rotate(4deg)', cheekScale: 1.3 },
    thinking: { mouth: 'mouth-o', dimples: 0, pupil: [-4, -5], cheeks: 0.85,
                browL: 'translate(0px,1px) rotate(3deg)', browR: 'translate(0px,-5px) rotate(-8deg)', cheekScale: 1 },
    talking:  { mouth: 'mouth', dimples: 1, pupil: [0, 0], cheeks: 1,
                browL: 'translate(0px,-1px)', browR: 'translate(0px,-1px)', cheekScale: 1.1 },
    sorry:    { mouth: 'mouth-flat', dimples: 0, pupil: [0, 3], cheeks: 0.6,
                browL: 'translate(0px,2px) rotate(-10deg)', browR: 'translate(0px,2px) rotate(10deg)', cheekScale: 1 }
  };

  var STYLE_ID = 'adian-avatar-style';
  var CSS = [
    '.adian-avatar{display:inline-block;line-height:0;}',
    '.adian-avatar svg{display:block;height:auto;overflow:visible;}',
    '.adian-avatar .adian-part{transform-box:fill-box;transform-origin:center;}',
    '.adian-avatar .adian-eye{transition:transform 70ms ease-in-out;}',
    '.adian-avatar .adian-pupil{transition:transform 380ms cubic-bezier(.3,.7,.3,1);}',
    '.adian-avatar .adian-brow{transition:transform 260ms ease-out;}',
    '.adian-avatar .adian-cheeks{transition:opacity 300ms ease;}',
    '.adian-avatar .adian-cheek{transition:transform 300ms ease;}',
    '.adian-avatar .adian-dimples{transition:opacity 150ms ease;}',
    '.adian-avatar .adian-mood-talking{animation:adian-bounce 340ms ease-in-out infinite alternate;}',
    '.adian-avatar .adian-mood-thinking{animation:adian-bob 1.8s ease-in-out infinite alternate;}',
    '@keyframes adian-bounce{from{transform:translateY(0)}to{transform:translateY(-2.5px)}}',
    '@keyframes adian-bob{from{transform:translateY(0) rotate(0deg)}to{transform:translateY(-2px) rotate(-1deg)}}',
    '@media (prefers-reduced-motion: reduce){',
    '  .adian-avatar .adian-mood-talking,.adian-avatar .adian-mood-thinking{animation:none;}',
    '  .adian-avatar .adian-pupil,.adian-avatar .adian-brow,.adian-avatar .adian-cheek{transition:none;}',
    '}'
  ].join('\n');

  function injectStyle() {
    if (document.getElementById(STYLE_ID)) return;
    var st = document.createElement('style');
    st.id = STYLE_ID;
    st.textContent = CSS;
    (document.head || document.documentElement).appendChild(st);
  }

  function reducedMotion() {
    try { return !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches); }
    catch (e) { return false; }
  }

  function rand(a, b) { return a + Math.random() * (b - a); }

  // ---------------------------------------------------------------- speech
  var synth = null;
  try { synth = window.speechSynthesis || null; } catch (e) { synth = null; }
  var voiceSupported = !!(synth && typeof window.SpeechSynthesisUtterance === 'function');
  var chosenVoice = null;

  var preferredVoiceName = null; // set by the page through AdianAvatar.setPreferredVoice()

  // Mandarin only: never Cantonese (zh-HK / yue), Taiwanese Hokkien (nan), Wu (wuu)
  // or the regional-dialect voices some browsers ship (e.g. zh-CN-liaoning, zh-CN-shaanxi).
  function isMandarin(v) {
    var lang = String(v.lang || '').replace(/_/g, '-').toLowerCase();
    var name = String(v.name || '').toLowerCase();
    if (/^(yue|nan|wuu|hak)/.test(lang) || lang.indexOf('zh-hk') === 0 || lang.indexOf('zh-mo') === 0) return false;
    if (/cantonese|粵|粤|hong kong|香港|hiugaai|hiumaan|wanlung|sinji|dialect|liaoning|shaanxi|xiaobei|xiaoni|台語|閩南|hokkien/.test(name)) return false;
    if (/^zh-(cn|tw|sg)(-|$)/.test(lang) && lang.split('-').length > 2 && !/hant|hans/.test(lang)) return false; // zh-cn-liaoning etc.
    return lang.indexOf('zh') === 0 || lang.indexOf('cmn') === 0;
  }

  function scoreVoice(v) {
    if (!isMandarin(v)) return -1;
    var lang = String(v.lang || '').replace(/_/g, '-').toLowerCase();
    var name = String(v.name || '').toLowerCase();
    var s = (lang.indexOf('zh-tw') === 0 || lang.indexOf('cmn-hant-tw') === 0) ? 300 : 100; // Taiwan Mandarin first
    if (/natural|neural|online|premium|enhanced/.test(name)) s += 30;
    if (/google|microsoft|apple|siri/.test(name)) s += 15;
    if (/hsiaoyu|hsiaochen|yating|meijia|xiaoxiao|國語|国语|mandarin/.test(name)) s += 5;
    if (v.localService) s += 2;
    return s;
  }

  function allVoices() {
    try { return synth.getVoices() || []; } catch (e) { return []; }
  }

  function pickVoice() {
    if (!voiceSupported) return null;
    var list = allVoices();
    if (preferredVoiceName) {
      for (var j = 0; j < list.length; j++) {
        if (list[j].name === preferredVoiceName && isMandarin(list[j])) { chosenVoice = list[j]; return list[j]; }
      }
    }
    var best = null, bestScore = -1;
    for (var i = 0; i < list.length; i++) {
      var sc = scoreVoice(list[i]);
      if (sc > bestScore) { best = list[i]; bestScore = sc; }
    }
    chosenVoice = best; // null => no Mandarin voice on this device
    return best;
  }

  // Mandarin voices on this device, best first (for a voice picker in the page)
  function mandarinVoices() {
    return allVoices().filter(isMandarin).sort(function (a, b) { return scoreVoice(b) - scoreVoice(a); });
  }

  if (voiceSupported) {
    pickVoice();
    var onVoices = function () { pickVoice(); };
    try {
      if (typeof synth.addEventListener === 'function') synth.addEventListener('voiceschanged', onVoices);
      else synth.onvoiceschanged = onVoices;
    } catch (e) { /* ignore */ }
  }

  function isCJK(ch) {
    var c = ch.charCodeAt(0);
    return (c >= 0x3400 && c <= 0x9FFF) || (c >= 0xF900 && c <= 0xFAFF) ||
           (c >= 0x3040 && c <= 0x30FF) || (c >= 0xAC00 && c <= 0xD7AF);
  }

  // ≈220 ms per CJK char, 60 ms per Latin char/digit, short pauses for punctuation.
  function estimateMs(text, rate) {
    var ms = 0;
    for (var i = 0; i < text.length; i++) {
      var ch = text.charAt(i);
      if (isCJK(ch)) ms += 220;
      else if (/[A-Za-z0-9]/.test(ch)) ms += 60;
      else if (/[，、,；;：:]/.test(ch)) ms += 150;
      else if (/[。！？!?.…\n]/.test(ch)) ms += 280;
      else if (ch === ' ') ms += 30;
    }
    return Math.max(500, ms / (rate || 1));
  }

  // Split into sentence-sized chunks (avoids Chrome's ~15 s utterance cut-off bug).
  function chunkText(text) {
    var parts = String(text).match(/[^。！？!?；;\n]+[。！？!?；;\n]*/g) || [];
    var out = [], buf = '';
    for (var i = 0; i < parts.length; i++) {
      var p = parts[i].trim();
      if (!p) continue;
      if ((buf + p).length <= 60) buf += p;
      else { if (buf) out.push(buf); buf = p; }
    }
    if (buf) out.push(buf);
    return out;
  }

  // ---------------------------------------------------------------- server TTS
  // Natural voice from our own TTS server (POST {text} -> audio/wav). Browser voices are
  // off by default because they sound robotic; enable them only via useBrowserVoice(true).
  var ttsServer = null;
  var browserVoiceAllowed = false;
  var audioCtx = null;

  function getAudioCtx() {
    if (!audioCtx) {
      var AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return null;
      // run at Gemini's 24 kHz so streamed pieces are played without per-piece resampling (no clicks at the joins)
      try { audioCtx = new AC({ sampleRate: 24000 }); } catch (e) { audioCtx = new AC(); }
    }
    return audioCtx;
  }

  // Must be called from a user gesture (click) so the browser allows audio playback.
  function unlockAudio() {
    var ctx = getAudioCtx();
    if (ctx && ctx.state === 'suspended') { try { ctx.resume(); } catch (e) { /* ignore */ } }
  }

  // ---------------------------------------------------------------- volume
  // All of 阿電's voice (Gemini stream and BreezyVoice WAV) goes through one master gain node.
  // The lip-sync meter listens before this node, so the mouth still moves at low volume or when muted.
  // The level is remembered per browser (localStorage; ignored when storage is blocked).
  var VOL_KEY = 'adian.volume', MUTE_KEY = 'adian.muted';
  var volume = 1, muted = false, master = null, volListeners = [];
  try {
    var savedVol = parseFloat(window.localStorage.getItem(VOL_KEY));
    // 11/12：每次打開頁面都有聲音：不沿用上次的「靜音」，音量最低從 30% 開始（以免在模擬裡按了靜音，顧問頁也一直沒聲音）
    if (isFinite(savedVol)) volume = Math.max(0.3, Math.min(1, savedVol));
    muted = false;
  } catch (e) { /* storage blocked: defaults */ }
  function gainValue() { return muted ? 0 : volume * volume; }   // squared: the slider feels even (loudness is logarithmic)
  function masterNode(ctx) {
    if (!master || master.context !== ctx) { master = ctx.createGain(); master.gain.value = gainValue(); master.connect(ctx.destination); }
    return master;
  }
  function applyVolume() {
    if (master) {
      try { master.gain.setTargetAtTime(gainValue(), master.context.currentTime, 0.03); } catch (e) { master.gain.value = gainValue(); }
    }
    try { window.localStorage.setItem(VOL_KEY, String(volume)); window.localStorage.setItem(MUTE_KEY, muted ? '1' : '0'); } catch (e) { /* ignore */ }
    volListeners.forEach(function (f) { try { f(); } catch (e) { /* ignore */ } });
  }
  function setVolume(v) {
    volume = Math.max(0, Math.min(1, +v || 0));
    if (volume > 0) muted = false;
    applyVolume();
  }
  function setMuted(on) {
    muted = !!on;
    if (!muted && volume === 0) volume = 0.6;   // unmuting from 0 → a usable level
    applyVolume();
  }
  var VOL_CSS = [
    '.adian-vol{display:inline-flex;align-items:center;gap:8px;vertical-align:middle;}',
    '.adian-vol-btn{flex:none;width:40px;height:38px;padding:0;border:3px solid #141B2D;border-radius:10px;background:#fff;color:#141B2D;',
    '  box-shadow:3px 3px 0 #141B2D;font-size:18px;line-height:1;cursor:pointer;}',
    '.adian-vol-btn[aria-pressed="true"]{background:#FFD84D;}',
    '.adian-vol-btn:active{transform:translate(2px,2px);box-shadow:1px 1px 0 #141B2D;}',
    '.adian-vol-range{-webkit-appearance:none;appearance:none;width:var(--adian-vol-w,110px);height:16px;margin:0;border:3px solid #141B2D;border-radius:8px;cursor:pointer;',
    '  background:linear-gradient(90deg,#27F550 var(--p,100%),#FAFAF5 var(--p,100%));}',
    '.adian-vol-range::-webkit-slider-thumb{-webkit-appearance:none;width:18px;height:26px;border:3px solid #141B2D;border-radius:6px;background:#FFD84D;}',
    '.adian-vol-range::-moz-range-thumb{width:14px;height:22px;border:3px solid #141B2D;border-radius:6px;background:#FFD84D;}',
    '.adian-vol-btn:focus-visible,.adian-vol-range:focus-visible{outline:3px solid #27F550;outline-offset:2px;}'
  ].join('\n');
  // Mute button + 0–100 % slider, kept in sync everywhere on the page.
  function volumeControl(container, opts) {
    opts = opts || {};
    if (typeof container === 'string') container = document.querySelector(container);
    if (!container) return null;
    if (!document.getElementById('adian-vol-style')) {
      var st = document.createElement('style'); st.id = 'adian-vol-style'; st.textContent = VOL_CSS;
      (document.head || document.documentElement).appendChild(st);
    }
    var wrap = document.createElement('div');
    wrap.className = 'adian-vol';
    if (opts.width) wrap.style.setProperty('--adian-vol-w', opts.width + 'px');
    wrap.innerHTML = '<button type="button" class="adian-vol-btn"></button>'
      + '<input type="range" class="adian-vol-range" min="0" max="100" step="5" aria-label="阿電的音量">';
    var btn = wrap.querySelector('button'), range = wrap.querySelector('input');
    var sync = function () {
      var v = muted ? 0 : Math.round(volume * 100);
      range.value = v; range.style.setProperty('--p', v + '%');
      range.setAttribute('aria-valuetext', muted ? '靜音' : v + '%');
      btn.textContent = v === 0 ? '🔇' : v < 40 ? '🔈' : v < 75 ? '🔉' : '🔊';
      btn.setAttribute('aria-pressed', String(muted));
      btn.setAttribute('aria-label', muted ? '取消靜音' : '靜音');
      btn.title = muted ? '取消靜音' : '靜音';
    };
    btn.addEventListener('click', function () { unlockAudio(); setMuted(!muted); });
    range.addEventListener('input', function () { unlockAudio(); setVolume(range.value / 100); });
    volListeners.push(sync);
    sync();
    container.appendChild(wrap);
    return wrap;
  }

  // One request per line, shared by the prefetch and the real playback. The gateway streams raw PCM
  // (audio/L16, 24 kHz) as Gemini speaks it, so playback can start on the first piece (~1 s); a plain WAV
  // (BreezyVoice fallback) arrives as one piece. A stream: { bufs: [AudioBuffer], done, error, listeners }.
  var streams = {};
  var streamKeys = [];
  function fetchStream(text) {
    var s = streams[text];
    if (s && !s.error) return s;
    var ctx = getAudioCtx();
    s = { bufs: [], done: false, error: null, listeners: [], ctrl: null };
    var notify = function () { s.listeners.slice().forEach(function (f) { try { f(); } catch (e) { /* ignore */ } }); };
    var fail = function (err) { s.error = err || new Error('TTS failed'); delete streams[text]; notify(); };
    if (!ctx || !ttsServer) { s.error = new Error('no audio'); return s; }
    streams[text] = s;
    if (streamKeys.indexOf(text) < 0) streamKeys.push(text);
    while (streamKeys.length > 60) delete streams[streamKeys.shift()];
    s.ctrl = typeof AbortController === 'function' ? new AbortController() : null;
    fetch(ttsServer + '/tts', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: text, voice: 'default' }), signal: s.ctrl ? s.ctrl.signal : undefined
    }).then(function (res) {
      if (!res.ok) throw new Error('TTS HTTP ' + res.status);
      var type = res.headers.get('content-type') || '';
      var rate = +((type.match(/rate=(\d+)/) || [])[1] || 24000);
      if (type.indexOf('L16') < 0 || !res.body || !res.body.getReader) {
        return res.arrayBuffer().then(function (data) {
          if (type.indexOf('L16') >= 0) return pcmBuffer(ctx, new Uint8Array(data), rate);
          return new Promise(function (ok, bad) { ctx.decodeAudioData(data, ok, bad); });
        }).then(function (buf) { s.bufs.push(buf); s.done = true; notify(); });
      }
      // the network delivers ~40 ms pieces about 4x faster than real time; join them into larger buffers
      // (first 0.3 s, then 0.5 s): few seams, and the next buffer is always ready before the current one ends
      var reader = res.body.getReader(), pending = [], pendingLen = 0;
      var flush = function () {
        var n = pendingLen - (pendingLen % 2);
        if (!n) return;
        var all = new Uint8Array(pendingLen), o = 0;
        pending.forEach(function (b) { all.set(b, o); o += b.length; });
        s.bufs.push(pcmBuffer(ctx, all.subarray(0, n), rate));
        pending = n < pendingLen ? [all.slice(n)] : []; pendingLen -= n;
        notify();
      };
      var pump = function () {
        return reader.read().then(function (r) {
          if (r.done) { flush(); s.done = true; notify(); return; }
          pending.push(r.value); pendingLen += r.value.length;
          if (pendingLen >= rate * 2 * (s.bufs.length ? 0.5 : 0.3)) flush();   // small enough to never run dry
          return pump();
        });
      };
      return pump();
    }).catch(fail);
    return s;
  }
  function pcmBuffer(ctx, bytes, rate) {
    var n = bytes.length >> 1, view = new DataView(bytes.buffer, bytes.byteOffset, n * 2);
    var buf = ctx.createBuffer(1, Math.max(1, n), rate), ch = buf.getChannelData(0);
    for (var i = 0; i < n; i++) ch[i] = view.getInt16(i * 2, true) / 32768;
    return buf;
  }
  // The visitor moved on: abandon every line still being generated (the server then skips them).
  function cancelPending() {
    Object.keys(streams).forEach(function (k) {
      var s = streams[k];
      if (!s.done) { delete streams[k]; if (s.ctrl) { try { s.ctrl.abort(); } catch (e) { /* ignore */ } } }
    });
  }

  // ---------------------------------------------------------------- avatar
  var instanceCounter = 0;

  function prefixIds(svgText, prefix) {
    return svgText
      .replace(/\bid="([^"]+)"/g, 'id="' + prefix + '$1"')
      .replace(/url\(#([^)]+)\)/g, 'url(#' + prefix + '$1)')
      .replace(/(xlink:href|href)="#([^"]+)"/g, '$1="#' + prefix + '$2"');
  }

  function Avatar(container, svg, prefix, size) {
    this.container = container;
    this.svg = svg;
    this.mood = 'idle';
    this.restoreMood = 'idle';
    this.voiceEnabled = true;
    this.destroyed = false;
    this._timers = {};
    this._speech = null; // current speech session
    this._drift = [0, 0];
    this._mouthName = 'mouth';
    this._talkLoop = false;

    var self = this;
    function q(id) { return svg ? svg.querySelector('#' + prefix + id) : null; }
    this.parts = {
      eyeL: q('eye-l'), eyeR: q('eye-r'),
      pupilL: q('pupil-l'), pupilR: q('pupil-r'),
      browL: q('brow-l'), browR: q('brow-r'),
      cheeks: q('cheeks'), cheekL: q('cheek-l'), cheekR: q('cheek-r'),
      dimples: q('dimples')
    };
    this.mouths = {};
    MOUTHS.forEach(function (m) { self.mouths[m] = q(m); });

    var p = this.parts;
    function cls(el, c) { if (el) { var a = (el.getAttribute('class') || '') + ' adian-part ' + c; el.setAttribute('class', a.trim()); } }
    cls(p.eyeL, 'adian-eye'); cls(p.eyeR, 'adian-eye');
    cls(p.pupilL, 'adian-pupil'); cls(p.pupilR, 'adian-pupil');
    cls(p.browL, 'adian-brow'); cls(p.browR, 'adian-brow');
    cls(p.cheekL, 'adian-cheek'); cls(p.cheekR, 'adian-cheek');
    if (p.cheeks) p.cheeks.setAttribute('class', 'adian-cheeks');
    if (p.dimples) p.dimples.setAttribute('class', 'adian-dimples');
    if (svg) svg.style.width = size + 'px';

    this._applyPose();
    this._scheduleBlink();
    this._scheduleDrift();
  }

  Avatar.prototype._setTimer = function (key, fn, ms) {
    this._clearTimer(key);
    var self = this;
    this._timers[key] = setTimeout(function () { delete self._timers[key]; if (!self.destroyed) fn(); }, ms);
  };
  Avatar.prototype._clearTimer = function (key) {
    if (this._timers[key]) { clearTimeout(this._timers[key]); delete this._timers[key]; }
  };

  Avatar.prototype._showMouth = function (name) {
    if (!this.mouths[name]) name = 'mouth';
    this._mouthName = name;
    for (var k in this.mouths) {
      var el = this.mouths[k];
      if (el) el.setAttribute('opacity', k === name ? '1' : '0');
    }
    if (this.mirror && !this.mirror.destroyed) this.mirror._showMouth(name); // a second avatar that copies the mouth
  };

  // Another avatar (e.g. a floating companion) copies this one's mouth and talking pose.
  Avatar.prototype.setMirror = function (other) { this.mirror = other || null; };
  Avatar.prototype._mirrorMood = function () {
    var m = this.mirror;
    if (!m || m.destroyed || m._speech) return;
    m.mood = this.mood; m._applyPose();
  };

  Avatar.prototype._applyPupils = function () {
    var pose = POSES[this.mood];
    var x = pose.pupil[0] + this._drift[0], y = pose.pupil[1] + this._drift[1];
    var t = 'translate(' + x.toFixed(2) + 'px,' + y.toFixed(2) + 'px)';
    if (this.parts.pupilL) this.parts.pupilL.style.transform = t;
    if (this.parts.pupilR) this.parts.pupilR.style.transform = t;
  };

  Avatar.prototype._applyPose = function () {
    var pose = POSES[this.mood], p = this.parts;
    if (this.svg) {
      var c = (this.svg.getAttribute('class') || '').replace(/\s*adian-mood-\w+/g, '');
      this.svg.setAttribute('class', (c + ' adian-mood-' + this.mood).trim());
    }
    if (p.browL) p.browL.style.transform = pose.browL;
    if (p.browR) p.browR.style.transform = pose.browR;
    if (p.cheeks) p.cheeks.style.opacity = String(pose.cheeks);
    var cs = pose.cheekScale === 1 ? '' : 'scale(' + pose.cheekScale + ')';
    if (p.cheekL) p.cheekL.style.transform = cs;
    if (p.cheekR) p.cheekR.style.transform = cs;
    if (p.dimples) p.dimples.style.opacity = String(pose.dimples);
    if (this.mood === 'thinking' || this.mood === 'sorry') this._drift = [0, 0];
    this._applyPupils();
    if (this.mood === 'talking') this._startTalkLoop();
    else { this._stopTalkLoop(); this._showMouth(pose.mouth); }
  };

  // ---- blinking
  Avatar.prototype._scheduleBlink = function () {
    var self = this;
    this._setTimer('blink', function () { self._blink(); }, rand(2500, 5000));
  };
  Avatar.prototype._blink = function () {
    var self = this, p = this.parts;
    if (p.eyeL) p.eyeL.style.transform = 'scaleY(0.1)';
    if (p.eyeR) p.eyeR.style.transform = 'scaleY(0.1)';
    this._setTimer('unblink', function () {
      if (p.eyeL) p.eyeL.style.transform = '';
      if (p.eyeR) p.eyeR.style.transform = '';
      // occasional double blink
      if (Math.random() < 0.15) self._setTimer('blink', function () { self._blink(); }, 220);
      else self._scheduleBlink();
    }, 150);
  };

  // ---- pupil drift (idle/happy/talking only, disabled for reduced motion)
  Avatar.prototype._scheduleDrift = function () {
    var self = this;
    this._setTimer('drift', function () {
      if (!reducedMotion() && (self.mood === 'idle' || self.mood === 'happy' || self.mood === 'talking')) {
        self._drift = Math.random() < 0.35 ? [0, 0] : [rand(-3, 3), rand(-2, 1.5)];
      } else {
        self._drift = [0, 0];
      }
      self._applyPupils();
      self._scheduleDrift();
    }, rand(1800, 4200));
  };

  // ---- talking mouth loop
  // Random cycle closed/half/open every ~110 ms (±40). If the TTS engine fires
  // `boundary` events, each boundary pops the mouth open and the loop only decays it.
  Avatar.prototype._startTalkLoop = function () {
    if (this._talkLoop) return;
    if (this._speech && this._speech.lipsync) { this._showMouth('mouth'); return; }
    this._talkLoop = true;
    this._lastBoundary = 0;
    this._talkTick();
  };
  Avatar.prototype._stopTalkLoop = function () {
    this._talkLoop = false;
    this._clearTimer('talk');
  };
  Avatar.prototype._talkTick = function () {
    if (!this._talkLoop) return;
    var self = this, cur = this._mouthName, next;
    var boundaryDriven = Date.now() - (this._lastBoundary || 0) < 450;
    if (boundaryDriven) {
      next = cur === 'mouth-open' ? 'mouth-half' : 'mouth';
    } else {
      var r = Math.random();
      if (cur === 'mouth') next = r < 0.55 ? 'mouth-half' : 'mouth-open';
      else if (cur === 'mouth-open') next = r < 0.6 ? 'mouth-half' : 'mouth';
      else next = r < 0.45 ? 'mouth-open' : 'mouth';
    }
    this._showMouth(next);
    this._setTimer('talk', function () { self._talkTick(); }, rand(70, 150));
  };
  Avatar.prototype._onBoundary = function () {
    this._lastBoundary = Date.now();
    if (this._talkLoop) this._showMouth(Math.random() < 0.6 ? 'mouth-open' : 'mouth-half');
  };

  // ---------------------------------------------------------------- public API
  Avatar.prototype.setMood = function (mood) {
    if (MOODS.indexOf(mood) < 0) mood = 'idle';
    if (this._speech) {
      // While speaking, keep the talking face; remember where to go afterwards.
      if (mood !== 'talking') this.restoreMood = mood;
      return;
    }
    if (mood !== 'talking') this.restoreMood = mood;
    if (mood === this.mood) return;
    this.mood = mood;
    this._applyPose();
  };

  Avatar.prototype.getMood = function () { return this.mood; };

  Avatar.prototype.setVoiceEnabled = function (on) {
    on = !!on;
    if (on === this.voiceEnabled) return;
    this.voiceEnabled = on;
    // If audio is playing and we just muted, stop the audio and finish the line silently.
    var sp = this._speech;
    if (!on && sp && sp.server) { this._stopServerAudio(sp); this._endSession(sp); return; }
    if (!on && sp && sp.audio) {
      sp.audio = false;
      sp.utterances.forEach(function (u) { u.onend = u.onerror = u.onboundary = u.onstart = null; });
      try { synth.cancel(); } catch (e) { /* ignore */ }
      var remaining = sp.chunks.slice(sp.index).join('');
      this._muteSession(sp, estimateMs(remaining, sp.rate));
    }
  };

  Avatar.prototype.stopSpeaking = function () {
    var sp = this._speech;
    if (!sp) return;
    if (sp.server) this._stopServerAudio(sp);
    if (sp.audio) {
      sp.utterances.forEach(function (u) { u.onend = u.onerror = u.onboundary = u.onstart = null; });
      try { synth.cancel(); } catch (e) { /* ignore */ }
    }
    this._endSession(sp);
  };

  Avatar.prototype.speak = function (text, opts) {
    var self = this;
    opts = opts || {};
    this.stopSpeaking(); // resolves any previous promise
    text = String(text == null ? '' : text).trim();
    if (!text || this.destroyed) return Promise.resolve();

    var rate = typeof opts.rate === 'number' ? opts.rate : 1;
    var pitch = typeof opts.pitch === 'number' ? opts.pitch : 1.1;

    return new Promise(function (resolve) {
      var sp = {
        resolve: resolve, done: false, audio: false, rate: rate,
        chunks: chunkText(text), index: 0, utterances: [],
        server: !!(self.voiceEnabled && ttsServer && getAudioCtx()),
        text: text,
        onStart: typeof opts.onStart === 'function' ? opts.onStart : null
      };
      // called once, when sound actually starts (or right away when there is no sound);
      // only then does 阿電 switch to the talking face, so it does not bob while the voice is still loading
      sp.started = function () {
        if (!sp.done && self._speech === sp && self.mood !== 'talking') {
          self.mood = 'talking';
          self._applyPose();
          self._mirrorMood();
        }
        if (sp.onStart) { var f = sp.onStart; sp.onStart = null; try { f(); } catch (e) { /* ignore */ } }
      };
      sp.lipsync = sp.server;
      if (!sp.chunks.length) sp.chunks = [text];
      self._speech = sp;
      if (self.mood !== 'talking') self.restoreMood = self.mood;

      if (sp.server) {
        self._speakServer(sp);
      } else if (self.voiceEnabled && browserVoiceAllowed && voiceSupported) {
        sp.audio = true;
        sp.started();
        self._speakChunks(sp, pitch);
      } else {
        sp.started();
        self._muteSession(sp, estimateMs(text, rate));
      }
    });
  };

  // Play TTS audio and drive the mouth from the real signal level (RMS of the waveform).
  // Split long text into sentence-sized parts so the first one can start playing quickly;
  // the next part is generated while the current one plays.
  function serverParts(text) {
    // TTS time grows with length (~1.5 s for 12 chars, ~4.4 s for 46), so the FIRST part is kept short
    // (cut at a comma around 20 chars) and later parts stay under ~40 chars; each part is generated
    // while the previous one is playing.
    var raw = String(text).replace(/([。！？；!?])/g, '$1\n').split('\n').map(function (s) { return s.trim(); }).filter(Boolean);
    var parts = [];
    raw.forEach(function (s) {
      var limit = function () { return parts.length ? 40 : 20; };
      while (s.length > limit() + 4) {
        var lim = limit(), cut = -1;
        for (var k = Math.min(lim, s.length - 4); k >= 5; k--) if ('，、：,'.indexOf(s.charAt(k)) >= 0) { cut = k; break; }
        if (cut < 0) break;
        parts.push(s.slice(0, cut + 1)); s = s.slice(cut + 1);
      }
      var last = parts[parts.length - 1];
      if (last && (s.length < 6 || (last.length < 8 && (last + s).length <= (parts.length === 1 ? 24 : 44)))) parts[parts.length - 1] = last + s;
      else parts.push(s);
    });
    return parts.length ? parts : [String(text)];
  }

  // Play TTS audio part by part and drive the mouth from the real signal level (RMS of the waveform).
  Avatar.prototype._speakServer = function (sp) {
    var self = this;
    sp.parts = serverParts(sp.text);
    var fallbackToMute = function (fromPart) {
      if (sp.done) return;
      sp.server = false; sp.lipsync = false;
      sp.started();
      self._startTalkLoop();
      self._muteSession(sp, estimateMs(sp.parts.slice(fromPart).join(''), sp.rate));
    };
    var playPart = function (i) {
      if (sp.done) return;
      var st = fetchStream(sp.parts[i]);
      if (i + 1 < sp.parts.length) fetchStream(sp.parts[i + 1]); // generate the next part while this one plays
      // generation can take a few seconds; give up if nothing arrives in 25 s
      self._setTimer('speechEnd', function () { if (!sp.sources || !sp.sources.length) fallbackToMute(i); }, 25000);
      var ctx = getAudioCtx();
      if (ctx.state === 'suspended') { try { ctx.resume(); } catch (e) { /* ignore */ } }
      // sound goes straight out; the mouth meter listens through a delay equal to the output latency
      // (large on Bluetooth), so the mouth moves when the sound is heard, not when it is scheduled
      var latency = Math.min(0.5, ctx.outputLatency || ctx.baseLatency || 0);
      var out = ctx.createGain();
      out.connect(masterNode(ctx));   // volume / mute; the meter below listens before it
      var analyser = ctx.createAnalyser();
      analyser.fftSize = 1024;
      var meter = latency > 0.005 && ctx.createDelay ? ctx.createDelay(1) : null;
      if (meter) { meter.delayTime.value = latency; out.connect(meter); meter.connect(analyser); } else out.connect(analyser);
      var sink = ctx.createGain(); sink.gain.value = 0; analyser.connect(sink); sink.connect(ctx.destination);
      var data = new Float32Array(analyser.fftSize);
      var level = 0, peak = 0.08, shape = 'mouth', shapeAt = 0, idx = 0, endAt = 0, finished = false;
      sp.sources = [];
      var tick = function () {
        if (sp.done) return;
        analyser.getFloatTimeDomainData(data);
        var sum = 0;
        for (var k = 0; k < data.length; k++) sum += data[k] * data[k];
        var rms = Math.sqrt(sum / data.length);
        level = level * 0.4 + rms * 0.6; // smooth
        // relative to the recent loudest level: voices differ a lot in loudness (Gemini ~0.1-0.5, BreezyVoice
        // much quieter), so fixed thresholds kept the mouth wide open the whole time
        peak = Math.max(level, peak * 0.99, 0.06);
        var r = level / peak, now = performance.now();
        var want = level < 0.02 || r < 0.45 ? 'mouth' : r > 0.78 ? 'mouth-open' : 'mouth-half';   // closes between syllables
        if (want !== shape && now - shapeAt > 70) { shape = want; shapeAt = now; self._showMouth(shape); }   // hold each shape ≥ 70 ms: no flicker
        sp.raf = requestAnimationFrame(tick);
      };
      var next = function () {
        if (finished || sp.done) return;
        finished = true;
        st.listeners = st.listeners.filter(function (f) { return f !== feed; });
        if (sp.raf) { try { cancelAnimationFrame(sp.raf); } catch (e) { /* ignore */ } sp.raf = null; }
        sp.sources = [];
        if (i + 1 < sp.parts.length) { self._showMouth('mouth'); playPart(i + 1); } else self._endSession(sp);
      };
      var feed = function () {
        if (sp.done || finished) return;
        if (st.error && !idx) {
          if (window.console) console.warn('[AdianAvatar] TTS server unavailable, speaking silently:', st.error.message);
          fallbackToMute(i); return;
        }
        while (idx < st.bufs.length) {
          var buf = st.bufs[idx++];
          var src = ctx.createBufferSource();
          src.buffer = buf;
          src.connect(out);
          // later pieces are queued back to back (exact sample count, so no gap or overlap at the seam)
          var at = endAt > ctx.currentTime + 0.01 ? endAt : ctx.currentTime + 0.05;
          src.start(at);
          endAt = at + buf.length / buf.sampleRate;
          sp.sources.push(src);
          if (idx === 1) {
            // show the text when the first sound is actually heard
            setTimeout(function () { if (!sp.done) sp.started(); }, Math.max(0, (at - ctx.currentTime + latency) * 1000));
            sp.raf = requestAnimationFrame(tick);
          }
        }
        if ((st.done || st.error) && idx) {
          self._setTimer('speechEnd', next, Math.max(0, (endAt - ctx.currentTime + latency) * 1000) + 60);
        }
      };
      st.listeners.push(feed);
      feed();
    };
    playPart(0);
  };

  Avatar.prototype._stopServerAudio = function (sp) {
    if (sp.raf) { try { cancelAnimationFrame(sp.raf); } catch (e) { /* ignore */ } sp.raf = null; }
    (sp.sources || []).forEach(function (s) { try { s.stop(); } catch (e) { /* ignore */ } });
    sp.sources = [];
  };

  Avatar.prototype._muteSession = function (sp, ms) {
    var self = this;
    this._setTimer('speechEnd', function () { self._endSession(sp); }, ms);
  };

  Avatar.prototype._speakChunks = function (sp, pitch) {
    var self = this;
    var voice = pickVoice();
    if (!voice) {
      // No Mandarin voice on this device: stay silent rather than fall back to Cantonese/English.
      this._muteSession(sp, estimateMs(sp.chunks.join(''), sp.rate));
      return;
    }
    try { if (synth.speaking || synth.pending) synth.cancel(); } catch (e) { /* ignore */ }
    try { if (synth.paused) synth.resume(); } catch (e) { /* ignore */ }

    sp.chunks.forEach(function (chunk, i) {
      var u = new window.SpeechSynthesisUtterance(chunk);
      u.voice = voice; u.lang = voice.lang;
      u.rate = sp.rate; u.pitch = pitch; u.volume = muted ? 0 : volume;
      u.onstart = function () { sp.index = i; self._armWatchdog(sp, sp.chunks.slice(i).join('')); };
      u.onboundary = function () { self._onBoundary(); };
      u.onend = function () {
        sp.index = i + 1;
        if (i === sp.chunks.length - 1) self._endSession(sp);
      };
      u.onerror = function () { self._endSession(sp); }; // 'interrupted', 'not-allowed', ...
      sp.utterances.push(u);
    });
    // Safety net in case the engine never fires start/end (autoplay policy, missing engine, etc.).
    this._armWatchdog(sp, sp.chunks.join(''), 2500);
    try {
      sp.utterances.forEach(function (u) { synth.speak(u); });
    } catch (e) {
      // Engine blew up: fall back to silent mouth animation.
      sp.audio = false;
      this._muteSession(sp, estimateMs(sp.chunks.join(''), sp.rate));
    }
  };

  Avatar.prototype._armWatchdog = function (sp, remainingText, extra) {
    var self = this;
    var ms = estimateMs(remainingText, sp.rate) * 2.5 + (extra || 4000);
    this._setTimer('speechEnd', function () {
      if (sp.audio) {
        sp.utterances.forEach(function (u) { u.onend = u.onerror = u.onboundary = u.onstart = null; });
        try { synth.cancel(); } catch (e) { /* ignore */ }
      }
      self._endSession(sp);
    }, ms);
  };

  Avatar.prototype._endSession = function (sp) {
    if (!sp || sp.done) return;
    sp.done = true;
    if (sp.started) sp.started(); // stopped before any sound: still release the waiting text
    if (sp.raf) { try { cancelAnimationFrame(sp.raf); } catch (e) { /* ignore */ } sp.raf = null; }
    if (this._speech === sp) {
      this._speech = null;
      this._clearTimer('speechEnd');
      this.mood = this.restoreMood || 'idle';
      if (this.mood === 'talking') this.mood = 'idle';
      if (!this.destroyed) this._applyPose();
      this._mirrorMood();
      if (this.mirror && !this.mirror.destroyed) this.mirror._showMouth('mouth');
    }
    sp.resolve();
  };

  Avatar.prototype.destroy = function () {
    this.stopSpeaking();
    this.destroyed = true;
    this._stopTalkLoop();
    for (var k in this._timers) clearTimeout(this._timers[k]);
    this._timers = {};
    if (this.container) this.container.innerHTML = '';
  };

  // ---------------------------------------------------------------- mount
  function mount(container, opts) {
    opts = opts || {};
    if (typeof container === 'string') container = document.querySelector(container);
    if (!container) return Promise.reject(new Error('AdianAvatar.mount: container not found'));
    var src = opts.src || 'assets/adian-rig.svg';
    var size = opts.size || 220;
    injectStyle();
    var prefix = 'adian' + (++instanceCounter) + '-';

    function fallback() {
      // e.g. opened via file:// where fetch is blocked: show a static image, keep the API working.
      container.innerHTML = '';
      var img = document.createElement('img');
      img.src = src; img.alt = '阿電'; img.style.width = size + 'px'; img.style.height = 'auto';
      container.appendChild(img);
      return new Avatar(container, null, prefix, size);
    }

    if (typeof fetch !== 'function') return Promise.resolve(fallback());
    return fetch(src).then(function (res) {
      if (!res.ok) throw new Error('HTTP ' + res.status);
      return res.text();
    }).then(function (txt) {
      var wrap = document.createElement('div');
      wrap.className = 'adian-avatar';
      wrap.innerHTML = prefixIds(txt.replace(/<\?xml[^>]*>/, ''), prefix);
      var svg = wrap.querySelector('svg');
      if (!svg) throw new Error('no <svg> in ' + src);
      svg.setAttribute('role', 'img');
      svg.setAttribute('aria-label', '阿電');
      container.innerHTML = '';
      container.appendChild(wrap);
      return new Avatar(container, svg, prefix, size);
    }).catch(function (err) {
      if (window.console) console.warn('[AdianAvatar] could not inline SVG, using static image:', err);
      return fallback();
    });
  }

  window.AdianAvatar = {
    mount: mount,
    voiceSupported: voiceSupported,
    moods: MOODS.slice(),
    getVoice: function () { return chosenVoice || pickVoice(); },
    listVoices: function () { return voiceSupported ? mandarinVoices() : []; },
    setTTSServer: function (url) { ttsServer = url ? String(url).replace(/\/+$/, '') : null; },
    getTTSServer: function () { return ttsServer; },
    useBrowserVoice: function (on) { browserVoiceAllowed = !!on; },
    unlockAudio: unlockAudio,
    cancelPending: cancelPending,
    // volume 0–1 (remembered in this browser); muted keeps lip-sync running
    setVolume: setVolume,
    getVolume: function () { return volume; },
    setMuted: setMuted,
    isMuted: function () { return muted; },
    onVolumeChange: function (fn) { if (typeof fn === 'function') volListeners.push(fn); },
    volumeControl: volumeControl,
    // warm the cache for the first sentence of a line that is about to be spoken
    prefetch: function (text) { if (ttsServer && getAudioCtx()) fetchStream(serverParts(String(text).trim())[0]); },
    // warm the cache so the next line plays instantly (errors ignored)
    setPreferredVoice: function (name) { preferredVoiceName = name || null; return pickVoice(); },
    onVoicesChanged: function (fn) {
      if (!voiceSupported) return;
      try { synth.addEventListener('voiceschanged', fn); } catch (e) { /* ignore */ }
    }
  };
})();
