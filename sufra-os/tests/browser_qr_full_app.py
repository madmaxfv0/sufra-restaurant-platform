"""Real HTTP + actual admin/waiter templates; only a temporary database is changed."""
import os,sys,json,sqlite3,tempfile,subprocess,time,socket
from pathlib import Path
from datetime import datetime,timedelta
import httpx
from cryptography.fernet import Fernet
from playwright.sync_api import sync_playwright
root=Path.cwd()
with tempfile.TemporaryDirectory() as directory:
 temp=Path(directory);db=temp/'test.db'
 src=sqlite3.connect('file:nova.db?mode=ro',uri=True);dst=sqlite3.connect(db);src.backup(dst);src.close()
 owner=dst.execute("select id from staff where role='OWNER' limit 1").fetchone()[0]
 now=datetime.now();token='qr-browser-admin'
 dst.execute('insert into authsession(token,staff_id,created_at,expires_at,last_seen_at) values(?,?,?,?,?)',(token,owner,now,now+timedelta(hours=1),now));dst.commit();dst.close()
 with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
 base=f'http://127.0.0.1:{port}'
 env={**os.environ,'DATABASE_URL':'sqlite:///'+str(db),'SUFRA_STAFF_URL':base,'SUFRA_PUBLIC_URL':'','SUFRA_STAFF_QR_KEY':Fernet.generate_key().decode(),'PYTHONDONTWRITEBYTECODE':'1','NOVA_SIMULATE':'0'}
 bootstrap='''import os,asyncio
from pathlib import Path
import app.database as database
database.DB_PATH=Path(os.environ['DATABASE_URL'].removeprefix('sqlite:///'))
import app.main as main
async def disabled():
    await asyncio.sleep(3600)
main.lifecycle.loop=disabled
import uvicorn
uvicorn.run(main.app,host='0.0.0.0',port=int(os.environ['QR_TEST_PORT']),log_level='error')
'''
 env['QR_TEST_PORT']=str(port)
 log=(temp/'server.log').open('w+')
 process=subprocess.Popen([sys.executable,'-c',bootstrap],cwd=root,env=env,stdout=log,stderr=log)
 try:
  client=httpx.Client(base_url=base,headers={'Authorization':'Bearer '+token},trust_env=False)
  for _ in range(100):
   try:
    if client.get('/api/auth/me').status_code==200:break
   except httpx.ConnectError:pass
   time.sleep(.1)
  else:log.seek(0);raise RuntimeError(log.read())
  who=client.get('/api/auth/me').json()
  r=client.post('/api/enterprise/hr/staff',json={'name':'QR Workflow Waiter','role':'waiter'});assert r.status_code==200,r.text
  employee=r.json();sid=employee['staff_id'];pin=employee['temporary_pin']
  with sync_playwright() as p:
   browser=p.chromium.launch();context=browser.new_context(accept_downloads=True)
   page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
   page.goto(base+'/admin/hr');page.wait_for_function('typeof NOVA!=="undefined" && !!NOVA.auth')
   page.evaluate('(data)=>NOVA.auth.setSession(data.token,data.staff,data.permissions)',{'token':token,**who});page.reload()
   page.locator(f'[data-badge-person="{sid}"]').click();page.locator('#badge-regenerate').wait_for()
   old=page.locator('#badge-open').get_attribute('href')
   page.locator('#badge-regenerate').click()
   page.wait_for_function('(old)=>document.querySelector("#badge-open")?.href!==old',arg=old)
   new=page.locator('#badge-open').get_attribute('href');assert '/waiter#staff_qr=' in new
   assert '127.0.0.1' not in new,'Phone badge must not use loopback'
   assert client.post('/api/auth/qr/identify',json={'qr_token':old.split('#staff_qr=')[1]}).status_code==401
   with page.expect_download() as download:page.locator('a[download]').click()
   file=temp/'badge.png';download.value.save_as(file);assert file.read_bytes().startswith(b'\x89PNG')
   # Capture print document instead of opening a physical printer dialog.
   page.evaluate('''()=>{const append=document.body.appendChild.bind(document.body);document.body.appendChild=function(el){const result=append(el);if(el.tagName==='IFRAME')el.contentWindow.print=()=>{window.printedBadge=el.contentDocument.body.innerHTML};return result}}''')
   page.locator('#badge-print').click();page.wait_for_function('!!window.printedBadge')
   printed=page.evaluate('window.printedBadge');assert 'data:image/png;base64,' in printed;assert pin not in printed
   with page.expect_popup() as popup:page.locator('#badge-open').click()
   waiter=popup.value;waiter.locator('#pin-input').wait_for();assert waiter.locator('#pin-input').get_attribute('maxlength')=='4'
   waiter.locator('#pin-input').fill(pin);waiter.locator('#w-shell').wait_for(state='visible')
   waiter.wait_for_function('window.NOVA_ACTIVE_STAFF?.id === '+str(sid));assert '/waiter' in waiter.url
   waiter.goto(base+'/waiter?fresh=1')
   waiter.locator('#auth-use-qr').wait_for()
   waiter.locator('.who[data-id="'+str(sid)+'"]').click()
   waiter.locator('#pin-input').fill(pin)
   waiter.locator('#w-shell').wait_for(state='visible')
   waiter.wait_for_function('window.NOVA_ACTIVE_STAFF?.id === '+str(sid))
   # Copy action works through clipboard or the explicit manual-copy fallback.
   page.evaluate("Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async text=>{window.copiedBadgeLink=text}}})")
   page.locator('#badge-copy').click();page.wait_for_function('!!window.copiedBadgeLink')
   assert page.evaluate('window.copiedBadgeLink')==new
   page.evaluate("()=>{navigator.clipboard.writeText=async()=>{throw new Error('Clipboard unavailable')}}")
   page.locator('#badge-copy').click();page.locator('textarea[readonly]').wait_for()
   assert page.locator('textarea[readonly]').input_value()==new
   # Expired admin session must go straight back to sign-in instead of HR error shell.
   with sqlite3.connect(db) as conn:conn.execute('update authsession set expires_at=? where token=?',(now-timedelta(minutes=1),token));conn.commit()
   page.evaluate("NOVA.api('/api/enterprise/hr/staff').catch(()=>{})")
   page.wait_for_url('**session_expired=1*');page.locator('#auth-mount .who').first.wait_for()
   assert page.evaluate('NOVA.auth.getToken()') is None
   assert not errors,errors
   print('Full app passed: regenerate/revoke, PNG download, PIN-free print, copy link, real waiter app PIN login, expired-session recovery.')
   browser.close()
 finally:
  process.terminate();process.wait(timeout=15);log.close()
