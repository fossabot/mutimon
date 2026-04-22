"""Tests for the track (state machine) feature."""

from unittest import mock


from mutimon import main


# ========================= evaluate_track =========================


class TestEvaluateTrack:
    def setup_method(self):
        main.setup_liquid({"defs": {}})

    def test_first_matching_state(self):
        item = {"price": 195.0}
        track = {
            "value": "{{price}}",
            "states": [
                {"test": "{{price}} > 200"},
                {"test": "{{price}} > 190"},
                {"test": "{{price}} > 180"},
                {"test": "{{price}} <= 180", "silent": True},
            ],
        }
        result = main.evaluate_track(track, item)
        assert result["_state"] == 1
        assert result["_state_name"] == "{{price}} > 190"
        assert result["_value"] == 195.0
        assert result["_silent"] is False

    def test_highest_state(self):
        item = {"price": 250.0}
        track = {
            "states": [
                {"test": "{{price}} > 200"},
                {"test": "{{price}} > 190"},
            ],
        }
        result = main.evaluate_track(track, item)
        assert result["_state"] == 0

    def test_lowest_state(self):
        item = {"price": 185.0}
        track = {
            "states": [
                {"test": "{{price}} > 200"},
                {"test": "{{price}} > 190"},
                {"test": "{{price}} > 180"},
            ],
        }
        result = main.evaluate_track(track, item)
        assert result["_state"] == 2

    def test_no_matching_state(self):
        item = {"price": 50.0}
        track = {
            "states": [
                {"test": "{{price}} > 200"},
                {"test": "{{price}} > 190"},
            ],
        }
        result = main.evaluate_track(track, item)
        assert result["_state"] is None
        assert result["_state_name"] is None

    def test_silent_flag(self):
        item = {"price": 150.0}
        track = {
            "states": [
                {"test": "{{price}} > 200"},
                {"test": "{{price}} <= 200", "silent": True},
            ],
        }
        result = main.evaluate_track(track, item)
        assert result["_state"] == 1
        assert result["_silent"] is True

    def test_value_rendering(self):
        item = {"price": 42.5}
        track = {
            "value": "{{price}}",
            "states": [{"test": "{{price}} > 0"}],
        }
        result = main.evaluate_track(track, item)
        assert result["_value"] == 42.5

    def test_value_string(self):
        item = {"status": "active"}
        track = {
            "value": "{{status}}",
            "states": [{"test": "1 > 0"}],  # always true
        }
        result = main.evaluate_track(track, item)
        assert result["_value"] == "active"

    def test_custom_name(self):
        item = {"price": 195.0}
        track = {
            "states": [
                {"test": "{{price}} > 190", "name": "above 190"},
            ],
        }
        result = main.evaluate_track(track, item)
        assert result["_state_name"] == "above 190"

    def test_name_fallback_to_test(self):
        item = {"price": 195.0}
        track = {
            "states": [
                {"test": "{{price}} > 190"},
            ],
        }
        result = main.evaluate_track(track, item)
        assert result["_state_name"] == "{{price}} > 190"

    def test_invalid_expression_skips(self, capsys):
        item = {"price": 195.0}
        track = {
            "states": [
                {"test": "invalid expression {{{}}}"},
                {"test": "{{price}} > 100"},
            ],
        }
        result = main.evaluate_track(track, item)
        assert result["_state"] == 1  # skips invalid, matches second

    def test_no_value_key(self):
        item = {"price": 100.0}
        track = {
            "states": [{"test": "{{price}} > 50"}],
        }
        result = main.evaluate_track(track, item)
        assert "_value" not in result


# ========================= process_rule with track =========================


