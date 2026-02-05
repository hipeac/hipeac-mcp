"""Vision models for RAG service (read-only)."""

from django.db import models


class Vision(models.Model):
    """HiPEAC Vision document (read-only)."""

    year = models.IntegerField(unique=True)

    class Meta:
        db_table = "hipeac_vision"
        ordering = ["-year"]
        managed = False

    def __str__(self) -> str:
        return f"Vision {self.year}"


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
