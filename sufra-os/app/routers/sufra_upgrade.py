
from __future__ import annotations

import base64
import json
import os
import re
import sqlite3
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse
from sqlmodel import Session, select

from ..database import DB_PATH, engine
from .. import netutil
from ..live import hub
from .. import availability as _av, canon, rtime
from ..models import DiningTable, Guest, MenuItem, Reservation, Station, TableStatus

router = APIRouter(prefix="/api/sufra")
BASE = Path(__file__).resolve().parents[1]
GENERATED = BASE / "static" / "generated"
GENERATED.mkdir(parents=True, exist_ok=True)

TURNOVER_BUFFER = 15

def ensure_schema():
    """Small idempotent migration for existing SQLite copies."""
    con = sqlite3.connect(str(DB_PATH))
    try:
        for table, col, sql in [
            ("menuitem", "image_url", "ALTER TABLE menuitem ADD COLUMN image_url TEXT NOT NULL DEFAULT ''"),
            ("reservation", "duration_minutes", "ALTER TABLE reservation ADD COLUMN duration_minutes INTEGER NOT NULL DEFAULT 105"),
            ("reservation", "left_at", "ALTER TABLE reservation ADD COLUMN left_at DATETIME"),
        ]:
            cols={r[1] for r in con.execute(f"PRAGMA table_info({table})")}
            if col not in cols:
                con.execute(sql)
        con.commit()
    finally:
        con.close()

def _duration(party:int)->int:
    """The house booking length. One rule, defined in canon.duration_for and
    read from the restaurant's own settings, so the manager's book, SUFRA 360
    and the walk-in projection all protect a table for the same span."""
    with Session(engine) as s:
        return canon.duration_for(s, party)

def reservation_end(r: Reservation):
    return r.starts_at + timedelta(minutes=int(getattr(r, "duration_minutes", 0) or _duration(r.party_size)))

def _overlap(a0,a1,b0,b1):
    return a0 < b1 and b0 < a1

def _pref_score(t: DiningTable, pref: str)->float:
    p=(pref or '').strip().lower()
    zone=(t.zone or '').lower()
    score=(t.seats*0.02)
    # Lower is better. These are deterministic floor heuristics rather than pretending a model knows room acoustics.
    if any(w in p for w in ('quiet','quietest','calm','sakit','тих')):
        score += 0 if 'private' in zone else 1 if 'main' in zone else 2
        score += (t.x + t.y) * -0.18  # favour outer/farther positions
    if any(w in p for w in ('window','pəncərə','окн')):
        edge=min(t.x,1-t.x,t.y,1-t.y); score += edge*4
    if any(w in p for w in ('terrace','outdoor','teras','террас')):
        score += 0 if 'terrace' in zone else 5
    if any(w in p for w in ('bar','counter','бар')):
        score += 0 if 'bar' in zone else 5
    if any(w in p for w in ('private','özəl','приват')):
        score += 0 if 'private' in zone else 6
    return score

def table_conflicts(s: Session, table_id: int, start: datetime, end: datetime, ignore_id: int|None=None):
    """Does anything protect this table across [start, end)?

    The status test lives in one place — availability.RELEASED_STATUSES — so a
    cancelled, no-show or finished booking stops blocking here exactly when it
    stops blocking everywhere else."""
    rows=s.exec(select(Reservation).where(Reservation.table_id==table_id)).all()
    for r in rows:
        if ignore_id and r.id==ignore_id: continue
        if (r.status or '').lower() in _av.RELEASED_STATUSES: continue
        rs=r.starts_at-timedelta(minutes=TURNOVER_BUFFER)
        re=reservation_end(r)+timedelta(minutes=TURNOVER_BUFFER)
        if _overlap(start,end,rs,re): return True
    return False

