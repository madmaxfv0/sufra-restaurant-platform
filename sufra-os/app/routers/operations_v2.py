from __future__ import annotations

import json
import base64
import re
import urllib.parse
import urllib.request
from pathlib import Path
from datetime import datetime, date
from fastapi import APIRouter, Body, Depends
from fastapi.responses import JSONResponse
from sqlmodel import Session, select

from .. import allergens as allergen_check
from .. import intelligence as ai
from .. import events, netutil
from ..database import engine
from ..live import hub, open_task
from ..models import (
    AuditLog, AvailabilityFlag, Complaint, DiningTable, Guest, Ingredient,
    ItemState, MenuArchive, MenuContent, MenuItem, MenuSection, Notification, Order, OrderChange,
    OrderItem, RecipeLine, Reservation, Role, Staff, TableArchive, TableNote,
    TableStatus, TaskKind,
)
from ..ops_utils import ARCHIVED_ZONE, archived_menu_ids, menu_sections, unavailable_menu_ids
from ..permissions import current_staff, has_permission, require_permission
from .. import rtime

router = APIRouter()

def db(): return Session(engine, expire_on_commit=False)

def _manager_role(staff: Staff) -> bool:
    return staff.role in {Role.OWNER, Role.GENERAL_MANAGER, Role.RESTAURANT_MANAGER}

def _table_by_number(s, number):
    t=s.exec(select(DiningTable).where(DiningTable.number==number)).first()
    return t if t and t.zone != ARCHIVED_ZONE else None

# Allergy parsing and dish screening live in app/allergens.py so the order
# inspector, the waiter's order pad and guest self-ordering all reach the same
# verdict. This module used to carry its own substring aliases, which read the
# guest's CRM profile and the table's notes but never the booking itself - so
# an allergy a guest typed into SUFRA 360 three weeks ago was invisible here.
# The substring matching also could not tell "coconut" from "nut".

@router.post('/api/ops/order-inspect')
def inspect_order(body: dict = Body(...), staff: Staff = Depends(require_permission('can_create_order'))):
    with db() as s:
        t=s.get(DiningTable,int(body.get('table_id',0)))
        if not t or t.zone == ARCHIVED_ZONE:
            return JSONResponse({'error':'Pick an active table first.'},400)
        draft=body.get('items') or []
        if not draft:
            return JSONResponse({'error':'The order is empty.'},400)
        menu={m.id:m for m in s.exec(select(MenuItem)).all()}
        draft_ids=[int(x.get('id',0) or 0) for x in draft if isinstance(x,dict)]
        screening=allergen_check.screen(s,t.id,draft_ids)
        declared=screening['declared']
        requested_allergens=set(declared['allergens'])
        blocked,reasons=unavailable_menu_ids(s)
        pressure={p['station']:p['now'] for p in ai.station_pressure(s)}
        issues=[]; prep=[]; draft_mains=0
        recipe_by_item={}
        for line in s.exec(select(RecipeLine)).all():
            recipe_by_item.setdefault(line.menu_item_id,[]).append(line.ingredient_id)
        ingredients={i.id:i.name for i in s.exec(select(Ingredient)).all()}
        for line in draft:
            m=menu.get(int(line.get('id',0)))
            if not m: continue
            qty=max(1,int(line.get('qty',1)))
            note=str(line.get('note') or '')
            if m.id in blocked or not m.available:
                issues.append({'severity':'critical','blocking':True,'code':'unavailable','title':f'{m.name} is unavailable.','detail':reasons.get(m.id,'It has been taken off sale by the kitchen.')})
            ing_names=[ingredients[i] for i in recipe_by_item.get(m.id,[]) if i in ingredients]
            for c in [x for x in screening['conflicts'] if x['menu_item_id']==m.id]:
                issues.append({'severity':'critical','blocking':True,'code':'allergy',
                    'title':f"{c['dish']} contains {c['allergen']}.",
                    'detail':f"{c['declared_by']} declared {c['allergen']} on the {c['source']}. "
                             f"This dish {c['evidence']}."})
            lname=m.name.lower(); nlow=note.lower()
            if (m.station.value=='grill' or 'steak' in lname) and not any(x in nlow for x in ('rare','medium rare','medium','medium well','well done','blue')):
                issues.append({'severity':'warning','blocking':False,'code':'temperature','title':f'{m.name}: temperature missing.','detail':'Choose a cooking temperature before the grill fires it.'})
            if ('dairy' in requested_allergens or 'no dairy' in nlow) and ('mashed potato' in nlow or 'mash' in nlow or 'mashed potato' in lname or 'mash' in lname):
                issues.append({'severity':'critical','blocking':True,'code':'dairy-side','title':'No-dairy request conflicts with mashed potato.','detail':'Mashed potato may contain butter or cream. Choose another side or confirm a dairy-free preparation.'})
            if m.course=='Main':
                draft_mains += qty
                low,high=ai.predict_prep_time(s,m,pressure.get(m.station.value,0))
                prep.append({'name':m.name,'minutes':high,'qty':qty})
        # Count already-sent mains as well, so the cover check is not fooled by multi-course sending.
        existing_mains=0
        order=s.exec(select(Order).where(Order.table_id==t.id,Order.paid==False)).first()  # noqa:E712
        if order:
            for oi in s.exec(select(OrderItem).where(OrderItem.order_id==order.id)).all():
                mm=menu.get(oi.menu_item_id)
                if mm and mm.course=='Main' and not oi.void_reason:
                    existing_mains += oi.qty
        # An allergy SUFRA cannot map onto the menu is the one that matters
        # most: it has to be said out loud rather than pass as "no risks".
        for term in declared['unrecognised']:
            issues.append({'severity':'warning','blocking':False,'code':'allergy-unknown',
                'title':f'"{term}" could not be checked against the menu.',
                'detail':'SUFRA does not recognise this as one of the allergens the '
                         'kitchen labels, so nothing here has been screened for it. '
                         'Confirm it with the guest and the kitchen by hand.'})
        for e in declared['unacknowledged']:
            issues.append({'severity':'critical','blocking':True,'code':'allergy-unread',
                'title':'An allergy note on this table has not been read.',
                'detail':e['term']})

        party=max(0,t.party_size)
        mains=existing_mains+draft_mains
        if party and mains < party:
            issues.append({'severity':'warning','blocking':False,'code':'main-count','title':f'{party} guests but only {mains} mains ordered.','detail':'Confirm whether someone is sharing, skipping a main, or still deciding.'})
        if party and mains > party+1:
            issues.append({'severity':'warning','blocking':False,'code':'main-count-high','title':f'{mains} mains for {party} guests.','detail':'Check for accidental duplicate mains.'})
        sequence=[]
        if prep:
            slow=max(x['minutes'] for x in prep); fast=min(x['minutes'] for x in prep)
            if slow-fast >= 6:
                issues.append({'severity':'info','blocking':False,'code':'timing','title':'Main-course preparation times vary significantly.','detail':'SUFRA generated a firing sequence so the course can land together.'})
                for x in sorted(prep,key=lambda z:-z['minutes']):
                    delay=max(0,slow-x['minutes'])
                    sequence.append({'name':x['name'],'minutes':x['minutes'],'fire_after':delay,'instruction':'Fire now' if delay==0 else f'Fire +{delay} min'})
        return {'ok':True,'table':t.number,'party':party,'issues':issues,'blocking':any(i['blocking'] for i in issues),'sequence':sequence,'checked_at':rtime.now().strftime('%H:%M')}

