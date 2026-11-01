from intextum_cli import llm_endpoints as endpoints
from intextum_cli.llm_endpoints import fetch_context_length


def test_ollama_detection_and_loaded_context(monkeypatch):
    answers = {
        "http://mini:11434/api/version": {"version": "0.40.6"},
        "http://mini:11434/api/ps": {
            "models": [{"name": "qwen3.8:27b", "context_length": 32768}]
        },
    }

    def fake_get(url, timeout):
        if url not in answers:
            raise OSError("not found")
        return answers[url]

    monkeypatch.setattr(endpoints, "_get_json", fake_get)
    assert endpoints.is_ollama("http://mini:11434/v1")
    assert not endpoints.is_ollama("http://other:1234/v1")
    assert (
        endpoints.fetch_context_length("http://mini:11434/v1", "qwen3.8:27b") == 32768
    )
    assert endpoints.fetch_context_length("http://mini:11434/v1", "kev") is None


def test_fetch_context_length_without_server():
    assert fetch_context_length("http://127.0.0.1:9/v1", "m", timeout=0.5) is None


def test_fetch_context_length_lm_studio_and_vllm(monkeypatch):
    responses = {
        "http://lms:1234/api/v0/models/qwen/qwen3.8-27b": {"loaded_context_length": 16686, "max_context_length": 262144},
        "http://vllm/v1/models": {"data": [{"id": "qwen36-35b", "max_model_len": 32768},
                                           {"id": "qwen38-27b", "max_model_len": 65536}]},
    }  # fmt: skip

    def fake_get(url, timeout):
        if url not in responses:
            raise OSError("404")
        return responses[url]

    monkeypatch.setattr(endpoints, "_get_json", fake_get)
    assert fetch_context_length("http://lms:1234/v1", "qwen/qwen3.8-27b") == 16686
    assert fetch_context_length("http://vllm/v1", "qwen38-27b") == 65536
    assert fetch_context_length("http://vllm/v1", "unknown") is None
