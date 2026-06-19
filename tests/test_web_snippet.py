import json
from provider_pipeline.sources.website import extract_from_practice_site, html_to_text
from provider_pipeline.sources.snippet import extract_from_snippets


def _fake(payload_dict, tokens=30):
    def fn(*, model, messages):
        return {"choices": [{"message": {"content": json.dumps(payload_dict)}}],
                "usage": {"total_tokens": tokens}}
    return fn


def test_html_to_text_strips_tags():
    html = "<html><body><h1>Dr Smith</h1><p>Call (239) 555-9999</p><script>x()</script></body></html>"
    text = html_to_text(html)
    assert "Dr Smith" in text and "239" in text
    assert "<" not in text and "x()" not in text


def test_website_extraction_returns_contact(tmp_path):
    fn = _fake({"address_line": "500 Oak Ave", "phone": "239-555-9999"})
    contact, tokens = extract_from_practice_site(
        "<p>500 Oak Ave, call 239-555-9999</p>", model="m",
        cache_dir=tmp_path, completion_fn=fn)
    assert contact.address_line == "500 Oak Ave"
    assert tokens == 30


def test_snippet_extraction_joins_and_returns(tmp_path):
    fn = _fake({"phone": "2395559999"})
    contact, tokens = extract_from_snippets(
        ["Dr Smith now at 500 Oak Ave", "Phone 239 555 9999"], model="m",
        cache_dir=tmp_path, completion_fn=fn)
    assert contact.phone == "2395559999"
    assert tokens == 30
