"""Job model for HiPEAC MCP server (read-only).

Maps to ``hipeac_job`` in the production database. Topics and application
areas are not FKs on this table — they use the same generic
``hipeac_rel_topics`` / ``hipeac_rel_application_areas`` relation tables as
other models (see ``hipeac_mcp.models.metadata``), keyed by this model's
content type.
"""

from django.db import models
from django.utils import timezone

from hipeac_mcp.db import get_content_type_id


def job_ct_id() -> int:
    """Return the ``content_type_id`` for Job."""
    return get_content_type_id("hipeac", "job")


class JobQuerySet(models.QuerySet["Job"]):
    """Custom queryset for Job model with chainable filtering methods."""

    def active(self):
        """Filter for jobs whose application deadline has not passed.

        :returns: QuerySet of active job postings.
        """
        return self.filter(deadline__gte=timezone.now().date())


class Job(models.Model):
    """HiPEAC job posting — read-only."""

    institution = models.ForeignKey(
        "hipeac_mcp.Institution", null=True, on_delete=models.SET_NULL, related_name="jobs"
    )
    employment_type = models.ForeignKey(
        "hipeac_mcp.Metadata", null=True, on_delete=models.SET_NULL, related_name="employment_jobs"
    )
    career_levels = models.ManyToManyField("hipeac_mcp.Metadata", related_name="career_jobs")

    title = models.CharField(max_length=250)
    slug = models.SlugField(max_length=255, blank=True)
    description = models.TextField()
    location = models.CharField(max_length=250, blank=True, default="")
    country = models.CharField(max_length=3, null=True, blank=True)
    email = models.EmailField(blank=True, default="")

    deadline = models.DateField(null=True)
    positions = models.PositiveSmallIntegerField(default=1, null=True)
    created_at = models.DateTimeField()

    objects = JobQuerySet.as_manager()

    class Meta:
        db_table = "hipeac_job"
        managed = False
        ordering = ["-id"]

    def __str__(self) -> str:
        return self.title

    def get_absolute_url(self) -> str:
        """Build the public URL for this job posting.

        :returns: Absolute path (no host) matching the ``job`` URL pattern.
        """
        return f"/jobs/{self.pk}/{self.slug}/"
