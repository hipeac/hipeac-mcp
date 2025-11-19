"""Institution models for HiPEAC MCP server."""

from django.db import models


class Institution(models.Model):
    """Institution model."""

    name = models.CharField(max_length=250)
    country = models.CharField(max_length=3)
    type = models.ForeignKey("hipeac_mcp.Metadata", null=True, on_delete=models.SET_NULL)

    class Meta:
        db_table = "hipeac_institution"
        managed = False

    def __str__(self) -> str:
        return self.name


class RelInstitution(models.Model):
    """Generic relation for User-Institution relationships."""

    content_type = models.ForeignKey("contenttypes.ContentType", on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    institution = models.ForeignKey(Institution, related_name="user_institutions", on_delete=models.CASCADE)

    class Meta:
        db_table = "hipeac_rel_institutions"
        managed = False
