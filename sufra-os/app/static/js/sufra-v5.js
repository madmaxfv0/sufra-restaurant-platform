
/* SUFRA V5 — canonical localhost WebAuthn, dark-only UI, settings security and guest navigation fixes. */
(()=>{
  const $=(q,r=document)=>r.querySelector(q), $$=(q,r=document)=>[...r.querySelectorAll(q)];
  const esc=x=>window.NOVA?.esc?NOVA.esc(x):String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

  // PIN-only build: keep the current hostname; do not switch origins.

  function darkOnly(){
    document.documentElement.dataset.theme='dark';
    try{localStorage.setItem('sufra-theme','dark')}catch{}
    $$('[data-theme-toggle],.theme-toggle').forEach(x=>x.remove());
    if(window.NOVA){try{NOVA.theme=(next)=>{document.documentElement.dataset.theme='dark';return 'dark'}}catch{}}
  }

  function fixGuestBack(){
    $$('.guest-back').forEach(b=>{
      b.onclick=(e)=>{e.preventDefault();e.stopPropagation();const menu=$('.g-tabs [data-screen="menu"]');if(menu){menu.click();return}const screen=$('[data-screen-panel="menu"],#screen-menu,.g-screen[data-screen="menu"]');if(screen){$$('.g-screen,[data-screen-panel]').forEach(x=>x.hidden=true);screen.hidden=false;window.scrollTo({top:0,behavior:'smooth'})}}
    });
  }

  async function api(path,body){return NOVA.api(path,body)}
  const activeStaff=()=>window.NOVA_ACTIVE_STAFF||window.NOVA?.auth?.getStaff?.()||null;

  async function enroll(staffId,employeePin=''){
    if(!window.PublicKeyCredential)throw new Error('This browser/device does not support passkeys.');
    if(location.hostname!=='localhost')throw new Error('Open SUFRA through localhost to use Touch ID / Face ID / passkeys.');
    if(typeof window.SUFRA_BIOMETRIC_ENROLL!=='function')throw new Error('Biometric module is not ready. Refresh this page once.');
    return window.SUFRA_BIOMETRIC_ENROLL(staffId,employeePin);
  }

  async function mountSecurity(){
    if(!location.pathname.endsWith('/admin/settings'))return;
    let mount=$('#v5-security-settings');
    if(!mount){
      const host=$('#set-roles')?.closest('.card')?.parentElement||document.querySelector('main');
      if(!host)return;
      const sec=document.createElement('section');sec.className='card v5-security-settings';sec.style.marginTop='18px';sec.innerHTML='<h3>Security & sign-in</h3><p>PIN changes and team access.</p><div id="v5-security-settings"></div>';host.appendChild(sec);mount=$('#v5-security-settings');
    }
    const me=activeStaff(); if(!me){mount.innerHTML='<p class="sub">Sign in to manage security.</p>';return}
    let people=[];
    try{people=(await api('/api/enterprise/hr/staff')).staff||[]}catch{people=[me]}
    const manager=['owner','general_manager','restaurant_manager'].includes(me.role);
    const myRow=people.find(x=>String(x.id)===String(me.id));
    mount.innerHTML=`<div class="v5-security-grid">
      <section class="v5-security-box"><h4>My PIN</h4><p>Change your personal four-digit sign-in PIN.</p>
        <label>Current PIN<input class="field" id="v5-current-pin" type="password" inputmode="numeric" maxlength="4"></label>
        <label>New PIN<input class="field" id="v5-new-pin" type="password" inputmode="numeric" maxlength="4"></label>
        <label>Confirm new PIN<input class="field" id="v5-confirm-pin" type="password" inputmode="numeric" maxlength="4"></label>
        <button class="btn solid" id="v5-change-pin" style="margin-top:14px">Change PIN</button><div class="v5-security-status" id="v5-pin-status"></div></section>
      
      ${manager?`<section class="v5-security-box" style="grid-column:1/-1"><h4>Team security</h4><p>Owners and managers can reset employee PINs.</p>
        <div class="v5-team-row"><label>Employee<select class="field" id="v5-team-person">${people.map(p=>`<option value="${p.id}">${esc(p.name)} · ${esc(String(p.role).replaceAll('_',' '))}</option>`).join('')}</select></label></div>
        <div class="btn-row" style="margin-top:14px"><button class="btn" id="v5-reset-pin">Reset selected employee PIN</button></div><div class="v5-security-status" id="v5-team-status"></div></section>`:''}
    </div>`;

    $('#v5-change-pin').onclick=async()=>{const st=$('#v5-pin-status'),a=$('#v5-current-pin').value,b=$('#v5-new-pin').value,c=$('#v5-confirm-pin').value;st.className='v5-security-status';if(!/^[0-9]{4}$/.test(b)){st.textContent='New PIN must be exactly 4 digits.';st.classList.add('bad');return}if(b!==c){st.textContent='New PIN entries do not match.';st.classList.add('bad');return}try{const r=await api('/api/enterprise/security/pin/change',{current_pin:a,new_pin:b});st.textContent=r.message;st.classList.add('ok');$('#v5-current-pin').value=$('#v5-new-pin').value=$('#v5-confirm-pin').value=''}catch(e){st.textContent=e.message;st.classList.add('bad')}};
    if($('#v5-my-bio')) $('#v5-my-bio').onclick=async()=>{const b=$('#v5-my-bio');b.disabled=true;try{await enroll(me.id,'');NOVA.toast('Biometric sign-in enrolled');setTimeout(mountSecurity,250)}catch(e){NOVA.fail(e)}finally{b.disabled=false}};
    if(manager){
      if($('#v5-team-bio')) $('#v5-team-bio').onclick=async()=>{const st=$('#v5-team-status'),id=+$('#v5-team-person').value,pin=$('#v5-team-pin').value;st.className='v5-security-status';if(id!==Number(me.id)&&!/^[0-9]{4}$/.test(pin)){st.textContent='The selected employee must enter their current 4-digit PIN.';st.classList.add('bad');return}try{await enroll(id,pin);st.textContent='Biometric credential enrolled for the selected employee.';st.classList.add('ok');$('#v5-team-pin').value='';setTimeout(mountSecurity,300)}catch(e){st.textContent=e.message;st.classList.add('bad')}};
      $('#v5-reset-pin').onclick=()=>{const id=+$('#v5-team-person').value;NOVA.modal('Reset employee PIN',`<p class="sub">Set a new 4-digit PIN. Leave blank to generate one automatically.</p><label class="lbl">New PIN<input class="field" id="v5-reset-value" inputmode="numeric" maxlength="4" placeholder="Generate automatically"></label><button class="btn solid block" id="v5-reset-go" style="margin-top:14px">Reset PIN</button>`,(body,close)=>{body.querySelector('#v5-reset-go').onclick=async()=>{try{const r=await api('/api/enterprise/security/pin/reset',{staff_id:id,new_pin:body.querySelector('#v5-reset-value').value});close();NOVA.modal('PIN reset',`<div class="bio-card"><b>New PIN: ${esc(r.temporary_pin)}</b><p>Give this PIN directly to the employee.</p></div>`)}catch(e){NOVA.fail(e)}}})};
    }
  }

  function removeHRSecurity(){
    $$('[data-hr-tab="security"]').forEach(x=>x.remove());
    if(location.pathname.endsWith('/admin/hr')){const on=$('[data-hr-tab].on');if(on?.dataset.hrTab==='security')$('[data-hr-tab="people"]')?.click()}
  }

  function boot(){darkOnly();fixGuestBack();removeHRSecurity();mountSecurity()}
  darkOnly();
  document.addEventListener('DOMContentLoaded',boot);
  document.addEventListener('click',e=>{if(e.target.closest('.guest-back'))setTimeout(fixGuestBack,0);if(e.target.closest('button,a'))setTimeout(()=>{darkOnly();removeHRSecurity()},0)},true);
  const mo=new MutationObserver(()=>{darkOnly();fixGuestBack();removeHRSecurity();if(location.pathname.endsWith('/admin/settings')&&!$('#v5-security-settings .v5-security-grid'))mountSecurity()});
  if(!location.pathname.startsWith('/admin')){
    mo.observe(document.documentElement,{subtree:true,childList:true});
  }
})();
