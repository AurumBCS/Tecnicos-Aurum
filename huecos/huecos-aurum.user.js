// ==UserScript==
// @name         Huecos Aurum
// @namespace    https://aurumbcs.github.io/Tecnicos-Aurum/
// @version      2026.11.02.1511
// @description  Lista de llamadas para rellenar huecos de técnicos y asignar a la hora pedida, encima de Oracle Field Service.
// @author       Aurum BC Security SL
// @match        https://securitasdirect.fs.ocs.oraclecloud.com/*
// @run-at       document-start
// @grant        none
// @updateURL    https://aurumbcs.github.io/Tecnicos-Aurum/huecos/huecos-aurum.user.js
// @downloadURL  https://aurumbcs.github.io/Tecnicos-Aurum/huecos/huecos-aurum.user.js
// ==/UserScript==

(function () {
'use strict';

/* Panel de Anna para rellenar huecos de técnicos (Aurum), encima de Oracle Field Service.
   Anna escribe la matrícula del técnico y el panel:
     1. busca al técnico, su posición en vivo (o su zona) y su ruta de hoy,
     2. pide a Oracle las actividades sin cita alrededor y las ordena para llamar,
     3. asigna la actividad a la hora que pide el cliente y avisa si Oracle no lo permite,
     4. prepara el texto del grupo de WhatsApp y la fila de la hoja para copiar y pegar.
   Los datos de clientes (nombre, teléfono, dirección) solo se muestran: no se guardan.
   Lo único que se guarda (en este navegador) es Mto + resultado + fecha.
   panelHuecos(true) solo instala la captura del token de Oracle; panelHuecos(false) abre o cierra el panel. */
function panelHuecos(soloGanchos) {
  var KEY = 'aurumHuecos.v1';
  var ID = 'aurum-huecos-panel';
  var A = window.__aurumHuecos = window.__aurumHuecos || {};

  // ---------- captura del token y del recurso de quien usa Oracle (de las peticiones que hace Oracle) ----------
  if (!A.hook) {
    A.hook = true;
    var oOpen = XMLHttpRequest.prototype.open, oSend = XMLHttpRequest.prototype.send, oHdr = XMLHttpRequest.prototype.setRequestHeader;
    XMLHttpRequest.prototype.open = function (m, u) { this.__aurumUrl = u; return oOpen.apply(this, arguments); };
    XMLHttpRequest.prototype.setRequestHeader = function (k, v) { if (k === 'X-OFS-CSRF-SECURE') A.csrf = v; return oHdr.apply(this, arguments); };
    XMLHttpRequest.prototype.send = function (b) {
      // La sincronización de Oracle lleva un dato de sesión ("trust") que hace falta para leer la ficha completa
      if (typeof FormData !== 'undefined' && b instanceof FormData && /m=sync/.test(this.__aurumUrl || '')) {
        try { if (b.get('trust')) A.trust = b.get('trust'); if (b.get('u')) A.login = b.get('u'); } catch (e) {}
      }
      if (typeof b === 'string') {
        try {
          if (/nearbyjobs&a=list/.test(this.__aurumUrl || '')) A.pid = JSON.parse(decodeURIComponent(b.replace(/^_ajax_json_packed_data=/, '').replace(/\+/g, ' '))).pid;
          else if (/m=map&a=coordinates/.test(this.__aurumUrl || '') && !A.pid) { var m = b.match(/(?:^|&)pid=(\d+)/); if (m) A.pid = +m[1]; }
        } catch (e) {}
      }
      return oSend.call(this, b);
    };
  }
  if (soloGanchos) return;

  var viejo = document.getElementById(ID);
  if (viejo) { viejo.remove(); var vb0 = document.getElementById(ID + '-volver'); if (vb0) vb0.remove(); return; }

  // Oracle guarda el token y el recurso de quien ha iniciado sesión; si no, se usan los capturados de sus peticiones
  function leerSesion() {
    var md = window.$md || {}, ls = {};
    try { ls = { tok: localStorage.getItem('CSRFSecureToken'), pid: localStorage.getItem('pid') }; } catch (e) {}
    A.csrf = md.CSRFSecureToken || ls.tok || A.csrf;
    A.pid = +(md.pid || ls.pid || A.pid) || A.pid;
  }
  function cabeceras() {
    leerSesion();
    return { 'Accept': 'application/json, text/javascript, */*; q=0.01', 'Content-Type': 'application/x-www-form-urlencoded', 'X-OA': '2', 'X-OFS-CSRF-SECURE': A.csrf || '', 'X-OFSC-BACKGROUND-PROCESS': '1', 'X-PLATFORM': '1', 'X-Requested-With': 'XMLHttpRequest' };
  }
  function post(url, cuerpo) {
    return fetch(url, { method: 'POST', headers: cabeceras(), body: cuerpo, credentials: 'same-origin' }).then(function (r) { return r.json(); }).then(function (j) {
      if (j && j.errorNo) throw new Error('Oracle: ' + j.errorNo);
      return j;
    });
  }
  function empaquetar(o) { return '_ajax_json_packed_data=' + encodeURIComponent(JSON.stringify(o)); }
  // Si Oracle aún no ha cargado la sesión, se espera un poco
  function esperarToken() {
    return new Promise(function (ok, ko) {
      leerSesion();
      if (A.csrf && A.pid) return ok();
      var i = 0, t = setInterval(function () {
        leerSesion();
        if (A.csrf && A.pid) { clearInterval(t); ok(); }
        else if (++i > 30) { clearInterval(t); ko(new Error('Oracle aún no ha cargado la sesión. Recarga Oracle y vuelve a pulsar Buscar.')); }
      }, 500);
    });
  }

  // ---------- registro (solo Mto, sin datos personales) ----------
  function leerReg() { try { return JSON.parse(localStorage.getItem(KEY)) || {}; } catch (e) { return {}; } }
  function guardarReg(r) { try { localStorage.setItem(KEY, JSON.stringify(r)); } catch (e) { alert('No se pudo guardar el registro en este navegador.'); } }
  function iso(d) { return d.getFullYear() + '-' + ('0' + (d.getMonth() + 1)).slice(-2) + '-' + ('0' + d.getDate()).slice(-2); }
  function hoyISO() { return iso(new Date()); }
  function ahoraTxt() { var d = new Date(); return ('0' + d.getDate()).slice(-2) + '/' + ('0' + (d.getMonth() + 1)).slice(-2) + ' ' + ('0' + d.getHours()).slice(-2) + ':' + ('0' + d.getMinutes()).slice(-2); }
  function diasAtras(n) { var r = [], d = new Date(); while (r.length < n) { d.setDate(d.getDate() - 1); if (d.getDay() !== 0 && d.getDay() !== 6) r.push(iso(d)); } return r; }
  function hhmm(min) { return ('0' + Math.floor(min / 60)).slice(-2) + ':' + ('0' + (min % 60)).slice(-2); }
  function aMin(txt) { var m = String(txt || '').match(/^(\d{1,2})[:.h]?(\d{2})?$/); return m ? +m[1] * 60 + +(m[2] || 0) : null; }

  // ---------- técnico ----------
  function buscarTecnico(mat) {
    return post('?m=managedgroup&a=searchResources', 'groupManagement=' + encodeURIComponent(JSON.stringify({ pid: 0, searchQuery: mat }))).then(function (j) {
      var rs = (j.groupManagement && j.groupManagement.resources) || [];
      var r = rs.filter(function (x) { return String(x.external_id) === mat && !x.group; })[0] || rs.filter(function (x) { return !x.group; })[0];
      if (!r) throw new Error('No encuentro al técnico ' + mat + ' en Oracle. Revisa la matrícula.');
      return { pid: r.pid, nombre: r.pname };
    });
  }
  function posicionVivo(pid) {
    return post('index.php?m=map&a=coordinates', 'pid=' + pid + '&params%5Bscreen%5D=activity&f=json').then(function (j) {
      if (j && j.lat && j.time && (Date.now() / 1000 - j.time) < 3 * 3600) return { lat: j.lat, lng: j.lng, hace: Math.round((Date.now() / 1000 - j.time) / 60) };
      return null;
    }).catch(function () { return null; });
  }
  function pedirRutas(pid, dias) {
    var cuerpo = 'entity=route_loading&action=get&data%5Bgroup_id%5D=d_' + pid + '&' + dias.map(function (d) { return 'data%5Bdates%5D%5B%5D=' + d; }).join('&') +
      '&data%5Bcurrent_date%5D=' + hoyISO() + '&data%5Bselect_from%5D=1&data%5Bselect_count%5D=20';
    return post('?m=supervisor&a=get', cuerpo).then(function (j) { return (j.data && j.data.routes) || {}; });
  }
  function rutaHoy(pid) {
    return pedirRutas(pid, [hoyISO()]).then(function (R) { return ((R[hoyISO()] || {})[pid] || {}).activitiesList || []; });
  }
  function rutas(pid) {
    return pedirRutas(pid, diasAtras(7).concat([hoyISO()])).then(function (R) {
      var cps = {}, hoy = [], cpUltima = null;
      Object.keys(R).forEach(function (d) {
        var ruta = R[d] && R[d][pid]; if (!ruta) return;
        (ruta.activitiesList || []).forEach(function (a) {
          var id = a.identifier || a.label || '';
          var m = id.match(/CP:\s*(\d{5})/);
          if (d === hoyISO()) { hoy.push(a); if (m && !/Tourline|Nueva Incorporaci|Hueco|Comida/i.test(id)) cpUltima = m[1]; }
          else if (m && !/Tourline|Nueva Incorporaci/i.test(id)) cps[m[1]] = (cps[m[1]] || 0) + 1;
        });
      });
      var cp = Object.keys(cps).sort(function (a, b) { return cps[b] - cps[a]; })[0];
      return { cpHabitual: cp, cpUltima: cpUltima, hoy: hoy };
    });
  }
  function geocodificarCP(cp) {
    return new Promise(function (ok) {
      if (!cp || !(window.google && google.maps && google.maps.Geocoder)) return ok(null);
      new google.maps.Geocoder().geocode({ address: cp + ', España' }, function (res, st) {
        if (st === 'OK' && res[0]) { var l = res[0].geometry.location; ok({ lat: l.lat(), lng: l.lng() }); } else ok(null);
      });
    });
  }

  // ---------- actividades sin cita alrededor ----------
  function cajaKm(c, km) { return { center: { lng: c.lng, lat: c.lat }, xd: km / (111 * Math.cos(c.lat * Math.PI / 180)), yd: km / 111 }; }
  // Oracle devuelve como mucho 100 actividades por petición: si una zona llega a 100, se parte en 4 y se vuelve a pedir
  function pedirCaja(caja, nivel, todas) {
    return post('?m=nearbyjobs&a=list', empaquetar({ pid: A.pid, dq: hoyISO(), sort_by: 1, bounding_box: JSON.stringify(caja), zoom_level: 12, selected: false })).then(function (j) {
      var pn = j.panel || [];
      if (pn.length < 100 || nivel >= 4) { pn.forEach(function (p) { todas[p.aid] = p; }); return; }
      var hx = caja.xd / 2, hy = caja.yd / 2;
      return Promise.all([[-1, -1], [-1, 1], [1, -1], [1, 1]].map(function (s) {
        return pedirCaja({ center: { lng: caja.center.lng + s[0] * hx, lat: caja.center.lat + s[1] * hy }, xd: hx, yd: hy }, nivel + 1, todas);
      }));
    });
  }
  function actividadesCerca(c, km) {
    var todas = {};
    return pedirCaja(cajaKm(c, km), 0, todas).then(function () {
      return Object.keys(todas).map(function (k) { var p = todas[k]; return leerActividad(p.hints && p.hints.ident || '', p, c); }).filter(Boolean);
    });
  }
  function km(a, b) {
    var R = 6371, dLat = (b.lat - a.lat) * Math.PI / 180, dLng = (b.lng - a.lng) * Math.PI / 180;
    var s = Math.sin(dLat / 2) * Math.sin(dLat / 2) + Math.cos(a.lat * Math.PI / 180) * Math.cos(b.lat * Math.PI / 180) * Math.sin(dLng / 2) * Math.sin(dLng / 2);
    return 2 * R * Math.asin(Math.sqrt(s));
  }
  function g(t, re) { var m = t.match(re); return m ? m[1].trim() : ''; }

  // 1 = rápido · 2 = averías y fallos · 3 = ampliaciones · 4 = lento (perimetral, Arlo, cámaras, VF4, cerraduras)
  function rangoTipo(tipo, motivo, itemsNum) {
    var ti = tipo.toLowerCase(), mo = motivo.toLowerCase();
    if (/perimetral|arlo|c[aá]mara|vf4|smartlock|cerradura/.test(ti + ' ' + mo)) return 4;
    if (/desmontaje|pilas|reubicaci/.test(ti)) return 1;
    if (/bloqueo/.test(ti) && itemsNum <= 10) return 1;
    if (/ampliaci/.test(ti)) return 3;
    return 2;
  }
  function leerActividad(t, p, centro) {
    t = t.replace(/\s+/g, ' ').trim();
    var mto = g(t, /Mto:\s*(\d+)/);
    if (!mto) return null;
    var partes = g(t, /Panel:\s*(.*?)CP:/).split('-');
    var items = g(t, /((?:>\s*)?\d+(?:-\d+)?)\s*items/);
    var itemsNum = items ? parseInt(items.replace(/[^\d]/g, ' ').trim().split(' ')[0], 10) + (/>/.test(items) ? 1 : 0) : 15;
    var motivo = g(t, /TEXTO\s*-?\s*(.*)$/).replace(/\*{4}.*$/, '').trim();
    var tipo = g(t, /Tipo:\s*(.*?)Panel:/);
    var pos = p && p.y ? { lat: p.y, lng: p.x } : null;
    // El texto puede empezar por la franja ("00:00-00:35 - N-Tienda…"): se quita antes de mirar si es negocio
    var inicio = t.replace(/^\s*\d\d:\d\d\s*-\s*\d\d:\d\d\s*/, '');
    return {
      mto: mto, aid: p && p.aid, bucket: p && p.pid, tipo: tipo,
      negocio: /^\s*-?\s*N-/.test(inicio),
      // Naves, oficinas, talleres…: en el mapa de Oracle no salen con estrella, pero atienden en horario laboral
      oficina: /^\s*-?\s*N-/.test(inicio) && /nave|oficina|empresa|industrial|taller|almac|pol[ií]gono|obra/i.test(g(inicio, /^\s*-?\s*N-([^-]+?)\s*-/)),
      inmueble: g(inicio, /^\s*-?\s*([PN]-[^-]+?)\s*-/),
      pueblo: (partes[1] || '').trim(), calle: partes.slice(2).join('-').trim(), cp: g(t, /CP:\s*(\d{5})/),
      nombre: g(t, /Nombre:\s*(.*?)Tlf:/), tlf: g(t, /Tlf:\s*([\d\s+]{6,})/).replace(/\s/g, ''),
      items: items, itemsNum: itemsNum, min: p && p.length || null,
      motivo: motivo, ultimoTrabajo: g(t, /Observaciones:\s*(.*?)\*{4}/),
      km: pos && centro ? km(centro, pos) : null,
      rango: rangoTipo(tipo, motivo, itemsNum)
    };
  }

  // ---------- orden ----------
  function banda(k) { return k == null ? 3 : k <= 5 ? 0 : k <= 10 ? 1 : k <= 20 ? 2 : 3; }
  function ordenar(lista, reg) {
    var hoy = hoyISO();
    function clave(a) {
      var r = reg[a.mto] || {};
      // Citas pedidas para hoy; luego negocios, pero solo dentro de los 10 km
      return [r.estado === 'cita' && r.fecha === hoy ? 0 : 1, a.km != null && a.km <= 10 ? 0 : 1, a.negocio ? 0 : 1, banda(a.km), a.rango, a.itemsNum, a.min == null ? 60 : a.min];
    }
    return lista.sort(function (x, y) {
      var a = clave(x), b = clave(y);
      for (var i = 0; i < a.length; i++) if (a[i] !== b[i]) return a[i] - b[i];
      return (x.km || 0) - (y.km || 0);
    });
  }
  function visible(a, reg) {
    var r = reg[a.mto];
    if (!r) return true;
    if (r.estado === 'asignado') return false;
    if (r.estado === 'noquiere') return r.hasta !== 'siempre' && r.hasta < hoyISO();
    if (r.estado === 'cita') return r.fecha <= hoyISO();
    return true;
  }

  // ---------- interfaz ----------
  var css = '#' + ID + '{position:fixed;top:60px;right:8px;width:460px;max-width:calc(100vw - 16px);bottom:8px;z-index:2147483000;background:#fff;color:#1d1d1f;border:1px solid #c9c9c9;border-radius:10px;box-shadow:0 6px 24px rgba(0,0,0,.25);font:13px/1.35 system-ui,-apple-system,Segoe UI,sans-serif;display:flex;flex-direction:column}' +
    '#' + ID + ' header{padding:10px 12px;border-bottom:1px solid #e5e5e5;display:flex;flex-wrap:wrap;gap:6px;align-items:center}' +
    '#' + ID + ' header b{flex:1 1 auto;font-size:15px}' +
    '#' + ID + ' input,#' + ID + ' select,#' + ID + ' textarea{font:inherit;padding:5px 7px;border:1px solid #bbb;border-radius:6px}' +
    '#' + ID + ' button{font:inherit;padding:4px 8px;border:1px solid #bbb;border-radius:6px;background:#f5f5f5;cursor:pointer}' +
    '#' + ID + ' button.pri{background:#1d1d1f;color:#fff;border-color:#1d1d1f}' +
    '#' + ID + ' button:disabled{opacity:.5;cursor:default}' +
    '#' + ID + ' .tec{padding:8px 12px;background:#f6f6f6;border-bottom:1px solid #e5e5e5;font-size:12px;display:none}' +
    '#' + ID + ' .lst{overflow:auto;flex:1;padding:6px 10px}' +
    '#' + ID + ' .act{border:1px solid #e3e3e3;border-radius:8px;padding:8px;margin:6px 0}' +
    '#' + ID + ' .act.neg{border-left:4px solid #e6b800}' +
    '#' + ID + ' .act.cita{background:#eef6ff}' +
    '#' + ID + ' .top{display:flex;justify-content:space-between;gap:6px;font-weight:600}' +
    '#' + ID + ' .sub{color:#555;margin:2px 0}' +
    '#' + ID + ' .mot{margin:4px 0}' +
    '#' + ID + ' .nota{color:#b3261e;font-size:12px}' +
    '#' + ID + ' .bien{color:#1a7f37;font-weight:600}' +
    '#' + ID + ' .mal{color:#b3261e;font-weight:600}' +
    '#' + ID + ' .tel{font-size:15px;font-weight:600;color:#0a58ca;text-decoration:none}' +
    '#' + ID + ' .btns{display:flex;flex-wrap:wrap;gap:4px;margin-top:6px}' +
    '#' + ID + ' .caja{margin-top:8px;padding:8px;border:1px dashed #999;border-radius:8px;background:#fafafa}' +
    '#' + ID + ' .ruta{margin:4px 0;font-size:12px}' +
    '#' + ID + ' .ruta div{padding:1px 0}' +
    '#' + ID + ' .pie{padding:6px 12px;border-top:1px solid #e5e5e5;color:#666;font-size:12px}';

  function el(tag, attrs, txt) {
    var e = document.createElement(tag);
    if (attrs) for (var k in attrs) { if (k === 'class') e.className = attrs[k]; else e.setAttribute(k, attrs[k]); }
    if (txt != null) e.textContent = txt;
    return e;
  }

  var st = el('style'); st.textContent = css;
  var p = el('div', { id: ID }); p.appendChild(st);
  var head = el('header');
  head.appendChild(el('b', null, 'Huecos · lista de llamadas'));
  var bCerrar = el('button', null, '✕');
  head.appendChild(bCerrar);
  var fila = el('div'); fila.style.cssText = 'display:flex;gap:6px;flex:1 1 100%';
  var inMat = el('input', { placeholder: 'Matrícula del técnico', size: '14', inputmode: 'numeric' });
  var selKm = el('select');
  [10, 20, 30].forEach(function (k) { selKm.appendChild(el('option', { value: k }, k + ' km')); });
  var bBuscar = el('button', { class: 'pri' }, 'Buscar');
  fila.appendChild(inMat); fila.appendChild(selKm); fila.appendChild(bBuscar);
  head.appendChild(fila);
  var fila2 = el('div'); fila2.style.cssText = 'display:flex;flex-wrap:wrap;gap:6px;align-items:center;flex:1 1 100%';
  fila2.appendChild(el('span', null, 'Buscar cerca de'));
  var selCentro = el('select');
  [['ultima', 'su última actividad de hoy'], ['vivo', 'su posición en vivo'], ['habitual', 'su zona habitual'], ['sitio', 'un sitio que escribo…']].forEach(function (o) { selCentro.appendChild(el('option', { value: o[0] }, o[1])); });
  fila2.appendChild(selCentro);
  // Para cuando la supervisora pide mandarlo fuera de su zona (p. ej. "Aranjuez")
  var inSitio = el('input', { placeholder: 'Pueblo, calle o CP (p. ej. Aranjuez)', size: '24' });
  inSitio.style.display = 'none';
  fila2.appendChild(inSitio);
  head.appendChild(fila2);
  // Pestañas para ver solo negocios o solo residencias (p. ej. en festivo los negocios están cerrados)
  var filtro = 'todos';
  try { filtro = localStorage.getItem(KEY + '.filtro') || 'todos'; } catch (e) {}
  var pestanas = el('div'); pestanas.style.cssText = 'display:flex;gap:0;flex:1 1 100%;border:1px solid #bbb;border-radius:6px;overflow:hidden';
  [['todos', 'Todos'], ['negocios', '★ Tiendas y locales'], ['naves', '🏢 Naves y oficinas'], ['residencias', 'Residencias']].forEach(function (o) {
    var b = el('button', { 'data-f': o[0] }, o[1]); b.style.cssText = 'flex:1;border:0;border-radius:0;margin:0';
    b.onclick = function () { filtro = o[0]; try { localStorage.setItem(KEY + '.filtro', filtro); } catch (e) {} marcarPestana(); pintar(); };
    pestanas.appendChild(b);
  });
  function marcarPestana() {
    Array.prototype.forEach.call(pestanas.children, function (b) { var on = b.getAttribute('data-f') === filtro; b.style.background = on ? '#1d1d1f' : '#f5f5f5'; b.style.color = on ? '#fff' : '#1d1d1f'; });
  }
  marcarPestana();
  head.appendChild(pestanas);
  var tec = el('div', { class: 'tec' });
  var lst = el('div', { class: 'lst' });
  var pie = el('div', { class: 'pie' });
  p.appendChild(head); p.appendChild(tec); p.appendChild(lst); p.appendChild(pie);
  document.body.appendChild(p);

  bCerrar.onclick = function () { p.remove(); };
  try { inMat.value = localStorage.getItem(KEY + '.mat') || ''; } catch (e) {}
  inMat.onkeydown = function (e) { if (e.key === 'Enter') buscar(); };

  var datos = [], tecnico = null;

  function registrar(mto, cambio) {
    var reg = leerReg();
    var r = reg[mto] || { intentos: [] };
    for (var k in cambio) r[k] = cambio[k];
    reg[mto] = r; guardarReg(reg); pintar();
  }

  // ---------- asignar a la hora que pide el cliente ----------
  function etiqueta(a) {
    var id = a.identifier || a.label || '';
    if (/Comida/i.test(id)) return 'Comida';
    if (/Tourline/i.test(id)) return 'Tourline';
    if (/Hueco/i.test(id)) return 'Hueco';
    var tipo = g(id, /Tipo:\s*(.*?)Panel:/), cp = g(id, /CP:\s*(\d{5})/), mto = g(id, /Mto:\s*(\d+)/);
    return (tipo || (a.label || 'Actividad').slice(0, 30)) + (cp ? ' (' + cp + ')' : '') + (mto ? ' · ' + mto : '');
  }
  function enRuta(lista) { return lista.filter(function (a) { return typeof a.eta === 'number' && !/Nueva Incorporaci/i.test(a.identifier || a.label || ''); }); }
  // La actividad nueva va detrás de la última que termina antes de la hora pedida
  function propuesta(lista, horaMin) {
    var mejor = null;
    lista.forEach(function (a) { if (a.eta + (a.length || 0) <= horaMin) mejor = a; });
    return mejor;
  }

  function abrirAsignar(a, tarjetaEl) {
    var previa = tarjetaEl.querySelector('.caja.asig'); if (previa) { previa.remove(); return; }
    var caja = el('div', { class: 'caja asig' });
    caja.appendChild(el('div', null, 'Ruta de hoy de ' + tecnico.nombre + ':'));
    var ruta = el('div', { class: 'ruta' }, 'Cargando…'); caja.appendChild(ruta);
    var f1 = el('div'); f1.style.cssText = 'display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin-top:6px';
    f1.appendChild(el('span', null, 'Hora que pide'));
    var inHora = el('input', { placeholder: '13:00', size: '5' });
    f1.appendChild(inHora);
    f1.appendChild(el('span', null, 'detrás de'));
    var selPrev = el('select'); selPrev.style.maxWidth = '230px';
    f1.appendChild(selPrev);
    caja.appendChild(f1);
    var bAsig = el('button', { class: 'pri' }, 'Asignar');
    var res = el('div'); res.style.marginTop = '6px';
    var bs = el('div', { class: 'btns' }); bs.appendChild(bAsig); caja.appendChild(bs); caja.appendChild(res);
    tarjetaEl.appendChild(caja);

    var lista = [];
    rutaHoy(tecnico.pid).then(function (l) {
      lista = enRuta(l);
      ruta.textContent = '';
      if (!lista.length) { ruta.textContent = 'No tiene actividades hoy en Oracle.'; bAsig.disabled = true; return; }
      lista.forEach(function (x) {
        ruta.appendChild(el('div', null, hhmm(x.eta) + '–' + hhmm(x.eta + (x.length || 0)) + '  ' + etiqueta(x)));
        selPrev.appendChild(el('option', { value: x.aid }, 'termina ' + hhmm(x.eta + (x.length || 0)) + ' · ' + etiqueta(x)));
      });
    }).catch(function (e) { ruta.textContent = e.message; });

    // Aviso previo: si lo que viene detrás empieza antes de que el técnico pueda acabar la nueva, se retrasará
    function revisar() {
      var h = aMin(inHora.value.trim()), prev = +selPrev.value;
      var i = lista.map(function (x) { return x.aid; }).indexOf(prev), sig = lista[i + 1], prevAct = lista[i];
      res.className = ''; res.textContent = '';
      if (h == null || !prevAct) return;
      var fin = Math.max(prevAct.eta + (prevAct.length || 0), h) + (a.min || 45);
      if (sig && sig.eta < fin) { res.className = 'mal'; res.textContent = 'Ojo: lo siguiente (' + hhmm(sig.eta) + ' ' + etiqueta(sig) + ') se retrasará unos ' + (fin - sig.eta) + ' min o más (sin contar el viaje).'; }
    }
    inHora.oninput = function () {
      var h = aMin(inHora.value.trim()); if (h == null) return;
      var prop = propuesta(lista, h);
      if (prop) selPrev.value = prop.aid;
      revisar();
      if (!prop) { res.className = 'mal'; res.textContent = 'A esa hora el técnico aún no ha empezado: elige tú detrás de qué actividad va.'; }
    };
    selPrev.onchange = revisar;

    bAsig.onclick = function () {
      var h = aMin(inHora.value.trim());
      if (h == null) { alert('Escribe la hora que pide el cliente (p. ej. 13:00).'); inHora.focus(); return; }
      var prev = +selPrev.value, prevAct = lista.filter(function (x) { return x.aid === prev; })[0];
      if (!prevAct) return;
      if (!confirm('¿Asignar el Mto ' + a.mto + ' a ' + tecnico.nombre + '?\n\nDetrás de: ' + etiqueta(prevAct) + ' (termina ' + hhmm(prevAct.eta + (prevAct.length || 0)) + ')\nHora que pide el cliente: ' + hhmm(h))) return;
      bAsig.disabled = true; res.className = ''; res.textContent = 'Asignando en Oracle…';
      var antes = {}; lista.forEach(function (x) { antes[x.aid] = x.eta; });
      post('index.php?m=activity&a=assignment', empaquetar({
        pid: A.pid, target_pid: tecnico.pid, loadListOnly: 1, listType: 'providers', target_date: hoyISO(),
        get_data: false, form_submitted: true,
        moving_activities: [{ aid: a.aid, prev: prev, date: '3000-01-01', pid: String(a.bucket) }]
      })).then(function (j) {
        if (!j || j.result !== 'success') throw new Error('Oracle no ha permitido la asignación' + (j && (j.message || j.error) ? ': ' + (j.message || j.error) : '.'));
        return rutaHoy(tecnico.pid);
      }).then(function (l) {
        var nueva = l.filter(function (x) { return x.aid === a.aid; })[0];
        if (!nueva) throw new Error('Oracle dice que la ha asignado, pero no aparece en la ruta del técnico. Revísalo en Oracle.');
        var eta = nueva.eta, dif = eta - h;
        res.className = Math.abs(dif) <= 30 ? 'bien' : 'mal';
        // Qué actividades del técnico ha movido Oracle al meter la nueva (la comida no cuenta)
        var movidas = enRuta(l).filter(function (x) { return antes[x.aid] != null && Math.abs(x.eta - antes[x.aid]) >= 15 && !/Comida/i.test(x.identifier || x.label || ''); })
          .map(function (x) { return etiqueta(x) + ' ' + hhmm(antes[x.aid]) + '→' + hhmm(x.eta); });
        res.textContent = 'Asignada. Oracle la pone a las ' + hhmm(eta) + ' (el cliente pidió ' + hhmm(h) + ').' +
          (Math.abs(dif) > 30 ? ' Ojo: hay ' + Math.abs(dif) + ' min de diferencia; cámbiala en Oracle o avisa al cliente.' : '') +
          (movidas.length ? ' Se han movido: ' + movidas.join('; ') + '.' : '');
        if (movidas.length) res.className = 'mal';
        a.horaAsignada = hhmm(eta);
        avisoAsignada(a, tarjetaEl);
      }).catch(function (e) {
        res.className = 'mal'; res.textContent = e.message; bAsig.disabled = false;
      });
    };
  }

  // ---------- todos los contactos (los de la ficha completa: móvil, fijo y personas de contacto) ----------
  function fichaCompleta(a) {
    var md = window.$md || {};
    var f = new FormData();
    [['__protocol', '7'], ['dv', A.dvSync || '{}'], ['pid', String(a.bucket)], ['u', A.login || (md.offline && md.offline.login) || ''], ['f', 'json'],
      ['pids', '[]'], ['aids', '[]'], ['restriction', '0'], ['qid', 'undefined'], ['fakeIds', '{}'], ['trust', A.trust], ['fakeIdsClean', '0'],
      ['dq', hoyISO()], ['date', hoyISO()], ['dispatcher', '1'], ['requestedAid', String(a.aid)], ['requestedDate', hoyISO()], ['skip_delta', '0']
    ].forEach(function (x) { f.append(x[0], x[1]); });
    var h = cabeceras(); delete h['Content-Type'];
    return fetch('?m=sync&a=write&ajax=1', { method: 'POST', headers: h, body: f, credentials: 'same-origin' }).then(function (r) { return r.json(); }).then(function (j) {
      if (j.delta && j.delta.version) A.dvSync = JSON.stringify(j.delta.version);   // las siguientes peticiones vienen mucho más ligeras
      return ((j.delta && j.delta.Activity) || {})[a.aid] || null;
    });
  }
  function camposBasicos(a) {
    var campos = ['cname', 'ccell', 'cphone'].map(function (c) { return '&data%5Bfields%5D%5B%5D=' + c; }).join('');
    return post('index.php?m=supervisor&a=get', 'entity=activity&action=get&data%5Baid%5D=' + a.aid + campos + '&f=json').then(function (j) { return (j.data && j.data.activity) || null; });
  }
  // Una sola petición por actividad para contactos y zonas
  var fichas = {};
  function ficha(a) {
    if (!fichas[a.aid]) fichas[a.aid] = (A.trust && a.bucket ? fichaCompleta(a).then(function (f) { return f || camposBasicos(a); }) : camposBasicos(a))
      .catch(function (e) { delete fichas[a.aid]; throw e; });
    return fichas[a.aid];
  }
  function contactos(a) {
    return ficha(a).then(function (f) {
      var lista = [];
      if (!f) return lista;
      if (f.ccell) lista.push({ etiqueta: 'Móvil', nombre: f.cname, tel: f.ccell });
      if (f.cphone) lista.push({ etiqueta: 'Fijo', nombre: f.cname, tel: f.cphone });
      // Propiedad 154 = "Personas de Contacto": tabla HTML con nombre y teléfono
      if (f['154']) {
        var doc = new DOMParser().parseFromString(String(f['154']), 'text/html');
        Array.prototype.forEach.call(doc.querySelectorAll('tr'), function (tr) {
          var td = tr.querySelectorAll('td');
          if (td.length >= 2) lista.push({ etiqueta: 'Contacto', nombre: td[0].textContent.trim(), tel: td[1].textContent.trim() });
        });
      }
      var vistos = {};
      return lista.filter(function (c) { var t = String(c.tel).replace(/\D/g, ''); if (!t || vistos[t]) return false; vistos[t] = 1; return true; });
    });
  }
  function pintarContactos(a, caja) {
    caja.textContent = 'Cargando contactos…';
    contactos(a).then(function (lista) {
      caja.textContent = '';
      if (!lista.length) { caja.textContent = 'Oracle no devuelve más contactos.'; return; }
      lista.forEach(function (c) {
        var fila = el('div'); fila.style.cssText = 'display:flex;gap:8px;align-items:baseline;flex-wrap:wrap';
        fila.appendChild(el('span', { class: 'sub' }, c.etiqueta));
        fila.appendChild(el('span', null, c.nombre || ''));
        fila.appendChild(el('a', { class: 'tel', href: 'tel:' + String(c.tel).replace(/\s/g, '') }, c.tel));
        caja.appendChild(fila);
      });
    }).catch(function () { caja.textContent = 'No se pudieron leer los contactos.'; });
  }

  // ---------- zonas de la instalación (propiedad 186: ID, versión, tipo, detector, descripción) ----------
  function zonas(f) {
    if (!f || !f['186']) return null;
    var doc = new DOMParser().parseFromString(String(f['186']), 'text/html');
    return Array.prototype.map.call(doc.querySelectorAll('tr'), function (tr) {
      var td = Array.prototype.map.call(tr.querySelectorAll('td'), function (x) { return x.textContent.trim(); });
      return td.length >= 6 ? { id: td[1], tipo: td[3], detector: td[4], descripcion: td[5] } : null;
    }).filter(Boolean);
  }
  function desplegableZonas(a) {
    var d = el('details'); d.style.margin = '4px 0';
    var s = el('summary', null, 'Zonas (ver)'); s.style.cursor = 'pointer';
    var cuerpo = el('div', { class: 'sub' });
    d.appendChild(s); d.appendChild(cuerpo);
    var cargado = false;
    function cargar() {
      if (cargado) return; cargado = true;
      cuerpo.textContent = 'Cargando zonas…';
      ficha(a).then(function (f) {
        var z = zonas(f);
        cuerpo.textContent = '';
        if (!z) { s.textContent = 'Zonas (sin datos)'; cuerpo.textContent = 'Oracle no devuelve las zonas. Recarga Oracle y vuelve a buscar.'; cargado = false; return; }
        // Resumen por código de zona ("MG ×3 · QR ×2 · FR ×1"): el detector a veces viene vacío, el código siempre
        var cuenta = {};
        z.forEach(function (x) { var k = (x.id || '').replace(/\d+$/, '') || (x.detector.split(' - ')[0] || '?').trim(); cuenta[k] = (cuenta[k] || 0) + 1; });
        s.textContent = 'Zonas (' + z.length + '): ' + Object.keys(cuenta).map(function (k) { return k + ' ×' + cuenta[k]; }).join(' · ');
        var t = el('table'); t.style.cssText = 'border-collapse:collapse;width:100%;font-size:12px;margin-top:4px';
        z.forEach(function (x) {
          var tr = el('tr');
          [x.id, x.descripcion, x.detector].forEach(function (v) { var td = el('td', null, v); td.style.cssText = 'border-top:1px solid #eee;padding:2px 4px;vertical-align:top'; tr.appendChild(td); });
          t.appendChild(tr);
        });
        cuerpo.appendChild(t);
      }).catch(function () { cuerpo.textContent = 'No se pudieron leer las zonas.'; cargado = false; });
    }
    d.addEventListener('toggle', function () { if (d.open) cargar(); });
    d.cargar = cargar;
    return d;
  }

  // ---------- aviso tras asignar: texto para el grupo de WhatsApp y fila para la hoja ----------
  function numeroInstalacion(a) {
    return post('index.php?m=supervisor&a=get', 'entity=activity&action=get&data%5Baid%5D=' + a.aid + '&f=json').then(function (j) {
      return (j.data && j.data.activity && j.data.activity.customer_number) || '';
    }).catch(function () { return ''; });
  }
  function copiar(texto, boton) {
    function ok() { var t = boton.textContent; boton.textContent = 'Copiado ✔'; setTimeout(function () { boton.textContent = t; }, 1500); }
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(texto).then(ok, function () { copiarViejo(texto); ok(); });
    else { copiarViejo(texto); ok(); }
  }
  function copiarViejo(texto) {
    var ta = el('textarea'); ta.value = texto; ta.style.cssText = 'position:fixed;left:-9999px'; document.body.appendChild(ta); ta.select();
    try { document.execCommand('copy'); } catch (e) {}
    ta.remove();
  }
  function nombreTecnico() { return tecnico.nombre.replace(/^.*?\d{5,}-/, '').trim(); }   // "💰E-V-362045-Juan Manuel…" → "Juan Manuel…"
  function avisoAsignada(a, tarjetaEl) {
    if (tarjetaEl.querySelector('.caja.aviso')) return;
    var caja = el('div', { class: 'caja aviso' });
    var inst = el('input', { placeholder: 'Nº instalación' }); inst.style.width = '110px';
    var estado = el('input', { value: 'ASIGNADA' }); estado.style.width = '100px';
    var obs = el('textarea', { rows: '2', placeholder: 'Observación (p. ej. clínica dental, a las 5 habló con…)' }); obs.style.cssText = 'width:100%;box-sizing:border-box;margin-top:6px';
    if (a.horaAsignada) obs.value = 'a las ' + a.horaAsignada + ' ';
    var f1 = el('div'); f1.style.cssText = 'display:flex;gap:6px;align-items:center;flex-wrap:wrap';
    f1.appendChild(el('span', null, 'Instalación')); f1.appendChild(inst); f1.appendChild(el('span', null, 'Estado')); f1.appendChild(estado);
    var bW = el('button', { class: 'pri' }, 'Copiar para WhatsApp');
    var bX = el('button', { class: 'pri' }, 'Copiar fila Excel');
    var bOk = el('button', null, 'Hecho, quitar de la lista');
    var bs = el('div', { class: 'btns' }); [bW, bX, bOk].forEach(function (b) { bs.appendChild(b); });
    caja.appendChild(f1); caja.appendChild(obs); caja.appendChild(bs);
    tarjetaEl.appendChild(caja);
    numeroInstalacion(a).then(function (n) { if (!inst.value) inst.value = n; });
    bW.onclick = function () {
      copiar(tecnico.nombre.replace(/^[^A-Za-z]+/, '') + ', \nNúmero de Instalación\n' + inst.value.trim() + '\nNúmero de Mantenimiento\n' + a.mto + (obs.value.trim() ? '\n' + obs.value.trim() : ''), bW);
    };
    bX.onclick = function () {
      var d = new Date(), f = ('0' + d.getDate()).slice(-2) + '-' + ('0' + (d.getMonth() + 1)).slice(-2) + '-' + String(d.getFullYear()).slice(-2);
      copiar([f, nombreTecnico().toUpperCase(), inst.value.trim(), a.mto, '', ''].join('\t'), bX);
    };
    bOk.onclick = function () { registrar(a.mto, { estado: 'asignado', fecha: hoyISO() }); };
  }

  // ---------- tarjetas ----------
  function tarjeta(a, reg, posicion) {
    var r = reg[a.mto] || {};
    var c = el('div', { class: 'act' + (a.negocio ? ' neg' : '') + (r.estado === 'cita' ? ' cita' : '') });
    var top = el('div', { class: 'top' });
    top.appendChild(el('span', null, (a.oficina ? '🏢 ' : a.negocio ? '★ ' : '') + a.tipo));
    top.appendChild(el('span', null, 'Mto ' + a.mto));
    c.appendChild(top);
    c.appendChild(el('div', { class: 'sub' }, [a.km != null ? a.km.toFixed(1) + ' km' : '', a.items ? a.items + ' items' : '', a.min ? a.min + ' min' : '', a.inmueble].filter(Boolean).join(' · ')));
    if (r.estado === 'cita') c.appendChild(el('div', { class: 'nota' }, 'El cliente pidió cita el ' + r.fecha.split('-').reverse().join('/') + ' a las ' + r.hora));
    if (r.intentos && r.intentos.length) c.appendChild(el('div', { class: 'nota' }, 'No contestó: ' + r.intentos.join(', ')));
    // Contactos: de entrada el de la lista; las primeras actividades cargan todos solas, el resto con el botón
    var cont = el('div');
    cont.appendChild(el('div', null, a.nombre || '(sin nombre)'));
    if (a.tlf) cont.appendChild(el('a', { class: 'tel', href: 'tel:' + a.tlf }, a.tlf));
    var bCont = el('button', null, 'Ver todos los contactos'); bCont.style.marginLeft = '8px';
    bCont.onclick = function () { pintarContactos(a, cont); };
    cont.appendChild(bCont);
    c.appendChild(cont);
    c.appendChild(el('div', { class: 'sub' }, [a.calle, a.pueblo, a.cp].filter(Boolean).join(', ')));
    c.appendChild(el('div', { class: 'mot' }, 'Motivo: ' + (a.motivo || '—')));
    var dz = desplegableZonas(a);
    c.appendChild(dz);
    // Las primeras actividades cargan solas contactos y resumen de zonas (es la misma petición)
    if (posicion < 8) { pintarContactos(a, cont); dz.cargar(); }
    if (a.ultimoTrabajo) c.appendChild(el('div', { class: 'sub' }, 'Última visita: ' + a.ultimoTrabajo));

    var bs = el('div', { class: 'btns' });
    var b1 = el('button', { class: 'pri' }, 'Sí → asignar'); b1.onclick = function () { abrirAsignar(a, c); };
    var b2 = el('button', null, 'Ya asignada (copiar)'); b2.onclick = function () { avisoAsignada(a, c); };
    var b3 = el('button', null, 'No contesta'); b3.onclick = function () { var rr = leerReg()[a.mto] || {}; registrar(a.mto, { estado: 'nocontesta', intentos: (rr.intentos || []).concat([ahoraTxt()]) }); };
    var b4 = el('button', null, 'No quiere'); b4.onclick = function () {
      var s = prompt('No quiere el mantenimiento.\nEscribe 1 = descartar para siempre, 2 = descartar 15 días', '2');
      if (s === '1') registrar(a.mto, { estado: 'noquiere', hasta: 'siempre' });
      else if (s === '2') { var d = new Date(); d.setDate(d.getDate() + 15); registrar(a.mto, { estado: 'noquiere', hasta: iso(d) }); }
    };
    var b5 = el('button', null, 'Pide otra hora/día'); b5.onclick = function () {
      var f = prompt('Fecha que pide el cliente (DD/MM)', new Date().toLocaleDateString('es-ES').slice(0, 5));
      if (!f) return;
      var h = prompt('Hora que pide (HH:MM)', '17:00'); if (!h) return;
      var pp = f.split('/');
      registrar(a.mto, { estado: 'cita', fecha: new Date().getFullYear() + '-' + ('0' + pp[1]).slice(-2) + '-' + ('0' + pp[0]).slice(-2), hora: h });
    };
    [b1, b2, b3, b4, b5].forEach(function (b) { bs.appendChild(b); });
    c.appendChild(bs);
    return c;
  }

  function pintar() {
    var reg = leerReg();
    function clase(a) { return a.oficina ? 'naves' : a.negocio ? 'negocios' : 'residencias'; }
    var lista = ordenar(datos.filter(function (a) {
      return visible(a, reg) && (filtro === 'todos' || filtro === clase(a));
    }), reg);
    lst.innerHTML = '';
    if (!tecnico) { lst.appendChild(el('p', null, 'Escribe la matrícula del técnico y pulsa Buscar.')); return; }
    var pendientes = datos.filter(function (a) { return visible(a, reg); });
    var cuenta = { negocios: 0, naves: 0, residencias: 0 };
    pendientes.forEach(function (a) { cuenta[clase(a)]++; });
    var nombres = { negocios: 'tiendas y locales', naves: 'naves ni oficinas', residencias: 'residencias' };
    if (!lista.length) lst.appendChild(el('p', null, !datos.length ? 'No hay actividades sin cita en esta zona. Prueba con más km.' :
      pendientes.length ? 'No hay ' + nombres[filtro] + ' pendientes en esta zona. Cambia de pestaña o prueba con más km.' :
      'Todas las actividades de esta zona ya están gestionadas. Prueba con más km.'));
    lista.forEach(function (a, i) { lst.appendChild(tarjeta(a, reg, i)); });
    var gestionadas = datos.length - pendientes.length;
    pie.textContent = lista.length + ' para llamar · pendientes en la zona: ' + cuenta.negocios + ' tiendas y locales, ' + cuenta.naves + ' naves y oficinas, ' + cuenta.residencias + ' residencias' +
      (gestionadas ? ' · ' + gestionadas + ' ya gestionadas' : '') + '. Los teléfonos no se guardan.';
  }

  function resumenHoy(hoy) {
    return enRuta(hoy).map(function (a) { return hhmm(a.eta) + ' ' + etiqueta(a).replace(/ · \d+$/, ''); }).join(' · ');
  }

  function buscar() {
    var mat = inMat.value.trim();
    if (!/^\w{4,}$/.test(mat)) { alert('Escribe la matrícula del técnico (p. ej. 374754).'); return; }
    try { localStorage.setItem(KEY + '.mat', mat); } catch (e) {}
    datos = []; tecnico = null; lst.innerHTML = ''; tec.style.display = 'none';
    pie.textContent = 'Conectando con Oracle…';
    esperarToken().then(function () {
      pie.textContent = 'Buscando al técnico…';
      return buscarTecnico(mat);
    }).then(function (t) {
      tecnico = t;
      return Promise.all([posicionVivo(t.pid), rutas(t.pid)]);
    }).then(function (res) {
      var vivo = res[0], ru = res[1];
      tecnico.hoy = resumenHoy(ru.hoy);
      // Orden de preferencia según el selector; si una opción no está disponible se pasa a la siguiente
      if (selCentro.value === 'sitio') {
        var sitio = inSitio.value.trim();
        if (!sitio) return Promise.reject(new Error('Escribe el sitio donde buscar (p. ej. Aranjuez).'));
        return geocodificarCP(sitio).then(function (c) {
          if (!c) throw new Error('No encuentro «' + sitio + '». Prueba con el pueblo y la provincia (p. ej. Aranjuez, Madrid).');
          tecnico.centro = c; tecnico.origen = sitio + ' (elegido a mano)';
        });
      }
      var orden = { ultima: ['ultima', 'vivo', 'habitual'], vivo: ['vivo', 'ultima', 'habitual'], habitual: ['habitual', 'ultima', 'vivo'] }[selCentro.value];
      function probar(i) {
        if (i >= orden.length) return Promise.reject(new Error('No sé dónde está ' + tecnico.nombre + ': no tiene posición en vivo ni rutas recientes.'));
        var o = orden[i];
        if (o === 'vivo') { if (vivo) { tecnico.centro = vivo; tecnico.origen = 'posición en vivo (hace ' + vivo.hace + ' min)'; return Promise.resolve(); } return probar(i + 1); }
        var cp = o === 'ultima' ? ru.cpUltima : ru.cpHabitual;
        return geocodificarCP(cp).then(function (c) {
          if (!c) return probar(i + 1);
          tecnico.centro = c; tecnico.origen = (o === 'ultima' ? 'su última actividad de hoy' : 'su zona habitual') + ' (CP ' + cp + ')';
        });
      }
      return probar(0);
    }).then(function () {
      tec.textContent = '';
      tec.appendChild(el('div', null, tecnico.nombre + ' · buscando cerca de ' + tecnico.origen));
      if (tecnico.hoy) tec.appendChild(el('div', null, 'Hoy: ' + tecnico.hoy));
      tec.style.display = 'block';
      pie.textContent = 'Buscando actividades sin cita a ' + selKm.value + ' km…';
      return actividadesCerca(tecnico.centro, +selKm.value);
    }).then(function (lista) {
      datos = lista;
      pintar();
    }).catch(function (e) { pie.textContent = e.message; });
  }

  bBuscar.onclick = buscar;
  selKm.onchange = function () { if (tecnico) buscar(); };
  selCentro.onchange = function () {
    inSitio.style.display = selCentro.value === 'sitio' ? '' : 'none';
    if (selCentro.value === 'sitio') { inSitio.focus(); return; }   // se busca al pulsar Buscar o Enter
    if (tecnico) buscar();
  };
  inSitio.onkeydown = function (e) { if (e.key === 'Enter') buscar(); };
  pintar();
  pie.textContent = 'Escribe la matrícula del técnico y pulsa Buscar.';
  if (inMat.value) inMat.select();
}


// Desde el principio: captura del token de Oracle (las peticiones de Oracle lo llevan)
panelHuecos(true);

// Botón fijo para abrir y cerrar el panel
function botonHuecos() {
  if (!document.body || document.getElementById('aurum-huecos-boton')) return;
  var b = document.createElement('button');
  b.id = 'aurum-huecos-boton';
  b.textContent = 'Huecos';
  b.title = 'Abrir o cerrar el panel de huecos (v2026.11.02.1511)';
  b.style.cssText = 'position:fixed;left:8px;bottom:8px;z-index:2147482999;padding:8px 14px;border-radius:18px;border:0;background:#1d1d1f;color:#fff;font:600 13px system-ui,sans-serif;cursor:pointer;box-shadow:0 2px 8px rgba(0,0,0,.3)';
  b.onclick = function () { panelHuecos(false); };
  document.body.appendChild(b);
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', botonHuecos);
else botonHuecos();
})();
