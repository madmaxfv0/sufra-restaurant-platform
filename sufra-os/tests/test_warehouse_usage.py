import unittest
from unittest.mock import patch
from sqlmodel import Session, select
import test_staff_qr as staff_tests
from app import anbar
from app.routers import anbar as warehouse_api
from app.models import Ingredient, MenuItem, RecipeLine, DiningTable, Order, OrderItem, AuditLog
from app.anbar_models import InvItem, InvTxn, InvBatch, WarehouseMigration


class WarehouseTests(unittest.TestCase):
    def setUp(self):
        self.case = staff_tests.StaffAccessTests(); self.case.setUp()
        self.engine=self.case.engine; self.client=self.case.client; self.headers=self.case.headers
        self.patches=[patch.object(m,'engine',self.engine) for m in (anbar,warehouse_api)]
        for p in self.patches:p.start()
        self.case.app.include_router(warehouse_api.router)
        with Session(self.engine) as s:
            ing=Ingredient(name='Sea bass fillet',unit='kg',in_stock=10,cost_per_unit=20)
            dish=MenuItem(name='Grilled sea bass',price=30)
            table=DiningTable(number=1)
            s.add(ing);s.add(dish);s.add(table);s.flush()
            self.ing=ing.id;self.dish=dish.id
            s.add(InvItem(ingredient_id=ing.id,base_unit='kg',recipe_unit='g',recipe_factor=.001,avg_cost=20,track_batches=True))
            s.add(InvBatch(ingredient_id=ing.id,qty_received=10,qty_base=10,unit_cost=20))
            s.add(RecipeLine(menu_item_id=dish.id,ingredient_id=ing.id,qty_per_portion=.22))
            order=Order(table_id=table.id);s.add(order);s.flush();self.order=order.id
            line=OrderItem(order_id=order.id,menu_item_id=dish.id,qty=3);s.add(line);s.flush();self.line=line.id
            s.commit()

    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.case.tearDown()

    def test_seed_kg_displays_grams_and_cost(self):
        r=self.client.get(f'/api/anbar/recipes/{self.dish}',headers=self.headers)
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['lines'][0]['qty'],220)
        self.assertEqual(r.json()['lines'][0]['cost'],4.4)

    def test_preparation_and_payment_deduct_once_including_batches(self):
        with Session(self.engine) as s:
            anbar.consume_order(s,self.order,only_item_id=self.line);s.commit()
            anbar.consume_order(s,self.order);s.commit()
            anbar.consume_order(s,self.order,only_item_id=self.line);s.commit()
            self.assertAlmostEqual(s.get(Ingredient,self.ing).in_stock,9.34)
            self.assertAlmostEqual(s.exec(select(InvBatch)).first().qty_base,9.34)
            self.assertEqual(len(s.exec(select(InvTxn)).all()),1)
        r=self.client.get(f'/api/anbar/recipe-usage?menu_item_id={self.dish}&portions=2',headers=self.headers)
        self.assertEqual(r.status_code,200,r.text)
        d=r.json();self.assertEqual(d['prepared_portions'],3)
        row=d['ingredients'][0]
        for key,want in {'per_portion':220,'used':660,'remaining':9340,'planned':440,'after_plan':8900}.items():self.assertEqual(row[key],want)
        with Session(self.engine) as s:self.assertAlmostEqual(s.get(Ingredient,self.ing).in_stock,9.34)

    def test_save_grams_stores_kg_and_rejects_invalid_recipe_atomically(self):
        path=f'/api/anbar/recipes/{self.dish}'
        r=self.client.post(path,headers=self.headers,json={'lines':[{'ingredient_id':self.ing,'qty':250}]})
        self.assertEqual(r.status_code,200,r.text)
        with Session(self.engine) as s:self.assertEqual(s.exec(select(RecipeLine)).first().qty_per_portion,.25)
        for lines in [[{'ingredient_id':self.ing,'qty':-1}],[{'ingredient_id':self.ing,'qty':100}]*2,[{'ingredient_id':self.ing,'qty':'nan'}]]:
            self.assertEqual(self.client.post(path,headers=self.headers,json={'lines':lines}).status_code,400)
        with Session(self.engine) as s:self.assertEqual(s.exec(select(RecipeLine)).first().qty_per_portion,.25)

    def test_legacy_editor_migration_once_preserves_seed_recipes(self):
        with Session(self.engine) as s:
            old=MenuItem(name='Legacy edited recipe');s.add(old);s.flush()
            s.add(RecipeLine(menu_item_id=old.id,ingredient_id=self.ing,qty_per_portion=300))
            s.add(AuditLog(action='anbar_recipe_save',entity_id=old.id))
            s.flush();anbar.normalize_recipe_units(s);s.commit();anbar.normalize_recipe_units(s);s.commit()
            self.assertEqual(s.exec(select(RecipeLine).where(RecipeLine.menu_item_id==old.id)).first().qty_per_portion,.3)
            self.assertEqual(s.exec(select(RecipeLine).where(RecipeLine.menu_item_id==self.dish)).first().qty_per_portion,.22)

    def test_missing_recipe_has_no_fabricated_usage(self):
        with Session(self.engine) as s:
            for line in s.exec(select(RecipeLine)).all():s.delete(line)
            s.commit()
        r=self.client.get(f'/api/anbar/recipe-usage?menu_item_id={self.dish}',headers=self.headers)
        self.assertFalse(r.json()['has_recipe']);self.assertEqual(r.json()['ingredients'],[])


if __name__=='__main__':unittest.main()
