"""Unit tests for HTML sanitization in email templates against XSS & HTML injection."""

from __future__ import annotations

from app.services.email_service import render_template, sanitize_context_value


def test_sanitize_context_value_escapes_html_tags() -> None:
    raw = '<script>alert("XSS")</script>'
    sanitized = sanitize_context_value(raw)
    assert '<script>' not in sanitized
    assert sanitized == '&lt;script&gt;alert(&quot;XSS&quot;)&lt;/script&gt;'


def test_sanitize_context_value_handles_nested_lists_and_dicts() -> None:
    data = {
        'user': '<b onmouseover=alert(1)>User</b>',
        'tags': ['<img src=x onerror=alert(1)>', 'normal'],
        'count': 5,
        'active': True,
        'missing': None,
    }
    sanitized = sanitize_context_value(data)

    assert '&lt;b onmouseover=alert(1)&gt;User&lt;/b&gt;' in sanitized['user']
    assert '&lt;img src=x onerror=alert(1)&gt;' in sanitized['tags'][0]
    assert sanitized['tags'][1] == 'normal'
    assert sanitized['count'] == 5
    assert sanitized['active'] is True
    assert sanitized['missing'] == ''


def test_render_template_escapes_malicious_user_inputs() -> None:
    welcome_html = render_template(
        'welcome',
        full_name='<script>alert("XSS")</script>',
        temporary_password=None,
    )
    assert '<script>' not in welcome_html
    assert (
        '&lt;script&gt;alert(&quot;XSS&quot;)&lt;/script&gt;' in welcome_html
    )

    account_created_html = render_template(
        'account_created',
        verify_link='http://localhost:8000/auth/verify-email?token=123&type=test',
    )
    assert 'token=123&amp;type=test' in account_created_html


def test_render_template_fallback_escapes_html() -> None:
    html = render_template(
        'non_existent_template',
        payload='<iframe src="http://evil.com"></iframe>',
    )

    assert '<iframe' not in html
    assert '&lt;iframe src=&quot;http://evil.com&quot;&gt;' in html
