/* SUFRA V6 — guest navigation + settings guard */
(()=>{
  const $=(q,r=document)=>r.querySelector(q), $$=(q,r=document)=>[...r.querySelectorAll(q)];
  function guestFix(){
    if(!document.body.classList.contains('app-guest'))return;
    const shell=$('.g-shell,.guest-shell'),tabs=$('.g-tabs');
    if(tabs&&shell){
      tabs.classList.add('v4-top-tabs');
      if(tabs.parentElement!==shell)shell.prepend(tabs);
      $$('.g-tabs button').forEach(b=>{b.hidden=false;b.removeAttribute('hidden');b.style.removeProperty('display')});
    }
    const bar=$('#sufra-order-bar');
    if(bar&&shell){
      if(bar.parentElement!==shell){tabs?tabs.insertAdjacentElement('afterend',bar):shell.prepend(bar)}
      const hasContent=!!bar.textContent.trim();
      if(!hasContent||!bar.classList.contains('up')){bar.hidden=true}else{bar.hidden=false}
    }
  }
  function settingsGuard(){
    if(!location.pathname.endsWith('/admin/settings'))return;
    const main=document.querySelector('main');if(main){main.style.visibility='visible';main.style.opacity='1'}
  }
  document.addEventListener('DOMContentLoaded',()=>{guestFix();settingsGuard()});
  document.addEventListener('click',()=>setTimeout(guestFix,0),true);
  if(!location.pathname.startsWith('/admin')){
    new MutationObserver(()=>{guestFix();settingsGuard()}).observe(document.documentElement,{subtree:true,childList:true});
  }
})();
