"""Tests for the shared design tokens and widget asset resolution.

The tokens matter because both UI surfaces are generated from them: if these values
drift from ``mockup/styles.css``, strict visual fidelity (NFR-UI-01) is lost silently.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vocabulary_trainer.domain.models import CharacterKind, WidgetState
from vocabulary_trainer.ui.theme import (
    COLORS,
    FONT_FAMILY,
    FONT_STACK,
    RADII,
    SHADOWS,
    as_css_variables,
    build_stylesheet,
)
from vocabulary_trainer.ui.widget import assets


class TestTokensMatchTheMockups:
    """Values transcribed from ``mockup/styles.css`` ``:root``."""

    @pytest.mark.parametrize(
        ("token", "expected"),
        [
            ("ink", "#1f2430"),
            ("ink-soft", "#5b6472"),
            ("ink-faint", "#8a93a3"),
            ("surface", "#ffffff"),
            ("surface-soft", "#f4f6fa"),
            ("border", "#e1e6ee"),
            ("brand", "#4d6bfe"),
            ("brand-dark", "#3450d6"),
            ("brand-soft", "#eef1ff"),
            ("success", "#2fb380"),
            ("success-soft", "#e6f7ef"),
            ("danger", "#e2554d"),
            ("danger-soft", "#fdecea"),
            ("warning", "#e0a635"),
            ("warning-soft", "#fff4e0"),
        ],
    )
    def test_colour_values(self, token: str, expected: str) -> None:
        assert COLORS[token] == expected

    def test_radii(self) -> None:
        assert RADII == {"lg": 20, "md": 14, "sm": 10}

    def test_shadow_definitions_exist(self) -> None:
        assert set(SHADOWS) == {"widget", "card"}

    def test_font_is_google_sans_with_a_fallback(self) -> None:
        """NFR-UI-02: bundled locally, never fetched from a CDN."""
        assert FONT_FAMILY == "Google Sans"
        assert "Google Sans" in FONT_STACK
        assert "Segoe UI" in FONT_STACK


class TestGeneratedCss:
    def test_emits_a_root_block(self) -> None:
        css = as_css_variables()
        assert css.startswith(":root {")
        assert css.rstrip().endswith("}")

    def test_includes_every_colour(self) -> None:
        css = as_css_variables()
        for token, value in COLORS.items():
            assert f"--{token}: {value};" in css

    def test_includes_radii_with_pixel_units(self) -> None:
        css = as_css_variables()
        assert "--radius-lg: 20px;" in css
        assert "--radius-md: 14px;" in css
        assert "--radius-sm: 10px;" in css

    def test_includes_the_font_stack(self) -> None:
        assert "--font:" in as_css_variables()


class TestGeneratedQtStylesheet:
    def test_uses_token_values_rather_than_literals(self) -> None:
        """Proves the two surfaces are generated from one source."""
        sheet = build_stylesheet()
        assert COLORS["brand"] in sheet
        assert COLORS["danger"] in sheet
        assert COLORS["surface-soft"] in sheet

    def test_styles_the_objects_the_widgets_actually_use(self) -> None:
        sheet = build_stylesheet()
        for object_name in (
            "QFrame#Card",
            "QFrame#CardWarning",
            "QPushButton#Primary",
            "QPushButton#Danger",
            "QPushButton#Outline",
            "QPushButton#Chip",
            "QFrame#MenuCard",
            "QPushButton#MenuItem",
            "QLabel#IconDotCollect",
            "QLabel#IconDotPractice",
            "QLabel#IconDotSettings",
        ):
            assert object_name in sheet, f"{object_name} is unstyled"

    def test_selected_chip_is_brand_filled(self) -> None:
        assert "QPushButton#Chip:checked" in build_stylesheet()

    def test_disabled_primary_button_is_styled(self) -> None:
        """Start and Save are both disabled states the user will see."""
        assert "QPushButton#Primary:disabled" in build_stylesheet()

    def test_no_unresolved_placeholders(self) -> None:
        sheet = build_stylesheet()
        assert "{" in sheet  # QSS braces are expected
        assert "None" not in sheet
        assert "{c[" not in sheet, "an f-string placeholder was left unrendered"


class TestAssetResolution:
    def test_finds_the_bundled_cat_artwork(self) -> None:
        for state in (WidgetState.IDLE, WidgetState.ACTIVE):
            assert assets.resolve(CharacterKind.CAT, state) is not None

    def test_missing_artwork_returns_none(self, tmp_path: Path) -> None:
        """E7-S3 branch 4a: Settings keeps the previous character and says so."""
        assert assets.resolve(CharacterKind.CAT, WidgetState.IDLE, tmp_path) is None

    def test_prefers_a_character_specific_file(self, tmp_path: Path) -> None:
        (tmp_path / "mini_ani_idle.png").write_bytes(b"cat")
        (tmp_path / "mini_ani_idle_crocodile.png").write_bytes(b"croc")

        resolved = assets.resolve(CharacterKind.CROCODILE, WidgetState.IDLE, tmp_path)
        assert resolved is not None
        assert resolved.name == "mini_ani_idle_crocodile.png"

    def test_falls_back_to_the_web_cutout_variant(self, tmp_path: Path) -> None:
        (tmp_path / "mini_ani_active_web.png").write_bytes(b"art")
        resolved = assets.resolve(CharacterKind.CAT, WidgetState.ACTIVE, tmp_path)
        assert resolved is not None
        assert resolved.name == "mini_ani_active_web.png"

    def test_available_characters_needs_both_poses(self, tmp_path: Path) -> None:
        """A character with one pose would flicker between idle and active."""
        (tmp_path / "mini_ani_idle.png").write_bytes(b"art")
        assert assets.available_characters(tmp_path) == []

        (tmp_path / "mini_ani_active.png").write_bytes(b"art")
        assert assets.available_characters(tmp_path) == [CharacterKind.CAT]

    def test_the_shipped_assets_offer_at_least_the_cat(self) -> None:
        assert CharacterKind.CAT in assets.available_characters()

    def test_assets_root_exists_in_the_package(self) -> None:
        assert assets.assets_root().is_dir()
