"""User model for HiPEAC MCP server."""

from django.db import models


class User(models.Model):
    """User model (read-only)."""

    username = models.CharField(max_length=150, unique=True)
    email = models.EmailField()
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)

    class Meta:
        db_table = "hipeac_user"
        managed = False
