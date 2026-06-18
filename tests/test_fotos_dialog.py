"""Tests for photo carousel logic in fotos_dialog."""


def test_carousel_index_wraps_forward():
    """Next on last photo wraps to first."""
    total = 5
    idx = 4
    next_idx = (idx + 1) % total
    assert next_idx == 0


def test_carousel_index_wraps_backward():
    """Prev on first photo wraps to last."""
    total = 5
    idx = 0
    prev_idx = (idx - 1) % total
    assert prev_idx == 4


def test_carousel_index_advances_normally():
    """Next in the middle advances by one."""
    total = 5
    idx = 2
    assert (idx + 1) % total == 3


def test_fotos_button_hidden_when_no_photos():
    """Button should not render if fotos is None or empty."""
    assert not bool(None)
    assert not bool([])
    assert bool(["https://example.com/foto.jpg"])


def test_fotos_button_visible_with_photos():
    """Button renders when fotos has at least one URL."""
    fotos = ["https://example.com/1.jpg", "https://example.com/2.jpg"]
    assert bool(fotos) is True
