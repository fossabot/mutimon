"""Shared fixtures for mutimon tests."""

import json

import pytest

from mutimon import main


@pytest.fixture
def tmp_mutimon(tmp_path, monkeypatch):
    """Set up an isolated ~/.mutimon directory for testing."""
    config_dir = tmp_path / "mutimon"
    config_dir.mkdir()
    (config_dir / "data").mkdir()
    (config_dir / "templates").mkdir()

    monkeypatch.setattr(main, "MUTIMON_DIR", str(config_dir))
    monkeypatch.setattr(main, "CONFIG_FILE", str(config_dir / "config.json"))
    monkeypatch.setattr(main, "TEMPLATES_DIR", str(config_dir / "templates"))
    monkeypatch.setattr(main, "DATA_DIR", str(config_dir / "data"))

    return config_dir


@pytest.fixture
def sample_config():
    """Return a minimal valid config dict."""
    return {
        "email": {
            "server": {
                "host": "smtp.test.com",
                "port": 587,
                "password": "testpass",
                "email": "test@test.com",
            }
        },
        "defs": {
            "test-site": {
                "url": "https://example.com",
                "query": {
                    "type": "list",
                    "selector": "div.item",
                    "variables": {
                        "title": {
                            "selector": "h3",
                            "value": {"type": "text"},
                        },
                        "url": {
                            "selector": "a",
                            "value": {
                                "type": "attribute",
                                "name": "href",
                                "prefix": "https://example.com",
                            },
                        },
                    },
                },
            }
        },
        "rules": [
            {
                "ref": "test-site",
                "name": "test-rule",
                "schedule": "0 * * * *",
                "subject": "Test: {{count}} items",
                "template": "./templates/test",
                "email": "user@test.com",
            }
        ],
    }


@pytest.fixture
def write_config(tmp_mutimon, sample_config):
    """Write sample config to the temp directory and return the path."""

    def _write(config=None):
        if config is None:
            config = sample_config
        config_file = tmp_mutimon / "config.json"
        config_file.write_text(json.dumps(config, indent=2))
        return str(config_file)

    return _write


@pytest.fixture
def sample_html():
    """Return sample HTML for extraction tests."""
    return """
    <html>
    <body>
        <div class="item" data-id="1">
            <h3>First Item</h3>
            <a href="/page/1">Link 1</a>
            <span class="score">42 points</span>
            <span class="tags"><span>python</span><span>web</span></span>
        </div>
        <div class="item" data-id="2">
            <h3>Second Item</h3>
            <a href="/page/2">Link 2</a>
            <span class="score">99 points</span>
            <span class="tags"><span>rust</span><span>cli</span></span>
        </div>
        <div class="item" data-id="3">
            <h3>Third Item</h3>
            <a href="/page/3">Link 3</a>
            <span class="score">7 points</span>
        </div>
    </body>
    </html>
    """
