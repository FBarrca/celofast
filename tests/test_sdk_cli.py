from types import SimpleNamespace

from celofast.cli import main


def test_configured_pull_and_check(tmp_path, monkeypatch, capsys):
    project = tmp_path / "pyproject.toml"
    project.write_text("""[tool.celofast.knowledge-models.inventory]
space-id = "space"
package-id = "package"
key = "inventory-km"
mode = "published"
output = "generated/inventory"
""")
    calls = []
    payload = {
        "layer": {
            "tenantId": "tenant",
            "nodeEntityId": "node",
            "records": [{"id": "Plant", "pql": '"Plant"', "attributes": [
                {"id": "ID", "pql": '"Plant"."ID"', "columnType": "STRING"},
                {"id": "LABEL", "pql": 'UPPER("Plant"."Name")', "columnType": "STRING"},
                {"id": "BROKEN", "pql": 'KPI("missing")', "columnType": "STRING"},
            ]}],
        }
    }

    def request(**kwargs):
        calls.append(kwargs)
        if kwargs["method"] == "GET":
            return {
                "id": "node",
                "key": "inventory-km",
                "draftId": "published",
                "activatedDraftId": "published",
                "inputVariableDefinitions": [],
            }
        return payload

    native = SimpleNamespace(
        root_with_key="root.inventory-km",
        key="inventory-km",
        client=SimpleNamespace(request=request),
    )

    # Zero-config: keys and column types come from the Data Model.
    table = SimpleNamespace(
        id="t1", name="Plant", alias=None, primary_keys=["ID"],
        get_columns=lambda: [SimpleNamespace(name="ID", type_="STRING"),
                             SimpleNamespace(name="Name", type_="STRING")],
    )
    probes = []

    def probe(expressions, limit):
        probes.append(expressions)
        if any("KPI" in expression for expression in expressions):
            raise RuntimeError("KPI missing does not exist")
        return [("P1", "MAIN")]

    connection = SimpleNamespace(_probe=probe, _type_of=lambda expression: "str")

    def factory(**kwargs):
        assert kwargs == {
            "space_id": "space",
            "package_id": "package",
            "mode": "published",
        }
        return SimpleNamespace(
            _resolver=SimpleNamespace(
                knowledge_model=lambda key: native,
                data_model=lambda km: SimpleNamespace(
                    get_tables=lambda: [table], get_foreign_keys=lambda: []
                ),
            ),
            _km_connection=lambda key: connection,
        )

    monkeypatch.setattr("celofast.CeloFast", factory)
    args = ["km", "pull", "inventory", "--project", str(project)]
    assert main([*args, "--check"]) == 1
    assert not (tmp_path / "generated").exists()
    assert main(args) == 0
    assert main([*args, "--check"]) == 0
    assert calls[0]["params"] == {"isDraft": False}
    out = capsys.readouterr().out
    assert "up to date" in out
    assert "1 object types, 0 links; 1 items skipped" in out
    definitions = (tmp_path / "generated" / "inventory" / "objects.py").read_text()
    # The failing calculated attribute was isolated at pull and reported.
    assert "Plant.BROKEN: fails in Celonis: KPI missing does not exist; not generated." in definitions
    assert "label: _d.Field[str | None] = _d.Field(" in definitions

    # An explicit mapping file supplies overrides; invalid ones fail clearly.
    (tmp_path / "broken.toml").write_text('[objects.Plant]\nkey = ["MISSING"]\n')
    monkeypatch.chdir(tmp_path)
    assert main([*args, "--mapping", "broken.toml", "--check"]) == 2
    error = capsys.readouterr().err
    assert "Plant: key attribute 'MISSING' is not a loaded field" in error


def test_configuration_error_is_distinct_from_drift(capsys):
    assert main(["km", "pull", "--km", "missing-other-fields", "--check"]) == 2
    assert "Missing KM configuration" in capsys.readouterr().err
