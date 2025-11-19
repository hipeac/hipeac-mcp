"""Tests for metadata tool."""

import inspect
from unittest.mock import MagicMock, Mock, patch

import pytest


def make_async_iterator(items):
    """Helper to create an async iterator from a list."""

    async def async_gen():
        for item in items:
            yield item

    return async_gen()


class TestMetadataTool:
    """Tests for get_metadata tool."""

    def test_get_metadata_callable(self):
        """Test get_metadata tool is callable and registered."""
        from hipeac_mcp.tools.metadata import get_metadata

        assert callable(get_metadata)

    def test_get_metadata_no_parameters(self):
        """Test get_metadata accepts no parameters (always returns all)."""
        from hipeac_mcp.tools.metadata import get_metadata

        sig = inspect.signature(get_metadata)

        # Should have no required parameters
        assert len(sig.parameters) == 0

    @pytest.mark.asyncio
    @patch("hipeac_mcp.tools.metadata.Metadata")
    async def test_get_metadata_returns_all_types(self, mock_metadata):
        """Test get_metadata always returns all metadata types."""
        from hipeac_mcp.schemas.metadata import MetadataType
        from hipeac_mcp.tools.metadata import get_metadata

        mock_topic = Mock()
        mock_topic.id = 1
        mock_topic.value = "Machine Learning"
        mock_topic.type = MetadataType.TOPIC.value

        mock_area = Mock()
        mock_area.id = 2
        mock_area.value = "Healthcare"
        mock_area.type = MetadataType.APPLICATION_AREA.value

        mock_inst = Mock()
        mock_inst.id = 3
        mock_inst.value = "University"
        mock_inst.type = MetadataType.INSTITUTION_TYPE.value

        # Mock the queryset for the single query with type__in
        mock_qs = MagicMock()
        mock_qs.order_by.return_value = mock_qs
        mock_qs.only.return_value = mock_qs
        mock_qs.__aiter__ = lambda self: make_async_iterator([mock_topic, mock_area, mock_inst])

        mock_metadata.objects.filter.return_value = mock_qs

        result = await get_metadata()

        # Should contain all metadata types
        assert result.topics is not None
        assert len(result.topics) == 1
        assert result.topics[0].value == "Machine Learning"

        assert result.application_areas is not None
        assert len(result.application_areas) == 1
        assert result.application_areas[0].value == "Healthcare"

        assert result.institution_types is not None
        assert len(result.institution_types) == 1
        assert result.institution_types[0].value == "University"

        assert result.membership_types is not None
        assert len(result.membership_types) == 4

    @pytest.mark.asyncio
    async def test_get_metadata_with_database(self):
        """Test get_metadata returns real data from database."""
        import os

        if not os.environ.get("DATABASE_URL"):
            pytest.skip("DATABASE_URL not set")

        from hipeac_mcp.schemas.metadata import MetadataResponse
        from hipeac_mcp.tools.metadata import get_metadata

        result = await get_metadata()

        assert isinstance(result, MetadataResponse)
        assert result.topics is not None and len(result.topics) > 0
        assert result.application_areas is not None and len(result.application_areas) > 0
        assert result.institution_types is not None and len(result.institution_types) > 0
        assert result.membership_types is not None and len(result.membership_types) == 4
