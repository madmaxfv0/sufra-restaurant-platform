"""Capture routed pages, nested tabs and safe dialogs using an isolated database.
Usage: PYTHONPATH=. .venv312/bin/python tests/browser_i18n_audit.py --langs ru az en
Screenshots and machine-readable visible text are saved under artifacts/i18n/.
"""
import argparse,ast,json,os,re,socket,sqlite3,subprocess,sys,tempfile,time,html
from pathlib import Path
from datetime import datetime,timedelta
import httpx
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
args=argparse.ArgumentParser();args.add_argument('--langs',nargs='+',default=['ru']);args.add_argument('--no-images',action='store_true');args=args.parse_args()
out=ROOT/'artifacts/i18n';out.mkdir(parents=True,exist_ok=True)
node=next(n for n in ast.parse((ROOT/'app/main.py').read_text()).body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='ADMIN_PAGES' for t in n.targets))
routes=['/admin'+('/'+k if k else '') for k in ast.literal_eval(node.value)]
with tempfile.TemporaryDirectory(prefix='sufra-i18n-') as folder:
 temp=Path(folder);db=temp/'audit.db';src=sqlite3.connect(f'file:{ROOT}/nova.db?mode=ro',uri=True);dst=sqlite3.connect(db);src.backup(dst);src.close()
 now=datetime.now();roles={}
 for scope,role in [('admin','OWNER'),('waiter','WAITER')]:
  sid=dst.execute('select id from staff where role=? limit 1',(role,)).fetchone()[0];token='isolated-i18n-'+scope
  dst.execute('insert into authsession(token,staff_id,created_at,expires_at,last_seen_at) values(?,?,?,?,?)',(token,sid,now,now+timedelta(hours=6),now));roles[scope]=token
 dst.commit();dst.close()
 with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
 base=f'http://127.0.0.1:{port}'
 env={**os.environ,'DATABASE_URL':'sqlite:///'+str(db),'PYTHONDONTWRITEBYTECODE':'1','NOVA_SIMULATE':'0','SUFRA_STAFF_URL':base}
 bootstrap="""import os,asyncio
from pathlib import Path
import app.database as database
database.DB_PATH=Path(os.environ['DATABASE_URL'].removeprefix('sqlite:///'))
import app.main as main
async def disabled(): await asyncio.sleep(36000)
main.lifecycle.loop=disabled
import uvicorn
uvicorn.run(main.app,host='127.0.0.1',port=PORT,log_level='error')
""".replace('PORT',str(port))
 log=(temp/'server.log').open('w+');proc=subprocess.Popen([sys.executable,'-c',bootstrap],cwd=ROOT,env=env,stdout=log,stderr=log)
 results=[]
 try:
  client=httpx.Client(base_url=base,trust_env=False)
  for _ in range(150):
   try:
    if client.get('/health/live').status_code==200:break
   except httpx.HTTPError:pass
   time.sleep(.1)
  profiles={scope:client.get('/api/auth/me',headers={'Authorization':'Bearer '+token}).json() for scope,token in roles.items()}
  with sync_playwright() as pw:
   browser=pw.chromium.launch()
   for lang in args.langs:
    context=browser.new_context(viewport={'width':1440,'height':1000},locale={'ru':'ru-RU','az':'az-AZ','en':'en-GB'}[lang]);page=context.new_page();errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    context.add_init_script('localStorage.setItem("nova-lang",'+json.dumps(lang)+');'+''.join(f'sessionStorage.setItem("nova-{scope}-{key}",{json.dumps(value if isinstance(value,str) else json.dumps(value))});' for scope in roles for key,value in [('token',roles[scope]),('staff',profiles[scope].get('staff')),('perms',profiles[scope].get('permissions'))]))
    def capture(name):
     page.wait_for_timeout(350)
     texts=page.evaluate('''()=>{const out=new Set();const w=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);let n;while(n=w.nextNode()){const e=n.parentElement;if(!e||e.closest('script,style,code,pre,[data-i18n-skip]')||!e.checkVisibility())continue;const s=n.textContent.trim();if(s)out.add(s)}for(const e of document.querySelectorAll('[placeholder],[title],[aria-label],img[alt]')){if(e.checkVisibility())for(const a of ['placeholder','title','aria-label','alt']){const s=e.getAttribute(a);if(s)out.add(s)}}return [...out]}''')
     stem=lang+'-'+re.sub('[^a-zA-Z0-9_-]+','-',name).strip('-');img=stem+'.png'
     if not args.no_images:page.screenshot(path=str(out/img),full_page=True,animations='disabled')
     results.append({'lang':lang,'page':name,'url':page.url.replace(base,''),'screenshot':img,'texts':texts,'errors':list(errors)});errors.clear()
    for route in ['/',*routes,'/waiter','/guest/1','/book','/pay/1','/admin?fresh=1','/waiter?fresh=1']:
     page.goto(base+route);page.wait_for_timeout(850);capture(route)
     if route in ['/admin?fresh=1','/waiter?fresh=1']:
      if page.locator('.who').count():page.locator('.who').first.click();capture(route+'-pin');page.locator('#pin-back').click()
      if page.locator('#auth-use-qr').count():page.locator('#auth-use-qr').click();capture(route+'-qr')
     tabsel={'/admin/hr':'[data-hr-tab]','/admin/anbar':'.anbar-tab','/waiter':'.w-nav [data-tab]'}.get(route)
     if tabsel:
      keys=page.locator(tabsel).evaluate_all('(els)=>els.map(e=>e.dataset.hrTab||e.dataset.tab)')
      for key in keys:
       page.locator(tabsel+('[data-hr-tab="'+key+'"]' if route.endswith('/hr') else '[data-tab="'+key+'"]')).click();page.wait_for_timeout(450);capture(route+'-'+key)
       dialogs={'people':['#hr-add-person','[data-edit-person]','[data-photo-person]'],'leave':['#leave-new'],'training':['#tr-new'],'inventory':['#inv-new'],'recipes':['[data-recipe]'],'usage':['#usage-recipe']}.get(key,[])
       for sel in dialogs:
        if page.locator(sel).count() and page.locator(sel).first.is_visible():
         page.locator(sel).first.click();page.wait_for_timeout(200);capture(route+'-'+key+'-'+sel)
         close=page.locator('.modal-close,.modal-x,[data-close],.modal .close,#modal-close')
         if close.count():close.first.click()
         else:page.keyboard.press('Escape')
     route_dialogs={'/admin/reservations':['#new-booking','#new-waitlist'],'/admin/kitchen':['#k-flag'],'/admin/menu':['#mo-section','#mo-dish','[data-edit-dish]'],'/admin/accounting':['#new-journal'],'/guest/1':['#filter-open']}.get(route,[])
     for sel in route_dialogs:
      if page.locator(sel).count() and page.locator(sel).first.is_visible():
       page.locator(sel).first.click();capture(route+'-'+sel)
       close=page.locator('#modal.open .close')
       if close.count():close.first.click()
       else:page.keyboard.press('Escape')
     if route=='/waiter':
      page.locator('.w-nav [data-tab="tables"]').click()
      table=page.locator('[data-open-table],.floor-table[data-table]')
      if table.count():
       table.first.click();page.wait_for_timeout(300)
       for tab in ['overview','order','seats','notes','bill']:
        if page.locator('[data-ws="'+tab+'"]').count():
         page.locator('[data-ws="'+tab+'"]').click();capture('/waiter-table-'+tab)
     print(lang,route,flush=True)
    context.close()
   browser.close()
 finally:
  proc.terminate();proc.wait(timeout=15);log.close()
  (out/'audit.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
  cards=''.join(f'<article><h2>{html.escape(r["lang"].upper()+" · "+r["page"])}</h2><a href="{r["screenshot"]}"><img loading="lazy" src="{r["screenshot"]}"></a></article>' for r in results)
  (out/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>SUFRA language audit</title><style>body{font:16px system-ui;background:#101725;color:#eee;margin:24px}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(350px,1fr));gap:24px}img{width:100%;max-height:650px;object-fit:contain;object-position:top}h2{font-size:16px}article{background:#1d293b;padding:16px}</style><h1>SUFRA language review</h1><p>Pages, tabs and dialogs captured from a temporary database copy.</p><main>'+cards+'</main>')
 print('Captured',len(results),'views;',sum(bool(r['errors']) for r in results),'views with JavaScript errors.')
