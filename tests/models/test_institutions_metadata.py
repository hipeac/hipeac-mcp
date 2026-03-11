"""Tests for Institution and Metadata model string representations."""

from hipeac_mcp.models.institutions import Institution
from hipeac_mcp.models.metadata import Metadata


class TestInstitutionStr:
    """Tests for Institution.__str__."""

    def test_str_returns_name(self):
        """__str__ returns the institution name."""
        inst = Institution(name="IMEC")
        assert str(inst) == "IMEC"


class TestMetadataStr:
    """Tests for Metadata.__str__."""

    def test_str_returns_value(self):
        """__str__ returns the metadata value."""
        m = Metadata(value="Deep Learning")
        assert str(m) == "Deep Learning"
