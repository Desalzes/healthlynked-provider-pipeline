import json
from provider_pipeline.llm import complete, extract_contact
from provider_pipeline.schemas import ContactTuple


def _fake(text, tokens=42):
    calls = {"n": 0}

    def fn(*, model, messages):
        calls["n"] += 1
        return {"choices": [{"message": {"content": text}}],
                "usage": {"total_tokens": tokens}}

    return fn, calls


def test_complete_caches_by_prompt(tmp_path):
    fn, calls = _fake("hello")
    out1, tok1 = complete("a prompt", model="m", cache_dir=tmp_path, completion_fn=fn)
    out2, tok2 = complete("a prompt", model="m", cache_dir=tmp_path, completion_fn=fn)
    assert out1 == out2 == "hello"
    assert tok1 == 42 and tok2 == 0   # second call served from cache, no tokens
    assert calls["n"] == 1


def test_extract_contact_parses_json(tmp_path):
    payload = json.dumps({"address_line": "500 Oak Ave", "city": "Naples",
                          "state": "FL", "zip": "34102", "phone": "239-555-9999"})
    fn, _ = _fake(payload)
    contact, tokens = extract_contact("page text", instruction="extract",
                                      model="m", cache_dir=tmp_path, completion_fn=fn)
    assert isinstance(contact, ContactTuple)
    assert contact.address_line == "500 Oak Ave"
    assert tokens == 42


def test_extract_contact_tolerates_fenced_json(tmp_path):
    fenced = "```json\n{\"phone\": \"2395559999\"}\n```"
    fn, _ = _fake(fenced)
    contact, _ = extract_contact("t", instruction="x", model="m",
                                 cache_dir=tmp_path, completion_fn=fn)
    assert contact.phone == "2395559999"
