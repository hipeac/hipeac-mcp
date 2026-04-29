"""Tests for member search and discovery tools."""

import inspect
from unittest.mock import AsyncMock, MagicMock, Mock, patch


def make_async_iterator(items):
    """Create an async iterator from a list."""

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
        mock_member.handle = "jsmith"
        mock_member.profile.institution.name = "Test University"
        mock_member.profile.institution.country = "BE"

        # Mock memberships.all() to return a sync iterable (prefetch cache)
        mock_member.memberships.all.return_value = []

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

        # membership_types is now part of the initial User.objects.filter() call, not a chained .filter()
        base_call_kwargs = mock_user.objects.filter.call_args.kwargs
        assert "memberships__type__in" in base_call_kwargs
        assert "member" in base_call_kwargs["memberships__type__in"]
        assert "associated_member" in base_call_kwargs["memberships__type__in"]
        assert isinstance(result, MemberSearchResponse)
        assert result.total == 0

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

    @patch("hipeac_mcp.tools.members.RelInstitution")
    @patch("hipeac_mcp.tools.members.RelTopic")
    @patch("hipeac_mcp.tools.members.RelApplicationArea")
    @patch("hipeac_mcp.tools.members.User")
    @patch("hipeac_mcp.tools.members.ContentType")
    async def test_search_members_empty_topic_filter_does_not_bypass(
        self, mock_ct, mock_user, mock_rel_area, mock_rel_topic, mock_rel_inst
    ):
        """Regression: when topic_ids matches 0 users, the filter must still be applied.

        Previously, `if topic_user_ids:` was False when the list was empty, so the
        filter was skipped and the full (country-filtered) member list was returned
        instead of an empty result set.
        """
        from hipeac_mcp.tools.members import search_members

        mock_ct.objects.aget = AsyncMock(return_value=MagicMock(id=1))

        # No users have this topic — the filter must still be applied (returning empty set).
        mock_topic_qs = MagicMock()
        mock_topic_values = MagicMock()
        mock_topic_values.__aiter__ = lambda self: make_async_iterator([])  # zero matches
        mock_topic_qs.values_list.return_value = mock_topic_values
        mock_rel_topic.objects.filter.return_value = mock_topic_qs

        # German members do exist — these should NOT appear in the result.
        mock_inst_qs = MagicMock()
        mock_inst_values = MagicMock()
        mock_inst_values.__aiter__ = lambda self: make_async_iterator([10, 11, 12])
        mock_inst_qs.values_list.return_value = mock_inst_values
        mock_rel_inst.objects.filter.return_value = mock_inst_qs

        # Track each filter call's return value separately so we can assert the
        # final queryset slice returns nothing.
        filtered_qs_after_topic = MagicMock()
        filtered_qs_after_topic.filter.return_value = filtered_qs_after_topic
        filtered_qs_after_topic.prefetch_related.return_value = filtered_qs_after_topic
        filtered_qs_after_topic.__getitem__.return_value.__aiter__ = lambda self: make_async_iterator([])

        mock_qs = MagicMock()
        mock_qs.distinct.return_value = mock_qs
        mock_qs.filter.return_value = filtered_qs_after_topic  # first filter (topic) returns new qs
        mock_user.objects.filter.return_value = mock_qs

        result = await search_members(topic_ids=[42], countries=["DE"])

        # topic filter must have been applied (filter called on the base queryset)
        mock_qs.filter.assert_called_once()
        assert result.total == 0
        assert result.members == []

    @patch("hipeac_mcp.tools.members.RelInstitution")
    @patch("hipeac_mcp.tools.members.RelTopic")
    @patch("hipeac_mcp.tools.members.RelApplicationArea")
    @patch("hipeac_mcp.tools.members.User")
    @patch("hipeac_mcp.tools.members.ContentType")
    async def test_search_members_excludes_affiliated_phd_by_default(
        self, mock_ct, mock_user, mock_rel_area, mock_rel_topic, mock_rel_inst
    ):
        """affiliated_phd must not appear in default search results.

        The base queryset should filter memberships__type__in to only include
        member, associated_member, and affiliated_member unless the caller
        explicitly passes membership_types.
        """
        from hipeac_mcp.schemas.metadata import MembershipType
        from hipeac_mcp.tools.members import search_members

        mock_ct.objects.aget = AsyncMock(return_value=MagicMock(id=1))

        mock_qs = MagicMock()
        mock_qs.distinct.return_value = mock_qs
        mock_qs.filter.return_value = mock_qs
        mock_qs.prefetch_related.return_value = mock_qs
        mock_qs.__getitem__.return_value.__aiter__ = lambda self: make_async_iterator([])
        mock_user.objects.filter.return_value = mock_qs

        await search_members()

        call_kwargs = mock_user.objects.filter.call_args.kwargs
        types_used = call_kwargs.get("memberships__type__in", [])
        assert MembershipType.MEMBER in types_used
        assert MembershipType.ASSOCIATED_MEMBER in types_used
        assert MembershipType.AFFILIATED_MEMBER in types_used
        assert MembershipType.AFFILIATED_PHD not in types_used

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