class TestProcessRuleTrack:
    def setup_method(self):
        main.setup_liquid({"defs": {}})

    def _make_config(self, tmp_mutimon):
        template = tmp_mutimon / "templates" / "test"
        template.write_text(
            "{% for item in items %}"
            "{{item.id}}: state={{item._state_name}} prev={{item._prev_state_name}} val={{item._value}}\n"
            "{% endfor %}"
        )
        return {
            "email": {
                "server": {
                    "host": "smtp.test.com",
                    "port": 587,
                    "password": "pass",
                    "email": "from@test.com",
                }
            },
            "defs": {
                "stock": {
                    "url": "https://example.com/{{symbol}}",
                    "query": {
                        "type": "single",
                        "selector": "div.price",
                        "id": {"source": "symbol", "regex": "(.+)"},
                        "variables": {
                            "price": {
                                "selector": "span",
                                "value": {"type": "text", "parse": "number"},
                            },
                        },
                    },
                }
            },
            "rules": [],
        }

    def _mock_fetch(self, html):
        fake_resp = mock.MagicMock()
        fake_resp.text = html
        fake_resp.headers = {}
        return mock.patch("mutimon.main.requests.get", return_value=fake_resp)

    def _make_html(self, price):
        return f'<html><body><div class="price"><span>{price}</span></div></body></html>'

    def test_new_item_notifies(self, tmp_mutimon):
        config = self._make_config(tmp_mutimon)
        rule = {
            "ref": "stock",
            "name": "track-new",
            "subject": "Alert: {{count}}",
            "template": "./templates/test",
            "email": "user@test.com",
            "input": {
                "params": {"symbol": "TEST"},
                "track": {
                    "value": "{{price}}",
                    "states": [
                        {"test": "{{price}} > 200", "name": "above 200"},
                        {"test": "{{price}} > 190", "name": "above 190"},
                        {"test": "{{price}} > 180", "name": "above 180"},
                        {"test": "{{price}} <= 180", "silent": True},
                    ],
                },
            },
        }
        with self._mock_fetch(self._make_html(195)):
            with mock.patch("mutimon.main.send_email") as mock_send:
                main.process_rule(config, rule)
                mock_send.assert_called_once()

        state = main.load_state("track-new")
        assert len(state) == 1
        assert state[0]["_state"] == 1
        assert state[0]["_state_name"] == "above 190"

    def test_new_item_silent_no_notify(self, tmp_mutimon):
        config = self._make_config(tmp_mutimon)
        rule = {
            "ref": "stock",
            "name": "track-silent-new",
            "subject": "Alert",
            "template": "./templates/test",
            "email": "user@test.com",
            "input": {
                "params": {"symbol": "TEST"},
                "track": {
                    "states": [
                        {"test": "{{price}} > 200"},
                        {"test": "{{price}} <= 200", "silent": True},
                    ],
                },
            },
        }
        with self._mock_fetch(self._make_html(150)):
            with mock.patch("mutimon.main.send_email") as mock_send:
                main.process_rule(config, rule)
                mock_send.assert_not_called()

        # State should still be saved
        state = main.load_state("track-silent-new")
        assert len(state) == 1
        assert state[0]["_state"] == 1

    def test_state_change_notifies(self, tmp_mutimon):
        """Price rises from 185 to 195 — crosses above 190 threshold."""
        config = self._make_config(tmp_mutimon)
        rule = {
            "ref": "stock",
            "name": "track-change",
            "subject": "Alert",
            "template": "./templates/test",
            "email": "user@test.com",
            "input": {
                "params": {"symbol": "TEST"},
                "track": {
                    "value": "{{price}}",
                    "states": [
                        {"test": "{{price}} > 200", "name": "above 200"},
                        {"test": "{{price}} > 190", "name": "above 190"},
                        {"test": "{{price}} > 180", "name": "above 180"},
                        {"test": "{{price}} <= 180", "silent": True},
                    ],
                },
            },
        }
        # Run 1: price 185 → state "above 180" (index 2)
        with self._mock_fetch(self._make_html(185)):
            with mock.patch("mutimon.main.send_email"):
                main.process_rule(config, rule)

        state = main.load_state("track-change")
        assert state[0]["_state"] == 2

        # Run 2: price 195 → state "above 190" (index 1) — state changed!
        with self._mock_fetch(self._make_html(195)):
            with mock.patch("mutimon.main.send_email") as mock_send:
                main.process_rule(config, rule)
                mock_send.assert_called_once()

        state = main.load_state("track-change")
        assert state[0]["_state"] == 1

    def test_same_state_no_notify(self, tmp_mutimon):
        """Price stays in the same bracket — no notification."""
        config = self._make_config(tmp_mutimon)
        rule = {
            "ref": "stock",
            "name": "track-same",
            "subject": "Alert",
            "template": "./templates/test",
            "email": "user@test.com",
            "input": {
                "params": {"symbol": "TEST"},
                "track": {
                    "states": [
                        {"test": "{{price}} > 190"},
                        {"test": "{{price}} > 180"},
                    ],
                },
            },
        }
        # Run 1: price 195
        with self._mock_fetch(self._make_html(195)):
            with mock.patch("mutimon.main.send_email"):
                main.process_rule(config, rule)

        # Run 2: price 198 — still in same state (>190)
        with self._mock_fetch(self._make_html(198)):
            with mock.patch("mutimon.main.send_email") as mock_send:
                main.process_rule(config, rule)
                mock_send.assert_not_called()

    def test_transition_to_silent_no_notify(self, tmp_mutimon):
        """Price drops below all thresholds into silent state."""
        config = self._make_config(tmp_mutimon)
        rule = {
            "ref": "stock",
            "name": "track-to-silent",
            "subject": "Alert",
            "template": "./templates/test",
            "email": "user@test.com",
            "input": {
                "params": {"symbol": "TEST"},
                "track": {
                    "states": [
                        {"test": "{{price}} > 190", "name": "above 190"},
                        {"test": "{{price}} > 180", "name": "above 180"},
                        {"test": "{{price}} <= 180", "silent": True},
                    ],
                },
            },
        }
        # Run 1: price 195 → above 190
        with self._mock_fetch(self._make_html(195)):
            with mock.patch("mutimon.main.send_email"):
                main.process_rule(config, rule)

        # Run 2: price drops to 150 → silent state
        with self._mock_fetch(self._make_html(150)):
            with mock.patch("mutimon.main.send_email") as mock_send:
                main.process_rule(config, rule)
                mock_send.assert_not_called()

        # State should still be saved as silent state
        state = main.load_state("track-to-silent")
        assert state[0]["_state"] == 2

    def test_full_cycle_up_down_up(self, tmp_mutimon):
        """Full cycle: price goes up, drops to silent, rises again — re-notifies."""
        config = self._make_config(tmp_mutimon)
        rule = {
            "ref": "stock",
            "name": "track-cycle",
            "subject": "Alert",
            "template": "./templates/test",
            "email": "user@test.com",
            "input": {
                "params": {"symbol": "TEST"},
                "track": {
                    "value": "{{price}}",
                    "states": [
                        {"test": "{{price}} > 190", "name": "above 190"},
                        {"test": "{{price}} > 180", "name": "above 180"},
                        {"test": "{{price}} <= 180", "silent": True},
                    ],
                },
            },
        }
        # Run 1: price 195 → above 190 (notify)
        with self._mock_fetch(self._make_html(195)):
            with mock.patch("mutimon.main.send_email") as mock_send:
                main.process_rule(config, rule)
                mock_send.assert_called_once()

        # Run 2: price 170 → silent (no notify)
        with self._mock_fetch(self._make_html(170)):
            with mock.patch("mutimon.main.send_email") as mock_send:
                main.process_rule(config, rule)
                mock_send.assert_not_called()

        # Run 3: price 185 → above 180 (notify — came back from silent)
        with self._mock_fetch(self._make_html(185)):
            with mock.patch("mutimon.main.send_email") as mock_send:
                main.process_rule(config, rule)
                mock_send.assert_called_once()

        # Run 4: price 195 → above 190 (notify — state changed again)
        with self._mock_fetch(self._make_html(195)):
            with mock.patch("mutimon.main.send_email") as mock_send:
                main.process_rule(config, rule)
                mock_send.assert_called_once()

        # Run 5: price 197 → still above 190 (no notify)
        with self._mock_fetch(self._make_html(197)):
            with mock.patch("mutimon.main.send_email") as mock_send:
                main.process_rule(config, rule)
                mock_send.assert_not_called()

    def test_template_gets_state_info(self, tmp_mutimon):
        """Verify template receives _state_name, _prev_state_name, _value."""
        config = self._make_config(tmp_mutimon)
        rule = {
            "ref": "stock",
            "name": "track-tpl",
            "subject": "Alert",
            "template": "./templates/test",
            "email": "user@test.com",
            "input": {
                "params": {"symbol": "TEST"},
                "track": {
                    "value": "{{price}}",
                    "states": [
                        {"test": "{{price}} > 190", "name": "above 190"},
                        {"test": "{{price}} > 180", "name": "above 180"},
                    ],
                },
            },
        }
        # Run 1: price 185 → above 180
        with self._mock_fetch(self._make_html(185)):
            with mock.patch("mutimon.main.send_email"):
                main.process_rule(config, rule)

        # Run 2: price 195 → above 190 (changed)
        with self._mock_fetch(self._make_html(195)):
            with mock.patch("mutimon.main.send_email") as mock_send:
                main.process_rule(config, rule)
                call_args = mock_send.call_args
                body = call_args[0][3]  # 4th arg is body
                assert "above 190" in body
                assert "above 180" in body  # prev state
                assert "195" in body

    def test_transient_fields_not_persisted(self, tmp_mutimon):
        """_prev_state, _prev_state_name, _silent should not be in saved state."""
        config = self._make_config(tmp_mutimon)
        rule = {
            "ref": "stock",
            "name": "track-persist",
            "subject": "Alert",
            "template": "./templates/test",
            "email": "user@test.com",
            "input": {
                "params": {"symbol": "TEST"},
                "track": {
                    "value": "{{price}}",
                    "states": [
                        {"test": "{{price}} > 180"},
                    ],
                },
            },
        }
        with self._mock_fetch(self._make_html(195)):
            with mock.patch("mutimon.main.send_email"):
                main.process_rule(config, rule)

        state = main.load_state("track-persist")
        item = state[0]
        assert "_prev_state" not in item
        assert "_prev_state_name" not in item
        assert "_silent" not in item
        assert "_state" in item
        assert "_state_name" in item
        assert "_value" in item


