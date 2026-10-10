/* Local QR decoding: camera frames and uploaded images never leave the device. */
NOVA.staffQR = async function(mount, onBadge, onBack) {
  let stream, timer, stopped=false, busy=false;
  const stop=()=>{stopped=true;clearTimeout(timer);stream?.getTracks().forEach(t=>t.stop());};
  mount.innerHTML=`<div class="signin-box"><div class="auth-head"><h1>Scan employee QR</h1><p>Scan your badge, then enter your personal PIN.</p></div>
    <video playsinline muted style="width:100%;max-height:280px" aria-label="QR camera preview"></video>
    <button class="btn solid block" id="qr-camera">Start camera</button>
    <label class="lbl">Or choose a QR image<input class="field" id="qr-file" type="file" accept="image/*"></label>
    <label class="lbl">Or paste your employee QR link<input class="field" id="qr-link" type="text" autocomplete="off"></label>
    <button class="btn block" id="qr-open">Continue</button><p id="qr-error" role="alert"></p>
    <button class="btn ghost block" id="qr-back">Back to employees</button></div>`;
  const error=mount.querySelector('#qr-error'),video=mount.querySelector('video');
  const canvas=document.createElement('canvas'),ctx=canvas.getContext('2d',{willReadFrequently:true});
  async function accept(raw){
    if(busy||stopped)return;busy=true;
    try{const url=new URL(raw,location.origin);const token=new URLSearchParams(url.hash.slice(1)).get('staff_qr');
      if(!token)throw new Error('This is not an employee QR code.');
      const r=await NOVA.api('/api/auth/qr/identify',{qr_token:token});
      if(stopped)return;
      const waiter=location.pathname.startsWith('/waiter');
      if(waiter!==['waiter','bartender'].includes(r.staff.role))throw new Error('Open the appropriate staff app for this employee.');
      stop();onBadge(r.staff,token);
    }catch(e){error.textContent=e.message}finally{busy=false}
  }
  function decode(source,w,h){
    const scale=Math.min(1,1000/Math.max(w,h));canvas.width=Math.round(w*scale);canvas.height=Math.round(h*scale);
    ctx.drawImage(source,0,0,canvas.width,canvas.height);const pixels=ctx.getImageData(0,0,canvas.width,canvas.height);
    return jsQR(pixels.data,pixels.width,pixels.height)?.data;
  }
  async function tick(){if(stopped)return;try{if(video.readyState>=2){const raw=decode(video,video.videoWidth,video.videoHeight);if(raw)await accept(raw)}}catch(e){error.textContent=e.message}if(!stopped)timer=setTimeout(tick,250)}
  mount.querySelector('#qr-camera').onclick=async()=>{
    try{if(!navigator.mediaDevices?.getUserMedia)throw new Error('Camera access requires HTTPS or localhost. Choose a QR image or paste your link instead.');
      stream?.getTracks().forEach(t=>t.stop());clearTimeout(timer);
      const camera=await navigator.mediaDevices.getUserMedia({video:{facingMode:{ideal:'environment'}},audio:false});
      if(stopped){camera.getTracks().forEach(t=>t.stop());return}stream=camera;video.srcObject=stream;await video.play();tick();
    }catch(e){error.textContent=e.message}
  };
  mount.querySelector('#qr-file').onchange=async e=>{const file=e.target.files[0];if(!file)return;try{
    const url=URL.createObjectURL(file),img=new Image();try{img.src=url;await img.decode();const raw=decode(img,img.naturalWidth,img.naturalHeight);if(!raw)throw new Error('No QR code found. Choose a clear image of your badge.');await accept(raw)}finally{URL.revokeObjectURL(url)}
  }catch(e){error.textContent=e.message}};
  mount.querySelector('#qr-open').onclick=()=>accept(mount.querySelector('#qr-link').value.trim());
  mount.querySelector('#qr-back').onclick=()=>{stop();onBack()};
  window.addEventListener('pagehide',stop,{once:true});
  if(location.hash.startsWith('#staff_qr=')){const raw=location.href;history.replaceState({},'',location.pathname+location.search);await accept(raw)}
};

NOVA.showStaffCredentials = function(r){
  NOVA.modal('Staff QR Badge',`<div class="staff-badge-card"><h3>${NOVA.esc(r.name||'Employee')}</h3>
    <p style="color:var(--muted);font-size:13px">Staff ID ${r.staff_id} · Scan to sign in</p>
    <img src="${NOVA.esc(r.qr_image)}" alt="Employee login QR" style="width:260px;max-width:100%;border-radius:12px;background:#fff;padding:10px">
    ${r.temporary_pin ? `<div style="background:var(--surface2);border-radius:10px;padding:12px 20px;margin:8px 0"><p style="margin:0 0 4px"><b>4-digit PIN: ${NOVA.esc(r.temporary_pin)}</b></p><p style="margin:0;font-size:12px;color:var(--muted)">Show PIN to employee. Do not display alongside the QR.</p></div>` : ''}
    <p id="badge-status" role="status" aria-live="polite"></p>
    <div class="btn-row" style="margin-top:8px"><a class="btn" id="badge-open" href="${NOVA.esc(r.qr_url)}" target="_blank" rel="noopener">${r.app_path==='/waiter'?'Open waiter app':'Open staff app'}</a><a class="btn" href="${NOVA.esc(r.qr_image)}" download="badge-${r.staff_id}.png">Download</a>
    <button class="btn" id="badge-print">Print</button><button class="btn" id="badge-regenerate">Regenerate</button><button class="btn ghost" id="badge-copy">Copy link</button></div></div>`,el=>{
    el.querySelector('#badge-regenerate').onclick=async()=>{
      const button=el.querySelector('#badge-regenerate'),status=el.querySelector('#badge-status');
      button.disabled=true;status.textContent='Generating a new QR…';
      try{const next=await NOVA.api(`/api/enterprise/hr/staff/${r.staff_id}/badge`,{});NOVA.showStaffCredentials(next);document.querySelector('#badge-status').textContent='New QR ready. The previous QR no longer works. Your PIN is unchanged.'}
      catch(e){status.textContent=e.message;button.disabled=false}
    };
    el.querySelector('#badge-copy').onclick=async()=>{try{await navigator.clipboard.writeText(r.qr_url);NOVA.toast('Login link copied')}catch{NOVA.modal('Employee login link',`<textarea class="field" readonly>${NOVA.esc(r.qr_url)}</textarea>`)}};
    el.querySelector('#badge-print').onclick=()=>{const frame=document.createElement('iframe');frame.style.display='none';document.body.appendChild(frame);
      const doc=frame.contentDocument;doc.open();doc.write(`<html><head><title>Staff Badge</title><style>body{text-align:center;font-family:sans-serif;padding:20px}img{border:1px solid #eee;padding:8px;border-radius:8px}</style></head><body><h2>${NOVA.esc(r.name||'Employee')}</h2><p>Staff ID ${r.staff_id}</p><img width="280" src="${NOVA.esc(r.qr_image)}"><p style="font-size:12px;color:#666">Scan in the SUFRA staff app, then enter your 4-digit PIN.</p></body></html>`);doc.close();
      const print=()=>{frame.contentWindow.focus();frame.contentWindow.print();setTimeout(()=>frame.remove(),60000)};
      const badge=doc.querySelector('img');if(badge.complete)print();else badge.onload=print;
    };
  });
};
