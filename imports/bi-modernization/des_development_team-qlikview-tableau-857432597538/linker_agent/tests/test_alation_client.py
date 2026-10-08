"""Unit tests for SwaggerAPIClient write-back methods — aiohttp is mocked."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from linker_agent.clients.alation_client import SwaggerAPIClient, SwaggerAPIConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FAKE_CONFIG = SwaggerAPIConfig(
    base_url="https://alation.example.com",
    api_token="test-token",
)


class _MockResponse:
    """Async context manager mimicking aiohttp.ClientResponse."""

    def __init__(self, status=200, json_data=None, raise_error=None):
        self.status = status
        self._json_data = json_data or {}
        self._raise_error = raise_error

    async def json(self):
        return self._json_data

    def raise_for_status(self):
        if self._raise_error:
            raise self._raise_error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


def _make_client_with_session(mock_session) -> SwaggerAPIClient:
    """Create a SwaggerAPIClient bypassing __aenter__ with a mock session."""
    client = SwaggerAPIClient(_FAKE_CONFIG)
    client.session = mock_session
    return client


# ---------------------------------------------------------------------------
# _put
# ---------------------------------------------------------------------------

class TestPutHelper:
    def test_put_sends_json_payload(self):
        mock_resp = _MockResponse(status=200, json_data={"ok": True})
        mock_session = MagicMock()
        mock_session.put.return_value = mock_resp

        client = _make_client_with_session(mock_session)

        result = asyncio.run(client._put("/integration/v2/term/", [{"id": 1}]))

        mock_session.put.assert_called_once()
        call_kwargs = mock_session.put.call_args
        assert "https://alation.example.com/integration/v2/term/" in str(call_kwargs)
        assert result == {"ok": True}

    def test_put_raises_on_http_error(self):
        err = aiohttp.ClientResponseError(MagicMock(), (), status=404, message="Not Found")
        mock_resp = _MockResponse(raise_error=err)
        mock_session = MagicMock()
        mock_session.put.return_value = mock_resp

        client = _make_client_with_session(mock_session)

        with pytest.raises(aiohttp.ClientResponseError):
            asyncio.run(client._put("/integration/v2/term/", [{"id": 99}]))

    def test_put_raises_on_connection_error(self):
        mock_session = MagicMock()
        mock_session.put.side_effect = aiohttp.ClientConnectorError(MagicMock(), OSError())

        client = _make_client_with_session(mock_session)

        with pytest.raises(aiohttp.ClientConnectorError):
            asyncio.run(client._put("/integration/v2/term/", []))

    def test_put_raises_without_session(self):
        client = SwaggerAPIClient(_FAKE_CONFIG)
        # session is None — not entered context manager
        with pytest.raises(RuntimeError, match="not initialized"):
            asyncio.run(client._put("/integration/v2/term/", []))


# ---------------------------------------------------------------------------
# update_term_description
# ---------------------------------------------------------------------------

class TestUpdateTermDescription:
    def test_basic_update_sends_list_payload(self):
        mock_resp = _MockResponse(status=200, json_data={"id": 10, "description": "<p>ok</p>"})
        mock_session = MagicMock()
        mock_session.put.return_value = mock_resp
        client = _make_client_with_session(mock_session)

        result = asyncio.run(client.update_term_description(10, "<p>ok</p>"))

        assert result == {"id": 10, "description": "<p>ok</p>"}
        call_url = mock_session.put.call_args[0][0]
        assert call_url.endswith("/integration/v2/term/")
        sent_payload = mock_session.put.call_args[1]["json"]
        assert isinstance(sent_payload, list)
        assert sent_payload[0]["id"] == 10
        assert sent_payload[0]["description"] == "<p>ok</p>"
        assert "template_id" not in sent_payload[0]

    def test_includes_template_id_when_provided(self):
        mock_resp = _MockResponse(status=200, json_data={"id": 5})
        mock_session = MagicMock()
        mock_session.put.return_value = mock_resp
        client = _make_client_with_session(mock_session)

        asyncio.run(client.update_term_description(5, "desc", template_id=42))

        sent_payload = mock_session.put.call_args[1]["json"]
        assert sent_payload[0]["template_id"] == 42

    def test_omits_template_id_when_none(self):
        mock_resp = _MockResponse(status=200, json_data={})
        mock_session = MagicMock()
        mock_session.put.return_value = mock_resp
        client = _make_client_with_session(mock_session)

        asyncio.run(client.update_term_description(1, "x", template_id=None))

        sent_payload = mock_session.put.call_args[1]["json"]
        assert "template_id" not in sent_payload[0]


# ---------------------------------------------------------------------------
# update_custom_field_values
# ---------------------------------------------------------------------------

class TestUpdateCustomFieldValues:
    def test_batch_update_sends_correct_endpoint(self):
        mock_resp = _MockResponse(status=200, json_data={"status": "updated"})
        mock_session = MagicMock()
        mock_session.put.return_value = mock_resp
        client = _make_client_with_session(mock_session)

        updates = [
            {"field_id": 10009, "otype": "glossary_term", "oid": 10, "value": "Yes"},
        ]
        result = asyncio.run(client.update_custom_field_values(updates))

        assert result == {"status": "updated"}
        call_url = mock_session.put.call_args[0][0]
        assert "/integration/v2/custom_field_value/" in call_url
        sent_payload = mock_session.put.call_args[1]["json"]
        assert sent_payload == updates

    def test_propagates_connection_error(self):
        mock_session = MagicMock()
        mock_session.put.side_effect = aiohttp.ClientConnectorError(MagicMock(), OSError())
        client = _make_client_with_session(mock_session)

        with pytest.raises(aiohttp.ClientConnectorError):
            asyncio.run(client.update_custom_field_values([{"field_id": 1}]))


# ---------------------------------------------------------------------------
# get_glossary_tree
# ---------------------------------------------------------------------------

class TestGetGlossaryTree:
    def test_returns_correct_structure(self):
        terms = [
            {
                "id": 1,
                "title": "Revenue",
                "description": "<p>Total revenue</p>",
                "glossary_ids": [10],
                "template_id": 5,
                "custom_fields": [],
            }
        ]

        client = SwaggerAPIClient(_FAKE_CONFIG)
        client.get_terms = AsyncMock(return_value=terms)

        result = asyncio.run(client.get_glossary_tree(glossary_id=10))

        assert result["status"] == "ok"
        assert result["glossary_id"] == 10
        assert result["term_count"] == 1
        assert result["terms"][0]["title"] == "Revenue"
        assert result["terms"][0]["description"] == "Total revenue"
