/* SUFRA POLISH V4 — identity, stable navigation, scroll memory and clean media controls. */
(()=>{
  const $=(q,r=document)=>r.querySelector(q), $$=(q,r=document)=>[...r.querySelectorAll(q)];
  const roster=()=>Array.isArray(window.NOVA_STAFF_ROSTER)?window.NOVA_STAFF_ROSTER:[];
  const esc=x=>window.NOVA?NOVA.esc(x):String(x??'');

  function photoMarkup(person, cls=''){
    const src=person?.photo_url;
    return src?`<img class="v4-person-photo ${cls}" src="${esc(src)}" alt="${esc(person.name||'Staff photo')}">`:'';
  }

  function paintLoginPhotos(){
    $$('.who[data-id]').forEach(card=>{
      const p=roster().find(x=>String(x.id)===String(card.dataset.id));
      if(!p?.photo_url)return;
      const face=$('.who-face',card); if(face)face.innerHTML=photoMarkup(p);
    });
    const pin=$('.pin-screen');
    if(pin){
      const name=$('.auth-head h1',pin)?.textContent?.trim();
      const p=roster().find(x=>x.name===name);
      const face=$('.who-face.big',pin); if(p?.photo_url&&face)face.innerHTML=photoMarkup(p,'big');
      /* V5 keeps the core glowing PIN dots. */
      $('.v3-biometric-note',pin)?.remove();
    }
  }

  function cleanButtons(){
    $$('button,a.btn').forEach(b=>{
      const icons=[...b.querySelectorAll('.ent-icon')]; icons.slice(1).forEach(i=>i.remove());
      if(['pin-go','bio-login'].includes(b.id))icons.forEach(i=>i.remove());
      [...b.childNodes].filter(n=>n.nodeType===Node.TEXT_NODE).forEach(n=>{
        n.textContent=n.textContent
          .replace(/^\s*[›]\s*[＋+]\s*/,'＋ ')
          .replace(/^\s*[＋+]\s*[＋+]\s*/,'＋ ')
          .replace(/^\s*([✓✎×−↗£₼▣↻⇩◷✉▧◉☀◐⌕✦←›])\s*\1\s*/,'$1 ');
      });
    });
    const bio=$('#bio-login'); if(bio)bio.textContent='Use Face ID / Touch ID / passkey';
  }

  const navSvg={
    home:'M3 11 12 4l9 7v9H6v-9m4 9v-6h4v6', live:'M4 12h3l2-5 4 10 2-5h5',
    floor:'M4 4h7v7H4zM13 4h7v4h-7zM13 10h7v10h-7zM4 13h7v7H4z',
    calendar:'M5 3v3m14-3v3M4 8h16v12H4z', orders:'M6 4h12v16H6zM9 8h6M9 12h6M9 16h4',
    kitchen:'M5 4v7m4-7v7M7 4v16M14 4v16m0-8c5 0 5-8 0-8', menu:'M6 4h12v16H6zM9 8h6M9 12h6',
    inventory:'M4 7l8-4 8 4-8 4zM4 7v10l8 4 8-4V7', people:'M8 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6m8-1a2.5 2.5 0 1 0 0-5m-13 14c0-4 2-6 5-6s5 2 5 6m1-5c4 0 6 2 6 5',
    chart:'M5 19V9m5 10V5m5 14v-7m5 7V3', money:'M12 3v18m4-14c-1-2-7-2-7 1 0 4 8 2 8 6 0 3-7 3-9 1',
    spark:'M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z', settings:'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8m0-5v2m0 14v2M3 12h2m14 0h2'
  };
  function ensureNavIcons(){
    const map={'/admin':'home',operations:'live',floor:'floor',reservations:'calendar',orders:'orders',kitchen:'kitchen',menu:'menu',inventory:'inventory',suppliers:'inventory',guests:'people',staff:'people',events:'calendar',analytics:'chart',finance:'money',copilot:'spark',settings:'settings',executive:'chart',hr:'people',accounting:'money',qr:'floor','booking-control':'calendar'};
    $$('.rail nav a').forEach(a=>{
      const href=a.getAttribute('href')||''; const key=href==='/admin'?'/admin':href.split('/').filter(Boolean).pop(); const kind=map[key]||'home';
      let i=a.querySelector('.nav-icon,.dot'); if(!i){i=document.createElement('i');a.prepend(i)}
      i.className='nav-icon';
      if(i.dataset.sufraIcon!==kind){
        i.dataset.sufraIcon=kind;
        i.innerHTML=`<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${navSvg[kind]||navSvg.home}"/></svg>`;
      }
    });
    $('#loc-switch')?.remove();
  }

  function guestTabs(){
    if(!document.body.classList.contains('app-guest'))return;
    const tabs=$('.g-tabs'), shell=$('.g-shell,.guest-shell');
    if(tabs&&shell&&!tabs.classList.contains('v4-top-tabs')){
      tabs.classList.add('v4-top-tabs');
      shell.insertBefore(tabs,shell.firstChild);
    }
    $$('.basket,.qr-order-basket').forEach(x=>{if(!x.classList.contains('up'))x.classList.add('v4-hidden-basket')});
  }

  function currentPerson(){
    const me=window.NOVA_ACTIVE_STAFF || window.NOVA?.auth?.getStaff?.();
    if(!me)return null;
    return roster().find(x=>String(x.id)===String(me.id)) || me;
  }

  function mountStaffIdentity(){
    const p=currentPerson(); if(!p||$('#v4-staff-identity'))return;
    const chip=document.createElement('button'); chip.type='button'; chip.id='v4-staff-identity'; chip.className='v4-staff-identity';
    chip.innerHTML=`${p.photo_url?photoMarkup(p):`<span class="v4-staff-initial">${esc((p.name||'?').slice(0,1))}</span>`}<span><b>${esc(p.name||'Staff')}</b><small>${esc(String(p.role||'').replaceAll('_',' '))}</small></span>`;
    const top=$('.top');
    if(top)top.appendChild(chip); else {
      const greeting=$('#w-greeting'); if(greeting)greeting.parentElement?.appendChild(chip); else document.body.appendChild(chip);
    }
    chip.onclick=()=>{
      const me=currentPerson();
      NOVA.modal('My SUFRA profile',`<div class="v4-profile-modal">${me.photo_url?photoMarkup(me,'large'):`<span class="v4-profile-fallback">${esc((me.name||'?').slice(0,1))}</span>`}<h2>${esc(me.name||'Staff')}</h2><p>${esc(String(me.role||'').replaceAll('_',' '))}</p><button class="btn ghost block" id="v4-switch-person">Switch employee</button></div>`,(body,close)=>{
        if($('#v4-enroll-bio',body)) $('#v4-enroll-bio',body).onclick=async()=>{try{if(!window.SUFRA_BIOMETRIC_ENROLL)throw new Error('Biometric module is still loading.');await window.SUFRA_BIOMETRIC_ENROLL(me.id);close()}catch(e){NOVA.fail(e)}};
        $('#v4-switch-person',body).onclick=async()=>{await NOVA.auth.logout();location.href=(location.pathname.startsWith('/waiter')?'/waiter':'/admin')+'?fresh=1'};
      });
    };
  }

  function menuPhotoButtons(){
    if(location.pathname!='/admin/menu')return;
    $$('[data-menu-remove]').forEach(remove=>{
      const id=remove.dataset.menuRemove; if(!id||remove.parentElement?.querySelector(`[data-v4-menu-photo="${id}"]`))return;
      const b=document.createElement('button');b.type='button';b.className='btn tiny';b.dataset.v4MenuPhoto=id;b.textContent='Photo';remove.insertAdjacentElement('beforebegin',b);
      b.onclick=()=>NOVA.modal('Dish photo',`<div class="v4-dish-photo"><img src="/static/img/dish-placeholder.svg" id="v4-photo-preview" alt="Dish preview"><label class="btn file-btn">Choose food photo<input id="v4-photo-file" type="file" accept="image/png,image/jpeg,image/webp" hidden></label><button class="btn solid" id="v4-photo-save">Save photo</button><button class="btn ghost" id="v4-photo-reset">Use default image</button><p class="form-error" id="v4-photo-error"></p></div>`,(body,close)=>{
        const file=$('#v4-photo-file',body), preview=$('#v4-photo-preview',body), error=$('#v4-photo-error',body); let data='';
        file.onchange=()=>{const f=file.files?.[0];if(!f)return;const rd=new FileReader();rd.onload=()=>{data=rd.result;preview.src=data};rd.readAsDataURL(f)};
        $('#v4-photo-save',body).onclick=async()=>{if(!data){error.textContent='Choose a food photo first.';return}try{const r=await NOVA.api(`/api/v4/menu/${id}/photo`,{data_url:data});NOVA.toast(r.message);close();saveScroll();location.reload()}catch(e){error.textContent=e.message}};
        $('#v4-photo-reset',body).onclick=async()=>{try{await NOVA.api(`/api/v4/menu/${id}/photo/reset`,{});NOVA.toast('Default image restored');close();saveScroll();location.reload()}catch(e){error.textContent=e.message}};
      });
    });
  }

  // Preserve page and sidebar position across reloads and action-driven refreshes.
  const scrollKey='sufra-scroll:'+location.pathname;
  function saveScroll(){
    try{sessionStorage.setItem(scrollKey,JSON.stringify({y:window.scrollY,rail:$('.rail')?.scrollTop||0,at:Date.now()}))}catch{}
  }
  function restoreScroll(){
    let d;try{d=JSON.parse(sessionStorage.getItem(scrollKey)||'null')}catch{}
    if(!d||Date.now()-d.at>30*60*1000)return;
    const restore=()=>{window.scrollTo(0,Number(d.y||0));const rail=$('.rail');if(rail)rail.scrollTop=Number(d.rail||0)};
    requestAnimationFrame(restore);setTimeout(restore,80);setTimeout(restore,280);setTimeout(restore,700);
  }
  let scrollTimer=0;addEventListener('scroll',()=>{clearTimeout(scrollTimer);scrollTimer=setTimeout(saveScroll,90)},{passive:true});addEventListener('beforeunload',saveScroll);
  document.addEventListener('click',e=>{if(e.target.closest('button,a'))saveScroll()},true);

  function cleanup(){paintLoginPhotos();cleanButtons();ensureNavIcons();guestTabs();mountStaffIdentity();menuPhotoButtons();$('.v3-biometric-note')?.remove();}
  document.addEventListener('DOMContentLoaded',()=>{cleanup();restoreScroll();setTimeout(cleanup,250);setTimeout(cleanup,900)});
  const mo=new MutationObserver(()=>{clearTimeout(window.__sufraV4Mo);window.__sufraV4Mo=setTimeout(cleanup,120)});
  if(!location.pathname.startsWith('/admin')){
    mo.observe(document.documentElement,{childList:true,subtree:true});
  }
})();
