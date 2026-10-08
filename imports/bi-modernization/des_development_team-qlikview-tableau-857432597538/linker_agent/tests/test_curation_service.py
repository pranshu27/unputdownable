"""Unit tests for CurationService — all Alation calls are mocked."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from linker_agent.models.curation_models import ErrorResponse, FieldUpdate, WriteResponse
from linker_agent.services.curation_service import CurationService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_client():
    client = MagicMock()
    client.update_term_description = AsyncMock(return_value={"id": 1})
    client.update_custom_field_values = AsyncMock(return_value={"status": "ok"})
    client._resolve_template_id = AsyncMock(return_value=None)
    return client


@pytest.fixture
def service(mock_client):
    return CurationService(mock_client)


def _http_error(status: int) -> aiohttp.ClientResponseError:
    err = aiohttp.ClientResponseError(
        request_info=MagicMock(),
        history=(),
        status=status,
        message=f"HTTP {status}",
    )
    return err


# ---------------------------------------------------------------------------
# update_term_description
# ---------------------------------------------------------------------------

class TestUpdateTermDescription:
    def test_success(self, service, mock_client):
        result = asyncio.run(service.update_term_description(1, "<p>Hello</p>"))
        assert isinstance(result, WriteResponse)
        assert result.success is True
        assert result.term_id == 1

    def test_empty_description_returns_400(self, service):
        result = asyncio.run(service.update_term_description(1, ""))
        assert isinstance(result, ErrorResponse)
        assert result.status_code == 400

    def test_whitespace_only_returns_400(self, service):
        result = asyncio.run(service.update_term_description(1, "   "))
        assert isinstance(result, ErrorResponse)
        assert result.status_code == 400

    def test_4xx_error_passes_through(self, service, mock_client):
        mock_client.update_term_description.side_effect = _http_error(403)
        result = asyncio.run(service.update_term_description(1, "<p>desc</p>"))
        assert isinstance(result, ErrorResponse)
        assert result.status_code == 403
        assert result.term_id == 1

    def test_5xx_error_mapped_to_502(self, service, mock_client):
        mock_client.update_term_description.side_effect = _http_error(500)
        result = asyncio.run(service.update_term_description(1, "<p>desc</p>"))
        assert isinstance(result, ErrorResponse)
        assert result.status_code == 502

    def test_connection_error_returns_503(self, service, mock_client):
        mock_client.update_term_description.side_effect = aiohttp.ClientConnectorError(
            MagicMock(), OSError("refused")
        )
        result = asyncio.run(service.update_term_description(1, "<p>desc</p>"))
        assert isinstance(result, ErrorResponse)
        assert result.status_code == 503

    def test_timeout_returns_503(self, service, mock_client):
        mock_client.update_term_description.side_effect = asyncio.TimeoutError()
        result = asyncio.run(service.update_term_description(1, "<p>desc</p>"))
        assert isinstance(result, ErrorResponse)
        assert result.status_code == 503

    def test_template_id_forwarded(self, service, mock_client):
        mock_client._resolve_template_id = AsyncMock(return_value=50)
        asyncio.run(service.update_term_description(5, "<p>ok</p>", template_id=50))
        mock_client.update_term_description.assert_awaited_once_with(
            term_id=5, description="<p>ok</p>", template_id=50
        )


# ---------------------------------------------------------------------------
# update_custom_field_values
# ---------------------------------------------------------------------------

class TestUpdateCustomFieldValues:
    def test_success(self, service):
        updates = [FieldUpdate(field_id=10009, value="Yes")]
        result = asyncio.run(service.update_custom_field_values(1, updates))
        assert isinstance(result, WriteResponse)
        assert result.success is True

    def test_empty_field_updates_returns_400(self, service):
        result = asyncio.run(service.update_custom_field_values(1, []))
        assert isinstance(result, ErrorResponse)
        assert result.status_code == 400

    def test_payload_has_correct_otype_and_oid(self, service, mock_client):
        updates = [
            FieldUpdate(field_id=10009, value="Yes"),
            FieldUpdate(field_id=10010, value="Public"),
        ]
        asyncio.run(service.update_custom_field_values(42, updates))
        payload = mock_client.update_custom_field_values.call_args[0][0]
        assert len(payload) == 2
        for entry in payload:
            assert entry["otype"] == "glossary_term"
            assert entry["oid"] == 42
        assert payload[0]["field_id"] == 10009
        assert payload[1]["field_id"] == 10010

    def test_4xx_error_passes_through(self, service, mock_client):
        mock_client.update_custom_field_values.side_effect = _http_error(404)
        updates = [FieldUpdate(field_id=10009, value="Yes")]
        result = asyncio.run(service.update_custom_field_values(1, updates))
        assert isinstance(result, ErrorResponse)
        assert result.status_code == 404

    def test_5xx_error_mapped_to_502(self, service, mock_client):
        mock_client.update_custom_field_values.side_effect = _http_error(500)
        updates = [FieldUpdate(field_id=10009, value="Yes")]
        result = asyncio.run(service.update_custom_field_values(1, updates))
        assert isinstance(result, ErrorResponse)
        assert result.status_code == 502

    def test_connection_error_returns_503(self, service, mock_client):
        mock_client.update_custom_field_values.side_effect = aiohttp.ClientConnectorError(
            MagicMock(), OSError("refused")
        )
        updates = [FieldUpdate(field_id=10009, value="Yes")]
        result = asyncio.run(service.update_custom_field_values(1, updates))
        assert isinstance(result, ErrorResponse)
        assert result.status_code == 503

    def test_template_id_included_in_payload_when_resolved(self, service, mock_client):
        mock_client._resolve_template_id = AsyncMock(return_value=50)
        updates = [FieldUpdate(field_id=10009, value="Yes")]
        asyncio.run(service.update_custom_field_values(1, updates, template_id=50))
        payload = mock_client.update_custom_field_values.call_args[0][0]
        assert payload[0].get("template_id") == 50

    def test_template_id_absent_when_none(self, service, mock_client):
        mock_client._resolve_template_id = AsyncMock(return_value=None)
        updates = [FieldUpdate(field_id=10009, value="Yes")]
        asyncio.run(service.update_custom_field_values(1, updates, template_id=None))
        payload = mock_client.update_custom_field_values.call_args[0][0]
        assert "template_id" not in payload[0]
