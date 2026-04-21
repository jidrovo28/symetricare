'use strict';
const App = {
  csrf() {
    return document.querySelector('[name=csrfmiddlewaretoken]')?.value
        || document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';
  },
  loading(show) {
    const el = document.getElementById('globalLoader');
    if (el) el.style.display = show ? 'flex' : 'none';
  },
  toast(msg, tipo='success') {
    const t = document.createElement('div');
    t.className = `alert alert-${tipo} alert-dismissible fade show position-fixed top-0 end-0 m-3 shadow-sm`;
    t.style.cssText = 'z-index:9999;min-width:280px;max-width:90vw';
    t.innerHTML = `${msg}<button type="button" class="btn-close" data-bs-dismiss="alert"></button>`;
    document.body.appendChild(t);
    setTimeout(() => bootstrap.Alert.getOrCreateInstance(t)?.close(), 7500);
  },
  async modal(url, params={}, modalId='mainModal') {
    try {
      const qs = new URLSearchParams({action:'add',...params}).toString();
      const r  = await fetch(`${url}?${qs}`);
      if (!r.ok) { App.toast(`Error ${r.status}`,'danger'); return; }
      const d  = await r.json();
      if (d.result) {
        const m    = document.getElementById(modalId);
        if (!m) { App.toast('Modal no encontrado','danger'); return; }
        const body = m.querySelector('.modal-body');
        body.innerHTML         = d.data;
        body.dataset.submitUrl = url;
        bootstrap.Modal.getOrCreateInstance(m).show();
      } else {
        App.toast(d.msg || 'Error','danger');
      }
    } catch(e) { App.toast(e.message,'danger'); }
  },
  async submit(form, successCb) {
    App.loading(true);
    try {
      const fd       = new FormData(form);
      const modalUrl = form.closest('.modal-body')?.dataset.submitUrl;
      const postUrl  = form.getAttribute('action') || modalUrl || window.location.href;
      const r  = await fetch(postUrl, {method:'POST',body:fd,headers:{'X-CSRFToken':App.csrf()}});
      const d  = await r.json();
      App.loading(false);
      if (d.result) {
        App.toast(d.msg || 'Guardado correctamente');
        if (typeof successCb === 'function') successCb(d);
      } else {
        App.toast(d.msg || 'Error al guardar','danger');
      }
    } catch(e) { App.loading(false); App.toast(e.message,'danger'); }
  },
  async delete(url, id, msg='¿Eliminar este registro?', cb) {
    if (!confirm(msg)) return;
    App.loading(true);
    try {
      const fd = new FormData();
      fd.append('action','delete'); fd.append('id',id);
      const r = await fetch(url, {method:'POST',body:fd,headers:{'X-CSRFToken':App.csrf()}});
      const d = await r.json();
      App.loading(false);
      if (d.result) { App.toast('Eliminado'); if(cb) cb(); else location.reload(); }
      else App.toast(d.msg||'Error','danger');
    } catch(e) { App.loading(false); App.toast(e.message,'danger'); }
  },
  debounce(fn, ms=300) { let t; return (...a) => { clearTimeout(t); t=setTimeout(()=>fn(...a),ms); }; },

  // Chips para listas dinámicas (APF, APP, Alergias, etc.)
  chips: {
    add(containerId, inputId, hiddenName) {
      const input = document.getElementById(inputId);
      const val   = input.value.trim();
      if (!val) return;
      const c = document.getElementById(containerId);
      const id = Date.now();
      const chip = document.createElement('span');
      chip.className = 'tag-chip me-1 mb-1';
      chip.innerHTML = `${val} <span class="remove" onclick="App.chips.remove(this,'${hiddenName}','${id}')">×</span>
        <input type="hidden" name="${hiddenName}" value="${val}" data-id="${id}">`;
      c.appendChild(chip);
      input.value = '';
      input.focus();
    },
    remove(btn, name, id) {
      btn.closest('.tag-chip').remove();
    }
  }
};

// Ficha: calcular total de tratamientos
const Ficha = {
  calcular() {
    let sub = 0;
    document.querySelectorAll('.trat-costo').forEach(el => {
      sub += parseFloat(el.value) || 0;
    });
    const desc  = parseFloat(document.getElementById('descuento')?.value) || 0;
    const total = Math.max(0, sub - desc);
    const abono = parseFloat(document.getElementById('abono')?.value) || 0;
    const saldo = Math.max(0, total - abono);
    const set = (id, v) => { const el=document.getElementById(id); if(el) el.textContent='$'+v.toFixed(2); };
    set('subtotalDisplay', sub);
    set('totalDisplay',    total);
    set('saldoDisplay',    saldo);
    const hidSub = document.getElementById('subtotalHidden');
    const hidTot = document.getElementById('totalHidden');
    if (hidSub) hidSub.value = sub.toFixed(2);
    if (hidTot) hidTot.value = total.toFixed(2);
  },

  agregarTratamiento(id, nombre, precio) {
    const cont = document.getElementById('tratamientosContainer');
    if (!cont) return;
    if (document.querySelector(`[data-srv="${id}"]`)) {
      App.toast('Servicio ya agregado','warning'); return;
    }
    const row = document.createElement('div');
    row.className = 'd-flex gap-2 align-items-start mb-2';
    row.dataset.srv = id;
    row.innerHTML = `
      <input type="hidden" name="servicio_id[]" value="${id}">
      <div class="flex-grow-1">
        <div class="small fw-600">${nombre}</div>
        <textarea name="observacion_trat[]" class="form-control form-control-sm mt-1" rows="1" placeholder="Observación..."></textarea>
      </div>
      <input type="number" name="costo_trat[]" class="form-control form-control-sm trat-costo" style="width:90px"
             value="${precio}" step="0.01" oninput="Ficha.calcular()">
      <button type="button" class="btn btn-xs btn-light border text-danger" onclick="Ficha.quitarTratamiento(this)">
        <i class="bi bi-trash"></i>
      </button>`;
    cont.appendChild(row);
    Ficha.calcular();
  },

  quitarTratamiento(btn) {
    btn.closest('[data-srv]').remove();
    Ficha.calcular();
  }
};

document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(el => new bootstrap.Tooltip(el));
  document.querySelectorAll('.alert[data-autohide]').forEach(el =>
    setTimeout(() => bootstrap.Alert.getOrCreateInstance(el)?.close(), 4000));
});
