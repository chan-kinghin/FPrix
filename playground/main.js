async function postJSON(url, body){
  const res = await fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
  if (!res.ok) throw new Error('HTTP '+res.status);
  return await res.json();
}

function pretty(obj){
  try { return JSON.stringify(obj, null, 2); } catch(e){ return String(obj); }
}

function clearOverlays(){
  const ov = document.getElementById('overlays');
  ov.innerHTML = '';
}

function renderOverlays(highlights, img){
  clearOverlays();
  if (!highlights || !highlights.length || !img.naturalWidth) return;
  const ov = document.getElementById('overlays');
  const scale = img.clientWidth / img.naturalWidth;
  ov.style.width = img.clientWidth + 'px';
  ov.style.height = img.clientHeight + 'px';
  for (const h of highlights){
    const box = document.createElement('div');
    box.className = 'box' + (h.type==='price' ? ' price' : '');
    box.style.left = Math.round(h.x * scale) + 'px';
    box.style.top = Math.round(h.y * scale) + 'px';
    box.style.width = Math.round(h.w * scale) + 'px';
    box.style.height = Math.round(h.h * scale) + 'px';
    ov.appendChild(box);
  }
}

function showScreenshot(filename, highlights){
  const img = document.getElementById('shot');
  const wrap = document.getElementById('shotWrap');
  const overlays = document.getElementById('overlays');
  overlays.innerHTML = '';
  if (!filename){ img.removeAttribute('src'); return; }
  const url = '/api/screenshot/' + encodeURIComponent(filename);
  img.onload = () => renderOverlays(highlights, img);
  img.src = url;
}

async function runQuery(){
  const q = document.getElementById('q').value.trim();
  const status = document.getElementById('status');
  const pre = document.getElementById('json');
  const confirm = document.getElementById('confirm');
  status.textContent = '查询中...';
  pre.textContent = '';
  confirm.innerHTML='';
  clearOverlays();
  try{
    const data = await postJSON('/api/query', {query:q});
    pre.textContent = pretty(data);
    status.textContent = data.status;
    if (data.status === 'needs_confirmation'){
      const cid = data.confirmation_id;
      const opts = data.options || [];
      confirm.innerHTML = '<h3>请选择：</h3>';
      for (const o of opts){
        const div = document.createElement('div');
        div.className = 'option';
        div.textContent = `${o.product_code} · ${o.material||''} · ${o.category||''} (${(o.confidence*100).toFixed(0)}%)`;
        div.onclick = async () => {
          const final = await postJSON('/api/confirm', {confirmation_id: cid, selected_option: o.id});
          pre.textContent = pretty(final);
          status.textContent = final.status;
          const hs = (final.data && (final.data.highlights || (final.data.highlight ? [final.data.highlight] : []))) || [];
          showScreenshot(final.screenshot_url, hs);
          confirm.innerHTML = '';
        };
        confirm.appendChild(div);
      }
      showScreenshot(null, null);
    } else if (data.status === 'success'){
      const hs = (data.data && (data.data.highlights || (data.data.highlight ? [data.data.highlight] : []))) || [];
      showScreenshot(data.screenshot_url, hs);
    } else {
      showScreenshot(null, null);
    }
  } catch(e){
    status.textContent = '请求失败';
    pre.textContent = String(e);
  }
}

document.getElementById('run').onclick = runQuery;
document.getElementById('q').addEventListener('keydown', e=>{ if (e.key==='Enter') runQuery(); });

