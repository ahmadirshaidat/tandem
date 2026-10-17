import io
import json

import pytest

from app.memory import embeddings


@pytest.mark.parametrize(
    "base,license_name",
    [
        ("unexpected/model", "mit"),
        ("intfloat/multilingual-e5-small", "other"),
    ],
)
def test_download_rejects_unapproved_license_provenance(monkeypatch, tmp_path, base, license_name):
    conversion = {"sha": "a" * 40, "cardData": {"base_model": base}}
    original = {"sha": "b" * 40, "cardData": {"license": license_name}}
    responses = iter([conversion, original])
    monkeypatch.setattr(
        embeddings.urllib.request,
        "urlopen",
        lambda *a, **k: io.BytesIO(json.dumps(next(responses)).encode()),
    )
    with pytest.raises(ValueError):
        embeddings.download("e5-small", tmp_path)
    assert not (tmp_path / "manifest.json").exists()


def test_download_records_original_license_and_verifies_hashes(monkeypatch, tmp_path):
    import hashlib

    artifacts = {"onnx/model_quantized.onnx": b"model", "tokenizer.json": b"tokenizer"}
    conversion = {
        "sha": "a" * 40,
        "cardData": {"base_model": "intfloat/multilingual-e5-small"},
        "siblings": [
            {"rfilename": name, "lfs": {"sha256": hashlib.sha256(data).hexdigest()}}
            for name, data in artifacts.items()
        ],
    }
    original = {"sha": "b" * 40, "cardData": {"license": "mit"}}
    responses = iter(
        [json.dumps(conversion).encode(), json.dumps(original).encode(), *artifacts.values()]
    )
    monkeypatch.setattr(
        embeddings.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(next(responses))
    )

    class Inference:
        def __init__(self, path):
            assert (path / "model.onnx").read_bytes() == b"model"

        def encode(self, *a, **k):
            return [[0.0] * 384]

    monkeypatch.setattr(embeddings, "LocalEmbedding", Inference)
    manifest = embeddings.download("e5-small", tmp_path)
    assert manifest["license"] == "mit"
    assert manifest["license_source"] == {
        "model": "intfloat/multilingual-e5-small",
        "revision": "b" * 40,
    }
    assert json.loads((tmp_path / "manifest.json").read_text()) == manifest
