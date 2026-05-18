"""Vision models for RAG service (read-only)."""

from django.db import models


class Vision(models.Model):
    """HiPEAC Vision document (read-only)."""

    HIDDEN = "hidden"
    DRAFT = "draft"
    PUBLISHED = "published"

    year = models.IntegerField(unique=True)
    status = models.CharField(max_length=20, default=HIDDEN)

    class Meta:
        db_table = "hipeac_vision"
        ordering = ["-year"]
        managed = False

    def __str__(self) -> str:
        return f"Vision {self.year}"

    @property
    def is_draft(self) -> bool:
        """Return True if the vision is a draft."""
        return self.status == self.DRAFT


class VisionSection(models.Model):
    """Vision section like Chapters, Recommendations, etc. (read-only)."""

    vision = models.ForeignKey(Vision, related_name="sections", on_delete=models.DO_NOTHING)
    name = models.CharField(max_length=100)
    position = models.PositiveIntegerField()

    class Meta:
        db_table = "hipeac_vision_section"
        ordering = ["vision", "position"]
        managed = False

    def __str__(self) -> str:
        return f"{self.vision} - {self.name}"


HIPEAC_BASE_URL = "https://www.hipeac.net"


class VisionFile(models.Model):
    """Public file (PDF, EPUB) attached to a Vision (read-only)."""

    content_type_id = models.IntegerField()
    object_id = models.IntegerField()
    file = models.CharField(max_length=500)  # relative storage path, e.g. "public/24/11/file.pdf"
    extra_data = models.JSONField(default=dict)
    is_public = models.BooleanField(default=False)

    class Meta:
        db_table = "hipeac_rel_files"
        managed = False

    def __str__(self) -> str:
        return f"{self.file_type}: {self.file}"

    @property
    def file_type(self) -> str:
        """Return the file type from extra_data (e.g. 'pdf', 'epub').

        :returns: File type string, defaults to 'default' if not set.
        """
        return self.extra_data.get("type", "default")

    @property
    def absolute_url(self) -> str:
        """Return the absolute public URL for the file.

        :returns: Absolute URL combining the base URL and the media path.
        """
        return f"{HIPEAC_BASE_URL}/media/{self.file}"


class VisionArticle(models.Model):
    """Vision article within a section (read-only)."""

    section = models.ForeignKey(VisionSection, related_name="articles", on_delete=models.DO_NOTHING)
    position = models.PositiveIntegerField()
    title = models.CharField(max_length=250)
    slug = models.SlugField(max_length=100)
    content = models.TextField(default="")
    content_tree = models.JSONField(default=dict)
    summary = models.TextField(blank=True)
    ai_summary = models.TextField(blank=True)
    is_aggregate = models.BooleanField(default=False)

    class Meta:
        db_table = "hipeac_vision_article"
        ordering = ["section__vision", "section", "position"]
        managed = False

    def __str__(self) -> str:
        return self.title

    def get_absolute_url(self) -> str:
        """Get article URL.

        :returns: Absolute URL for the article
        """
        return f"/vision/{self.section.vision.year}/{self.slug}/"

    def get_download_url(self) -> str:
        """Get article download URL.

        :returns: Download URL for the article PDF
        """
        return f"/vision/{self.section.vision.year}/{self.slug}/download/"

    def get_summary(self) -> str:
        """Get summary with summary field taking precedence over ai_summary.

        :returns: Summary text (summary if available, otherwise ai_summary)
        """
        return self.summary or self.ai_summary or ""
