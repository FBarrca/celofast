"""Read-only integration checks using .env and the inventory KM in pyproject.toml.

Run when normal Celofast OAuth credentials are configured. Exclude with
``uv run pytest -m "not live"``. Never author or update cloud KM items.
"""

import pytest

from celofast import CeloFast

pytestmark = pytest.mark.live


def test_live_pull_import_and_object_page(inventory_package):
    module = inventory_package
    source = module.km.source
    cf = CeloFast(source.space_id, source.package_id, mode=source.mode)
    client = cf.km(module.km)
    page = client.objects(module.Plant).fetch_page(page_size=2)
    assert all(isinstance(item, module.Plant) for item in page.items)
    if page.items:
        first = page.items[0]
        assert client.objects(module.Plant).get(first.key) == first


def test_live_event_log_history_and_activity_conditions(inventory_package):
    module = inventory_package
    Line, Activity = module.SalesOrderScheduleLine, module.SalesOrderScheduleLineActivity
    source = module.km.source
    client = CeloFast(source.space_id, source.package_id, mode=source.mode).km(module.km)
    lines = client.objects(Line)
    activities = Line.relations.activities

    issued = lines.where(activities.contains("PostGoodsIssue")).fetch_page(page_size=10_000)
    counted = lines.where(activities.count().gt(0)).fetch_page(page_size=10_000)
    assert {line.key for line in issued} == {line.key for line in counted}
    if not issued.items:
        return
    line = issued.items[0]
    history = line.links.activities.fetch_page()
    assert history.items and all(isinstance(event, Activity) for event in history)
    assert all(event.case == line.key for event in history)
    times = [event.timestamp for event in history if event.timestamp is not None]
    assert times == sorted(times)
    assert history.items[0].links.case.fetch() == line


def test_live_object_link_attributes_are_generated(inventory_package):
    # The Data Model's Object Link (bill of materials) serves the KM's LINK_ attributes.
    from pathlib import Path

    objects = (Path(inventory_package.__file__).parent / "objects.py").read_text(encoding="utf-8")
    assert "Object Link" not in objects.split("\nclass ", 1)[0]  # No such "Not generated" note.
    fields = inventory_package.MaterialMasterPlant.fields
    assert fields.is_end_node.value_type == "int"
    assert fields.num_incoming_bill_of_material_links.value_type == "int"


def test_live_object_link_relations_follow_the_bill_of_materials(inventory_package):
    module = inventory_package
    MMP, BOM = module.MaterialMasterPlant, module.RelationshipBillOfMaterials
    source = module.km.source
    client = CeloFast(source.space_id, source.package_id, mode=source.mode).km(module.km)
    links = MMP.relations
    linked = client.objects(MMP).where(links.link_targets.any()).fetch_page(page_size=10_000)
    counted = client.objects(MMP).where(MMP.fields.num_outgoing_bill_of_material_links.gt(0))
    assert {m.key for m in linked} == {m.key for m in counted.fetch_page(page_size=10_000)}
    if not linked.items:
        return
    component = linked.items[0]
    targets = {m.key for m in component.links.link_targets.fetch_page(page_size=10_000)}
    rows = client.objects(BOM).where(BOM.fields.material_master_plant_component_id.eq(component.key))
    assert targets == {row.material_master_plant_product_id for row in rows.fetch_page(page_size=10_000)}
    product = client.objects(MMP).get(next(iter(targets)))
    assert component.key in {m.key for m in product.links.link_sources.fetch_page(page_size=10_000)}