def choose_table(s: Session, party:int, when:datetime, pref:str='', duration:int|None=None):
    duration=duration or _duration(party); end=when+timedelta(minutes=duration)
    candidates=[]
    for t in s.exec(select(DiningTable)).all():
        if t.seats < party: continue
        if t.zone == canon.ARCHIVED_ZONE: continue
        if table_conflicts(s,t.id,when,end): continue
        # Current occupant blocks a near-term booking until expected release + turnover.
        if t.status != TableStatus.AVAILABLE and t.seated_at:
            current_end=t.seated_at+timedelta(minutes=max(_duration(t.party_size or 2),75)+TURNOVER_BUFFER)
            if when < current_end: continue
        waste=(t.seats-party)*1.5
        candidates.append((_pref_score(t,pref)+waste,t))
    candidates.sort(key=lambda x:(x[0],x[1].seats,x[1].number))
    return candidates[0][1] if candidates else None

def reservation_overlay(s:Session, table_id:int, now:datetime|None=None):
    now=now or rtime.now()
    rows=[r for r in s.exec(select(Reservation).where(Reservation.table_id==table_id)).all()
          if r.status not in ('cancelled','no_show','completed','left')]
    rows.sort(key=lambda r:r.starts_at)
    guests={g.id:g for g in s.exec(select(Guest)).all()}
    active=None; upcoming=None
    for r in rows:
        if r.starts_at <= now <= reservation_end(r): active=r
        if r.starts_at > now and (upcoming is None or r.starts_at < upcoming.starts_at): upcoming=r
    r=active or upcoming
    if not r: return None
    g=guests.get(r.guest_id)
    return {
        'id':r.id,'guest':g.name if g else 'Guest','party':r.party_size,
        'time':r.starts_at.strftime('%H:%M'),'starts_at':r.starts_at.isoformat(),
        'ends_at':reservation_end(r).isoformat(),'status':r.status,
        'active':bool(active),'minutes_until':max(0,round((r.starts_at-now).total_seconds()/60)),
    }

def walkin_availability(s:Session, at:datetime|None=None, horizon_minutes:int=90):
    at=at or rtime.now(); until=at+timedelta(minutes=horizon_minutes)
    out=[]
    for t in s.exec(select(DiningTable)).all():
        if t.zone == canon.ARCHIVED_ZONE: continue
        conflict=table_conflicts(s,t.id,at,until)
        free=t.status==TableStatus.AVAILABLE and not conflict
        ov=reservation_overlay(s,t.id,at)
        out.append({'id':t.id,'number':t.number,'seats':t.seats,'zone':t.zone,'walkin_free':free,'reservation':ov})
    return out

def _image_prompt(name:str, blurb:str=''):
    desc=(blurb or '').strip()
    return (
      f"Hyperrealistic editorial restaurant food photograph of exactly this dish: {name}. "
      + (f"Dish description: {desc}. " if desc else '')
      + "Accurate ingredients and recognizable preparation, elegant modern fine-dining plating, natural believable portions, "
        "soft side lighting, shallow depth of field, neutral ceramic plate, restaurant table, no text, no hands, no people, "
        "no extra unrelated foods. The food must visually match the dish name, not a generic meal. Square composition."
    )

def generate_food_image(name:str, blurb:str='', item_id:int|None=None):
    key=os.getenv('OPENAI_API_KEY','').strip()
    if not key:
        raise RuntimeError('AI food photos need OPENAI_API_KEY. Upload a photo meanwhile, or set the key and retry.')
    payload=json.dumps({
        'model':'gpt-image-2', 'prompt':_image_prompt(name,blurb),
        'size':'1024x1024','quality':'medium','n':1
    }).encode()
    req=urllib.request.Request('https://api.openai.com/v1/images/generations', data=payload, method='POST', headers={
        'Authorization':f'Bearer {key}','Content-Type':'application/json'
    })
    try:
        with netutil.urlopen(req,timeout=120) as r: data=json.load(r)
    except urllib.error.HTTPError as e:
        detail=e.read().decode('utf-8','ignore')[:500]
        raise RuntimeError(f'Image generation failed ({e.code}): {detail}')
    first=(data.get('data') or [{}])[0]
    raw=first.get('b64_json')
    if not raw:
        url=first.get('url')
        if url:
            with netutil.urlopen(url,timeout=60) as r: binary=r.read()
        else:
            raise RuntimeError('The image service returned no image data.')
    else:
        binary=base64.b64decode(raw)
    slug=re.sub(r'[^a-z0-9]+','-',name.lower()).strip('-')[:45] or 'dish'
    fn=f"{item_id or 'new'}-{slug}-{int(datetime.now().timestamp())}.png"
    (GENERATED/fn).write_bytes(binary)
    return '/static/generated/'+fn