@router.post('/api/ops/order-items/{item_id}/change')
async def change_sent_item(item_id:int, body:dict=Body(...), staff:Staff=Depends(require_permission('can_edit_order'))):
    with db() as s:
        item=s.get(OrderItem,item_id)
        if not item: return JSONResponse({'error':'That order line no longer exists.'},404)
        order=s.get(Order,item.order_id); table=s.get(DiningTable,order.table_id) if order else None; menu=s.get(MenuItem,item.menu_item_id)
        if not order or order.paid or not table: return JSONResponse({'error':'That bill is already closed.'},400)
        if item.void_reason: return JSONResponse({'error':'That line has already been voided.'},409)
        action=body.get('action','modify')
        old={'qty':item.qty,'note':item.note,'state':item.state.value,'void_reason':item.void_reason}
        if action=='void':
            if not has_permission(staff.role, 'can_void_item'):
                return JSONResponse({'error':'Voiding a sent item requires manager permission.','needs_manager':True},403)
            reason=(body.get('reason') or '').strip()
            if reason not in {'Guest changed mind', 'Incorrect item entered', 'Allergy correction',
                              'Manager request', 'Kitchen issue'}:
                return JSONResponse({'error':'Choose a reason for the void.'},400)
            item.void_reason=reason
            kind='void'; new={'voided':True,'reason':reason}
        else:
            if action != 'modify':
                return JSONResponse({'error':'Unknown order change.'},400)
            if 'qty' in body:
                try: qty=int(body['qty'])
                except (TypeError,ValueError): return JSONResponse({'error':'Quantity must be a number.'},400)
                if not 1 <= qty <= 50: return JSONResponse({'error':'Quantity must be between 1 and 50.'},400)
                item.qty=qty
            if 'note' in body:
                item.note=str(body.get('note') or '').strip()
                if len(item.note)>500:return JSONResponse({'error':'Item notes are too long.'},400)
            reason=(body.get('reason') or 'Guest requested a change').strip()
            kind='modify'; new={'qty':item.qty,'note':item.note}
        s.add(item)
        ch=OrderChange(order_item_id=item.id,table_id=table.id,requested_by=staff.id,kind=kind,
                       old_value=json.dumps(old,ensure_ascii=False),new_value=json.dumps(new,ensure_ascii=False),reason=reason)
        s.add(ch)
        s.add(AuditLog(staff_id=staff.id,action=f'order_{kind}',entity_type='order_item',entity_id=item.id,
                       detail=f'Table {table.number} · {menu.name if menu else item.menu_item_id} · {reason}'))
        s.add(Notification(level='critical' if kind=='void' else 'warning',title=f'ORDER CHANGE · Table {table.number}',
                           body=f"{kind.upper()}: {menu.name if menu else 'item'} · {reason}",audience='kitchen'))
        s.commit(); s.refresh(ch)
    await hub.send('state',{'changed':['order-change','kitchen']})
    return {'ok':True,'change_id':ch.id,'message':'Kitchen has been updated with the change.'}

