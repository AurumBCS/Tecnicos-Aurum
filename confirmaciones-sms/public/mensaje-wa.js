// Mensaje de confirmación por WhatsApp (16/11/2026: sustituye al SMS). Lo usan tecnico.html y je.html.
// Casa ("P-…" en Tipo de Cliente de Oracle): de tú y con el nombre del cliente. Negocio ("N-…"): de usted.
// Si Oracle no dice qué es, no se nombra ni casa ni negocio.
// quien = { yo: 'Carlos' }       → lo envía el propio técnico ("soy Carlos, el técnico de Verisure… pasaré")
// quien = { tecnico: 'Carlos' }  → lo envía su jefe de equipo ("nuestro técnico Carlos pasará")
const sinAcentos = t => String(t || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
function telefonoDe(c) { return String(c.telefono || '').replace(/\D/g, '').slice(-9); }
function nombreDePila(texto) {
  // "Apellidos, Nombre", "Nombre Apellidos" o "Nombre Apellidos (matrícula)"; una matrícula sola no es un nombre
  const t = String(texto || '').replace(/\(.*?\)/g, '').trim();
  let n = (t.includes(',') ? t.split(',')[1] : t).trim().split(/\s+/)[0] || '';
  if (/\d/.test(n)) return '';
  return n ? n.charAt(0).toUpperCase() + n.slice(1).toLowerCase() : '';
}

// Nombre del mantenimiento en palabras del cliente (los de Oracle son internos)
function tareaDe(tipo, usted) {
  const t = sinAcentos(tipo), su = usted ? 'la' : 'tu', sus = usted ? 'las' : 'tus';
  if (/desmontaje/.test(t)) return 'retirar los equipos de la alarma';
  if (/\banp\b|\bamp\b|documentacion/.test(t)) return 'hacer el cambio de titular de la alarma';
  if (/pilas/.test(t)) return `cambiar las pilas de un elemento de ${su} alarma`;
  if (/supervision/.test(t)) return `revisar un elemento de ${su} alarma que no comunica bien`;
  if (/gsm|cobertura/.test(t)) return `revisar la comunicación de ${su} alarma`;
  if (/falsas/.test(t)) return 'revisar los saltos de alarma';
  if (/smartlock/.test(t)) return `revisar ${su} cerradura inteligente`;
  if (/aver.*arlo/.test(t)) return `revisar ${su} cámara`;
  if (/arlo|camara/.test(t)) return /\b([2-9]|\d{2,})\b/.test(t) ? `instalar ${sus} nuevas cámaras` : `instalar ${su} nueva cámara`;
  if (/ampliacion|campana|zerovision/.test(t)) return `instalar los nuevos elementos de ${su} alarma`;
  if (/reubicacion/.test(t)) return `cambiar de sitio elementos de ${su} alarma`;
  if (/upgrade|cambio de equipo/.test(t)) return `actualizar ${su} alarma al nuevo equipo`;
  if (/montaje|nueva instalacion/.test(t)) return `instalar ${su} alarma`;
  if (/revision/.test(t)) return `hacer la revisión de ${su} alarma`;
  if (/averia/.test(t)) return `revisar una avería de ${su} alarma`;
  return `hacer un mantenimiento de ${su} alarma`;
}
function cuandoEs(fecha) {
  const d = new Date(fechaISO(fecha) + 'T12:00:00');
  if (isNaN(d)) return fecha ? 'El ' + fecha : 'Pronto';
  const hoy = new Date(); hoy.setHours(12, 0, 0, 0);
  const dias = Math.round((d - hoy) / 864e5);
  if (dias === 0) return 'Hoy';
  if (dias === 1) return 'Mañana';
  const nombres = ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado'];
  return `El ${nombres[d.getDay()]} ${d.getDate()}/${d.getMonth() + 1}`;
}
function tramoEs(ts) {
  const m = /(\d{1,2})(?:[:.h](\d{2}))?\s*(?:-|a)\s*(\d{1,2})(?:[:.h](\d{2}))?/.exec(String(ts || ''));
  if (!m) return ts ? `en el horario de *${ts}h*` : '';
  const h = (a, b) => `${Number(a)}:${b || '00'}`;
  return `entre las *${h(m[1], m[2])} y las ${h(m[3], m[4])}*`;
}
function mensajeWhatsApp(c, quien) {
  quien = quien || {};
  const tc = String(c.tipoCliente || ''), negocio = /^N-/i.test(tc), casa = /^P-/i.test(tc);
  const propio = !quien.tecnico && !('tecnico' in quien);
  const yo = String(quien.yo || '').trim(), tec = String(quien.tecnico || '').trim();
  const lugar = negocio ? ' por su negocio' : casa ? ' por tu casa' : '';
  const tarea = `*${tareaDe(c.tipo, negocio)}*`;
  const tramo = tramoEs(c.timeslot);
  let presento, visita, llegada;
  if (propio) {
    presento = yo ? `Soy *${yo}*, el técnico de *Verisure*.` : 'Soy el técnico de *Verisure*.';
    visita = `${cuandoEs(c.fecha)} pasaré${lugar} para ${tarea}.`;
    llegada = tramo ? `Llegaré ${tramo}.\n\n` : '';
  } else {
    presento = negocio ? 'Le escribo de *Verisure*.' : 'Te escribo de *Verisure*.';
    visita = `${cuandoEs(c.fecha)} nuestro técnico${tec ? ' *' + tec + '*' : ''} pasará${lugar} para ${tarea}.`;
    llegada = tramo ? `Llegará ${tramo}.\n\n` : '';
  }
  if (negocio) {
    return `Hola, ${new Date().getHours() < 14 ? 'buenos días' : 'buenas tardes'}. ${presento} ${visita}\n\n` + llegada
      + `¿Estará abierto y habrá alguien para ${propio ? 'atenderme' : 'atenderle'} a esa hora?\n\n`
      + '✅ Responda *SÍ* para confirmar\n❌ Responda *NO* si no es posible y le cambiamos la cita\n\nMuchas gracias.';
  }
  const nombre = nombreDePila(String(c.cliente || '').trim().split(/\s+/)[0]);
  return `Hola${nombre ? ' ' + nombre : ''}, ${presento.charAt(0).toLowerCase() + presento.slice(1)} ${visita}\n\n` + llegada
    + (casa ? '¿Te viene bien estar en casa a esa hora?' : '¿Te viene bien a esa hora?') + '\n\n'
    + '✅ Responde *SÍ* para confirmar\n❌ Responde *NO* si no puedes y te cambiamos la cita\n\n¡Muchas gracias!';
}

// ── Cliente que dice NO (17/11/2026, texto de Gustavo) ──────────────────────
// Al marcar "No" la tarjeta muestra este mensaje para copiarlo o mandarlo por WhatsApp al cliente.
const MENSAJE_NO_PUEDE = 'Gracias por su respuesta, en caso de no poder atender su cita, llame al 910121122 '
  + 'para concretar nueva fecha y hora con uno de nuestros agentes.\n\nFeliz tarde.';
function cajaNoPuede(c) {
  const tel = telefonoDe(c);
  const wa = /^[67]/.test(tel) && c.status !== 'sin_whatsapp';
  const t = MENSAJE_NO_PUEDE.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/\n/g, '<br>');
  return `<div class="caja-nopuede">
    <div class="caja-titulo">✉️ Mensaje para el cliente que no puede</div>
    <div class="caja-texto">${t}</div>
    <div class="card-actions">
      <button class="btn btn-sec" onclick="copiarNoPuede()">📋 Copiar</button>
      ${wa ? `<button class="btn btn-wa" onclick="enviarNoPuede('${tel}')">💬 Enviar por WhatsApp</button>` : ''}
    </div>
  </div>`;
}
function copiarNoPuede() {
  const avisar = ok => typeof showToast === 'function' && showToast(ok ? 'Mensaje copiado' : 'No se pudo copiar', ok ? 'success' : 'error');
  const aMano = () => {
    const a = document.createElement('textarea');
    a.value = MENSAJE_NO_PUEDE; a.style.position = 'fixed'; a.style.opacity = '0';
    document.body.appendChild(a); a.select();
    let ok = false; try { ok = document.execCommand('copy'); } catch (e) {}
    a.remove(); avisar(ok);
  };
  if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(MENSAJE_NO_PUEDE).then(() => avisar(true), aMano);
  else aMano();
}
function enviarNoPuede(tel) {
  const url = `https://wa.me/34${tel}?text=${encodeURIComponent(MENSAJE_NO_PUEDE)}`;
  const w = window.open(url, '_blank');
  if (!w) window.location.href = url;
}
