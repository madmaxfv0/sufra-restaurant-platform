"""Verify dynamic translation and stable form values without a live database."""
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
scripts=['nova-core.js','sufra-translations.js','sufra-final-i18n.js']
fixture='''<!doctype html><html><body><h1>Employee directory</h1><select id="leave"><option>annual</option><option>sick</option></select><div id="late"></div><input id="field" placeholder="Work email"><span data-i18n-skip>Employee directory</span><textarea>Employee directory</textarea></body></html>'''
with sync_playwright() as p:
 browser=p.chromium.launch()
 for lang,title,annual in [('ru','Список сотрудников','ежегодный'),('az','Əməkdaş siyahısı','illik'),('en','Employee directory','annual')]:
  context=browser.new_context();page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.route('http://i18n.test/**',lambda route:route.fulfill(content_type='text/html',body=fixture))
  page.goto('http://i18n.test/');page.evaluate('(lang)=>localStorage.setItem("nova-lang",lang)',lang)
  for name in scripts:
   code=(ROOT/'app/static/js'/name).read_text();page.evaluate('(code)=>new Function(code)',code);page.add_script_tag(content=code)
  page.wait_for_function('(title)=>document.querySelector("h1").textContent===title',arg=title)
  page.wait_for_timeout(200)
  assert page.locator('#leave option').first.text_content()==annual
  assert page.locator('#leave').input_value()=='annual'
  assert page.locator('#leave option').nth(1).evaluate('o=>o.value')=='sick',lang
  # Different batches of added nodes and later edits must all get translated.
  page.evaluate('''()=>{const p=document.createElement('p');p.textContent='Headcount';document.querySelector('#late').append(p);setTimeout(()=>{const b=document.createElement('button');b.textContent='Assign training';document.querySelector('#late').append(b)},5)}''')
  page.wait_for_timeout(150)
  if lang!='en':assert 'Headcount' not in page.locator('#late').inner_text()
  page.locator('#late p').evaluate("e=>e.firstChild.data='Leave requests'")
  page.locator('#field').evaluate("e=>e.setAttribute('placeholder','Choose employee photo')")
  page.wait_for_timeout(150)
  if lang!='en':
   assert page.locator('#late p').inner_text()!='Leave requests'
   assert page.locator('#field').get_attribute('placeholder')!='Choose employee photo'
   translated=page.evaluate("SUFRA_FINAL_I18N.translate('Forecast confidence: low · generated 2026-09-15 12:00')")
   assert 'Forecast confidence' not in translated and 'generated' not in translated,translated
   assert 'ingredients' not in page.evaluate("SUFRA_FINAL_I18N.translate('Main · 3 ingredients')")
  assert page.locator('[data-i18n-skip]').inner_text()=='Employee directory'
  assert page.locator('textarea').input_value()=='Employee directory'
  assert not errors,errors
  context.close()
 browser.close()
print('Translation runtime passed: EN/AZ/RU, late inserts, text/attribute edits, stable enum values, dynamic quantities and skipped content.')
