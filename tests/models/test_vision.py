"""Tests for Vision model properties and string representations."""

from hipeac_mcp.models.vision import HIPEAC_BASE_URL, Vision, VisionArticle, VisionFile, VisionSection


def _make_vision(year: int = 2025) -> Vision:
    """Build an unsaved Vision instance without database access."""
    return Vision(year=year)


def _make_section(vision: Vision, name: str = "Chapters") -> VisionSection:
    """Build an unsaved VisionSection instance without database access."""
    return VisionSection(vision=vision, name=name, position=1)


def _make_article(section: VisionSection, title: str = "AI Trends", slug: str = "ai-trends") -> VisionArticle:
    """Build an unsaved VisionArticle instance without database access."""
    return VisionArticle(section=section, title=title, slug=slug, summary="", ai_summary="")


def _make_file(file_path: str = "public/2025/report.pdf", extra: dict | None = None) -> VisionFile:
    """Build an unsaved VisionFile instance without database access."""
    return VisionFile(file=file_path, extra_data=extra or {})


class TestVisionStr:
    """Tests for Vision.__str__."""

    def test_includes_year(self):
        """__str__ returns 'Vision YYYY'."""
        assert str(_make_vision(2025)) == "Vision 2025"

    def test_different_year(self):
        """Year is reflected dynamically."""
        assert str(_make_vision(2024)) == "Vision 2024"


class TestVisionSectionStr:
    """Tests for VisionSection.__str__."""

    def test_includes_vision_and_name(self):
        """__str__ returns 'Vision YYYY - SectionName'."""
        section = _make_section(_make_vision(2025), "Recommendations")
        assert str(section) == "Vision 2025 - Recommendations"


class TestVisionFileProperties:
    """Tests for VisionFile properties and __str__."""

    def test_str_uses_type_and_path(self):
        """__str__ combines file_type and file path."""
        f = _make_file(extra={"type": "pdf"})
        assert str(f) == "pdf: public/2025/report.pdf"

    def test_file_type_from_extra_data(self):
        """file_type reads the 'type' key from extra_data."""
        assert _make_file(extra={"type": "epub"}).file_type == "epub"

    def test_file_type_defaults_to_default(self):
        """file_type falls back to 'default' when 'type' key is absent."""
        assert _make_file(extra={}).file_type == "default"

    def test_absolute_url_combines_base_and_media_path(self):
        """absolute_url prefixes the HIPEAC base URL and /media/."""
        f = _make_file("public/24/11/file.pdf")
        assert f.absolute_url == f"{HIPEAC_BASE_URL}/media/public/24/11/file.pdf"


class TestVisionArticleMethods:
    """Tests for VisionArticle model methods."""

    def test_str_returns_title(self):
        """__str__ returns the article title."""
        article = _make_article(_make_section(_make_vision(2025)), title="New Hardware")
        assert str(article) == "New Hardware"

    def test_get_absolute_url(self):
        """get_absolute_url builds the correct path."""
        article = _make_article(_make_section(_make_vision(2025)), slug="new-hardware")
        assert article.get_absolute_url() == "/vision/2025/new-hardware/"

    def test_get_download_url(self):
        """get_download_url appends /download/ to the article path."""
        article = _make_article(_make_section(_make_vision(2025)), slug="new-hardware")
        assert article.get_download_url() == "/vision/2025/new-hardware/download/"

    def test_get_summary_prefers_summary_over_ai_summary(self):
        """Summary field takes precedence over ai_summary."""
        article = _make_article(_make_section(_make_vision()))
        article.summary = "Human summary"
        article.ai_summary = "AI summary"
        assert article.get_summary() == "Human summary"

    def test_get_summary_falls_back_to_ai_summary(self):
        """Returns ai_summary when summary is empty."""
        article = _make_article(_make_section(_make_vision()))
        article.summary = ""
        article.ai_summary = "AI summary"
        assert article.get_summary() == "AI summary"

    def test_get_summary_returns_empty_when_both_absent(self):
        """Returns empty string when neither summary field is populated."""
        article = _make_article(_make_section(_make_vision()))
        article.summary = ""
        article.ai_summary = ""
        assert article.get_summary() == ""
