"""Local-only ONNX embeddings. Downloads contain public weights, never workspace text."""

import argparse
import hashlib
import json
import re
import threading
import urllib.request
from pathlib import Path

from app.core.config import settings

CANDIDATES = {
    "e5-small": "Xenova/multilingual-e5-small",
    "minilm": "Xenova/paraphrase-multilingual-MiniLM-L12-v2",
}
BASE_MODELS = {
    "e5-small": "intfloat/multilingual-e5-small",
    "minilm": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
}
_lock = threading.Lock()
_load_lock = threading.Lock()
_models = {}


class ModelUnavailable(Exception):
    pass


class LocalEmbedding:
    def __init__(self, path=None):
        self.path = Path(path or settings.memory_model_path)
        try:
            self.manifest = json.loads((self.path / "manifest.json").read_text())
            if (
                self.manifest["model"] not in CANDIDATES.values()
                or self.manifest["dimension"] != 384
            ):
                raise ValueError
            import onnxruntime as ort
            from tokenizers import Tokenizer

            for name, checksum in self.manifest["sha256"].items():
                if name not in {"model.onnx", "tokenizer.json"}:
                    raise ValueError
                if (
                    hashlib.file_digest((self.path / name).open("rb"), "sha256").hexdigest()
                    != checksum
                ):
                    raise ValueError
            self.tokenizer = Tokenizer.from_file(str(self.path / "tokenizer.json"))
            self.tokenizer.enable_truncation(max_length=256)
            self.tokenizer.enable_padding()
            options = ort.SessionOptions()
            options.intra_op_num_threads = 2
            options.inter_op_num_threads = 1
            self.session = ort.InferenceSession(
                str(self.path / "model.onnx"),
                sess_options=options,
                providers=["CPUExecutionProvider"],
            )
            self.inputs = {i.name for i in self.session.get_inputs()}
        except Exception:
            raise ModelUnavailable("Local embedding model unavailable") from None

    @property
    def identity(self):
        return self.manifest["model"], self.manifest["version"]

    def encode(self, texts, *, query=False):
        try:
            return self._encode(texts, query=query)
        except Exception:
            raise ModelUnavailable("Local embedding inference unavailable") from None

    def _encode(self, texts, *, query=False):
        import numpy as np

        if not texts:
            return []
        output = []
        for start in range(0, len(texts), 16):
            batch = texts[start : start + 16]
            if "e5" in self.manifest["model"]:
                batch = [("query: " if query else "passage: ") + t for t in batch]
            with _lock:
                tokens = self.tokenizer.encode_batch(batch)
            inputs = {
                "input_ids": np.array([t.ids for t in tokens], dtype=np.int64),
                "attention_mask": np.array([t.attention_mask for t in tokens], dtype=np.int64),
                "token_type_ids": np.array([t.type_ids for t in tokens], dtype=np.int64),
            }
            vectors = self.session.run(None, {k: v for k, v in inputs.items() if k in self.inputs})[
                0
            ]
            if vectors.ndim == 3:
                mask = inputs["attention_mask"][..., None]
                vectors = (vectors * mask).sum(axis=1) / mask.sum(axis=1).clip(min=1)
            vectors = vectors / np.linalg.norm(vectors, axis=1, keepdims=True).clip(min=1e-12)
            if vectors.shape[1] != 384 or not np.isfinite(vectors).all():
                raise ModelUnavailable("Invalid local embedding dimension")
            output.extend(vectors.astype(float).tolist())
        return output


def model():
    if not settings.memory_embedding_enabled:
        raise ModelUnavailable("Local embedding disabled")
    key = str(settings.memory_model_path)
    stamp = settings.memory_model_path / "manifest.json"
    try:
        version = stamp.stat().st_mtime_ns
        # A cold start must not allocate one full model per concurrent worker.
        with _load_lock:
            cached = _models.get(key)
            if not cached or cached[0] != version:
                _models[key] = (version, LocalEmbedding())
            return _models[key][1]
    except (OSError, ValueError, KeyError):
        raise ModelUnavailable("Local embedding model unavailable") from None


def download(candidate, destination):
    """Pin the public model revision and verify each downloaded artifact's SHA256."""
    name = CANDIDATES[candidate]
    req = urllib.request.Request(
        f"https://huggingface.co/api/models/{name}?blobs=true",
        headers={"User-Agent": "Tandem-local-embeddings"},
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        metadata = json.load(response)
    revision = metadata.get("sha", "")
    license_name = metadata.get("cardData", {}).get("license")
    license_source = {"model": name, "revision": revision}
    if license_name is None:
        # These ONNX conversions identify their original model but omit its license.
        base = BASE_MODELS[candidate]
        if metadata.get("cardData", {}).get("base_model") != base:
            raise ValueError("Expected original model link is required")
        with urllib.request.urlopen(
            f"https://huggingface.co/api/models/{base}", timeout=30
        ) as response:
            original = json.load(response)
        base_revision = original.get("sha", "")
        if not re.fullmatch(r"[a-f0-9]{40}", base_revision):
            raise ValueError("Verified original model revision is required")
        license_name = original.get("cardData", {}).get("license")
        license_source = {"model": base, "revision": base_revision}
    if not re.fullmatch(r"[a-f0-9]{40}", revision) or license_name not in {"mit", "apache-2.0"}:
        raise ValueError("Verified revision and approved model license are required")
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    sums, sizes = {}, {}
    siblings = {f["rfilename"]: f for f in metadata["siblings"]}
    for remote, local in [
        ("onnx/model_quantized.onnx", "model.onnx"),
        ("tokenizer.json", "tokenizer.json"),
    ]:
        target = destination / (local + ".partial")
        try:
            with (
                urllib.request.urlopen(
                    f"https://huggingface.co/{name}/resolve/{revision}/{remote}", timeout=120
                ) as response,
                target.open("wb") as out,
            ):
                total = 0
                while data := response.read(1024 * 1024):
                    total += len(data)
                    if total > 200 * 1024 * 1024:
                        raise ValueError("Model artifact exceeds download bound")
                    out.write(data)
            checksum = hashlib.file_digest(target.open("rb"), "sha256").hexdigest()
            expected = siblings.get(remote, {}).get("lfs", {}).get("sha256")
            if expected and checksum != expected:
                raise ValueError("Model checksum mismatch")
            sums[local], sizes[local] = checksum, total
            target.replace(destination / local)
        finally:
            target.unlink(missing_ok=True)
    manifest = {
        "model": name,
        "version": revision + "-q8",
        "dimension": 384,
        "license": license_name,
        "license_source": license_source,
        "sha256": sums,
        "bytes": sizes,
        "source": f"https://huggingface.co/{name}/tree/{revision}",
    }
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    LocalEmbedding(destination).encode(["Synthetic English test اختبار عربي"], query=True)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", choices=CANDIDATES)
    parser.add_argument("--destination", type=Path, default=settings.memory_model_path)
    args = parser.parse_args()
    try:
        print(json.dumps(download(args.candidate, args.destination)))
    except Exception:
        raise SystemExit(
            "Model download/verification failed; no content or credentials logged"
        ) from None
