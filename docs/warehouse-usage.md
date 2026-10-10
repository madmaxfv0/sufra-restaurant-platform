# Warehouse recipes and usage

The navigation label is now **Warehouse** (Russian: **Склад**). Internal `/admin/anbar` and `/api/anbar` routes remain compatible. All 60 existing ingredient names have Russian translations; select RU in the language controls.

Open **Warehouse → Dish ingredient usage** to select a dish, reporting period and planned portions. The view shows:

- Each ingredient and its per-portion quantity in grams, millilitres or counted units.
- Recorded recipe-based usage for that dish in the selected period.
- Current stock after all recorded receipts, dishes, waste and adjustments.
- Ingredient requirements and remaining stock for a hypothetical preparation plan.

The plan never changes stock. A kitchen ticket moving into preparation posts its recipe quantities to the ledger. Later ticket advances and settlement do not deduct the same ingredients again. Settlement remains a fallback for orders that did not pass through the kitchen controls. Each prepared line records its portion count; ledger movements retain historical quantities even after recipe edits. Quantities are estimates from recipes, not measurements of what a cook actually weighed. Record additional preparation losses through Waste and use Stocktake for physical counts.

**Recipes & Costing** and **Edit recipe** let administrators enter the kitchen's exact quantities per portion. Missing recipes are flagged, without invented ingredients or gram amounts. The inspected database contained 31 dishes without recipes; these need kitchen input before usage can be estimated.

The unit bug is fixed: canonical `RecipeLine.qty_per_portion` is stored in the ingredient's base unit. A stored 0.22 kg displays as 220 g and costs/consumes 0.22 kg. Saving 250 g stores 0.25 kg. The old editor wrote display quantities directly; startup converts only recipes identified by its saved-recipe audit records, once. Seeded recipes already in base units remain unchanged. Forecast calculations use the same base quantities.

Historical stock movements and current stock balances are not retrospectively rewritten. If an older version undercounted consumption, conduct a physical stocktake to establish the correct opening stock for the corrected calculations.

Verification uses temporary databases, including a migration check against a copy of the restaurant database. Run `python -m unittest discover -s tests -v` and `PYTHONPATH=. python tests/browser_warehouse.py` to check quantity conversion, repeat-call protection, preserved stock during previews, Russian ingredient display and admin QR controls.
