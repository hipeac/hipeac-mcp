"""Metadata models for HiPEAC MCP server."""

from django.db import models


class Metadata(models.Model):
    """Metadata model for topics, application areas, institution types, etc."""

    APPLICATION_AREA = "application_area"
    TOPIC = "topic"
    INSTITUTION_TYPE = "institution_type"

    type = models.CharField(max_length=32)
    value = models.CharField(max_length=64)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "hipeac_metadata"
        managed = False
        ordering = ["type", "position", "value"]

    def __str__(self) -> str:
        return self.value


class RelTopic(models.Model):
    """Generic relation for User-Topic relationships."""

    content_type = models.ForeignKey("contenttypes.ContentType", on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    topic = models.ForeignKey(Metadata, related_name="user_topics", on_delete=models.CASCADE)

    class Meta:
        db_table = "hipeac_rel_topics"
        managed = False


class RelApplicationArea(models.Model):
    """Generic relation for User-ApplicationArea relationships."""

    content_type = models.ForeignKey("contenttypes.ContentType", on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    application_area = models.ForeignKey(Metadata, related_name="user_areas", on_delete=models.CASCADE)

    class Meta:
        db_table = "hipeac_rel_application_areas"
        managed = False
