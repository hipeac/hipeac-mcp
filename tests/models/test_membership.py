"""Tests for MembershipQuerySet filtering methods."""

from unittest.mock import MagicMock

from hipeac_mcp.models.membership import MembershipQuerySet


class TestMembershipQuerySet:
    """Tests for MembershipQuerySet chainable filter methods."""

    def test_active_filters_by_no_end_date(self):
        """active() applies end_date__isnull=True to the queryset."""
        qs = MagicMock(spec=MembershipQuerySet)
        MembershipQuerySet.active(qs)
        qs.filter.assert_called_once_with(end_date__isnull=True)

    def test_ended_filters_by_end_date_present(self):
        """ended() applies end_date__isnull=False to the queryset."""
        qs = MagicMock(spec=MembershipQuerySet)
        MembershipQuerySet.ended(qs)
        qs.filter.assert_called_once_with(end_date__isnull=False)
