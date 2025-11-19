"""Membership model for HiPEAC MCP server."""

from django.db import models


class MembershipQuerySet(models.QuerySet["Membership"]):
    """Custom queryset for Membership model with chainable filtering methods."""

    def active(self):
        """Filter for active memberships (no end date).

        :returns: QuerySet of active memberships.
        """
        return self.filter(end_date__isnull=True)

    def ended(self):
        """Filter for ended memberships (with end date).

        :returns: QuerySet of ended memberships.
        """
        return self.filter(end_date__isnull=False)


class Membership(models.Model):
    """Membership model for tracking member status."""

    user = models.ForeignKey("hipeac_mcp.User", related_name="memberships", on_delete=models.CASCADE)
    type = models.CharField(max_length=20)
    advisor = models.ForeignKey(
        "hipeac_mcp.User", related_name="affiliates", null=True, blank=True, on_delete=models.SET_NULL
    )
    date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    reason = models.CharField(max_length=20, blank=True, default="")
    comments = models.TextField(blank=True, default="")

    objects = MembershipQuerySet.as_manager()

    class Meta:
        db_table = "hipeac_membership"
        managed = False