# ========================= resolve_inputs with track =========================


class TestResolveInputsTrack:
    def test_track_passed_through(self):
        rule = {
            "input": {
                "params": {"symbol": "TEST"},
                "track": {
                    "states": [{"test": "{{price}} > 100"}],
                },
            }
        }
        result = main.resolve_inputs(rule)
        assert result[0]["track"] is not None
        assert result[0]["track"]["states"][0]["test"] == "{{price}} > 100"

    def test_no_track_returns_none(self):
        rule = {"input": {"params": {"q": "test"}}}
        result = main.resolve_inputs(rule)
        assert result[0]["track"] is None

    def test_no_input_returns_none_track(self):
        rule = {"params": {"q": "test"}}
        result = main.resolve_inputs(rule)
        assert result[0]["track"] is None


# ========================= schema validation =========================


class TestTrackSchema:
    def test_valid_track_config(self, write_config):
        config = {
            "email": {
                "server": {
                    "host": "smtp.test.com",
                    "port": 587,
                    "password": "x",
                    "email": "x@x.com",
                }
            },
            "defs": {
                "stock": {
                    "url": "https://example.com",
                    "query": {
                        "type": "single",
                        "selector": "div",
                        "variables": {
                            "price": {
                                "selector": "span",
                                "value": {"type": "text", "parse": "number"},
                            }
                        },
                    },
                }
            },
            "rules": [
                {
                    "ref": "stock",
                    "name": "test",
                    "schedule": "0 * * * *",
                    "subject": "Test",
                    "template": "./templates/test",
                    "email": "x@x.com",
                    "input": {
                        "params": {"symbol": "X"},
                        "track": {
                            "value": "{{price}}",
                            "states": [
                                {"test": "{{price}} > 200", "name": "above 200"},
                                {"test": "{{price}} > 190"},
                                {
                                    "test": "{{price}} <= 180",
                                    "silent": True,
                                },
                            ],
                        },
                    },
                }
            ],
        }
        write_config(config)
        # Should not raise
        main.validate_config(config)
