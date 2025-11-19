"""Tests for metadata resources."""

from unittest.mock import MagicMock, patch


class TestMetadataResources:
    """Tests for metadata resources with mocked database."""

    @patch("hipeac_mcp.resources.metadata.Metadata")
    def test_topics_resource(self, mock_metadata):
        """Test topics resource returns formatted list."""
        from hipeac_mcp.resources.metadata import topics

        mock_topic = MagicMock()
        mock_topic.id = 1
        mock_topic.value = "Artificial Intelligence"

        mock_qs = MagicMock()
        mock_qs.order_by.return_value = mock_qs
        mock_qs.only.return_value = [mock_topic]
        mock_metadata.objects.filter.return_value = mock_qs

        result = topics()

        assert "Artificial Intelligence" in result
        assert "ID: 1" in result

    @patch("hipeac_mcp.resources.metadata.Metadata")
    def test_application_areas_resource(self, mock_metadata):
        """Test application areas resource returns formatted list."""
        from hipeac_mcp.resources.metadata import application_areas

        mock_area = MagicMock()
        mock_area.id = 10
        mock_area.value = "Healthcare"

        mock_qs = MagicMock()
        mock_qs.order_by.return_value = mock_qs
        mock_qs.only.return_value = [mock_area]
        mock_metadata.objects.filter.return_value = mock_qs

        result = application_areas()

        assert "Healthcare" in result
        assert "ID: 10" in result

    @patch("hipeac_mcp.resources.metadata.Metadata")
    def test_institution_types_resource(self, mock_metadata):
        """Test institution types resource returns formatted list."""
        from hipeac_mcp.resources.metadata import institution_types

        mock_type = MagicMock()
        mock_type.id = 20
        mock_type.value = "University"

        mock_qs = MagicMock()
        mock_qs.order_by.return_value = mock_qs
        mock_qs.only.return_value = [mock_type]
        mock_metadata.objects.filter.return_value = mock_qs

        result = institution_types()

        assert "University" in result
        assert "ID: 20" in result

    @patch("hipeac_mcp.resources.metadata.Metadata")
    def test_membership_types_resource(self, mock_metadata):
        """Test membership types resource returns formatted list."""
        from hipeac_mcp.resources.metadata import membership_types

        result = membership_types()

        assert "Member" in result or "member" in result

    def test_topics_resource_function_exists(self):
        """Test topics resource function is defined."""
        from hipeac_mcp.resources.metadata import topics

        assert callable(topics)

    def test_application_areas_resource_function_exists(self):
        """Test application areas resource function is defined."""
        from hipeac_mcp.resources.metadata import application_areas

        assert callable(application_areas)

    def test_institution_types_resource_function_exists(self):
        """Test institution types resource function is defined."""
        from hipeac_mcp.resources.metadata import institution_types

        assert callable(institution_types)

    def test_membership_types_resource_function_exists(self):
        """Test membership types resource function is defined."""
        from hipeac_mcp.resources.metadata import membership_types

        assert callable(membership_types)
