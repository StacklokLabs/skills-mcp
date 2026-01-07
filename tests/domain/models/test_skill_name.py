"""Tests for SkillName value object."""

import pytest

from skills_mcp.domain.exceptions import InvalidSkillNameError
from skills_mcp.domain.models.skill_name import SkillName


class TestSkillNameValidation:
    """Tests for SkillName validation rules."""

    def test_valid_simple_name(self) -> None:
        """Valid simple name should be accepted."""
        name = SkillName("myskill")
        assert name.value == "myskill"

    def test_valid_name_with_numbers(self) -> None:
        """Valid name with numbers should be accepted."""
        name = SkillName("skill123")
        assert name.value == "skill123"

    def test_valid_name_with_hyphens(self) -> None:
        """Valid name with hyphens should be accepted."""
        name = SkillName("my-skill-name")
        assert name.value == "my-skill-name"

    def test_valid_single_char_name(self) -> None:
        """Single character name should be accepted."""
        name = SkillName("a")
        assert name.value == "a"

    def test_valid_max_length_name(self) -> None:
        """Name at maximum length should be accepted."""
        name = SkillName("a" * 64)
        assert len(name.value) == 64

    def test_invalid_empty_name(self) -> None:
        """Empty name should be rejected."""
        with pytest.raises(InvalidSkillNameError) as exc_info:
            SkillName("")
        assert "empty" in str(exc_info.value).lower()

    def test_invalid_name_too_long(self) -> None:
        """Name longer than 64 characters should be rejected."""
        with pytest.raises(InvalidSkillNameError) as exc_info:
            SkillName("a" * 65)
        assert "64" in str(exc_info.value)

    def test_invalid_name_uppercase(self) -> None:
        """Uppercase letters should be rejected."""
        with pytest.raises(InvalidSkillNameError) as exc_info:
            SkillName("MySkill")
        assert "lowercase" in str(exc_info.value).lower()

    def test_invalid_name_starts_with_number(self) -> None:
        """Name starting with number should be rejected."""
        with pytest.raises(InvalidSkillNameError) as exc_info:
            SkillName("123skill")
        assert "start with a letter" in str(exc_info.value).lower()

    def test_invalid_name_starts_with_hyphen(self) -> None:
        """Name starting with hyphen should be rejected."""
        with pytest.raises(InvalidSkillNameError) as exc_info:
            SkillName("-skill")
        assert "start with a letter" in str(exc_info.value).lower()

    def test_invalid_name_ends_with_hyphen(self) -> None:
        """Name ending with hyphen should be rejected."""
        with pytest.raises(InvalidSkillNameError) as exc_info:
            SkillName("skill-")
        assert "not end with a hyphen" in str(exc_info.value).lower()

    def test_invalid_name_consecutive_hyphens(self) -> None:
        """Consecutive hyphens should be rejected."""
        with pytest.raises(InvalidSkillNameError) as exc_info:
            SkillName("my--skill")
        assert "single hyphens" in str(exc_info.value).lower()

    def test_invalid_name_with_underscore(self) -> None:
        """Underscores should be rejected."""
        with pytest.raises(InvalidSkillNameError) as exc_info:
            SkillName("my_skill")
        assert "lowercase" in str(exc_info.value).lower()

    def test_invalid_name_with_spaces(self) -> None:
        """Spaces should be rejected."""
        with pytest.raises(InvalidSkillNameError) as exc_info:
            SkillName("my skill")
        assert "lowercase" in str(exc_info.value).lower()

    def test_invalid_name_with_special_chars(self) -> None:
        """Special characters should be rejected."""
        with pytest.raises(InvalidSkillNameError) as exc_info:
            SkillName("my@skill")
        assert "lowercase" in str(exc_info.value).lower()


class TestSkillNameEquality:
    """Tests for SkillName equality and hashing."""

    def test_equal_names(self) -> None:
        """Same values should be equal."""
        name1 = SkillName("myskill")
        name2 = SkillName("myskill")
        assert name1 == name2

    def test_unequal_names(self) -> None:
        """Different values should not be equal."""
        name1 = SkillName("skill1")
        name2 = SkillName("skill2")
        assert name1 != name2

    def test_hash_consistency(self) -> None:
        """Equal names should have equal hashes."""
        name1 = SkillName("myskill")
        name2 = SkillName("myskill")
        assert hash(name1) == hash(name2)

    def test_usable_as_dict_key(self) -> None:
        """SkillName should be usable as dict key."""
        name = SkillName("myskill")
        d = {name: "value"}
        assert d[SkillName("myskill")] == "value"

    def test_usable_in_set(self) -> None:
        """SkillName should be usable in sets."""
        names = {SkillName("skill1"), SkillName("skill2"), SkillName("skill1")}
        assert len(names) == 2


class TestSkillNameStringRepresentation:
    """Tests for SkillName string representations."""

    def test_str_returns_value(self) -> None:
        """str() should return the value."""
        name = SkillName("myskill")
        assert str(name) == "myskill"

    def test_repr_is_informative(self) -> None:
        """repr() should be informative."""
        name = SkillName("myskill")
        assert "SkillName" in repr(name)
        assert "myskill" in repr(name)
