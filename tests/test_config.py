"""Tests for the --profile token-cache mapping.

The profile name becomes part of a filename, so the sanitizer is the only thing
standing between user input and the path written to disk. These pin its safety.
"""

from __future__ import annotations

import pytest

from spotify_cleaner.config import _profile_cache_path


def test_plain_name_becomes_scoped_cache_file():
    assert _profile_cache_path("alice") == ".cache-spotify-alice"


def test_dashes_underscores_and_digits_survive():
    assert _profile_cache_path("bob_2") == ".cache-spotify-bob_2"


def test_traversal_value_cannot_escape_project_dir():
    # A path-like value must collapse to a flat, safe token: no slashes or dots
    # reach the filename, so the cache can never land outside the project.
    result = _profile_cache_path("../../etc/passwd")
    assert result == ".cache-spotify-etc-passwd"
    assert "/" not in result and ".." not in result


def test_spaces_and_punctuation_collapse_and_trim():
    assert _profile_cache_path("  Bob  Smith!! ") == ".cache-spotify-Bob-Smith"


def test_all_unsafe_name_is_rejected():
    with pytest.raises(SystemExit):
        _profile_cache_path("///")