@router.get('/api/ops/kitchen-control')
def kitchen_control(staff:Staff=Depends(current_staff)):
    with db() as s:
        menu={m.id:m for m in s.exec(select(MenuItem)).all()}; tables={t.id:t for t in s.exec(select(DiningTable)).all()}; staffmap={p.id:p for p in s.exec(select(Staff)).all()}
        items={i.id:i for i in s.exec(select(OrderItem)).all()}
        changes=[]
        for c in s.exec(select(OrderChange).where(OrderChange.status=='open').order_by(OrderChange.created_at.desc())).all():
            oi=items.get(c.order_item_id); m=menu.get(oi.menu_item_id) if oi else None; t=tables.get(c.table_id); who=staffmap.get(c.requested_by)
            changes.append({'id':c.id,'kind':c.kind,'table':t.number if t else '?','item':m.name if m else 'Item','reason':c.reason,
                            'new':c.new_value,'by':who.name if who else 'Staff','at':c.created_at.strftime('%H:%M')})
        flags=[]
        for f in s.exec(select(AvailabilityFlag).where(AvailabilityFlag.active==True).order_by(AvailabilityFlag.created_at.desc())).all():  # noqa:E712
            flags.append({'id':f.id,'kind':f.kind,'ref_id':f.ref_id,'label':f.label,'note':f.note})
        archived=archived_menu_ids(s)
        return {'changes':changes,'flags':flags,
                'menu_items':[{'id':m.id,'name':m.name,'course':m.course} for m in menu.values() if m.id not in archived],
                'ingredients':[{'id':i.id,'name':i.name,'unit':i.unit,'stock':i.in_stock} for i in s.exec(select(Ingredient).order_by(Ingredient.name)).all()]}

@router.post('/api/ops/kitchen/availability')
async def set_availability(body:dict=Body(...),staff:Staff=Depends(require_permission('can_manage_availability'))):
    kind=str(body.get('kind') or '').strip()
    try: ref_id=int(body.get('ref_id') or 0)
    except (TypeError,ValueError): ref_id=0
    available=body.get('available',False) is True or str(body.get('available','')).lower() in {'1','true','yes','on'}
    note=str(body.get('note') or '').strip()
    if kind not in {'menu_item','ingredient'}: return JSONResponse({'error':'Choose a dish or ingredient.'},400)
    if ref_id<=0: return JSONResponse({'error':'Choose the exact dish or ingredient.'},400)
    try:
        with db() as s:
            obj=s.get(MenuItem,ref_id) if kind=='menu_item' else s.get(Ingredient,ref_id)
            if not obj: return JSONResponse({'error':'That item no longer exists.'},404)
            active=s.exec(select(AvailabilityFlag).where(AvailabilityFlag.kind==kind,AvailabilityFlag.ref_id==ref_id,AvailabilityFlag.active==True)).all()  # noqa:E712
            for f in active:
                f.active=False; s.add(f)
            if not available:
                s.add(AvailabilityFlag(kind=kind,ref_id=ref_id,label=obj.name,note=note or 'Unavailable tonight',created_by=staff.id))
            s.add(Notification(level='warning' if not available else 'good',title=f"{obj.name} {'unavailable' if not available else 'back on'}",body=note or ('Kitchen marked it unavailable.' if not available else 'Kitchen restored availability.'),audience='all'))
            events.record(s, 'menu_availability', 'Menu availability changed',
                          detail=f"{obj.name} · " + ('available again' if available else (note or 'sold out')),
                          actor=staff.name or 'Kitchen',
                          severity='note' if available else 'warning')
            s.commit()
    except Exception as exc:
        return JSONResponse({'error':'Availability could not be updated.','detail':str(exc)},500)
    await hub.send('state',{'changed':['availability','menu']})
    return {'ok':True,'message':f"{obj.name} {'is unavailable' if not available else 'is available again'}."}

