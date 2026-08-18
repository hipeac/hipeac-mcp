"""Tests for job search and retrieval tools."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, Mock, patch


def make_async_iterator(items):
    """Create an async iterator from a list."""

    async def async_gen():
        for item in items:
            yield item

    return async_gen()


def make_job(
    job_id=1,
    title="Research Engineer",
    description="A" * 500,
    location="Leuven",
    country="BE",
    deadline=date(2027, 1, 1),
    positions=1,
    institution_id=10,
    institution_name="KU Leuven",
    institution_country="BE",
    employment_type_id=16,
    employment_type_value="Full-time",
    career_levels=(),
    slug="research-engineer",
):
    """Build a mock Job model instance with select_related/prefetch_related already populated."""
    job = Mock()
    job.id = job_id
    job.title = title
    job.description = description
    job.location = location
    job.country = country
    job.deadline = deadline
    job.positions = positions
    job.slug = slug
    job.get_absolute_url.return_value = f"/jobs/{job_id}/{slug}/"

    job.institution_id = institution_id
    if institution_id is not None:
        job.institution = Mock(name=institution_name, country=institution_country)
        job.institution.name = institution_name
    else:
        job.institution = None

    job.employment_type_id = employment_type_id
    if employment_type_id is not None:
        job.employment_type = Mock(id=employment_type_id, value=employment_type_value)
    else:
        job.employment_type = None

    career_level_mocks = [Mock(id=cl_id, value=cl_value) for cl_id, cl_value in career_levels]
    job.career_levels.all.return_value = career_level_mocks

    return job


class TestTruncate:
    """Tests for the _truncate helper."""

    def test_returns_text_unchanged_when_short_enough(self):
        """Test text shorter than the limit is returned as-is."""
        from hipeac_mcp.tools.jobs import _truncate

        assert _truncate("short text", 100) == "short text"

    def test_truncates_on_word_boundary(self):
        """Test text longer than the limit is cut at the last space."""
        from hipeac_mcp.tools.jobs import _truncate

        result = _truncate("one two three four five", 12)
        assert result == "one two…"
        assert not result.startswith("one two t")

    def test_strips_surrounding_whitespace(self):
        """Test leading/trailing whitespace is stripped before length checks."""
        from hipeac_mcp.tools.jobs import _truncate

        assert _truncate("  padded  ", 100) == "padded"


class TestJobTools:
    """Tests for search_jobs and get_job tool registration and behaviour."""

    def test_search_jobs_callable(self):
        """Test search_jobs tool is callable and registered."""
        from hipeac_mcp.tools.jobs import search_jobs

        assert callable(search_jobs)

    def test_get_job_callable(self):
        """Test get_job tool is callable and registered."""
        from hipeac_mcp.tools.jobs import get_job

        assert callable(get_job)

    @patch("hipeac_mcp.tools.jobs.job_ct_id", return_value=999)
    @patch("hipeac_mcp.tools.jobs.fetch_metadata_items", new_callable=AsyncMock, return_value={})
    @patch("hipeac_mcp.tools.jobs.RelApplicationArea")
    @patch("hipeac_mcp.tools.jobs.RelTopic")
    @patch("hipeac_mcp.tools.jobs.Job")
    @patch("hipeac_mcp.tools.jobs.ensure_connection_async", new_callable=AsyncMock)
    async def test_search_jobs_active_by_default(
        self, mock_conn, mock_job_cls, mock_rel_topic, mock_rel_area, mock_meta, mock_ct_id
    ):
        """Test search_jobs uses Job.objects.active() unless include_expired is passed."""
        from hipeac_mcp.tools.jobs import search_jobs

        mock_qs = MagicMock()
        mock_qs.select_related.return_value = mock_qs
        mock_qs.prefetch_related.return_value = mock_qs
        mock_qs.distinct.return_value = mock_qs
        mock_qs.__getitem__.return_value.__aiter__ = lambda self: make_async_iterator([])
        mock_job_cls.objects.active.return_value = mock_qs

        result = await search_jobs.__wrapped__()

        mock_job_cls.objects.active.assert_called_once()
        mock_job_cls.objects.all.assert_not_called()
        assert result.total == 0

    @patch("hipeac_mcp.tools.jobs.job_ct_id", return_value=999)
    @patch("hipeac_mcp.tools.jobs.fetch_metadata_items", new_callable=AsyncMock, return_value={})
    @patch("hipeac_mcp.tools.jobs.RelApplicationArea")
    @patch("hipeac_mcp.tools.jobs.RelTopic")
    @patch("hipeac_mcp.tools.jobs.Job")
    @patch("hipeac_mcp.tools.jobs.ensure_connection_async", new_callable=AsyncMock)
    async def test_search_jobs_include_expired_uses_all(
        self, mock_conn, mock_job_cls, mock_rel_topic, mock_rel_area, mock_meta, mock_ct_id
    ):
        """Test include_expired=True switches to Job.objects.all()."""
        from hipeac_mcp.tools.jobs import search_jobs

        mock_qs = MagicMock()
        mock_qs.select_related.return_value = mock_qs
        mock_qs.prefetch_related.return_value = mock_qs
        mock_qs.distinct.return_value = mock_qs
        mock_qs.__getitem__.return_value.__aiter__ = lambda self: make_async_iterator([])
        mock_job_cls.objects.all.return_value = mock_qs

        await search_jobs.__wrapped__(include_expired=True)

        mock_job_cls.objects.all.assert_called_once()
        mock_job_cls.objects.active.assert_not_called()

    @patch("hipeac_mcp.tools.jobs.job_ct_id", return_value=999)
    @patch("hipeac_mcp.tools.jobs.fetch_metadata_items", new_callable=AsyncMock, return_value={})
    @patch("hipeac_mcp.tools.jobs.RelApplicationArea")
    @patch("hipeac_mcp.tools.jobs.RelTopic")
    @patch("hipeac_mcp.tools.jobs.Job")
    @patch("hipeac_mcp.tools.jobs.ensure_connection_async", new_callable=AsyncMock)
    async def test_search_jobs_limit_capped_at_50(
        self, mock_conn, mock_job_cls, mock_rel_topic, mock_rel_area, mock_meta, mock_ct_id
    ):
        """Test limit is capped at 50 even if a larger value is requested."""
        from hipeac_mcp.tools.jobs import search_jobs

        captured_slice = {}

        def capture_slice(self, k):
            captured_slice["slice"] = k
            return make_async_iterator([])

        mock_qs = MagicMock()
        mock_qs.select_related.return_value = mock_qs
        mock_qs.prefetch_related.return_value = mock_qs
        mock_qs.distinct.return_value = mock_qs
        mock_qs.__getitem__ = capture_slice
        mock_job_cls.objects.active.return_value = mock_qs

        result = await search_jobs.__wrapped__(limit=500)

        assert captured_slice["slice"].stop == 50
        assert result.limit == 50

    @patch("hipeac_mcp.tools.jobs.job_ct_id", return_value=999)
    @patch("hipeac_mcp.tools.jobs.fetch_metadata_items", new_callable=AsyncMock, return_value={})
    @patch("hipeac_mcp.tools.jobs.RelApplicationArea")
    @patch("hipeac_mcp.tools.jobs.RelTopic")
    @patch("hipeac_mcp.tools.jobs.Job")
    @patch("hipeac_mcp.tools.jobs.ensure_connection_async", new_callable=AsyncMock)
    async def test_search_jobs_returns_formatted_results(
        self, mock_conn, mock_job_cls, mock_rel_topic, mock_rel_area, mock_meta, mock_ct_id
    ):
        """Test search_jobs returns structured summaries with truncated descriptions."""
        from hipeac_mcp.schemas.jobs import JobSearchResponse
        from hipeac_mcp.tools.jobs import search_jobs

        job = make_job(career_levels=[(18, "PhD student")])
        mock_qs = MagicMock()
        mock_qs.select_related.return_value = mock_qs
        mock_qs.prefetch_related.return_value = mock_qs
        mock_qs.distinct.return_value = mock_qs
        mock_qs.__getitem__.return_value.__aiter__ = lambda self: make_async_iterator([job])
        mock_job_cls.objects.active.return_value = mock_qs

        result = await search_jobs.__wrapped__()

        assert isinstance(result, JobSearchResponse)
        assert result.total == 1
        summary = result.jobs[0]
        assert summary.title == "Research Engineer"
        assert summary.institution.name == "KU Leuven"
        assert summary.employment_type.value == "Full-time"
        assert summary.career_levels[0].value == "PhD student"
        assert len(summary.description_preview) <= 301  # + ellipsis
        assert summary.url == "https://www.hipeac.net/jobs/1/research-engineer/"

    @patch("hipeac_mcp.tools.jobs.job_ct_id", return_value=999)
    @patch("hipeac_mcp.tools.jobs.fetch_metadata_items", new_callable=AsyncMock, return_value={})
    @patch("hipeac_mcp.tools.jobs.RelApplicationArea")
    @patch("hipeac_mcp.tools.jobs.RelTopic")
    @patch("hipeac_mcp.tools.jobs.Job")
    @patch("hipeac_mcp.tools.jobs.ensure_connection_async", new_callable=AsyncMock)
    async def test_search_jobs_topic_filter_applied(
        self, mock_conn, mock_job_cls, mock_rel_topic, mock_rel_area, mock_meta, mock_ct_id
    ):
        """Test topic_ids filters via the generic RelTopic relation, scoped to the Job content type."""
        from hipeac_mcp.tools.jobs import search_jobs

        mock_topic_values = MagicMock()
        mock_topic_values.__aiter__ = lambda self: make_async_iterator([1, 2])
        mock_rel_topic.objects.filter.return_value.values_list.return_value = mock_topic_values

        mock_qs = MagicMock()
        mock_qs.select_related.return_value = mock_qs
        mock_qs.prefetch_related.return_value = mock_qs
        mock_qs.distinct.return_value = mock_qs
        mock_qs.filter.return_value = mock_qs
        mock_qs.__getitem__.return_value.__aiter__ = lambda self: make_async_iterator([])
        mock_job_cls.objects.active.return_value = mock_qs

        await search_jobs.__wrapped__(topic_ids=[42])

        mock_rel_topic.objects.filter.assert_called_once()
        call_kwargs = mock_rel_topic.objects.filter.call_args.kwargs
        assert call_kwargs["topic_id__in"] == [42]
        mock_qs.filter.assert_called_once_with(id__in=[1, 2])

    @patch("hipeac_mcp.tools.jobs.job_ct_id", return_value=999)
    @patch("hipeac_mcp.tools.jobs.fetch_metadata_items", new_callable=AsyncMock, return_value={})
    @patch("hipeac_mcp.tools.jobs.RelApplicationArea")
    @patch("hipeac_mcp.tools.jobs.RelTopic")
    @patch("hipeac_mcp.tools.jobs.Job")
    @patch("hipeac_mcp.tools.jobs.ensure_connection_async", new_callable=AsyncMock)
    async def test_get_job_returns_full_description(
        self, mock_conn, mock_job_cls, mock_rel_topic, mock_rel_area, mock_meta, mock_ct_id
    ):
        """Test get_job returns the complete, untruncated description."""
        from hipeac_mcp.schemas.jobs import Job as JobDetail
        from hipeac_mcp.tools.jobs import get_job

        mock_rel_topic.objects.filter.return_value.__aiter__ = lambda self: make_async_iterator([])
        mock_rel_area.objects.filter.return_value.__aiter__ = lambda self: make_async_iterator([])

        job = make_job(description="A" * 5000)
        mock_qs = MagicMock()
        mock_qs.select_related.return_value = mock_qs
        mock_qs.prefetch_related.return_value = mock_qs
        mock_qs.aget = AsyncMock(return_value=job)
        mock_job_cls.objects.select_related.return_value = mock_qs

        result = await get_job.__wrapped__(job_id=1)

        assert isinstance(result, JobDetail)
        assert len(result.description) == 5000
        mock_qs.aget.assert_called_once_with(id=1)