@router.post('/menu/generate-image-disabled')
async def generate_image(body:dict=Body(...)):
    name=(body.get('name') or '').strip(); blurb=(body.get('blurb') or '').strip(); item_id=body.get('item_id')
    if not name: return JSONResponse({'error':'Enter the dish name first.'},400)
    try: image_url=generate_food_image(name,blurb,int(item_id) if item_id else None)
    except Exception as e: return JSONResponse({'error':str(e)},503)
    if item_id:
        with Session(engine,expire_on_commit=False) as s:
            m=s.get(MenuItem,int(item_id))
            if m:
                m.image_url=image_url; s.add(m); s.commit()
    await hub.send('state',{'changed':['menu']})
    return {'ok':True,'image_url':image_url,'message':f'AI photo created for {name}'}

@router.post('/menu/items')
async def add_menu_item(body:dict=Body(...)):
    name=(body.get('name') or '').strip()
    if not name: return JSONResponse({'error':'Dish name is required.'},400)
    try: station=Station(str(body.get('station') or 'hot').lower())
    except Exception: station=Station.HOT
    with Session(engine,expire_on_commit=False) as s:
        m=MenuItem(name=name,course=body.get('course') or 'Main',station=station,price=float(body.get('price') or 0),
                   food_cost=float(body.get('food_cost') or 0),base_minutes=int(body.get('base_minutes') or 12),
                   blurb=body.get('blurb') or '',tags=body.get('tags') or '',image_url=body.get('image_url') or '')
        s.add(m); s.commit(); s.refresh(m); mid=m.id
    # If no photo was uploaded, generate one automatically when an API key exists.
    image_url=m.image_url
    data_url=(body.get('image_data') or '').strip()
    if data_url.startswith('data:image/'):
        try:
            header,encoded=data_url.split(',',1); ext='webp' if 'webp' in header else 'png' if 'png' in header else 'jpg'
            fn=f"{mid}-{re.sub(r'[^a-z0-9]+','-',name.lower()).strip('-')[:40]}.{ext}"
            (GENERATED/fn).write_bytes(base64.b64decode(encoded)); image_url='/static/generated/'+fn
            with Session(engine, expire_on_commit=False) as s:
                x=s.get(MenuItem,mid); x.image_url=image_url; s.add(x); s.commit()
        except Exception:
            image_url=''
    if not image_url and os.getenv('OPENAI_API_KEY'):
        try:
            image_url=generate_food_image(name,m.blurb,mid)
            with Session(engine, expire_on_commit=False) as s:
                x=s.get(MenuItem,mid); x.image_url=image_url; s.add(x); s.commit()
        except Exception:
            image_url=''
    await hub.send('state',{'changed':['menu']})
    return {'ok':True,'id':mid,'image_url':image_url,'message':f'{name} added to the menu.'}

@router.post('/menu/items/{item_id}/remove')
async def remove_menu_item(item_id:int):
    with Session(engine,expire_on_commit=False) as s:
        m=s.get(MenuItem,item_id)
        if not m: return JSONResponse({'error':'That dish no longer exists.'},404)
        name=m.name; m.available=False; s.add(m); s.commit()
    await hub.send('state',{'changed':['menu']})
    return {'ok':True,'message':f'{name} removed from active menus.'}

@router.get('/reservations/availability')
def availability(at:str='',party:int=2):
    try: when=datetime.fromisoformat(at) if at else datetime.now()
    except ValueError: when=datetime.now()
    with Session(engine, expire_on_commit=False) as s:
        table=choose_table(s,party,when,'')
        rows=walkin_availability(s,when)
        return {'ok':True,'suggested_table':table.number if table else None,'tables':rows,
                'walkin_free':sum(1 for r in rows if r['walkin_free']),'reserved':sum(1 for r in rows if r['reservation'])}
