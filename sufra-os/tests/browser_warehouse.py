"""Browser verification using real styles/scripts and an isolated API/database."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'tests'))
from test_warehouse_usage import WarehouseTests
from playwright.sync_api import sync_playwright
from urllib.parse import urlparse
from sqlmodel import Session
from app.models import Staff,Role
from app.security import hash_pin
case=WarehouseTests();case.setUp()
try:
 with Session(case.engine) as s:
  employee=Staff(name='Sofia Test',role=Role.WAITER,pin_hash=hash_pin('1148'));s.add(employee);s.commit();s.refresh(employee);staff_id=employee.id
 root=Path.cwd()
 with sync_playwright() as p:
  browser=p.chromium.launch();page=browser.new_page(viewport={'width':1440,'height':1000})
  errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  def route(r):
   u=urlparse(r.request.url);path=u.path
   if path.startswith('/static/'):
    file=root/'app'/path.lstrip('/');r.fulfill(body=file.read_bytes(),content_type='text/css' if file.suffix=='.css' else 'text/javascript');return
   if path.startswith('/api/'):
    response=case.client.request(r.request.method,path+('?' +u.query if u.query else ''),headers=r.request.headers,content=r.request.post_data)
    r.fulfill(status=response.status_code,body=response.content,headers=dict(response.headers));return
   head=''.join(f'<link rel="stylesheet" href="/static/css/{css}.css">' for css in ['nova','enterprise','sufra-v6','anbar','staff-access'])
   auth="<script>sessionStorage.setItem('nova-admin-token','admin-test');localStorage.setItem('nova-lang','ru');</script>"
   body='<div id="enterprise-hr"></div>' if path.endswith('hr') else '<nav id="anbar-tabs"><button class="anbar-tab" data-tab="usage">Dish ingredient usage</button></nav><div id="anbar-panel"></div><aside id="anbar-drawer" hidden><div id="anbar-drawer-body" class="anbar-drawer-inner"></div></aside>'
   scripts=''.join(f'<script src="/static/js/{name}.js"></script>' for name in ['nova-core','vendor/jsQR','staff-qr','enterprise','anbar','sufra-final-i18n'])
   boot='bootEnterpriseHR()' if path.endswith('hr') else "location.hash='usage';bootAnbar()"
   r.fulfill(content_type='text/html',body=f'<!doctype html><html><head><meta charset="utf-8">{head}</head><body class="app-admin"><main style="padding:28px">{body}</main><div id="modal" class="modal-backdrop"></div>{auth}{scripts}<script>{boot}</script></body></html>')
  page.route('**/*',route)
  page.goto('https://restaurant.test/admin/hr')
  button=page.locator(f'[data-badge-person="{staff_id}"]');button.wait_for();button.click()
  try:page.locator('.staff-badge-card img').wait_for(timeout=5000)
  except Exception:
   print('HR errors:',errors);print(page.locator('body').inner_text());raise
  first=page.locator('a[download]').get_attribute('href');assert first.startswith('data:image/png;base64,')
  page.locator('#modal .close').click()
  page.locator(f'[data-badge-person="{staff_id}"]').click()
  try:page.locator('.staff-badge-card img').wait_for(timeout=5000)
  except Exception:
   print('HR errors:',errors);print(page.locator('body').inner_text());raise
  assert page.locator('a[download]').get_attribute('href')==first
  page.locator('#badge-regenerate').click()
  page.wait_for_function('(old)=>document.querySelector("a[download]")?.href!==old',arg=first)
  page.goto('https://restaurant.test/admin/anbar')
  try:page.locator('#usage-portions').wait_for(timeout=5000)
  except Exception:
   print('Page errors:',errors);print(page.locator('body').inner_text());raise
  page.wait_for_function('document.body.innerText.includes("Филе сибаса")')
  assert '220' in page.locator('.warehouse-usage').inner_text()
  page.locator('#usage-portions').fill('3');page.locator('#usage-calculate').click()
  page.wait_for_function('document.querySelector(".warehouse-usage")?.innerText.includes("660")')
  page.screenshot(path='/tmp/warehouse-usage-ru.png',full_page=True)
  page.locator('#usage-recipe').click();page.locator('.l-qty').wait_for()
  assert page.locator('.l-qty').input_value()=='220'
  page.wait_for_function('document.querySelector(".l-item")?.innerText.includes("Филе сибаса")',timeout=5000)
  for js in ['anbar','staff-qr','enterprise','nova-core','sufra-v5','sufra-polish-v3','sufra-final-i18n']:
   page.evaluate('(code)=>{new Function(code);return true}',(root/'app/static/js'/f'{js}.js').read_text())
  assert not errors,errors
  print('Browser passed: HR badge generation/reopening/rotation; Russian warehouse ingredients; portions preview; gram-based recipe editor.')
  browser.close()
finally:case.tearDown()