@router.post('/api/ops/order-changes/{change_id}/ack')
async def ack_change(change_id:int,staff:Staff=Depends(require_permission('can_manage_availability'))):
    with db() as s:
        c=s.get(OrderChange,change_id)
        if not c: return JSONResponse({'error':'That change is gone.'},404)
        c.status='acknowledged'; c.acknowledged_at=rtime.now(); c.acknowledged_by=staff.id; s.add(c); s.commit()
    await hub.send('state',{'changed':['order-change-ack']})
    return {'ok':True}

async def _page_manager(s,table,reason,source='guest'):
    s.add(Notification(level='critical',title=f'Manager requested · Table {table.number}',body=reason,audience='manager'))
    open_task(s,table,TaskKind.CALL,f'Manager requested at table {table.number}: {reason}',1)

@router.post('/api/ops/guest/{table_number}/manager')
async def guest_manager(table_number:int,body:dict=Body(...)):
    with db() as s:
        t=_table_by_number(s,table_number)
        if not t:return JSONResponse({'error':'That table is not active.'},404)
        reason=(body.get('reason') or 'Guest asked to speak with a manager').strip(); await _page_manager(s,t,reason); s.commit()
    await hub.send('state',{'changed':['manager-request']}); return {'ok':True,'message':'A manager has been notified.'}

@router.post('/api/ops/guest/{table_number}/complaint')
async def guest_complaint(table_number:int,body:dict=Body(...)):
    with db() as s:
        t=_table_by_number(s,table_number)
        if not t:return JSONResponse({'error':'That table is not active.'},404)
        message=(body.get('message') or '').strip()
        if not message:return JSONResponse({'error':'Please describe what happened.'},400)
        category=body.get('category','service'); severity=body.get('severity','normal')
        c=Complaint(table_id=t.id,source='guest',category=category,severity=severity,message=message); s.add(c)
        s.add(Notification(level='critical',title=f'Guest complaint · Table {t.number}',body=f'{category}: {message}',audience='manager'))
        open_task(s,t,TaskKind.CALL,f'Complaint at table {t.number}: {message}',1); s.commit(); s.refresh(c)
    await hub.send('state',{'changed':['complaint']}); return {'ok':True,'id':c.id,'message':'Your complaint has been sent to the manager on duty.'}

@router.post('/api/ops/waiter/table/{table_id}/complaint')
async def waiter_complaint(table_id:int,body:dict=Body(...),staff:Staff=Depends(current_staff)):
    with db() as s:
        t=s.get(DiningTable,table_id)
        if not t:return JSONResponse({'error':'No such table.'},404)
        message=(body.get('message') or '').strip()
        if not message:return JSONResponse({'error':'Write the complaint first.'},400)
        c=Complaint(table_id=t.id,source='waiter',staff_id=staff.id,category=body.get('category','service'),severity=body.get('severity','normal'),message=message);s.add(c)
        s.add(Notification(level='critical',title=f'Complaint filed · Table {t.number}',body=f'{staff.name}: {message}',audience='manager'));s.commit();s.refresh(c)
    await hub.send('state',{'changed':['complaint']});return {'ok':True,'id':c.id,'message':'Complaint filed for management.'}

@router.get('/api/ops/complaints')
def complaints(staff:Staff=Depends(current_staff)):
    if staff.role not in {Role.OWNER,Role.GENERAL_MANAGER,Role.RESTAURANT_MANAGER,Role.HOST}:
        return JSONResponse({'error':'Your role cannot view complaints.'},403)
    with db() as s:
        tables={t.id:t for t in s.exec(select(DiningTable)).all()}; people={p.id:p for p in s.exec(select(Staff)).all()}
        rows=[]
        for c in s.exec(select(Complaint).order_by(Complaint.created_at.desc())).all():
            t=tables.get(c.table_id); p=people.get(c.staff_id)
            rows.append({'id':c.id,'table':t.number if t else '?','source':c.source,'by':p.name if p else c.source,'category':c.category,
                         'severity':c.severity,'message':c.message,'status':c.status,'at':c.created_at.strftime('%H:%M')})
        return {'complaints':rows[:100],'open':sum(1 for r in rows if r['status']=='open')}

@router.post('/api/ops/complaints/{complaint_id}/resolve')
async def resolve_complaint(complaint_id:int,staff:Staff=Depends(require_permission('can_manage_complaints'))):
    with db() as s:
        c=s.get(Complaint,complaint_id)
        if not c:return JSONResponse({'error':'That complaint is gone.'},404)
        c.status='resolved';c.resolved_at=rtime.now();c.resolved_by=staff.id;s.add(c);s.commit()
    await hub.send('state',{'changed':['complaint-resolved']});return {'ok':True}

