// 阿電 2.5D (preview): tilt + parallax + moving light + suspension bob, on the layered rig (adian-rig-25d.svg).
// Layers: l-far (far wheels) / l-body (cabin, body, mouth) / l-near (near wheels) / l-face (eyes, brows),
// plus l-shadow (ground shadow) and l-spec (highlight clipped to the car).
(function () {
  var clamp = function (v) { return Math.max(-1, Math.min(1, v)); };

  function enhance(svg, opts) {
    opts = opts || {};
    var q = function (id) { return svg.querySelector('[id="' + id + '"]'); };
    var L = { far: q('l-far'), body: q('l-body'), near: q('l-near'), face: q('l-face'),
              shadow: q('l-shadow'), spec: q('l-spec'), pl: q('pupil-l'), pr: q('pupil-r') };
    var host = opts.host || svg.parentElement;
    var st = { tx: 0, ty: 0, gx: 0, gy: 0, talk: 0, lastInput: -1e9 };
    svg.style.overflow = 'visible';
    svg.style.willChange = 'transform';

    window.addEventListener('pointermove', function (e) {
      var r = host.getBoundingClientRect();
      st.gx = clamp((e.clientX - (r.left + r.width / 2)) / (window.innerWidth / 2));
      st.gy = clamp((e.clientY - (r.top + r.height / 2)) / (window.innerHeight / 2));
      st.lastInput = performance.now();
    });
    window.addEventListener('deviceorientation', function (e) {   // phones: tilt the device
      if (e.gamma == null) return;
      st.gx = clamp(e.gamma / 30); st.gy = clamp((e.beta - 45) / 30);
      st.lastInput = performance.now();
    });

    var set = function (g, x, y) { if (g) g.setAttribute('transform', 'translate(' + x.toFixed(2) + ' ' + y.toFixed(2) + ')'); };

    function frame(now) {
      if (now - st.lastInput > 2500) {           // no input: gentle idle sway
        st.gx = Math.sin(now / 1700) * 0.6;
        st.gy = Math.sin(now / 2300) * 0.3;
      }
      st.tx += (st.gx - st.tx) * 0.08;
      st.ty += (st.gy - st.ty) * 0.08;
      var tx = st.tx, ty = st.ty;
      var talking = opts.isTalking ? opts.isTalking() : false;
      st.talk += ((talking ? 1 : 0) - st.talk) * 0.1;
      // suspension: slow breathing when idle, quick small bounce while talking
      var bob = Math.sin(now / (900 - st.talk * 760)) * (1.2 + st.talk * 1.6);

      svg.style.transform = 'perspective(900px) rotateY(' + (tx * 13).toFixed(2) + 'deg) rotateX(' + (-ty * 7).toFixed(2) + 'deg)';
      set(L.far, -tx * 10, -ty * 3 + bob * 0.3);   // far side moves against the tilt
      set(L.body, tx * 2, ty * 1 + bob);
      set(L.near, tx * 9, ty * 3 + bob * 0.2);    // near wheels and eyes come forward
      set(L.face, tx * 7, ty * 4 + bob);
      if (L.shadow) L.shadow.setAttribute('transform', 'translate(' + (-tx * 12).toFixed(2) + ' 0) translate(275 434) scale(' +
        (1 - bob * 0.012 + Math.abs(tx) * 0.04).toFixed(3) + ' 1) translate(-275 -434)');
      if (L.spec) { L.spec.setAttribute('cx', (300 - tx * 160).toFixed(1)); L.spec.setAttribute('cy', (245 - ty * 40).toFixed(1)); }
      if (opts.pupils !== false && L.pl && L.pr) {  // eyes follow the pointer
        var p = 'translate(' + (st.gx * 5).toFixed(2) + 'px,' + (st.gy * 4).toFixed(2) + 'px)';
        L.pl.style.transform = p; L.pr.style.transform = p;
      }
      requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
    return st;
  }

  window.Adian25D = { enhance: enhance };
})();
