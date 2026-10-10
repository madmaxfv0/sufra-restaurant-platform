/* The venue's currency symbol, injected by the page from restaurant
   settings (see main._currency). One symbol for the whole product. */
const CUR = (window.SUFRA_CURRENCY || '\u20bc');
/* SUFRA table QR menu — browse, save and send an order from the table QR. */
function bootGuest(tableNumber) {
  const $ = s => document.querySelector(s);
  const $$ = s => [...document.querySelectorAll(s)];
  let items = [], sections = [], course = 'All', search = '', sendingOrder=false;
  const FALLBACK_PHOTO='/static/img/dish-placeholder.svg';
  const cart = new Map(JSON.parse(localStorage.getItem(`sufra-cart-${tableNumber}`) || '[]'));
  const filters = new Set();
  const saved = new Set(JSON.parse(localStorage.getItem(`nova-saved-${tableNumber}`) || '[]'));
  const DIETS = [['vegan','Vegan'],['vegetarian','Vegetarian'],['gf','Gluten free'],['halal','Halal']];
  const AVOID = [['nuts','No nuts'],['shellfish','No shellfish'],['dairy','No dairy'],['fish','No fish'],['gluten','No gluten'],['sesame','No sesame'],['egg','No egg']];
  const COURSES = ['All','Snack','Starter','Main','Side','Dessert','Drink'];

  const lang=()=>window.NOVAI18N?NOVAI18N.get():'en';
  const localItem=i=>{const l=lang();return {...i,name:(i.name_i18n&&i.name_i18n[l])||i.name,blurb:(i.blurb_i18n&&i.blurb_i18n[l])||i.blurb};};
  const photo=i=>i.image_url||FALLBACK_PHOTO;
  const persistCart=()=>{localStorage.setItem(`sufra-cart-${tableNumber}`,JSON.stringify([...cart.entries()]));renderCartBar();};
  const cartQty=id=>Number(cart.get(Number(id))||0);
  function addToCart(id,delta=1){id=Number(id);const i=items.find(x=>x.id===id);if(!i||!i.available)return;const q=Math.max(0,cartQty(id)+delta);q?cart.set(id,q):cart.delete(id);persistCart();renderMenu();}
  function renderCartBar(){let bar=document.querySelector('#sufra-order-bar');if(!bar){bar=document.createElement('aside');bar.id='sufra-order-bar';bar.className='sufra-order-bar';const host=document.querySelector('.g-shell,.guest-shell')||document.body;const tabs=host.querySelector('.g-tabs');tabs?tabs.insertAdjacentElement('afterend',bar):host.prepend(bar)}const qty=[...cart.values()].reduce((a,b)=>a+Number(b||0),0);const total=[...cart.entries()].reduce((sum,[id,q])=>{const i=items.find(x=>x.id===Number(id));return sum+(i?Number(i.price||0)*Number(q||0):0)},0);bar.classList.toggle('up',qty>0);bar.hidden=!qty;bar.innerHTML=qty?`<div><b>${qty} ${qty===1?'item':'items'} for Table ${tableNumber}</b><span>${CUR}${total.toFixed(2)} · sent directly to the restaurant</span></div><button class="btn solid" id="review-order">Review & send</button>`:'';const b=bar.querySelector('#review-order');if(b)b.onclick=openCart;}
  function openCart(){const lines=[...cart.entries()].map(([id,q])=>{const i=items.find(x=>x.id===Number(id));return i?{...i,qty:Number(q)}:null}).filter(Boolean);if(!lines.length)return;NOVA.sheet(`Table ${tableNumber} order`,`<div class="qr-cart-lines">${lines.map(i=>`<div class="qr-cart-line"><div><b>${NOVA.esc(localItem(i).name)}</b><span>${CUR}${Number(i.price).toFixed(2)} each</span></div><div class="qty-stepper"><button data-minus="${i.id}" aria-label="Remove one">−</button><b>${i.qty}</b><button data-plus="${i.id}" aria-label="Add one">+</button></div><strong>${CUR}${(Number(i.price)*i.qty).toFixed(2)}</strong></div>`).join('')}</div><label class="lbl">Note for the kitchen or waiter<textarea class="field" id="qr-order-note" rows="3" placeholder="For example: sauce on the side"></textarea></label><div class="qr-order-warning">For severe allergies, speak directly with a waiter before sending.</div><button class="btn solid block" id="send-qr-order">Send order to kitchen</button><p class="form-error" id="qr-order-error"></p>`,(el,close)=>{el.querySelectorAll('[data-minus]').forEach(b=>b.onclick=()=>{addToCart(+b.dataset.minus,-1);close();openCart()});el.querySelectorAll('[data-plus]').forEach(b=>b.onclick=()=>{addToCart(+b.dataset.plus,1);close();openCart()});el.querySelector('#send-qr-order').onclick=async()=>{if(sendingOrder)return;sendingOrder=true;const btn=el.querySelector('#send-qr-order');btn.disabled=true;btn.textContent='Sending…';const note=el.querySelector('#qr-order-note').value.trim();try{const payload={items:[...cart.entries()].map(([id,qty])=>({id:Number(id),qty:Number(qty),note}))};const r=await NOVA.api(`/api/guest/${tableNumber}/order`,payload);cart.clear();persistCart();close();NOVA.toast(`Order sent · about ${r.eta||'—'} minutes`)}catch(e){el.querySelector('#qr-order-error').textContent=e.message;btn.disabled=false;btn.textContent='Send order to kitchen'}finally{sendingOrder=false}}});}


  function persist() {
    localStorage.setItem(`nova-saved-${tableNumber}`, JSON.stringify([...saved]));
    const tab = $('#tab-saved'); if (tab) tab.textContent = saved.size || '';
  }
  function goto(name) {
    $$('.g-tabs button').forEach(b => b.classList.toggle('on', b.dataset.screen === name));
    $$('.g-shell > section[data-screen], .guest-shell > section[data-screen]').forEach(s => s.hidden = s.dataset.screen !== name);
    if (name === 'saved') renderSaved();
    const screen=document.querySelector(`section[data-screen="${name}"]`);
    if(screen&&name!=='menu'&&!screen.querySelector('.guest-back')){const back=document.createElement('button');back.className='guest-back';back.type='button';back.textContent='← Back to menu';back.onclick=(e)=>{e.preventDefault();goto('menu');window.scrollTo({top:0,behavior:'smooth'})};screen.prepend(back)}
    window.scrollTo({top:0, behavior:'smooth'});
    if(window.NOVAI18N)NOVAI18N.apply();
  }
  $$('.g-tabs button').forEach(b => b.onclick = () => goto(b.dataset.screen));

  function matches(i) {
    if (course !== 'All' && i.course !== course) return false;
    if (search && !`${i.name} ${i.blurb} ${(i.tags||[]).join(' ')}`.toLowerCase().includes(search)) return false;
    for (const f of filters) {
      if (f.startsWith('no:')) { if ((i.tags||[]).includes(f.slice(3))) return false; }
      else if (!(i.tags||[]).includes(f)) return false;
    }
    return true;
  }
  function renderFilters() {
    const a=[...filters];
    $('#active-filters').innerHTML=a.length ? a.map(f=>`<button class="chip-x" data-f="${f}">${NOVA.esc(f.replace('no:','no '))} ×</button>`).join('')+'<button class="chip-x clear">Clear all</button>' : '';
    $$('#active-filters .chip-x').forEach(b=>b.onclick=()=>{b.classList.contains('clear')?filters.clear():filters.delete(b.dataset.f);renderFilters();renderMenu();});
  }
  function openFilters() {
    NOVA.sheet('Filter the menu', `<p class="sub">Choose what you want to see. For severe allergies, still speak to your waiter.</p>
      <h3>Show me only</h3><div class="chip-grid">${DIETS.map(([k,l])=>`<button class="chip-pick ${filters.has(k)?'on':''}" data-f="${k}">${l}</button>`).join('')}</div>
      <h3>Leave out</h3><div class="chip-grid">${AVOID.map(([k,l])=>`<button class="chip-pick ${filters.has('no:'+k)?'on':''}" data-f="no:${k}">${l}</button>`).join('')}</div>
      <button class="btn solid block" id="f-done" style="margin-top:16px">Done</button>`, (el,close)=>{
        el.querySelectorAll('.chip-pick').forEach(b=>b.onclick=()=>{const f=b.dataset.f;filters.has(f)?filters.delete(f):filters.add(f);b.classList.toggle('on');renderFilters();renderMenu();});
        el.querySelector('#f-done').onclick=close;
      });
  }
  function renderNav() {
    const canonical=['Snack','Starter','Main','Side','Dessert','Drink'];
    const live=[...new Set(items.map(i=>i.course).filter(Boolean))];
    const courses=['All',...canonical.filter(c=>live.includes(c)),...live.filter(c=>!canonical.includes(c))];
    if(!courses.includes(course))course='All';
    $('#courses').innerHTML=courses.map(c=>`<button class="${c===course?'on':''}" data-c="${NOVA.esc(c)}">${NOVA.esc(c==='All'?c:sectionLabel(c))}</button>`).join('');
    $$('#courses button').forEach(b=>b.onclick=()=>{course=b.dataset.c;renderNav();renderMenu();});
  }
  function tags(i) {
    return (i.tags||[]).filter(t=>['vegan','vegetarian','gf','halal'].includes(t)).map(t=>`<span class="tag good">${TAG_LABEL[t]||t}</span>`).join('')+
      (i.tags||[]).filter(t=>['nuts','shellfish','dairy','fish','gluten','sesame','egg'].includes(t)).map(t=>`<span class="tag warn">${TAG_LABEL[t]||t}</span>`).join('');
  }
  function sectionLabel(c){
    const l=lang(); const sec=sections.find(x=>x.name===c);
    if(sec){ if(l==='az'&&sec.name_az)return sec.name_az; if(l==='ru'&&sec.name_ru)return sec.name_ru; }
    return c;
  }
  function dishCard(i){
    return `<article class="dish ${i.available?'':'off'}" data-id="${i.id}">
      ${`<img class="dish-photo" src="${NOVA.esc(photo(i))}" alt="${NOVA.esc(i.name)}" loading="lazy" onerror="this.onerror=null;this.src='${FALLBACK_PHOTO}'">`}
      <div class="body"><h4>${NOVA.esc(i.name)}${i.signature?'<em class="sig-tag">signature</em>':''}${i.available?'':'<em class="unavailable-tag">Unavailable</em>'}</h4><p>${NOVA.esc(i.blurb)}</p>
      <div class="meta">${tags(i)}${i.available?(i.wait?`<span class="tag">${NOVA.esc(i.wait)} min</span>`:''):`<span class="tag warn">${NOVA.esc(i.unavailable_reason||'Kitchen unavailable')}</span>`}</div><span class="price">${CUR}${Number(i.price).toFixed(0)}</span></div>
      <div class="dish-actions"><button class="dish-save ${saved.has(i.id)?'on':''}" data-save="${i.id}">${saved.has(i.id)?'♥ Saved':'♡ Save'}</button>${i.available?`<button class="btn solid dish-add-order" data-add-order="${i.id}">＋ Add${cartQty(i.id)?` · ${cartQty(i.id)} in order`:''}</button>`:''}</div></article>`;
  }
  function renderMenu() {
    const list=items.filter(matches).map(localItem);
    if(!list.length){$('#dishes').innerHTML=NOVA.empty('Nothing matches that.','Try another search or clear a filter.');return;}
    if(course==='All'){
      const order=sections.length?sections.map(s=>s.name):[];
      const seen=[...new Set(list.map(i=>i.course))];
      const groupOrder=[...order.filter(c=>seen.includes(c)),...seen.filter(c=>!order.includes(c))];
      $('#dishes').innerHTML=groupOrder.map(c=>`<h3 class="menu-section-head">${NOVA.esc(sectionLabel(c))}</h3>`+list.filter(i=>i.course===c).map(dishCard).join('')).join('');
    } else {
      $('#dishes').innerHTML=list.map(dishCard).join('');
    }
    $$('#dishes .dish').forEach(el=>el.onclick=e=>{if(e.target.closest('[data-save],[data-add-order]'))return;openDish(items.find(i=>i.id===+el.dataset.id));});
    $$('[data-save]').forEach(b=>b.onclick=e=>{e.stopPropagation();toggleSave(+b.dataset.save);});
    $$('[data-add-order]').forEach(b=>b.onclick=e=>{e.stopPropagation();addToCart(+b.dataset.addOrder,1);NOVA.toast('Added to Table '+tableNumber+' order');});
  }
  function toggleSave(id){saved.has(id)?saved.delete(id):saved.add(id);persist();renderMenu();if(!document.querySelector('section[data-screen="saved"]').hidden)renderSaved();}
  function openDish(i){if(!i)return;i=localItem(i);NOVA.sheet(i.name,`${i.signature?'<span class="tag star">Chef\'s signature</span>':''}<p class="sub" style="font-size:14px">${NOVA.esc(i.blurb)}</p>
    <div class="kv"><span>Price</span><b>${CUR}${Number(i.price).toFixed(0)}</b></div>${i.protein?`<div class="kv"><span>Protein</span><b>${i.protein}g</b></div>`:''}${i.kcal?`<div class="kv"><span>Energy</span><b>${i.kcal} kcal</b></div>`:''}
    <div style="margin:12px 0">${tags(i)}</div><p class="sub">For allergies or modifications, please confirm directly with your waiter.</p>
    <div class="btn-row"><button class="btn ghost" id="save-dish">${saved.has(i.id)?'♥ Remove saved':'♡ Save dish'}</button>${i.available?'<button class="btn solid" id="order-dish">＋ Add to table order</button>':''}</div>`,(el,close)=>{el.querySelector('#save-dish').onclick=()=>{toggleSave(i.id);close();};const add=el.querySelector('#order-dish');if(add)add.onclick=()=>{addToCart(i.id,1);close();NOVA.toast('Added to Table '+tableNumber+' order')};});}
  function renderSaved(){const list=items.filter(i=>saved.has(i.id)).map(localItem);$('#saved-dishes').innerHTML=list.length?list.map(i=>`<div class="card" style="margin-bottom:10px"><div class="kv"><span><b>${NOVA.esc(i.name)}</b><div class="micro">${NOVA.esc(i.blurb)}</div></span><b>${CUR}${Number(i.price).toFixed(0)}</b></div><button class="btn ghost tiny" data-remove="${i.id}">Remove</button></div>`).join(''):NOVA.empty('Nothing saved yet.','Tap the heart beside dishes you may want.');$$('[data-remove]').forEach(b=>b.onclick=()=>toggleSave(+b.dataset.remove));}

  async function syncRequests(){
    try{
      const st=await NOVA.api(`/api/guest/${tableNumber}/state`);
      const open=new Set(st.open_requests||[]);
      $$('.quick button').forEach(b=>{
        const sub=b.querySelector('span'); if(sub && !b.dataset.defaultText) b.dataset.defaultText=sub.textContent;
        const on=open.has(b.dataset.kind); b.classList.toggle('request-open',on);
        if(sub) sub.textContent=on?'waiter notified':(b.dataset.defaultText||sub.textContent);
      });
    }catch{}
  }
  $$('.quick button').forEach(b=>{ const sub=b.querySelector('span'); if(sub)b.dataset.defaultText=sub.textContent; b.onclick=async()=>{
    const kind=b.dataset.kind;if(kind==='complaint'){NOVA.sheet('File a complaint',`<label class="lbl">Category<select class="field" id="g-cmp-cat"><option value="service">Service</option><option value="food">Food</option><option value="billing">Billing</option><option value="other">Other</option></select></label><label class="lbl">What happened<textarea class="field" id="g-cmp-msg" rows="5" placeholder="Tell us what happened"></textarea></label><button class="btn solid block" id="g-cmp-send">Send to manager</button><p class="form-error" id="g-cmp-error"></p>`,(el,close)=>{el.querySelector('#g-cmp-send').onclick=async()=>{try{const r=await NOVA.api(`/api/ops/guest/${tableNumber}/complaint`,{category:el.querySelector('#g-cmp-cat').value,message:el.querySelector('#g-cmp-msg').value});close();NOVA.toast(r.message)}catch(e){el.querySelector('#g-cmp-error').textContent=e.message}}});return}if(kind==='manager'){b.disabled=true;try{const r=await NOVA.api(`/api/ops/guest/${tableNumber}/manager`,{reason:'Guest requested a manager'});NOVA.toast(r.message)}catch(e){NOVA.fail(e)}setTimeout(()=>b.disabled=false,1200);return}
    b.disabled=true; try{const r=await NOVA.api(`/api/guest/${tableNumber}/request`,{kind});NOVA.toast(`We've told your waiter — ${r.message}`);await syncRequests();}catch(e){NOVA.fail(e);} setTimeout(()=>b.disabled=false,1200);
  };});
  async function refreshMenuLive(){try{const d=await NOVA.api('/api/menu');items=d.items||[];sections=d.sections||[];renderNav();renderMenu();if(!document.querySelector('section[data-screen="saved"]').hidden)renderSaved()}catch{}}
  NOVA.on(()=>{syncRequests();refreshMenuLive()}); setInterval(syncRequests,15000); syncRequests();
  async function ask(q){if(!q.trim())return;const box=$('#menu-answer');box.innerHTML=NOVA.skeleton(2);try{const r=await NOVA.api('/api/menu/ask',{question:q});box.innerHTML=`<p class="answer">${NOVA.esc(r.answer)}</p>${(r.picks||[]).map(p=>`<button class="pick-dish" data-id="${p.id}"><span><b>${NOVA.esc(p.name)}</b><em>${NOVA.esc(p.why)}</em></span><b>${CUR}${p.price}</b></button>`).join('')}`;box.querySelectorAll('.pick-dish').forEach(b=>b.onclick=()=>openDish(items.find(i=>i.id===+b.dataset.id)));}catch(e){box.innerHTML=`<p class="answer bad">${NOVA.esc(e.message)}</p>`;}}
  $('#menu-ask').onsubmit=e=>{e.preventDefault();const i=e.target.querySelector('input');ask(i.value);i.value='';};
  $$('#assistant .seeds button').forEach(b=>b.onclick=()=>ask(b.textContent));
  $('#dish-search').oninput=e=>{search=e.target.value.toLowerCase();renderMenu();};
  $('#filter-open').onclick=openFilters;

  persist(); renderNav(); renderFilters(); renderCartBar();
  NOVA.load($('#dishes'), async()=>{const d=await NOVA.api('/api/menu');items=d.items||[];sections=d.sections||[];renderNav();renderMenu();});
}