@router.get('/api/ops/floor-control')
def floor_control(staff:Staff=Depends(require_permission('can_assign_tables'))):
    with db() as s:
        waiters=s.exec(select(Staff).where(Staff.role.in_([Role.WAITER,Role.BARTENDER])).order_by(Staff.name)).all()
        tables=s.exec(select(DiningTable).order_by(DiningTable.number)).all()
        amap={a.table_id:a for a in s.exec(select(TableArchive).where(TableArchive.active==True)).all()}  # noqa:E712
        return {'waiters':[{'id':w.id,'name':w.name,'section':w.section,'on_shift':w.on_shift} for w in waiters],
                'tables':[{'id':t.id,'number':t.number,'seats':t.seats,'zone':t.zone,'waiter_id':t.waiter_id,'status':t.status.value} for t in tables if t.zone!=ARCHIVED_ZONE],
                'archived':[{'id':t.id,'number':t.number,'seats':t.seats,'zone':amap[t.id].original_zone if t.id in amap else 'Main'} for t in tables if t.zone==ARCHIVED_ZONE]}

@router.post('/api/ops/tables/{table_id}/assign')
async def assign_table(table_id:int,body:dict=Body(...),staff:Staff=Depends(require_permission('can_assign_tables'))):
    with db() as s:
        t=s.get(DiningTable,table_id);wid=body.get('waiter_id');w=s.get(Staff,int(wid)) if wid not in (None,'',0,'0') else None
        if not t or t.zone==ARCHIVED_ZONE:return JSONResponse({'error':'That table is not active.'},404)
        if w and w.role not in {Role.WAITER,Role.BARTENDER}:return JSONResponse({'error':'Choose a waiter or bartender.'},400)
        t.waiter_id=w.id if w else None;s.add(t);s.add(AuditLog(staff_id=staff.id,action='assign_table',entity_type='table',entity_id=t.id,detail=f'Table {t.number} → {w.name if w else "unassigned"}'));s.commit()
    await hub.send('state',{'changed':['table-assignment']});return {'ok':True,'message':f'Table {t.number} assignment updated.'}

@router.post('/api/ops/tables')
async def add_table(body:dict=Body(...),staff:Staff=Depends(require_permission('can_assign_tables'))):
    with db() as s:
        number=int(body.get('number',0));seats=max(1,int(body.get('seats',2)))
        if number<=0:return JSONResponse({'error':'Enter a table number.'},400)
        if s.exec(select(DiningTable).where(DiningTable.number==number)).first():return JSONResponse({'error':'That table number already exists. Restore it if it is archived.'},400)
        t=DiningTable(number=number,seats=seats,zone=(body.get('zone') or 'Main').strip(),shape=body.get('shape','round'),x=float(body.get('x',.5)),y=float(body.get('y',.5)),status=TableStatus.AVAILABLE,waiter_id=int(body['waiter_id']) if body.get('waiter_id') else None);s.add(t);s.commit();s.refresh(t)
    await hub.send('state',{'changed':['table-added']});return {'ok':True,'id':t.id,'message':f'Table {number} added.'}

@router.post('/api/ops/tables/{table_id}/archive')
async def archive_table(table_id:int,staff:Staff=Depends(require_permission('can_assign_tables'))):
    with db() as s:
        t=s.get(DiningTable,table_id)
        if not t or t.zone==ARCHIVED_ZONE:return JSONResponse({'error':'That table is already removed.'},400)
        if t.status not in {TableStatus.AVAILABLE,TableStatus.CLEANING}:return JSONResponse({'error':'Finish the current service before removing this table.'},400)
        if s.exec(select(Order).where(Order.table_id==t.id,Order.paid==False)).first():return JSONResponse({'error':'This table still has an open bill.'},400)  # noqa:E712
        upcoming=s.exec(select(Reservation).where(Reservation.table_id==t.id,Reservation.starts_at>=rtime.now(),Reservation.status=='confirmed')).first()
        if upcoming:return JSONResponse({'error':'Move or cancel the upcoming reservation before removing this table.'},400)
        s.add(TableArchive(table_id=t.id,original_zone=t.zone,archived_by=staff.id));t.zone=ARCHIVED_ZONE;t.waiter_id=None;t.party_size=0;t.status=TableStatus.AVAILABLE;s.add(t);s.commit()
    await hub.send('state',{'changed':['table-archived']});return {'ok':True,'message':f'Table {t.number} removed from the floor.'}

