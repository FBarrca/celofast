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

[tool.celofast.knowledge-models.inventory.mapping.objects.Plant]
key = ["ID"]
""")
    calls = []
    payload = {
        "layer": {
            "tenantId": "tenant",
            "nodeEntityId": "node",
            "records": [{"id": "Plant", "attributes": [
                {"id": "ID", "pql": '"Plant"."ID"', "columnType": "STRING"},
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
                    get_tables=lambda: [], get_foreign_keys=lambda: []
                ),
            )
        )

    monkeypatch.setattr("celofast.CeloFast", factory)
    args = ["km", "pull", "inventory", "--project", str(project)]
    assert main([*args, "--check"]) == 1
    assert not (tmp_path / "generated").exists()
    assert main(args) == 0
    assert main([*args, "--check"]) == 0
    assert calls[0]["params"] == {"isDraft": False}
    assert "up to date" in capsys.readouterr().out
    assert (tmp_path / "generated" / "inventory" / "objects.py").is_file()

    # An explicit mapping file replaces the configured table.
    (tmp_path / "unmapped.toml").write_text("exclude = []")
    monkeypatch.chdir(tmp_path)
    assert main([*args, "--mapping", "unmapped.toml", "--check"]) == 2
    error = capsys.readouterr().err
    assert "Plant (map it under objects or add it to exclude): no declared identifier" in error


def test_configuration_error_is_distinct_from_drift(capsys):
    assert main(["km", "pull", "--km", "missing-other-fields", "--check"]) == 2
    assert "Missing KM configuration" in capsys.readouterr().err