class TestEnsureMetadataCache:
    """Tests for the _ensure_metadata_cache helper."""

    async def test_returns_early_when_already_populated(self):
        """Does not query the database when the cache is already warm."""
        from hipeac_mcp.tools.members import _ensure_metadata_cache, _metadata_cache

        _metadata_cache["topic"] = {1: MagicMock()}  # pre-warm the cache
        try:
            with patch("hipeac_mcp.tools.members.ensure_connection_async", new_callable=AsyncMock) as mock_conn:
                await _ensure_metadata_cache()
            mock_conn.assert_not_called()
        finally:
            _metadata_cache.clear()


class TestSearchMembersWithActiveMembership:
    """Tests that the active membership branch is reached."""

    @patch("hipeac_mcp.tools.members._ensure_metadata_cache", new_callable=AsyncMock)
    @patch("hipeac_mcp.tools.members.RelInstitution")
    @patch("hipeac_mcp.tools.members.RelTopic")
    @patch("hipeac_mcp.tools.members.RelApplicationArea")
    @patch("hipeac_mcp.tools.members.User")
    @patch("hipeac_mcp.tools.members.ContentType")
    async def test_includes_active_membership_in_result(
        self, mock_ct, mock_user, mock_rel_area, mock_rel_topic, mock_rel_inst, mock_cache
    ):
        """Member with an active membership has the membership field set."""
        from hipeac_mcp.tools.members import search_members

        mock_ct.objects.aget = AsyncMock(return_value=MagicMock(id=1))

        mock_membership = MagicMock()
        mock_membership.type = "member"
        mock_membership.end_date = None

        mock_member = Mock()
        mock_member.id = 1
        mock_member.first_name = "Anna"
        mock_member.last_name = "Doe"
        mock_member.username = "adoe"
        mock_member.handle = "adoe"

        # Mock memberships.all() to return a sync iterable (prefetch cache)
        mock_member.memberships.all.return_value = [mock_membership]

        mock_qs = MagicMock()
        mock_qs.distinct.return_value = mock_qs
        mock_qs.select_related.return_value = mock_qs
        mock_qs.prefetch_related.return_value = mock_qs
        mock_qs.filter.return_value = mock_qs
        mock_qs.__getitem__.return_value.__aiter__ = lambda self: make_async_iterator([mock_member])
        mock_user.objects.filter.return_value = mock_qs

        for rel_mock in [mock_rel_inst, mock_rel_topic, mock_rel_area]:
            result_qs = MagicMock()
            result_qs.__aiter__ = lambda self: make_async_iterator([])
            rel_mock.objects.filter.return_value.select_related.return_value = result_qs

        result = await search_members(query="Anna")

        assert result.total == 1
        assert result.members[0].membership == "member"