@router.post('/api/ops/tables/{table_id}/restore')
async def restore_table(table_id:int,staff:Staff=Depends(require_permission('can_assign_tables'))):
    with db() as s:
        t=s.get(DiningTable,table_id)
        if not t or t.zone!=ARCHIVED_ZONE:return JSONResponse({'error':'That table is already active.'},400)
        a=s.exec(select(TableArchive).where(TableArchive.table_id==t.id,TableArchive.active==True).order_by(TableArchive.archived_at.desc())).first()  # noqa:E712
        t.zone=a.original_zone if a else 'Main';s.add(t)
        if a:a.active=False;a.restored_at=rtime.now();s.add(a)
        s.commit()
    await hub.send('state',{'changed':['table-restored']});return {'ok':True,'message':f'Table {t.number} restored.'}


def _ensure_sections(s):
    existing={x.name for x in s.exec(select(MenuSection)).all()}
    defaults=[]
    for m in s.exec(select(MenuItem)).all():
        if m.course not in defaults:defaults.append(m.course)
    for idx,name in enumerate(defaults):
        if name not in existing:s.add(MenuSection(name=name,sort_order=idx*10))
    s.commit()


def _name_photo_fallback(name: str, lock: int | str = 1) -> str:
    q = urllib.parse.quote_plus(
        (name or 'restaurant dish').strip() + ',food,dish'
    )
    return f'https://loremflickr.com/900/700/{q}?lock={lock}'

@router.get('/api/ops/menu/photo-suggest')
def suggest_menu_photo(
    q: str = '',
    staff: Staff = Depends(require_permission('can_manage_menu'))
):
    """Find a photograph matching the actual dish name."""
    name = (q or '').strip()

    if not name:
        return JSONResponse(
            {'error': 'Enter the dish name first.'},
            400
        )

    fallback = _name_photo_fallback(
        name,
        abs(hash(name)) % 100000 + 1
    )

    try:
        params = {
            'action': 'query',
            'generator': 'search',
            'gsrnamespace': '6',
            'gsrlimit': '12',
            'gsrsearch': f'"{name}" food dish',
            'prop': 'imageinfo',
            'iiprop': 'url',
            'iiurlwidth': '900',
            'format': 'json',
            'formatversion': '2',
        }

        url = (
            'https://commons.wikimedia.org/w/api.php?'
            + urllib.parse.urlencode(params)
        )

        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'SUFRA-Restaurant-OS/1.0'}
        )

        with netutil.urlopen(req, timeout=3.5) as response:
            data = json.load(response)

        words = [
            w.lower()
            for w in re.findall(r'[A-Za-z0-9]+', name)
            if len(w) > 1
        ]

        ranked = []

        for page in data.get('query', {}).get('pages') or []:
            info = (page.get('imageinfo') or [{}])[0]
            image = info.get('thumburl') or info.get('url')

            if not image:
                continue

            title = str(page.get('title') or '').lower()
            score = sum(4 for w in words if w in title)

            if 'food' in title or 'dish' in title:
                score += 1

            ranked.append(
                (score, image, page.get('title') or '')
            )

        if ranked:
            ranked.sort(key=lambda x: x[0], reverse=True)
            score, image, title = ranked[0]

            return {
                'ok': True,
                'image_url': image,
                'source': 'Wikimedia Commons',
                'matched_title': title,
                'query': name,
            }

    except Exception:
        pass

    return {
        'ok': True,
        'image_url': fallback,
        'source': 'keyword fallback',
        'matched_title': name,
        'query': name,
    }


@router.get('/api/ops/menu-management')
def menu_management(staff:Staff=Depends(require_permission('can_manage_menu'))):
    with db() as s:
        _ensure_sections(s); archived=archived_menu_ids(s); menu={m.id:m for m in s.exec(select(MenuItem)).all()}
        content={c.menu_item_id:c for c in s.exec(select(MenuContent)).all()}
        def itemrow(m):
            c=content.get(m.id)
            return {'id':m.id,'name':m.name,'course':m.course,'price':m.price,'available':m.available,'blurb':m.blurb,'station':m.station.value,'tags':m.tags,'base_minutes':m.base_minutes,'food_cost':m.food_cost,
                    'image_url':c.image_url if c else '', 'image_source':c.image_source if c else 'auto',
                    'name_az':c.name_az if c else '', 'name_ru':c.name_ru if c else '',
                    'blurb_az':c.blurb_az if c else '', 'blurb_ru':c.blurb_ru if c else ''}
        return {'sections':[{'id':x.id,'name':x.name,'name_az':x.name_az,'name_ru':x.name_ru,'sort_order':x.sort_order} for x in s.exec(select(MenuSection).where(MenuSection.active==True).order_by(MenuSection.sort_order,MenuSection.name)).all()],  # noqa:E712
                'items':[itemrow(m) for m in menu.values() if m.id not in archived],
                'archived':[itemrow(m) for m in menu.values() if m.id in archived]}

