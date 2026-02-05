"""Event models for RAG service (read-only)."""

from django.db import models


class Event(models.Model):
    """HiPEAC Event (ACACES, Conference, CSW) - read-only."""

    ACACES = "acaces"
    CONFERENCE = "conference"
    CSW = "csw"

    TYPE_CHOICES = (
        (ACACES, "ACACES"),
        (CONFERENCE, "Conference"),
        (CSW, "Computing Systems Week (CSW)"),
    )

    type = models.CharField(max_length=16, choices=TYPE_CHOICES)
    slug = models.SlugField(max_length=100, unique=True)
    city = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=2, blank=True)
    timezone = models.CharField(max_length=64, default="Europe/Brussels")

    start_date = models.DateField()
    end_date = models.DateField()
    registration_start_date = models.DateField()
    registration_early_deadline = models.DateTimeField(null=True, blank=True)
    registration_deadline = models.DateTimeField()

    hashtag = models.CharField(max_length=32, blank=True)
    description = models.TextField(blank=True)
    logistics = models.TextField(blank=True)

    config = models.JSONField(default=dict)

    class Meta:
        db_table = "hipeac_event"
        ordering = ["-start_date"]
        managed = False

    def __str__(self) -> str:
        return self.name

    @property
    def name(self) -> str:
        """Get event name."""
        year = self.start_date.year
        if self.type == self.ACACES:
            return f"ACACES {year}"
        if self.type == self.CONFERENCE:
            return f"HiPEAC {year}"
        if self.type == self.CSW:
            season = "Spring" if self.start_date.month < 6 else "Autumn"
            return f"CSW {season} {year}"
        return f"{self.type} {year}"

    @property
    def year(self) -> int:
        """Get event year."""
        return self.start_date.year

    def get_absolute_url(self) -> str:
        """Get event URL."""
        if self.type == self.ACACES:
            return f"/acaces/{self.year}/"
        if self.type == self.CONFERENCE:
            return f"/conference/{self.year}/{self.slug}/"
        if self.type == self.CSW:
            return f"/csw/{self.year}/{self.slug}/"
        return "#"


class RelatedPlace(models.Model):
    """Generic place relationship - read-only."""

    content_type_id = models.IntegerField()
    object_id = models.IntegerField()
    place_id = models.IntegerField()
    position = models.IntegerField(default=0)
    is_primary = models.BooleanField(default=False)

    class Meta:
        db_table = "hipeac_rel_places"
        managed = False


class Place(models.Model):
    """Physical location (venues, hotels) - read-only."""

    name = models.CharField(max_length=200)
    address = models.CharField(max_length=250, blank=True)
    city = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=2, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    class Meta:
        db_table = "hipeac_place"
        managed = False

    def __str__(self) -> str:
        return self.name


class Activity(models.Model):
    """Event activity (keynote, course, workshop, social) - read-only."""

    event = models.ForeignKey(Event, related_name="activities", on_delete=models.DO_NOTHING)
    type_id = models.IntegerField()
    title = models.CharField(max_length=250)
    slug = models.SlugField(max_length=100)
    description = models.TextField(blank=True)
    summary = models.TextField(blank=True)

    extra_data = models.JSONField(default=dict)

    class Meta:
        db_table = "hipeac_event_activity"
        ordering = ["event", "id"]
        managed = False

    def __str__(self) -> str:
        return self.title

    def get_absolute_url(self) -> str:
        """Get activity URL."""
        return f"/activity/{self.id}/{self.slug}/"


class Session(models.Model):
    """Activity session with specific time slot - read-only."""

    activity = models.ForeignKey(Activity, related_name="sessions", on_delete=models.DO_NOTHING)
    title = models.CharField(max_length=250, blank=True)
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    program = models.TextField(blank=True)

    class Meta:
        db_table = "hipeac_event_activity_session"
        ordering = ["activity", "start_at"]
        managed = False

    def __str__(self) -> str:
        return self.title or f"Session {self.id}"


class ActivityUser(models.Model):
    """Activity-User relationship (speakers, organizers) - read-only."""

    activity = models.ForeignKey(Activity, related_name="rel_users", on_delete=models.DO_NOTHING)
    user_id = models.IntegerField()

    extra_data = models.JSONField(default=dict)

    class Meta:
        db_table = "hipeac_rel_activity_user"
        managed = False


class EventUser(models.Model):
    """User profile (for speakers) - read-only."""

    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    institution_id = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = "auth_user"
        managed = False

    def __str__(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @property
    def name(self) -> str:
        """Get full name."""
        return f"{self.first_name} {self.last_name}"


class EventInstitution(models.Model):
    """Institution (for speaker affiliations) - read-only."""

    name = models.CharField(max_length=200)
    short_name = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=2, blank=True)

    class Meta:
        db_table = "hipeac_institution"
        managed = False

    def __str__(self) -> str:
        return self.short_name or self.name


class EventMetadata(models.Model):
    """Metadata (for activity types) - read-only."""

    SESSION_TYPE = "session_type"

    type = models.CharField(max_length=50)
    value = models.CharField(max_length=100)

    class Meta:
        db_table = "hipeac_metadata"
        managed = False

    def __str__(self) -> str:
        return self.value
