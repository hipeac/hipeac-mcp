"""Tests for member search and discovery tools."""

import inspect
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest


def make_async_iterator(items):
    """Helper to create an async iterator from a list."""

    async def async_gen():
        for item in items:
            yield item

    return async_gen()


class TestMemberTools:
    """Tests for member tools."""

    def test_search_members_callable(self):
        """Test search_members tool is callable and registered."""
        from hipeac_mcp.tools.members import search_members

        assert callable(search_members)

    @pytest.mark.asyncio
    @patch("hipeac_mcp.tools.members._ensure_metadata_cache", new_callable=AsyncMock)
    @patch("hipeac_mcp.tools.members.RelInstitution")
    @patch("hipeac_mcp.tools.members.RelTopic")
    @patch("hipeac_mcp.tools.members.RelApplicationArea")
    @patch("hipeac_mcp.tools.members.User")
    @patch("hipeac_mcp.tools.members.ContentType")
    async def test_search_members_no_results(
        self, mock_ct, mock_user, mock_rel_area, mock_rel_topic, mock_rel_inst, mock_cache
    ):
        """Test search_members returns message when no results found."""
        from hipeac_mcp.tools.members import search_members

        mock_ct.objects.aget = AsyncMock(return_value=MagicMock(id=1))

        mock_qs = MagicMock()
        mock_qs.distinct.return_value = mock_qs
        mock_qs.select_related.return_value = mock_qs
        mock_qs.prefetch_related.return_value = mock_qs
        mock_qs.filter.return_value = mock_qs
        mock_qs.__getitem__.return_value.__aiter__ = lambda self: make_async_iterator([])

        mock_user.objects.filter.return_value = mock_qs

        result = await search_members(query="NonExistent")

        assert result.total == 0
        assert result.members == []

    @pytest.mark.asyncio
    @patch("hipeac_mcp.tools.members._ensure_metadata_cache", new_callable=AsyncMock)
    @patch("hipeac_mcp.tools.members.RelInstitution")
    @patch("hipeac_mcp.tools.members.RelTopic")
    @patch("hipeac_mcp.tools.members.RelApplicationArea")
    @patch("hipeac_mcp.tools.members.User")
    @patch("hipeac_mcp.tools.members.ContentType")
    async def test_search_members_with_results(
        self, mock_ct, mock_user, mock_rel_area, mock_rel_topic, mock_rel_inst, mock_cache
    ):
        """Test search_members returns formatted results."""
        from hipeac_mcp.tools.members import search_members

        mock_ct.objects.aget = AsyncMock(return_value=MagicMock(id=1))

        mock_member = Mock()
        mock_member.id = 1
        mock_member.first_name = "Jane"
        mock_member.last_name = "Smith"
        mock_member.username = "jsmith"
        mock_member.profile.institution.name = "Test University"
        mock_member.profile.institution.country = "BE"

        # Mock memberships.filter() to return async iterator
        mock_memberships = MagicMock()
        mock_memberships.__aiter__ = lambda self: make_async_iterator([])
        mock_member.memberships.filter.return_value = mock_memberships

        mock_qs = MagicMock()
        mock_qs.distinct.return_value = mock_qs
        mock_qs.select_related.return_value = mock_qs
        mock_qs.prefetch_related.return_value = mock_qs
        mock_qs.filter.return_value = mock_qs
        mock_qs.__getitem__.return_value.__aiter__ = lambda self: make_async_iterator([mock_member])

        mock_user.objects.filter.return_value = mock_qs

        # Mock the relation queries for profile details
        mock_rel_inst_result = MagicMock()
        mock_rel_inst_result.__aiter__ = lambda self: make_async_iterator([])
        mock_rel_inst.objects.filter.return_value.select_related.return_value = mock_rel_inst_result

        mock_rel_topic_result = MagicMock()
        mock_rel_topic_result.__aiter__ = lambda self: make_async_iterator([])
        mock_rel_topic.objects.filter.return_value.select_related.return_value = mock_rel_topic_result

        mock_rel_area_result = MagicMock()
        mock_rel_area_result.__aiter__ = lambda self: make_async_iterator([])
        mock_rel_area.objects.filter.return_value.select_related.return_value = mock_rel_area_result

        result = await search_members(query="Jane")

        assert result.total == 1
        assert len(result.members) == 1
        assert result.members[0].first_name == "Jane"
        assert result.members[0].last_name == "Smith"
        assert result.members[0].username == "jsmith"
        assert str(result.members[0].profile_url) == "https://www.hipeac.net/~jsmith/"

    @pytest.mark.asyncio
    @patch("hipeac_mcp.tools.members._ensure_metadata_cache", new_callable=AsyncMock)
    @patch("hipeac_mcp.tools.members.RelInstitution")
    @patch("hipeac_mcp.tools.members.RelTopic")
    @patch("hipeac_mcp.tools.members.RelApplicationArea")
    @patch("hipeac_mcp.tools.members.User")
    @patch("hipeac_mcp.tools.members.ContentType")
    async def test_search_members_with_topic_filter(
        self, mock_ct, mock_user, mock_rel_area, mock_rel_topic, mock_rel_inst, mock_cache
    ):
        """Test search_members with topic filter."""
        from hipeac_mcp.schemas.members import MemberSearchResponse
        from hipeac_mcp.tools.members import search_members

        mock_ct.objects.aget = AsyncMock(return_value=MagicMock(id=1))

        mock_topic_qs = MagicMock()
        mock_values_list = MagicMock()
        mock_values_list.__aiter__ = lambda self: make_async_iterator([1, 2])
        mock_topic_qs.values_list.return_value = mock_values_list
        mock_rel_topic.objects.filter.return_value = mock_topic_qs

        mock_qs = MagicMock()
        mock_qs.distinct.return_value = mock_qs
        mock_qs.filter.return_value = mock_qs
        mock_qs.select_related.return_value = mock_qs
        mock_qs.prefetch_related.return_value = mock_qs
        mock_qs.__getitem__.return_value.__aiter__ = lambda self: make_async_iterator([])

        mock_user.objects.filter.return_value = mock_qs

        result = await search_members(topic_ids=[42])

        mock_rel_topic.objects.filter.assert_called()
        assert isinstance(result, MemberSearchResponse)
        assert result.total == 0

    @pytest.mark.asyncio
    @patch("hipeac_mcp.tools.members.RelInstitution")
    @patch("hipeac_mcp.tools.members.RelTopic")
    @patch("hipeac_mcp.tools.members.RelApplicationArea")
    @patch("hipeac_mcp.tools.members.User")
    @patch("hipeac_mcp.tools.members.ContentType")
    async def test_search_members_with_country_filter(
        self, mock_ct, mock_user, mock_rel_area, mock_rel_topic, mock_rel_inst
    ):
        """Test search_members with country filter."""
        from hipeac_mcp.tools.members import search_members

        mock_ct.objects.aget = AsyncMock(return_value=MagicMock(id=1))

        mock_inst_qs = MagicMock()
        mock_values_list = MagicMock()
        mock_values_list.__aiter__ = lambda self: make_async_iterator([1, 2, 3])
        mock_inst_qs.values_list.return_value = mock_values_list
        mock_rel_inst.objects.filter.return_value = mock_inst_qs

        mock_qs = MagicMock()
        mock_qs.distinct.return_value = mock_qs
        mock_qs.filter.return_value = mock_qs
        mock_qs.select_related.return_value = mock_qs
        mock_qs.prefetch_related.return_value = mock_qs
        mock_qs.__getitem__.return_value.__aiter__ = lambda self: make_async_iterator([])

        mock_user.objects.filter.return_value = mock_qs

        await search_members(countries=["BE"])

        mock_rel_inst.objects.filter.assert_called()
        mock_qs.filter.assert_called()

    @pytest.mark.asyncio
    @patch("hipeac_mcp.tools.members.RelInstitution")
    @patch("hipeac_mcp.tools.members.RelTopic")
    @patch("hipeac_mcp.tools.members.RelApplicationArea")
    @patch("hipeac_mcp.tools.members.User")
    @patch("hipeac_mcp.tools.members.ContentType")
    async def test_search_members_limit_enforced(
        self, mock_ct, mock_user, mock_rel_area, mock_rel_topic, mock_rel_inst
    ):
        """Test search_members enforces max limit of 100."""
        from hipeac_mcp.tools.members import search_members

        mock_ct.objects.aget = AsyncMock(return_value=MagicMock(id=1))

        # Mock user queryset
        mock_qs = MagicMock()
        mock_qs.distinct.return_value = mock_qs
        mock_qs.filter.return_value = mock_qs
        mock_qs.select_related.return_value = mock_qs
        mock_qs.prefetch_related.return_value = mock_qs
        mock_qs.__getitem__.return_value.__aiter__ = lambda self: make_async_iterator([])

        mock_user.objects.filter.return_value = mock_qs

        await search_members(limit=200)

        mock_qs.__getitem__.assert_called()
        call_args = mock_qs.__getitem__.call_args
        assert call_args[0][0].stop == 100

    @pytest.mark.asyncio
    @patch("hipeac_mcp.tools.members._ensure_metadata_cache", new_callable=AsyncMock)
    @patch("hipeac_mcp.tools.members.RelInstitution")
    @patch("hipeac_mcp.tools.members.RelTopic")
    @patch("hipeac_mcp.tools.members.RelApplicationArea")
    @patch("hipeac_mcp.tools.members.User")
    @patch("hipeac_mcp.tools.members.ContentType")
    async def test_search_members_with_application_area_filter(
        self, mock_ct, mock_user, mock_rel_area, mock_rel_topic, mock_rel_inst, mock_cache
    ):
        """Test search_members with application area filter."""
        from hipeac_mcp.schemas.members import MemberSearchResponse
        from hipeac_mcp.tools.members import search_members

        mock_ct.objects.aget = AsyncMock(return_value=MagicMock(id=1))

        mock_area_qs = MagicMock()
        mock_area_values = MagicMock()
        mock_area_values.__aiter__ = lambda self: make_async_iterator([5, 6])
        mock_area_qs.values_list.return_value = mock_area_values
        mock_rel_area.objects.filter.return_value = mock_area_qs

        mock_qs = MagicMock()
        mock_qs.distinct.return_value = mock_qs
        mock_qs.filter.return_value = mock_qs
        mock_qs.select_related.return_value = mock_qs
        mock_qs.prefetch_related.return_value = mock_qs
        mock_qs.__getitem__.return_value.__aiter__ = lambda self: make_async_iterator([])

        mock_user.objects.filter.return_value = mock_qs

        result = await search_members(application_area_ids=[5])

        mock_rel_area.objects.filter.assert_called()
        assert isinstance(result, MemberSearchResponse)
        assert result.total == 0

    @pytest.mark.asyncio
    @patch("hipeac_mcp.tools.members._ensure_metadata_cache", new_callable=AsyncMock)
    @patch("hipeac_mcp.tools.members.RelInstitution")
    @patch("hipeac_mcp.tools.members.RelTopic")
    @patch("hipeac_mcp.tools.members.RelApplicationArea")
    @patch("hipeac_mcp.tools.members.User")
    @patch("hipeac_mcp.tools.members.ContentType")
    async def test_search_members_with_institution_type_filter(
        self, mock_ct, mock_user, mock_rel_area, mock_rel_topic, mock_rel_inst, mock_cache
    ):
        """Test search_members with institution type filter."""
        from hipeac_mcp.schemas.members import MemberSearchResponse
        from hipeac_mcp.tools.members import search_members

        mock_ct.objects.aget = AsyncMock(return_value=MagicMock(id=1))

        mock_inst_qs = MagicMock()
        mock_inst_values = MagicMock()
        mock_inst_values.__aiter__ = lambda self: make_async_iterator([10, 11])
        mock_inst_qs.values_list.return_value = mock_inst_values
        mock_rel_inst.objects.filter.return_value = mock_inst_qs

        mock_qs = MagicMock()
        mock_qs.distinct.return_value = mock_qs
        mock_qs.filter.return_value = mock_qs
        mock_qs.select_related.return_value = mock_qs
        mock_qs.prefetch_related.return_value = mock_qs
        mock_qs.__getitem__.return_value.__aiter__ = lambda self: make_async_iterator([])

        mock_user.objects.filter.return_value = mock_qs

        result = await search_members(institution_type_ids=[1])

        mock_rel_inst.objects.filter.assert_called()
        assert isinstance(result, MemberSearchResponse)
        assert result.total == 0

    @pytest.mark.asyncio
    @patch("hipeac_mcp.tools.members._ensure_metadata_cache", new_callable=AsyncMock)
    @patch("hipeac_mcp.tools.members.RelInstitution")
    @patch("hipeac_mcp.tools.members.RelTopic")
    @patch("hipeac_mcp.tools.members.RelApplicationArea")
    @patch("hipeac_mcp.tools.members.User")
    @patch("hipeac_mcp.tools.members.ContentType")
    async def test_search_members_with_membership_type_filter(
        self, mock_ct, mock_user, mock_rel_area, mock_rel_topic, mock_rel_inst, mock_cache
    ):
        """Test search_members with membership type filter."""
        from hipeac_mcp.schemas.members import MemberSearchResponse
        from hipeac_mcp.tools.members import search_members

        mock_ct.objects.aget = AsyncMock(return_value=MagicMock(id=1))

        # Mock user queryset
        mock_qs = MagicMock()
        mock_qs.distinct.return_value = mock_qs
        mock_qs.filter.return_value = mock_qs
        mock_qs.select_related.return_value = mock_qs
        mock_qs.prefetch_related.return_value = mock_qs
        mock_qs.__getitem__.return_value.__aiter__ = lambda self: make_async_iterator([])

        mock_user.objects.filter.return_value = mock_qs

        result = await search_members(membership_types=["member", "associated_member"])

        assert mock_qs.filter.call_count == 1
        call_args = mock_qs.filter.call_args
        assert "memberships__type__in" in str(call_args)
        assert isinstance(result, MemberSearchResponse)
        assert result.total == 0

    @pytest.mark.asyncio
    @patch("hipeac_mcp.tools.members._ensure_metadata_cache", new_callable=AsyncMock)
    @patch("hipeac_mcp.tools.members.RelInstitution")
    @patch("hipeac_mcp.tools.members.RelTopic")
    @patch("hipeac_mcp.tools.members.RelApplicationArea")
    @patch("hipeac_mcp.tools.members.User")
    @patch("hipeac_mcp.tools.members.ContentType")
    async def test_search_members_with_numeric_topic_id(
        self, mock_ct, mock_user, mock_rel_area, mock_rel_topic, mock_rel_inst, mock_cache
    ):
        """Test search_members handles numeric topic IDs."""
        from hipeac_mcp.schemas.members import MemberSearchResponse
        from hipeac_mcp.tools.members import search_members

        mock_ct.objects.aget = AsyncMock(return_value=MagicMock(id=1))

        mock_topic_qs = MagicMock()
        mock_topic_values = MagicMock()
        mock_topic_values.__aiter__ = lambda self: make_async_iterator([1])
        mock_topic_qs.values_list.return_value = mock_topic_values
        mock_rel_topic.objects.filter.return_value = mock_topic_qs

        mock_qs = MagicMock()
        mock_qs.distinct.return_value = mock_qs
        mock_qs.filter.return_value = mock_qs
        mock_qs.select_related.return_value = mock_qs
        mock_qs.prefetch_related.return_value = mock_qs
        mock_qs.__getitem__.return_value.__aiter__ = lambda self: make_async_iterator([])

        mock_user.objects.filter.return_value = mock_qs

        result = await search_members(topic_ids=[42])

        mock_rel_topic.objects.filter.assert_called()
        assert isinstance(result, MemberSearchResponse)
        assert result.total == 0

    def test_search_members_parameter_types(self):
        """Test search_members accepts correct parameter types."""
        from hipeac_mcp.tools.members import search_members

        sig = inspect.signature(search_members)

        assert "query" in sig.parameters
        assert "topic_ids" in sig.parameters
        assert "application_area_ids" in sig.parameters
        assert "countries" in sig.parameters
        assert "institution_type_ids" in sig.parameters
        assert "membership_types" in sig.parameters
        assert "limit" in sig.parameters


class TestMemberModels:
    """Tests for member-related Django models."""

    def test_user_model_exists(self):
        """Test User model is importable."""
        from hipeac_mcp.models import User

        assert User is not None

    def test_membership_model_exists(self):
        """Test Membership model is importable."""
        from hipeac_mcp.models import Membership

        assert Membership is not None

    def test_membership_queryset_active_method(self):
        """Test Membership has active queryset method."""
        from hipeac_mcp.models import Membership

        assert hasattr(Membership.objects, "active")

    def test_rel_topic_model_exists(self):
        """Test RelTopic model is importable."""
        from hipeac_mcp.models import RelTopic

        assert RelTopic is not None

    def test_rel_application_area_model_exists(self):
        """Test RelApplicationArea model is importable."""
        from hipeac_mcp.models import RelApplicationArea

        assert RelApplicationArea is not None

    def test_rel_institution_model_exists(self):
        """Test RelInstitution model is importable."""
        from hipeac_mcp.models import RelInstitution

        assert RelInstitution is not None