@router.post('/api/ops/menu/sections')
async def add_section(body:dict=Body(...),staff:Staff=Depends(require_permission('can_manage_menu'))):
    name=(body.get('name') or '').strip()
    if not name:return JSONResponse({'error':'Enter a section name.'},400)
    with db() as s:
        if s.exec(select(MenuSection).where(MenuSection.name==name,MenuSection.active==True)).first():return JSONResponse({'error':'That section already exists.'},400)  # noqa:E712
        s.add(MenuSection(name=name,sort_order=int(body.get('sort_order',50)),
                          name_az=str(body.get('name_az') or '').strip(),
                          name_ru=str(body.get('name_ru') or '').strip()));s.commit()
    await hub.send('state',{'changed':['menu-section']});return {'ok':True,'message':f'{name} section added.'}

@router.post('/api/ops/menu/sections/{section_id}')
async def rename_section(section_id:int,body:dict=Body(...),staff:Staff=Depends(require_permission('can_manage_menu'))):
    new=(body.get('name') or '').strip()
    if not new:return JSONResponse({'error':'Enter the new section name.'},400)
    with db() as s:
        sec=s.get(MenuSection,section_id)
        if not sec:return JSONResponse({'error':'Section not found.'},404)
        old=sec.name;sec.name=new
        if 'name_az' in body:sec.name_az=str(body.get('name_az') or '').strip()
        if 'name_ru' in body:sec.name_ru=str(body.get('name_ru') or '').strip()
        s.add(sec)
        for m in s.exec(select(MenuItem).where(MenuItem.course==old)).all():m.course=new;s.add(m)
        s.commit()
    await hub.send('state',{'changed':['menu-section']});return {'ok':True}

@router.delete('/api/ops/menu/sections/{section_id}')
@router.post('/api/ops/menu/sections/{section_id}/delete')
async def delete_section(section_id:int,staff:Staff=Depends(require_permission('can_manage_menu'))):
    with db() as s:
        sec=s.get(MenuSection,section_id)
        if not sec:return JSONResponse({'error':'Section not found.'},404)
        archived=archived_menu_ids(s)
        active=[m for m in s.exec(select(MenuItem).where(MenuItem.course==sec.name)).all() if m.id not in archived]
        if active:return JSONResponse({'error':'Move or archive the dishes in this section first.'},400)
        sec.active=False;s.add(sec);s.commit()
    await hub.send('state',{'changed':['menu-section']});return {'ok':True}

@router.post('/api/ops/menu/items')
async def add_menu_item(body:dict=Body(...),staff:Staff=Depends(require_permission('can_manage_menu'))):
    name=(body.get('name') or '').strip();course=(body.get('course') or 'Main').strip()
    if not name:return JSONResponse({'error':'Enter a dish name.'},400)

    # SUFRA multilingual menu integrity:
    # every new English dish must have AZ + RU names.
    name_az=str(body.get('name_az') or '').strip()
    name_ru=str(body.get('name_ru') or '').strip()
    blurb=str(body.get('blurb') or '').strip()
    blurb_az=str(body.get('blurb_az') or '').strip()
    blurb_ru=str(body.get('blurb_ru') or '').strip()

    missing=[]
    if not name_az: missing.append('Azerbaijani name')
    if not name_ru: missing.append('Russian name')
    if blurb and not blurb_az: missing.append('Azerbaijani description')
    if blurb and not blurb_ru: missing.append('Russian description')

    if missing:
        return JSONResponse({
            'error':'Translation incomplete: '+', '.join(missing)+'.'
        },400)
    station=body.get('station','hot')
    try: from ..models import Station; station=Station(station)
    except Exception:return JSONResponse({'error':'Choose a valid kitchen station.'},400)
    try:
        price=float(body.get('price') or 0); cost=float(body.get('food_cost') or 0); mins=max(1,int(body.get('base_minutes') or 10))
    except (TypeError,ValueError): return JSONResponse({'error':'Check price, food cost and prep minutes.'},400)
    with db() as s:
        m=MenuItem(name=name,course=course,station=station,price=price,food_cost=cost,base_minutes=mins,blurb=blurb,tags=str(body.get('tags') or ''),available=True,hue=int(body.get('hue') or 150));s.add(m);s.commit();s.refresh(m)
        c=MenuContent(menu_item_id=m.id,image_url=str(body.get('image_url') or '').strip(),image_source='url' if body.get('image_url') else 'auto',
                      name_az=name_az,name_ru=name_ru,
                      blurb_az=blurb_az,blurb_ru=blurb_ru)
        s.add(c); _ensure_sections(s)
        events.record(s, 'menu_updated', 'Menu item changed', detail=f'{name} added to {course}',
                      actor=staff.name or 'Menu admin')
        s.commit()
    await hub.send('state',{'changed':['menu']});return {'ok':True,'id':m.id,'message':f'{name} added to {course}.'}

