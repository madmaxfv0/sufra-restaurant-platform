import sys, json, base64
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'tests'))
from test_staff_qr import StaffAccessTests
from playwright.sync_api import sync_playwright
case=StaffAccessTests();case.setUp()
try:
 d=case.provision()
 root=Path.cwd()
 with sync_playwright() as p:
  browser=p.chromium.launch()
  page=browser.new_page(viewport={'width':390,'height':844})
  errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  def route(r):
   from urllib.parse import urlparse
   path=urlparse(r.request.url).path
   if path.startswith('/static/'):
    file=root/'app'/path.lstrip('/')
    r.fulfill(body=file.read_bytes(),content_type='text/javascript' if file.suffix=='.js' else 'text/css');return
   if path.startswith('/api/'):
    response=case.client.request(r.request.method,path,headers=r.request.headers,content=r.request.post_data)
    r.fulfill(status=response.status_code,body=response.content,headers=dict(response.headers));return
   r.fulfill(content_type='text/html',body='''<html><body><main id="auth-mount"></main><div id="modal"></div>
    <script>window.NOVA_STAFF_ROSTER=[];</script>
    <script src="/static/js/nova-core.js"></script><script src="/static/js/vendor/jsQR.js"></script><script src="/static/js/staff-qr.js"></script>
    <script>NOVA.auth.staffLogin(document.querySelector('#auth-mount'),(staff)=>{window.signedIn=staff;document.querySelector('#auth-mount').textContent='Signed in';});</script></body></html>''')
  page.route('**/*',route)
  page.goto('https://restaurant.test/waiter')
  assert page.locator('#staff-scan').count()==0
  page.evaluate("NOVA.staffQR(document.querySelector('#auth-mount'),()=>{},()=>{})")
  page.goto(d['qr_url'])
  page.locator('#pin-back').click()
  page.evaluate("NOVA.staffQR(document.querySelector('#auth-mount'),(staff,token)=>{NOVA.auth.staffLogin(document.querySelector('#auth-mount'),()=>{});location.hash='staff_qr='+token},()=>{})")
  page.locator('#qr-file').set_input_files({'name':'badge.png','mimeType':'image/png','buffer':base64.b64decode(d['qr_image'].split(',')[1])})
  page.locator('#pin-input').wait_for()
  page.locator('#pin-input').fill(d['temporary_pin'])
  page.wait_for_function('window.signedIn !== undefined')
  assert page.evaluate('window.signedIn.id')==d['staff_id']
  assert page.evaluate("localStorage.getItem('nova-waiter-token')") is None
  # Direct badge link prompts a PIN, even with an existing signed-in session.
  page.goto(d['qr_url'])
  page.locator('#pin-input').wait_for()
  assert '#staff_qr=' not in page.url
  # Print/download modal renders genuine badge; no secrets persisted by it.
  page.evaluate('(r)=>NOVA.showStaffCredentials(r)',d)
  assert page.locator('a[download]').get_attribute('href')==d['qr_image']
  # Compile all changed JS, including the existing settings file.
  for file in ['nova-core.js','staff-qr.js','enterprise.js','sufra-v5.js']:
   page.evaluate('(code)=>{new Function(code);return true}',(root/'app/static/js'/file).read_text())
  assert not errors,errors
  print('Browser checks passed: QR image decoding, PIN login, fragment cleanup, badge download, and JS syntax.')
  browser.close()
finally:case.tearDown()
