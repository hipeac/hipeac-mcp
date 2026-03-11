"""Tests for EventRagService."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hipeac_mcp.services.rags.events.service import EventRagService


@pytest.fixture
def service():
    """Create an EventRagService with mocked FAISS (no real index needed)."""
    with patch.object(EventRagService, "__init__", lambda self, event_id: None):
        svc = EventRagService.__new__(EventRagService)
        svc.event_id = 100
        svc.COLLECTION_NAME = "event_100"
        svc.generator = MagicMock()
        return svc


class TestAggregateChunks:
    """Tests for _aggregate_chunks."""

    def test_overview_chunk_creates_overview_entry(self, service):
        """Overview document type creates an 'overview' key with activity_id=0."""
        chunks = [
            {
                "content": "Event overview text",
                "similarity_score": 0.9,
                "metadata": {
                    "document_type": "overview",
                    "event_name": "HiPEAC 2026",
                    "event_id": 100,
                    "event_year": 2026,
                    "event_url": "/2026/krakow/",
                },
            }
        ]
        result = service._aggregate_chunks(chunks)

        assert "overview" in result
        assert result["overview"]["activity_id"] == 0
        assert result["overview"]["title"] == "HiPEAC 2026 Overview"
        assert result["overview"]["activity_type"] == "Overview"
        assert result["overview"]["similarity_score"] == 0.9

    def test_activity_chunk_creates_activity_entry(self, service):
        """Activity document type creates a keyed entry by activity_id."""
        chunks = [
            {
                "content": "Workshop on RISC-V",
                "similarity_score": 0.85,
                "metadata": {
                    "document_type": "activity",
                    "activity_id": 42,
                    "activity_type": "workshop",
                    "event_name": "HiPEAC 2026",
                    "event_id": 100,
                    "event_year": 2026,
                    "activity_url": "/2026/krakow/#/workshop/42/",
                },
            }
        ]
        result = service._aggregate_chunks(chunks)

        assert "42" in result
        assert result["42"]["activity_id"] == 42
        assert result["42"]["activity_type"] == "Workshop"

    def test_multiple_chunks_same_activity_keeps_best_score(self, service):
        """Multiple chunks for the same activity keep the highest similarity score."""
        chunks = [
            {
                "content": "Chunk 1",
                "similarity_score": 0.7,
                "metadata": {"document_type": "activity", "activity_id": 42, "activity_type": "workshop"},
            },
            {
                "content": "Chunk 2",
                "similarity_score": 0.9,
                "metadata": {"document_type": "activity", "activity_id": 42, "activity_type": "workshop"},
            },
        ]
        result = service._aggregate_chunks(chunks)

        assert result["42"]["similarity_score"] == 0.9
        assert len(result["42"]["chunks"]) == 2

    def test_multiple_overview_chunks_keep_best_score(self, service):
        """Multiple overview chunks keep the highest similarity score."""
        chunks = [
            {
                "content": "Overview part 1",
                "similarity_score": 0.6,
                "metadata": {"document_type": "overview", "event_name": "Test"},
            },
            {
                "content": "Overview part 2",
                "similarity_score": 0.8,
                "metadata": {"document_type": "overview", "event_name": "Test"},
            },
        ]
        result = service._aggregate_chunks(chunks)

        assert result["overview"]["similarity_score"] == 0.8
        assert len(result["overview"]["chunks"]) == 2

    def test_mixed_overview_and_activity_chunks(self, service):
        """Overview and activity chunks are aggregated separately."""
        chunks = [
            {
                "content": "Event info",
                "similarity_score": 0.9,
                "metadata": {"document_type": "overview", "event_name": "Test"},
            },
            {
                "content": "Workshop info",
                "similarity_score": 0.8,
                "metadata": {"document_type": "activity", "activity_id": 10, "activity_type": "workshop"},
            },
        ]
        result = service._aggregate_chunks(chunks)

        assert len(result) == 2
        assert "overview" in result
        assert "10" in result

    def test_empty_results(self, service):
        """Empty input returns empty dict."""
        assert service._aggregate_chunks([]) == {}


class TestEnrichFromDatabase:
    """Tests for _enrich_from_database."""

    @staticmethod
    def _make_activity(activity_id, title, summary="", room_id=None):
        """Create a mock Activity."""
        activity = MagicMock()
        activity.id = activity_id
        activity.title = title
        activity.ai_summary = summary
        activity.summary = ""
        activity.room_id = room_id
        return activity

    @staticmethod
    def _make_room(room_id, name, place_name):
        """Create a mock Room with a related place."""
        room = MagicMock()
        room.id = room_id
        room.name = name
        room.place = MagicMock()
        room.place.name = place_name
        return room

    @staticmethod
    def _make_activity_user(object_id, user_id, position=0, extra_data=None):
        """Create a mock ActivityUser relation."""
        rel = MagicMock()
        rel.object_id = object_id
        rel.user_id = user_id
        rel.position = position
        rel.extra_data = extra_data
        return rel

    @staticmethod
    def _make_user(user_id, name):
        """Create a mock EventUser."""
        user = MagicMock()
        user.id = user_id
        user.name = name
        return user

    @staticmethod
    def _make_institution_rel(object_id, institution_id):
        """Create a mock RelatedInstitution."""
        rel = MagicMock()
        rel.object_id = object_id
        rel.institution_id = institution_id
        rel.position = 0
        return rel

    @staticmethod
    def _make_institution(inst_id, name):
        """Create a mock EventInstitution."""
        inst = MagicMock()
        inst.id = inst_id
        inst.__str__ = lambda self: name
        return inst

    @staticmethod
    def _make_async_iterator(items):
        """Create an async iterable from a list of items."""

        async def _iter(self):
            for item in items:
                yield item

        mock_qs = MagicMock()
        mock_qs.__aiter__ = _iter
        return mock_qs

    @patch("hipeac_mcp.services.rags.events.service.ensure_connection_async", new_callable=AsyncMock)
    @patch("hipeac_mcp.services.rags.events.service.activity_ct_id", return_value=39)
    @patch("hipeac_mcp.services.rags.events.service.user_ct_id", return_value=25)
    async def test_enriches_title_and_summary(self, mock_user_ct, mock_act_ct, mock_conn):
        """Activities are enriched with title and summary from the database."""
        service = EventRagService.__new__(EventRagService)
        service.event_id = 100

        activity = self._make_activity(42, "RISC-V Workshop", summary="An AI summary")
        aggregated = {"42": {"activity_id": 42, "title": "", "summary": "", "chunks": []}}

        with (
            patch("hipeac_mcp.services.rags.events.service.Activity") as mock_activity_cls,
            patch("hipeac_mcp.services.rags.events.service.Room") as mock_room_cls,
            patch("hipeac_mcp.services.rags.events.service.ActivityUser") as mock_au_cls,
        ):
            mock_activity_cls.objects.filter.return_value = self._make_async_iterator([activity])
            mock_room_cls.objects.select_related.return_value.filter.return_value = self._make_async_iterator([])
            mock_au_cls.objects.filter.return_value.order_by.return_value = self._make_async_iterator([])

            await service._enrich_from_database(aggregated)

        assert aggregated["42"]["title"] == "RISC-V Workshop"
        assert aggregated["42"]["summary"] == "An AI summary"

    @patch("hipeac_mcp.services.rags.events.service.ensure_connection_async", new_callable=AsyncMock)
    @patch("hipeac_mcp.services.rags.events.service.activity_ct_id", return_value=39)
    @patch("hipeac_mcp.services.rags.events.service.user_ct_id", return_value=25)
    async def test_enriches_room_info(self, mock_user_ct, mock_act_ct, mock_conn):
        """Activities with rooms are enriched with room and place name."""
        service = EventRagService.__new__(EventRagService)
        service.event_id = 100

        activity = self._make_activity(42, "Workshop", room_id=5)
        room = self._make_room(5, "S2 (L0)", "ICE Kraków")

        aggregated = {"42": {"activity_id": 42, "title": "", "summary": "", "chunks": []}}

        with (
            patch("hipeac_mcp.services.rags.events.service.Activity") as mock_activity_cls,
            patch("hipeac_mcp.services.rags.events.service.Room") as mock_room_cls,
            patch("hipeac_mcp.services.rags.events.service.ActivityUser") as mock_au_cls,
        ):
            mock_activity_cls.objects.filter.return_value = self._make_async_iterator([activity])
            mock_room_cls.objects.select_related.return_value.filter.return_value = self._make_async_iterator([room])
            mock_au_cls.objects.filter.return_value.order_by.return_value = self._make_async_iterator([])

            await service._enrich_from_database(aggregated)

        assert aggregated["42"]["room"] == "S2 (L0) — ICE Kraków"

    @patch("hipeac_mcp.services.rags.events.service.ensure_connection_async", new_callable=AsyncMock)
    @patch("hipeac_mcp.services.rags.events.service.activity_ct_id", return_value=39)
    @patch("hipeac_mcp.services.rags.events.service.user_ct_id", return_value=25)
    async def test_enriches_people_with_roles(self, mock_user_ct, mock_act_ct, mock_conn):
        """People are assigned correct roles based on extra_data flags."""
        service = EventRagService.__new__(EventRagService)
        service.event_id = 100

        activity = self._make_activity(42, "Workshop")
        au_speaker = self._make_activity_user(42, 1, extra_data={"is_speaker": True})
        au_organizer = self._make_activity_user(42, 2, extra_data={"is_organizer": True})
        au_main = self._make_activity_user(42, 3, extra_data={"is_main_speaker": True})
        user1 = self._make_user(1, "Alice")
        user2 = self._make_user(2, "Bob")
        user3 = self._make_user(3, "Charlie")
        inst_rel = self._make_institution_rel(1, 10)
        inst = self._make_institution(10, "MIT")

        aggregated = {"42": {"activity_id": 42, "title": "", "summary": "", "chunks": []}}

        with (
            patch("hipeac_mcp.services.rags.events.service.Activity") as mock_activity_cls,
            patch("hipeac_mcp.services.rags.events.service.Room") as mock_room_cls,
            patch("hipeac_mcp.services.rags.events.service.ActivityUser") as mock_au_cls,
            patch("hipeac_mcp.services.rags.events.service.EventUser") as mock_user_cls,
            patch("hipeac_mcp.services.rags.events.service.RelatedInstitution") as mock_ri_cls,
            patch("hipeac_mcp.services.rags.events.service.EventInstitution") as mock_inst_cls,
        ):
            mock_activity_cls.objects.filter.return_value = self._make_async_iterator([activity])
            mock_room_cls.objects.select_related.return_value.filter.return_value = self._make_async_iterator([])
            mock_au_cls.objects.filter.return_value.order_by.return_value = self._make_async_iterator(
                [au_speaker, au_organizer, au_main]
            )
            mock_user_cls.objects.filter.return_value = self._make_async_iterator([user1, user2, user3])
            mock_ri_cls.objects.filter.return_value = self._make_async_iterator([inst_rel])
            mock_inst_cls.objects.filter.return_value = self._make_async_iterator([inst])

            await service._enrich_from_database(aggregated)

        people = aggregated["42"]["people"]
        roles = {p["name"]: p["role"] for p in people}
        assert roles["Alice"] == "speaker"
        assert roles["Bob"] == "organizer"
        assert roles["Charlie"] == "main_speaker"

    @patch("hipeac_mcp.services.rags.events.service.ensure_connection_async", new_callable=AsyncMock)
    @patch("hipeac_mcp.services.rags.events.service.activity_ct_id", return_value=39)
    @patch("hipeac_mcp.services.rags.events.service.user_ct_id", return_value=25)
    async def test_acaces_infers_teacher_role(self, mock_user_ct, mock_act_ct, mock_conn):
        """ACACES activities assign 'teacher' role when no explicit role flag is set."""
        service = EventRagService.__new__(EventRagService)
        service.event_id = 100

        activity = self._make_activity(42, "Advanced ML Course")
        au_teacher = self._make_activity_user(42, 1, extra_data={})
        user1 = self._make_user(1, "Prof. Smith")

        aggregated = {
            "overview": {
                "activity_id": 0,
                "title": "ACACES 2025 Overview",
                "event_name": "ACACES 2025",
                "chunks": [],
            },
            "42": {"activity_id": 42, "title": "", "summary": "", "chunks": []},
        }

        with (
            patch("hipeac_mcp.services.rags.events.service.Activity") as mock_activity_cls,
            patch("hipeac_mcp.services.rags.events.service.Room") as mock_room_cls,
            patch("hipeac_mcp.services.rags.events.service.ActivityUser") as mock_au_cls,
            patch("hipeac_mcp.services.rags.events.service.EventUser") as mock_user_cls,
            patch("hipeac_mcp.services.rags.events.service.RelatedInstitution") as mock_ri_cls,
            patch("hipeac_mcp.services.rags.events.service.EventInstitution") as mock_inst_cls,
        ):
            mock_activity_cls.objects.filter.return_value = self._make_async_iterator([activity])
            mock_room_cls.objects.select_related.return_value.filter.return_value = self._make_async_iterator([])
            mock_au_cls.objects.filter.return_value.order_by.return_value = self._make_async_iterator([au_teacher])
            mock_user_cls.objects.filter.return_value = self._make_async_iterator([user1])
            mock_ri_cls.objects.filter.return_value = self._make_async_iterator([])
            mock_inst_cls.objects.filter.return_value = self._make_async_iterator([])

            await service._enrich_from_database(aggregated)

        people = aggregated["42"]["people"]
        assert len(people) == 1
        assert people[0]["role"] == "teacher"

    @patch("hipeac_mcp.services.rags.events.service.ensure_connection_async", new_callable=AsyncMock)
    async def test_skips_enrichment_when_no_activity_ids(self, mock_conn):
        """Enrichment is skipped when there are no activity IDs (overview only)."""
        service = EventRagService.__new__(EventRagService)
        service.event_id = 100

        aggregated = {"overview": {"activity_id": 0, "title": "Overview", "chunks": []}}

        await service._enrich_from_database(aggregated)

        # No crash, overview is left unchanged
        assert aggregated["overview"]["title"] == "Overview"

    @patch("hipeac_mcp.services.rags.events.service.ensure_connection_async", new_callable=AsyncMock)
    @patch("hipeac_mcp.services.rags.events.service.activity_ct_id", return_value=39)
    @patch("hipeac_mcp.services.rags.events.service.user_ct_id", return_value=25)
    async def test_institution_resolved_for_people(self, mock_user_ct, mock_act_ct, mock_conn):
        """Institution name is resolved from RelatedInstitution → EventInstitution."""
        service = EventRagService.__new__(EventRagService)
        service.event_id = 100

        activity = self._make_activity(42, "Talk")
        au = self._make_activity_user(42, 1, extra_data={"is_speaker": True})
        user = self._make_user(1, "Dr. Jones")
        inst_rel = self._make_institution_rel(1, 20)
        inst = self._make_institution(20, "ETH Zurich")

        aggregated = {"42": {"activity_id": 42, "title": "", "summary": "", "chunks": []}}

        with (
            patch("hipeac_mcp.services.rags.events.service.Activity") as mock_activity_cls,
            patch("hipeac_mcp.services.rags.events.service.Room") as mock_room_cls,
            patch("hipeac_mcp.services.rags.events.service.ActivityUser") as mock_au_cls,
            patch("hipeac_mcp.services.rags.events.service.EventUser") as mock_user_cls,
            patch("hipeac_mcp.services.rags.events.service.RelatedInstitution") as mock_ri_cls,
            patch("hipeac_mcp.services.rags.events.service.EventInstitution") as mock_inst_cls,
        ):
            mock_activity_cls.objects.filter.return_value = self._make_async_iterator([activity])
            mock_room_cls.objects.select_related.return_value.filter.return_value = self._make_async_iterator([])
            mock_au_cls.objects.filter.return_value.order_by.return_value = self._make_async_iterator([au])
            mock_user_cls.objects.filter.return_value = self._make_async_iterator([user])
            mock_ri_cls.objects.filter.return_value = self._make_async_iterator([inst_rel])
            mock_inst_cls.objects.filter.return_value = self._make_async_iterator([inst])

            await service._enrich_from_database(aggregated)

        people = aggregated["42"]["people"]
        assert people[0]["institution"] == "ETH Zurich"


class TestSearchActivities:
    """Tests for search_activities end-to-end."""

    @patch("hipeac_mcp.services.rags.events.service.EventRagService.search", new_callable=AsyncMock)
    async def test_returns_structured_response(self, mock_search):
        """search_activities wraps search results into an EventSearchResponse."""
        service = EventRagService.__new__(EventRagService)
        service.event_id = 100

        mock_search.return_value = [
            {
                "activity_id": 42,
                "title": "RISC-V Workshop",
                "activity_type": "Workshop",
                "room": "S2 — ICE",
                "summary": "A workshop",
                "similarity_score": 0.9,
                "content_preview": "Preview text",
                "people": [{"id": 1, "name": "Alice", "institution": "MIT", "role": "speaker"}],
                "event_name": "HiPEAC 2026",
                "event_id": 100,
                "event_year": 2026,
                "url": "/2026/krakow/#/workshop/42/",
            }
        ]

        result = await service.search_activities("RISC-V")

        assert result.query == "RISC-V"
        assert result.event_id == 100
        assert result.total_results == 1
        assert result.results[0].title == "RISC-V Workshop"
        assert result.results[0].room == "S2 — ICE"
        assert result.results[0].people[0].name == "Alice"
        assert result.results[0].url == "https://www.hipeac.net/2026/krakow/#/workshop/42/"

    @patch("hipeac_mcp.services.rags.events.service.EventRagService.search", new_callable=AsyncMock)
    async def test_limit_capped_at_10(self, mock_search):
        """Limit is capped at 10 and forwarded to search."""
        service = EventRagService.__new__(EventRagService)
        service.event_id = 100
        mock_search.return_value = []

        await service.search_activities("test", limit=100)

        mock_search.assert_called_once_with("test", 10)

    @patch("hipeac_mcp.services.rags.events.service.EventRagService.search", new_callable=AsyncMock)
    async def test_empty_results(self, mock_search):
        """Empty search results return an empty EventSearchResponse."""
        service = EventRagService.__new__(EventRagService)
        service.event_id = 100
        mock_search.return_value = []

        result = await service.search_activities("nonexistent")

        assert result.total_results == 0
        assert result.results == []
        assert result.event_name == ""


class TestSearch:
    """Tests for the search method (aggregation + enrichment + formatting)."""

    @patch.object(EventRagService, "_enrich_from_database", new_callable=AsyncMock)
    async def test_aggregation_and_content_preview(self, mock_enrich):
        """Search aggregates chunks and creates content previews."""
        service = EventRagService.__new__(EventRagService)
        service.event_id = 100

        # Mock the parent search to return raw chunks
        base_results = [
            {
                "content": "This is a detailed description of the RISC-V workshop that covers many topics.",
                "similarity_score": 0.9,
                "metadata": {
                    "document_type": "activity",
                    "activity_id": 42,
                    "activity_type": "workshop",
                    "event_name": "HiPEAC 2026",
                    "event_id": 100,
                    "event_year": 2026,
                    "activity_url": "/2026/krakow/#/workshop/42/",
                },
            }
        ]

        with patch.object(service, "_multi_query_search", new_callable=AsyncMock) as mock_base:
            mock_base.return_value = base_results
            results = await service.search("RISC-V", limit=5)

        assert len(results) == 1
        assert results[0]["activity_id"] == 42
        assert "content_preview" in results[0]
        assert "chunks" not in results[0]

    @patch.object(EventRagService, "_enrich_from_database", new_callable=AsyncMock)
    async def test_results_sorted_by_score(self, mock_enrich):
        """Results are sorted by similarity_score descending."""
        service = EventRagService.__new__(EventRagService)
        service.event_id = 100

        base_results = [
            {
                "content": "Low score chunk",
                "similarity_score": 0.5,
                "metadata": {"document_type": "activity", "activity_id": 10, "activity_type": "workshop"},
            },
            {
                "content": "High score chunk",
                "similarity_score": 0.9,
                "metadata": {"document_type": "activity", "activity_id": 20, "activity_type": "keynote"},
            },
        ]

        with patch.object(service, "_multi_query_search", new_callable=AsyncMock) as mock_base:
            mock_base.return_value = base_results
            results = await service.search("test", limit=5)

        assert results[0]["similarity_score"] > results[1]["similarity_score"]
        assert results[0]["activity_id"] == 20

    async def test_search_error_returns_empty(self):
        """Search errors are caught and return an empty list."""
        service = EventRagService.__new__(EventRagService)
        service.event_id = 100

        with patch.object(service, "_multi_query_search", new_callable=AsyncMock, side_effect=Exception("FAISS")):
            results = await service.search("test")

        assert results == []

    @patch.object(EventRagService, "_enrich_from_database", new_callable=AsyncMock)
    async def test_search_requests_triple_chunks(self, mock_enrich):
        """Search requests 3x the limit from FAISS for better aggregation coverage."""
        service = EventRagService.__new__(EventRagService)
        service.event_id = 100

        with patch.object(service, "_multi_query_search", new_callable=AsyncMock) as mock_base:
            mock_base.return_value = []
            await service.search("test", limit=5)

        mock_base.assert_called_once_with(["test"], 15)


class TestEventRagServiceInit:
    """Tests for EventRagService.__init__."""

    def test_sets_event_id_and_collection_name(self):
        """__init__ stores event_id and derives the COLLECTION_NAME."""
        with (
            patch.object(EventRagService, "_load_or_create_index"),
            patch("hipeac_mcp.services.rags.events.service.EventDocumentGenerator"),
            patch("hipeac_mcp.services.rags.base.get_embedding_provider"),
            patch("hipeac_mcp.services.rags.base.settings") as mock_settings,
        ):
            mock_settings.FAISS_INDEX_PATH = "/var/tmp/test_rag"
            svc = EventRagService(event_id=42)

        assert svc.event_id == 42
        assert svc.COLLECTION_NAME == "event_42"


class TestEnrichFromDatabasePeopleBranches:
    """Tests for uncovered branches in the people-enrichment loop."""

    @staticmethod
    def _make_async_iterator(items):
        """Create an async iterable from a list of items."""

        async def _iter(self):
            for item in items:
                yield item

        mock_qs = MagicMock()
        mock_qs.__aiter__ = _iter
        return mock_qs

    @patch("hipeac_mcp.services.rags.events.service.ensure_connection_async", new_callable=AsyncMock)
    @patch("hipeac_mcp.services.rags.events.service.activity_ct_id", return_value=39)
    @patch("hipeac_mcp.services.rags.events.service.user_ct_id", return_value=25)
    async def test_skips_user_not_in_users_map(self, mock_user_ct, mock_act_ct, mock_conn):
        """A user referenced in ActivityUser but not fetched from DB is skipped."""
        service = EventRagService.__new__(EventRagService)
        service.event_id = 100

        activity = MagicMock()
        activity.id = 42
        activity.title = "Talk"
        activity.slug = "talk"
        activity.summary = ""
        activity.ai_summary = ""
        activity.room_id = None

        # au references user_id=99, but we return no users from the DB query
        au = MagicMock()
        au.object_id = 42  # must match activity_id so the rel is looked up
        au.user_id = 99
        au.extra_data = {"is_speaker": True}

        aggregated = {"42": {"activity_id": 42, "title": "", "summary": "", "chunks": []}}

        with (
            patch("hipeac_mcp.services.rags.events.service.Activity") as mock_activity_cls,
            patch("hipeac_mcp.services.rags.events.service.Room") as mock_room_cls,
            patch("hipeac_mcp.services.rags.events.service.ActivityUser") as mock_au_cls,
            patch("hipeac_mcp.services.rags.events.service.EventUser") as mock_user_cls,
            patch("hipeac_mcp.services.rags.events.service.RelatedInstitution") as mock_ri_cls,
            patch("hipeac_mcp.services.rags.events.service.EventInstitution") as mock_inst_cls,
        ):
            mock_activity_cls.objects.filter.return_value = self._make_async_iterator([activity])
            mock_room_cls.objects.select_related.return_value.filter.return_value = self._make_async_iterator([])
            mock_au_cls.objects.filter.return_value.order_by.return_value = self._make_async_iterator([au])
            mock_user_cls.objects.filter.return_value = self._make_async_iterator([])  # no users returned
            mock_ri_cls.objects.filter.return_value = self._make_async_iterator([])
            mock_inst_cls.objects.filter.return_value = self._make_async_iterator([])

            await service._enrich_from_database(aggregated)

        assert aggregated["42"]["people"] == []

    @patch("hipeac_mcp.services.rags.events.service.ensure_connection_async", new_callable=AsyncMock)
    @patch("hipeac_mcp.services.rags.events.service.activity_ct_id", return_value=39)
    @patch("hipeac_mcp.services.rags.events.service.user_ct_id", return_value=25)
    async def test_skips_user_with_no_recognized_role(self, mock_user_ct, mock_act_ct, mock_conn):
        """Non-ACACES activity user with no role flags is silently skipped."""
        service = EventRagService.__new__(EventRagService)
        service.event_id = 100

        activity = MagicMock()
        activity.id = 42
        activity.title = "Workshop"
        activity.slug = "workshop"
        activity.summary = ""
        activity.ai_summary = ""
        activity.room_id = None

        # No is_speaker / is_organizer / is_main_speaker; event is NOT ACACES
        au = MagicMock()
        au.object_id = 42  # must match activity_id
        au.user_id = 1
        au.extra_data = {}

        user = MagicMock()
        user.id = 1
        user.name = "Attendee"

        aggregated = {
            "overview": {"activity_id": 0, "event_name": "HiPEAC 2026", "chunks": []},
            "42": {"activity_id": 42, "title": "", "summary": "", "chunks": []},
        }

        with (
            patch("hipeac_mcp.services.rags.events.service.Activity") as mock_activity_cls,
            patch("hipeac_mcp.services.rags.events.service.Room") as mock_room_cls,
            patch("hipeac_mcp.services.rags.events.service.ActivityUser") as mock_au_cls,
            patch("hipeac_mcp.services.rags.events.service.EventUser") as mock_user_cls,
            patch("hipeac_mcp.services.rags.events.service.RelatedInstitution") as mock_ri_cls,
            patch("hipeac_mcp.services.rags.events.service.EventInstitution") as mock_inst_cls,
        ):
            mock_activity_cls.objects.filter.return_value = self._make_async_iterator([activity])
            mock_room_cls.objects.select_related.return_value.filter.return_value = self._make_async_iterator([])
            mock_au_cls.objects.filter.return_value.order_by.return_value = self._make_async_iterator([au])
            mock_user_cls.objects.filter.return_value = self._make_async_iterator([user])
            mock_ri_cls.objects.filter.return_value = self._make_async_iterator([])
            mock_inst_cls.objects.filter.return_value = self._make_async_iterator([])

            await service._enrich_from_database(aggregated)

        assert aggregated["42"]["people"] == []

    @patch("hipeac_mcp.services.rags.events.service.ensure_connection_async", new_callable=AsyncMock)
    async def test_silently_ignores_db_errors(self, mock_conn):
        """A database error during enrichment is caught and logged without raising."""
        mock_conn.side_effect = RuntimeError("connection lost")

        service = EventRagService.__new__(EventRagService)
        service.event_id = 100
        aggregated = {"42": {"activity_id": 42, "title": "", "chunks": []}}

        await service._enrich_from_database(aggregated)

        # Original aggregated data is unchanged
        assert aggregated["42"]["activity_id"] == 42

    """Tests for EventRagService.index_event."""

    @patch("hipeac_mcp.services.rags.events.service.ensure_connection_async", new_callable=AsyncMock)
    async def test_indexes_event_successfully(self, mock_conn):
        """index_event returns True when chunks are generated and upserted."""
        service = EventRagService.__new__(EventRagService)
        service.generator = MagicMock()
        service.generator.generate_chunks = AsyncMock(
            return_value=[{"id": "e100_a1", "content": "Workshop content", "metadata": {"activity_id": 1}}]
        )
        service.generate_embedding = AsyncMock(return_value=[0.1] * 128)
        service.upsert_documents = MagicMock(return_value=True)

        event = MagicMock()
        event.id = 100
        event.name = "HiPEAC 2026"

        result = await service.index_event(event)

        assert result is True
        service.upsert_documents.assert_called_once()

    @patch("hipeac_mcp.services.rags.events.service.ensure_connection_async", new_callable=AsyncMock)
    async def test_returns_false_when_no_chunks(self, mock_conn):
        """index_event returns False and logs a warning when no chunks are produced."""
        service = EventRagService.__new__(EventRagService)
        service.generator = MagicMock()
        service.generator.generate_chunks = AsyncMock(return_value=[])

        event = MagicMock()
        event.id = 100

        result = await service.index_event(event)

        assert result is False

    @patch("hipeac_mcp.services.rags.events.service.ensure_connection_async", new_callable=AsyncMock)
    async def test_returns_false_on_exception(self, mock_conn):
        """index_event catches exceptions and returns False."""
        service = EventRagService.__new__(EventRagService)
        service.generator = MagicMock()
        service.generator.generate_chunks = AsyncMock(side_effect=RuntimeError("DB error"))

        event = MagicMock()
        event.id = 100

        result = await service.index_event(event)

        assert result is False
