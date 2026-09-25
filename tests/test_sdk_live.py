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
