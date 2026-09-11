"""Locale selection and completeness of the small built-in catalogue."""

from __future__ import annotations

import ast
from pathlib import Path
from string import Formatter

from tidalamp import i18n


def _translated_literals() -> set[str]:
    """Collect every literal passed to ``_`` in the package."""
    package = Path(i18n.__file__).parent
    strings: set[str] = set()
    dynamic: list[str] = []
    for path in package.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "_"
            ):
                continue
            if (
                len(node.args) == 1
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                strings.add(node.args[0].value)
            else:
                dynamic.append(f"{path.name}:{node.lineno}")
    assert not dynamic, "translations must be statically auditable: " + ", ".join(dynamic)
    return strings


def _fields(text: str) -> set[str]:
    return {name for _, name, _, _ in Formatter().parse(text) if name is not None}


def test_language_uses_the_standard_environment_precedence():
    assert i18n._language({"LANG": "es_CL.UTF-8"}) == "es"
    assert i18n._language({"LANG": "es_CL.UTF-8", "LC_MESSAGES": "en_GB"}) == "en"
    assert i18n._language({"LANG": "es_CL.UTF-8", "LC_ALL": "en_US.UTF-8"}) == "en"
    assert i18n._language({"LC_ALL": "C.UTF-8", "LANG": "en_US.UTF-8"}) == "es"
    assert i18n._language({"LANGUAGE": "en_GB:es", "LC_ALL": "es_CL"}) == "en"
    assert i18n._language({"LANGUAGE": "fr_FR:en_GB"}) == "en"


def test_spanish_is_the_source_and_unknown_languages_fall_back_to_it():
    i18n.use("es")
    assert i18n._("cargando…") == "cargando…"

    i18n.use("fr")
    assert i18n._("cargando…") == "cargando…"


def test_english_translates_literals_and_formatted_values():
    i18n.use("en")
    assert i18n._("cargando…") == "loading…"
    assert (
        i18n._("reproduciendo {label}").format(label="TOOL - Schism")
        == "playing TOOL - Schism"
    )
    assert i18n.config_template().startswith("# tidalamp configuration.")


def test_every_translated_literal_has_exactly_one_catalogue_entry():
    assert _translated_literals() == set(i18n.ENGLISH)


def test_modules_that_translate_do_not_shadow_the_translation_function():
    package = Path(i18n.__file__).parent
    shadowed: list[str] = []
    for path in package.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imports_translation = any(
            isinstance(node, ast.ImportFrom)
            and node.module == "i18n"
            and any(alias.name == "_" for alias in node.names)
            for node in ast.walk(tree)
        )
        if not imports_translation:
            continue
        for node in ast.walk(tree):
            if (isinstance(node, ast.arg) and node.arg == "_") or (
                isinstance(node, ast.Name)
                and node.id == "_"
                and isinstance(node.ctx, ast.Store)
            ):
                shadowed.append(f"{path.name}:{node.lineno}")
    assert not shadowed, "translation function shadowed at " + ", ".join(shadowed)


def test_translations_preserve_format_fields():
    for source, translation in i18n.ENGLISH.items():
        assert _fields(translation) == _fields(source), source
        assert translation.count("%(keys)s") == source.count("%(keys)s"), source
