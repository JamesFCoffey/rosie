from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.rule_engine import load_rules_from_yaml


def test_json_loader_parses_rules(tmp_path: Path) -> None:
    data = {
        "rules": [
            {"id": "R1", "name": "txt", "globs": ["*.txt"], "action": "info"},
            {"id": "R2", "name": "log", "exts": [".log"], "action": "info"},
        ]
    }
    jf = tmp_path / "rules.json"
    jf.write_text(json.dumps(data), encoding="utf-8")

    rs = load_rules_from_yaml(jf)
    assert len(rs.rules) == 2
    assert rs.rules[0].id == "R1"
    assert rs.rules[1].id == "R2"


def test_yaml_without_pyyaml_raises_clear_error(monkeypatch, tmp_path: Path) -> None:
    yf = tmp_path / "rules.yaml"
    yf.write_text(
        """
rules:
- {id: Rext, name: ext-md, exts: [".md"], action: info}
- {id: Rglob, name: glob-notes, globs: ["notes.*"], action: info}
        """.strip(),
        encoding="utf-8",
    )

    # Force import of yaml to fail even if installed
    real_import = __import__

    def fake_import(name, *args, **kwargs):  # type: ignore[override]
        if name == "yaml":
            raise ModuleNotFoundError("No module named 'yaml'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)

    with pytest.raises(RuntimeError) as ei:
        load_rules_from_yaml(yf)
    assert "PyYAML is not installed" in str(ei.value)

