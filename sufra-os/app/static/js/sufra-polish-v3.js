/* SUFRA POLISH V3 — additive UI only. */
(()=>{
  const $=(q,r=document)=>r.querySelector(q), $$=(q,r=document)=>[...r.querySelectorAll(q)];

  function addBookingLinks(){
    if(location.pathname==='/admin/reservations'){
      const top=$('.top');
      if(top && !$('#v3-public-book')){
        const group=document.createElement('div'); group.className='v3-head-actions';
        group.innerHTML='<a id="v3-public-book" class="btn solid" href="/book" target="_blank">Open customer booking site</a><a class="btn" href="/admin/booking-control">AI table assignments</a>';
        top.appendChild(group);
      }
    }
  }

  function enhanceRoster(){
    const auth=$('#auth-mount'); if(!auth)return;
    $$('.who',auth).forEach(card=>{
      if(card.dataset.v3)return; card.dataset.v3='1';
      const role=$('.who-role',card); if(role) role.setAttribute('title',role.textContent||'');
    });
    const pin=$('.pin-screen',auth);
    if(false && pin && !$('#v3-biometric-note',pin)){
      const note=document.createElement('div'); note.id='v3-biometric-note'; note.className='v3-biometric-note';
      note.innerHTML='<b>Biometric sign-in</b><span>After a passkey is enrolled, this device can use Face ID, Touch ID or Windows Hello. Profile photos are not used as face templates.</span>';
      const err=$('#pin-error',pin); if(err) err.insertAdjacentElement('afterend',note);
    }
  }

  function labelBuild(){
    document.documentElement.dataset.sufraPolish='v3';
  }

  function run(){addBookingLinks();enhanceRoster();labelBuild()}
  document.addEventListener('DOMContentLoaded',()=>{
    run();
    const mo=new MutationObserver(()=>run()); mo.observe(document.body,{subtree:true,childList:true});
  });
})();
