"""
Bengali/English toggle tests (V12): locale parity + HTML wiring.
- en/bn key sets identical, no empty strings
- every data-i18n key used in index.html exists in the locale
- toggle button + loader present in app.js
"""
import io
import json
import os
import re

STATIC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")


def _locale():
    with io.open(os.path.join(STATIC, "locale.json"), encoding="utf-8") as f:
        return json.load(f)


def test_locale_key_parity():
    d = _locale()
    assert set(d["en"]) == set(d["bn"]), "en/bn keys diverged"
    assert len(d["en"]) > 50, "locale too small to cover the UI"
    empties = [k for k in d["en"] if not d["en"][k].strip() or not d["bn"][k].strip()]
    assert empties == [], f"empty translations: {empties}"


def test_html_keys_exist_in_locale():
    d = _locale()
    with io.open(os.path.join(STATIC, "index.html"), encoding="utf-8") as f:
        html = f.read()
    used = set(re.findall(r'data-i18n="([^"]+)"', html))
    used_ph = set(re.findall(r'data-i18n-ph="([^"]+)"', html))
    assert len(used) > 40, "too few tagged strings"
    missing = (used | used_ph) - set(d["en"])
    assert missing == set(), f"HTML uses keys missing from locale: {missing}"
    assert 'id="lang-toggle"' in html


def test_app_js_locale_wiring():
    with io.open(os.path.join(STATIC, "app.js"), encoding="utf-8") as f:
        js = f.read()
    for token in ["loadLocale", "applyLocale", "chhaya-lang", "data-i18n", "lang-toggle"]:
        assert token in js, f"missing {token} in app.js"
