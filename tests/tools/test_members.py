"""Tests for member search and discovery tools."""

import inspect
from unittest.mock import MagicMock, Mock, patch


class TestMemberTools:
    """Tests for member tools."""

    def test_search_members_callable(self):
        """Test search_members tool is callable and registered."""
        from hipeac_mcp.tools.members import search_members

        assert callable(search_members)

    def test_find_experts_callable(self):
        """Test find_experts tool is callable and registered."""
        from hipeac_mcp.tools.members import find_experts

        assert callable(find_experts)

    @patch("hipeac_mcp.tools.members.RelInstitution")
    @patch("hipeac_mcp.tools.members.RelTopic")
    @patch("hipeac_mcp.tools.members.RelApplicationArea")
    @patch("hipeac_mcp.tools.members.User")
    @patch("hipeac_mcp.tools.members.ContentType")
    def test_search_members_no_results(self, mock_ct, mock_user, mock_rel_area, mock_rel_topic, mock_rel_inst):
        """Test search_members returns message when no results found."""
        from hipeac_mcp.tools.members import search_members

        mock_ct.objects.get.return_value = MagicMock(id=1)

        mock_qs = MagicMock()
        mock_qs.distinct.return_value = mock_qs
        mock_qs.select_related.return_value = mock_qs
        mock_qs.prefetch_related.return_value = mock_qs
        mock_qs.filter.return_value = mock_qs
        mock_qs.__getitem__.return_value = []

        mock_user.objects.filter.return_value = mock_qs

        result = search_members(query="NonExistent")

        assert "No members found" in result

    @patch("hipeac_mcp.tools.members.RelInstitution")
    @patch("hipeac_mcp.tools.members.RelTopic")
    @patch("hipeac_mcp.tools.members.RelApplicationArea")
    @patch("hipeac_mcp.tools.members.User")
    @patch("hipeac_mcp.tools.members.ContentType")
    def test_search_members_with_results(self, mock_ct, mock_user, mock_rel_area, mock_rel_topic, mock_rel_inst):
        """Test search_members returns formatted results."""
        from hipeac_mcp.tools.members import search_members

        mock_ct.objects.get.return_value = MagicMock(id=1)

        mock_member = Mock()
        mock_member.id = 1
        mock_member.first_name = "Jane"
        mock_member.last_name = "Smith"
        mock_member.username = "jsmith"
        mock_member.memberships.filter.return_value = []

        mock_qs = MagicMock()
        mock_qs.distinct.return_value = mock_qs
        mock_qs.select_related.return_value = mock_qs
        mock_qs.prefetch_related.return_value = mock_qs
        mock_qs.filter.return_value = mock_qs
        mock_qs.__getitem__.return_value = [mock_member]

        mock_user.objects.filter.return_value = mock_qs

        mock_rel_inst.objects.filter.return_value.select_related.return_value = []
        mock_rel_topic.objects.filter.return_value.select_related.return_value = []
        mock_rel_area.objects.filter.return_value.select_related.return_value = []

        result = search_members(query="Jane")

        assert "Found 1 member(s)" in result
        assert "Jane Smith" in result
        assert "@jsmith" in result
        assert "https://www.hipeac.net/~jsmith/" in result

    @patch("hipeac_mcp.tools.members.RelInstitution")
    @patch("hipeac_mcp.tools.members.RelTopic")
    @patch("hipeac_mcp.tools.members.RelApplicationArea")
    @patch("hipeac_mcp.tools.members.User")
    @patch("hipeac_mcp.tools.members.ContentType")
    def test_search_members_with_topic_filter(self, mock_ct, mock_user, mock_rel_area, mock_rel_topic, mock_rel_inst):
        """Test search_members with topic filter."""
        from hipeac_mcp.tools.members import search_members

        mock_ct.objects.get.return_value = MagicMock(id=1)

        mock_topic_qs = MagicMock()
        mock_topic_qs.values_list.return_value = [1, 2]
        mock_rel_topic.objects.filter.return_value = mock_topic_qs

        mock_qs = MagicMock()
        mock_qs.distinct.return_value = mock_qs
        mock_qs.filter.return_value = mock_qs
        mock_qs.select_related.return_value = mock_qs
        mock_qs.prefetch_related.return_value = mock_qs
        mock_qs.__getitem__.return_value = []

        mock_user.objects.filter.return_value = mock_qs

        result = search_members(topics=["AI"])

        mock_rel_topic.objects.filter.assert_called()
        assert isinstance(result, str)

    @patch("hipeac_mcp.tools.members.RelInstitution")
    @patch("hipeac_mcp.tools.members.RelTopic")
    @patch("hipeac_mcp.tools.members.RelApplicationArea")
    @patch("hipeac_mcp.tools.members.User")
    @patch("hipeac_mcp.tools.members.ContentType")
    def test_search_members_with_country_filter(self, mock_ct, mock_user, mock_rel_area, mock_rel_topic, mock_rel_inst):
        """Test search_members with country filter."""
        from hipeac_mcp.tools.members import search_members

        mock_ct.objects.get.return_value = MagicMock(id=1)

        mock_inst_qs = MagicMock()
        mock_inst_qs.values_list.return_value = [1, 2, 3]
        mock_rel_inst.objects.filter.return_value = mock_inst_qs

        mock_qs = MagicMock()
        mock_qs.distinct.return_value = mock_qs
        mock_qs.filter.return_value = mock_qs
        mock_qs.select_related.return_value = mock_qs
        mock_qs.prefetch_related.return_value = mock_qs
        mock_qs.__getitem__.return_value = []

        mock_user.objects.filter.return_value = mock_qs

        result = search_members(countries=["BE"])

        mock_rel_inst.objects.filter.assert_called()
        mock_qs.filter.assert_called()

    @patch("hipeac_mcp.tools.members.RelInstitution")
    @patch("hipeac_mcp.tools.members.RelTopic")
    @patch("hipeac_mcp.tools.members.RelApplicationArea")
    @patch("hipeac_mcp.tools.members.User")
    @patch("hipeac_mcp.tools.members.ContentType")
    def test_search_members_limit_enforced(self, mock_ct, mock_user, mock_rel_area, mock_rel_topic, mock_rel_inst):
        """Test search_members enforces max limit of 100."""
        from hipeac_mcp.tools.members import search_members

        mock_ct.objects.get.return_value = MagicMock(id=1)

        # Mock user queryset
        mock_qs = MagicMock()
        mock_qs.distinct.return_value = mock_qs
        mock_qs.filter.return_value = mock_qs
        mock_qs.select_related.return_value = mock_qs
        mock_qs.prefetch_related.return_value = mock_qs
        mock_qs.__getitem__.return_value = []

        mock_user.objects.filter.return_value = mock_qs

        search_members(limit=200)

        mock_qs.__getitem__.assert_called()
        call_args = mock_qs.__getitem__.call_args
        assert call_args[0][0].stop == 100

    @patch("hipeac_mcp.tools.members.Metadata")
    @patch("hipeac_mcp.tools.members.RelInstitution")
    @patch("hipeac_mcp.tools.members.RelApplicationArea")
    @patch("hipeac_mcp.tools.members.RelTopic")
    @patch("hipeac_mcp.tools.members.User")
    @patch("hipeac_mcp.tools.members.ContentType")
    def test_find_experts_with_topic(
        self, mock_ct, mock_user, mock_rel_topic, mock_rel_area, mock_rel_inst, mock_metadata
    ):
        """Test find_experts searches by topic."""
        from hipeac_mcp.tools.members import Metadata, find_experts

        mock_ct.objects.get.return_value = MagicMock(id=1)

        mock_meta = Mock()
        mock_meta.id = 5
        mock_meta.value = "Machine Learning"
        mock_meta.type = Metadata.TOPIC

        mock_meta_qs = MagicMock()
        mock_meta_qs.filter.return_value = [mock_meta]
        mock_metadata.objects.filter.return_value = mock_meta_qs
        mock_metadata.TOPIC = Metadata.TOPIC

        mock_topic_qs = MagicMock()
        mock_topic_qs.values_list.return_value = [1, 2]
        mock_rel_topic.objects.filter.return_value = mock_topic_qs

        mock_inst_qs = MagicMock()
        mock_inst_qs.values_list.return_value = []
        mock_rel_inst.objects.filter.return_value = mock_inst_qs

        mock_expert = Mock()
        mock_expert.id = 1
        mock_expert.first_name = "Expert"
        mock_expert.last_name = "User"
        mock_expert.username = "expert1"
        mock_expert.profile.institution.name = "University"

        mock_qs = MagicMock()
        mock_qs.distinct.return_value = mock_qs
        mock_qs.filter.return_value = mock_qs
        mock_qs.select_related.return_value = mock_qs
        mock_qs.__getitem__.return_value = [mock_expert]

        mock_user.objects.filter.return_value = mock_qs

        result = find_experts(expertise=["Machine Learning"])

        assert isinstance(result, str)
        mock_metadata.objects.filter.assert_called()
        mock_rel_topic.objects.filter.assert_called()

    @patch("hipeac_mcp.tools.members.RelInstitution")
    @patch("hipeac_mcp.tools.members.RelTopic")
    @patch("hipeac_mcp.tools.members.RelApplicationArea")
    @patch("hipeac_mcp.tools.members.User")
    @patch("hipeac_mcp.tools.members.ContentType")
    def test_search_members_with_application_area_filter(
        self, mock_ct, mock_user, mock_rel_area, mock_rel_topic, mock_rel_inst
    ):
        """Test search_members with application area filter."""
        from hipeac_mcp.tools.members import search_members

        mock_ct.objects.get.return_value = MagicMock(id=1)

        mock_area_qs = MagicMock()
        mock_area_qs.values_list.return_value = [5, 6]
        mock_rel_area.objects.filter.return_value = mock_area_qs

        mock_qs = MagicMock()
        mock_qs.distinct.return_value = mock_qs
        mock_qs.filter.return_value = mock_qs
        mock_qs.select_related.return_value = mock_qs
        mock_qs.prefetch_related.return_value = mock_qs
        mock_qs.__getitem__.return_value = []

        mock_user.objects.filter.return_value = mock_qs

        result = search_members(application_areas=["Healthcare"])

        mock_rel_area.objects.filter.assert_called()
        assert isinstance(result, str)

    @patch("hipeac_mcp.tools.members.RelInstitution")
    @patch("hipeac_mcp.tools.members.RelTopic")
    @patch("hipeac_mcp.tools.members.RelApplicationArea")
    @patch("hipeac_mcp.tools.members.User")
    @patch("hipeac_mcp.tools.members.ContentType")
    def test_search_members_with_institution_type_filter(
        self, mock_ct, mock_user, mock_rel_area, mock_rel_topic, mock_rel_inst
    ):
        """Test search_members with institution type filter."""
        from hipeac_mcp.tools.members import search_members

        mock_ct.objects.get.return_value = MagicMock(id=1)

        mock_inst_qs = MagicMock()
        mock_inst_qs.values_list.return_value = [10, 11]
        mock_rel_inst.objects.filter.return_value = mock_inst_qs

        mock_qs = MagicMock()
        mock_qs.distinct.return_value = mock_qs
        mock_qs.filter.return_value = mock_qs
        mock_qs.select_related.return_value = mock_qs
        mock_qs.prefetch_related.return_value = mock_qs
        mock_qs.__getitem__.return_value = []

        mock_user.objects.filter.return_value = mock_qs

        result = search_members(institution_types=["academia"])

        mock_rel_inst.objects.filter.assert_called()
        assert isinstance(result, str)

    @patch("hipeac_mcp.tools.members.RelInstitution")
    @patch("hipeac_mcp.tools.members.RelTopic")
    @patch("hipeac_mcp.tools.members.RelApplicationArea")
    @patch("hipeac_mcp.tools.members.User")
    @patch("hipeac_mcp.tools.members.ContentType")
    def test_search_members_with_membership_type_filter(
        self, mock_ct, mock_user, mock_rel_area, mock_rel_topic, mock_rel_inst
    ):
        """Test search_members with membership type filter."""
        from hipeac_mcp.tools.members import search_members

        mock_ct.objects.get.return_value = MagicMock(id=1)

        # Mock user queryset
        mock_qs = MagicMock()
        mock_qs.distinct.return_value = mock_qs
        mock_qs.filter.return_value = mock_qs
        mock_qs.select_related.return_value = mock_qs
        mock_qs.prefetch_related.return_value = mock_qs
        mock_qs.__getitem__.return_value = []

        mock_user.objects.filter.return_value = mock_qs

        result = search_members(membership_types=["member", "associated_member"])

        assert mock_qs.filter.call_count == 1
        call_args = mock_qs.filter.call_args
        assert "memberships__type__in" in str(call_args)
        assert isinstance(result, str)

    @patch("hipeac_mcp.tools.members.RelInstitution")
    @patch("hipeac_mcp.tools.members.RelTopic")
    @patch("hipeac_mcp.tools.members.RelApplicationArea")
    @patch("hipeac_mcp.tools.members.User")
    @patch("hipeac_mcp.tools.members.ContentType")
    def test_search_members_with_numeric_topic_id(
        self, mock_ct, mock_user, mock_rel_area, mock_rel_topic, mock_rel_inst
    ):
        """Test search_members handles numeric topic IDs."""
        from hipeac_mcp.tools.members import search_members

        mock_ct.objects.get.return_value = MagicMock(id=1)

        mock_topic_qs = MagicMock()
        mock_topic_qs.values_list.return_value = [1]
        mock_rel_topic.objects.filter.return_value = mock_topic_qs

        mock_qs = MagicMock()
        mock_qs.distinct.return_value = mock_qs
        mock_qs.filter.return_value = mock_qs
        mock_qs.select_related.return_value = mock_qs
        mock_qs.prefetch_related.return_value = mock_qs
        mock_qs.__getitem__.return_value = []

        mock_user.objects.filter.return_value = mock_qs

        result = search_members(topics=["42"])

        mock_rel_topic.objects.filter.assert_called()
        assert isinstance(result, str)

    def test_search_members_parameter_types(self):
        """Test search_members accepts correct parameter types."""
        from hipeac_mcp.tools.members import search_members

        sig = inspect.signature(search_members)

        assert "query" in sig.parameters
        assert "topics" in sig.parameters
        assert "application_areas" in sig.parameters
        assert "countries" in sig.parameters
        assert "institution_types" in sig.parameters
        assert "membership_types" in sig.parameters
        assert "limit" in sig.parameters

    def test_find_experts_parameter_types(self):
        """Test find_experts accepts correct parameter types."""
        from hipeac_mcp.tools.members import find_experts

        sig = inspect.signature(find_experts)

        assert "expertise" in sig.parameters
        assert "min_members" in sig.parameters or "country" in sig.parameters


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