@router.post('/api/ops/menu/items/{item_id}/content')
async def update_menu_content(item_id:int,body:dict=Body(...),staff:Staff=Depends(require_permission('can_manage_menu'))):
    with db() as s:
        m=s.get(MenuItem,item_id)
        if not m:return JSONResponse({'error':'Dish not found.'},404)
        c=s.exec(select(MenuContent).where(MenuContent.menu_item_id==m.id)).first()
        if not c:c=MenuContent(menu_item_id=m.id)
        for attr in ('image_url','name_az','name_ru','blurb_az','blurb_ru'):
            if attr in body:setattr(c,attr,str(body.get(attr) or '').strip())
        if 'image_url' in body:c.image_source='url' if c.image_url else 'auto'
        c.updated_at=rtime.now();s.add(c)
        for attr in ('name','blurb','tags','course'):
            if attr in body and body.get(attr) is not None:setattr(m,attr,str(body.get(attr) or '').strip())
        if 'price' in body:m.price=float(body.get('price') or 0)
        if 'food_cost' in body:m.food_cost=float(body.get('food_cost') or 0)
        if 'base_minutes' in body:m.base_minutes=max(1,int(body.get('base_minutes') or 1))
        s.add(m)
        events.record(s, 'menu_updated', 'Menu item changed', detail=m.name,
                      actor=staff.name or 'Menu admin')
        s.commit()
    await hub.send('state',{'changed':['menu']});return {'ok':True,'message':f'{m.name} updated.'}

@router.post('/api/ops/menu/items/{item_id}/image')
async def upload_menu_image(item_id:int,body:dict=Body(...),staff:Staff=Depends(require_permission('can_manage_menu'))):
    data=str(body.get('data_url') or '')
    m=re.match(r'^data:image/(png|jpeg|jpg|webp);base64,(.+)$',data,re.I|re.S)
    if not m:return JSONResponse({'error':'Choose a PNG, JPG or WEBP image.'},400)
    raw=base64.b64decode(m.group(2),validate=False)
    if len(raw)>6*1024*1024:return JSONResponse({'error':'Image must be smaller than 6 MB.'},400)
    ext='jpg' if m.group(1).lower() in {'jpeg','jpg'} else m.group(1).lower()
    folder=Path(__file__).resolve().parents[1]/'static'/'uploads'/'menu';folder.mkdir(parents=True,exist_ok=True)
    filename=f'{item_id}-{int(rtime.now().timestamp())}.{ext}';(folder/filename).write_bytes(raw)
    url=f'/static/uploads/menu/{filename}'
    with db() as s:
        dish=s.get(MenuItem,item_id)
        if not dish:return JSONResponse({'error':'Dish not found.'},404)
        c=s.exec(select(MenuContent).where(MenuContent.menu_item_id==item_id)).first()
        if not c:c=MenuContent(menu_item_id=item_id)
        c.image_url=url;c.image_source='upload';c.updated_at=rtime.now();s.add(c);s.commit()
    await hub.send('state',{'changed':['menu-image']});return {'ok':True,'image_url':url,'message':'Photo saved.'}

@router.delete('/api/ops/menu/items/{item_id}')
async def archive_menu_item(item_id:int,staff:Staff=Depends(require_permission('can_manage_menu'))):
    with db() as s:
        m=s.get(MenuItem,item_id)
        if not m:return JSONResponse({'error':'Dish not found.'},404)
        old=s.exec(select(MenuArchive).where(MenuArchive.menu_item_id==m.id,MenuArchive.active==True)).first()  # noqa:E712
        if not old:s.add(MenuArchive(menu_item_id=m.id,archived_by=staff.id));s.commit()
    await hub.send('state',{'changed':['menu']});return {'ok':True,'message':f'{m.name} removed from active menus.'}

@router.post('/api/ops/menu/items/{item_id}/restore')
async def restore_menu_item(item_id:int,staff:Staff=Depends(require_permission('can_manage_menu'))):
    with db() as s:
        m=s.get(MenuItem,item_id)
        if not m:return JSONResponse({'error':'Dish not found.'},404)
        for a in s.exec(select(MenuArchive).where(MenuArchive.menu_item_id==m.id,MenuArchive.active==True)).all():a.active=False;a.restored_at=rtime.now();s.add(a)  # noqa:E712
        s.commit()
    await hub.send('state',{'changed':['menu']});return {'ok':True,'message':f'{m.name} restored.'}
