from __future__ import annotations

import json
import os
from pathlib import Path

from .store import Error, encoded, file_hash, fingerprint


def model_info(lib):
    row = lib.db.execute("SELECT value FROM meta WHERE key='model_path'").fetchone()
    if not row or not Path(row[0]).is_dir():
        raise Error("Configure a local model using init --model-path or index build --model-path", "missing_model")
    path = Path(row[0])
    weights = sorted(path.glob("*.safetensors"))
    if not weights:
        raise Error("v0.1 semantic mode requires local safetensors weights", "missing_model")
    signatures = {str(f.relative_to(path)): file_hash(f) for f in sorted(path.rglob("*.json"))}
    signatures.update({f.name: file_hash(f) for f in weights})
    return path, fingerprint(signatures)


def load_model(path):
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    try:
        import torch
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise Error("Install book-logic[semantic] to use vector retrieval", "missing_dependency") from exc
    torch.set_num_threads(2)
    return SentenceTransformer(str(path), device="cpu", local_files_only=True, trust_remote_code=False)


def split(text, tokenizer, limit, overlap=16):
    offsets = tokenizer(text, add_special_tokens=False, return_offsets_mapping=True, truncation=False, verbose=False)["offset_mapping"]
    if limit <= overlap:
        raise Error("Model context too short", "model_error")
    for left in range(0, len(offsets), limit - overlap):
        right = min(left + limit, len(offsets))
        start, end = offsets[left][0], offsets[right - 1][1]
        if end > start:
            yield start, end
        if right == len(offsets):
            break


def build(lib, model_path=None):
    try:
        import fcntl
    except ImportError as exc:
        raise Error("Semantic index writer currently supports macOS/Linux", "unsupported_platform") from exc
    with (lib.root / "index-writer.lock").open("a") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise Error("Another semantic index build is running", "busy") from exc
        try:
            return _build(lib, model_path)
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _build(lib, model_path=None):
    if model_path:
        path = Path(model_path).expanduser().resolve()
        if not path.is_dir():
            raise Error("Model directory not found", "missing_model")
        with lib.transaction():
            lib.db.execute("INSERT OR REPLACE INTO meta VALUES('model_path',?)", (str(path),))
    path, signature = model_info(lib)
    model = load_model(path)
    import numpy as np
    from .retrieval import documents, document_signature
    rows = documents(lib)
    signature_docs = document_signature(rows)
    limit = min(112, model.max_seq_length - model.tokenizer.num_special_tokens_to_add() - 8)
    chunks, texts = [], []
    for row in rows:
        for start, end in split(row["text"], model.tokenizer, limit):
            text = row["text"][start:end]
            if len(model.tokenizer(text)["input_ids"]) > model.max_seq_length:
                raise Error("Chunk would be truncated by model", "model_error")
            chunks.append({"document_id": row["id"], "start": start, "end": end})
            texts.append(text)
    if not texts:
        raise Error("No indexable text")
    manifest = {"model_signature": signature, "document_signature": signature_docs, "chunks": chunks,
                "max_seq_length": model.max_seq_length, "chunk_tokens": limit, "dimension": model.get_sentence_embedding_dimension()}
    gid = fingerprint(manifest)
    stage = lib.root / "indexes" / gid
    stage.mkdir(parents=True, exist_ok=True)
    arrays = []
    for start in range(0, len(texts), 256):
        part = stage / f"batch-{start}.npy"
        expected = min(256, len(texts) - start)
        if part.exists():
            vec = np.load(part, allow_pickle=False)
            if vec.shape != (expected, manifest["dimension"]) or not np.isfinite(vec).all():
                raise Error("Interrupted batch is corrupt; preserve it and inspect before rebuilding", "corrupt_index")
        else:
            vec = model.encode(texts[start:start + 256], batch_size=32, normalize_embeddings=True, show_progress_bar=False).astype("float32")
            if vec.shape != (expected, manifest["dimension"]) or not np.isfinite(vec).all():
                raise Error("Model returned invalid vectors", "model_error")
            with part.with_suffix(".tmp").open("wb") as stream:
                np.save(stream, vec, allow_pickle=False)
            part.with_suffix(".tmp").replace(part)
        arrays.append(vec)
    vector_path = stage / "vectors.npy"
    with (stage / "vectors.tmp").open("wb") as stream:
        np.save(stream, np.concatenate(arrays), allow_pickle=False)
    (stage / "vectors.tmp").replace(vector_path)
    manifest["vectors_sha256"] = file_hash(vector_path)
    (stage / "manifest.tmp").write_text(encoded(manifest), encoding="utf-8")
    (stage / "manifest.tmp").replace(stage / "manifest.json")
    with lib.transaction():
        if document_signature(documents(lib)) != signature_docs:
            raise Error("Library changed during indexing; generation kept inactive", "stale_index")
        if model_info(lib)[1] != signature:
            raise Error("Model changed during indexing; generation kept inactive", "stale_index")
        lib.db.execute("INSERT OR REPLACE INTO meta VALUES('active_index',?)", (gid,))
    return {"generation": gid, "chunks": len(chunks), "dimension": manifest["dimension"]}


def index_status(lib):
    from .retrieval import documents, document_signature
    row = lib.db.execute("SELECT value FROM meta WHERE key='active_index'").fetchone()
    if not row:
        return {"state": "not_built"}
    manifest = json.loads((lib.root / "indexes" / row[0] / "manifest.json").read_text())
    _, signature = model_info(lib)
    current = manifest["document_signature"] == document_signature(documents(lib)) and manifest["model_signature"] == signature
    return {"generation": row[0], "state": "current" if current else "stale"}


def query_index(lib, query, allowed):
    state = index_status(lib)
    if state["state"] != "current":
        raise Error("Semantic index missing or stale; run index build", "stale_index")
    folder = lib.root / "indexes" / state["generation"]
    manifest = json.loads((folder / "manifest.json").read_text())
    if file_hash(folder / "vectors.npy") != manifest["vectors_sha256"]:
        raise Error("Vector file hash mismatch", "corrupt_index")
    path, _ = model_info(lib)
    model = load_model(path)
    import numpy as np
    if len(model.tokenizer(query)["input_ids"]) > model.max_seq_length:
        raise Error("Split the question to fit the model context", "query_too_long")
    vectors = np.load(folder / "vectors.npy", allow_pickle=False)
    if vectors.shape != (len(manifest["chunks"]), manifest["dimension"]):
        raise Error("Vector shape mismatch", "corrupt_index")
    q = model.encode([query], normalize_embeddings=True, show_progress_bar=False)[0]
    ranking, locations = [], {}
    for i in np.argsort(-(vectors @ q)):
        chunk = manifest["chunks"][int(i)]
        did = chunk["document_id"]
        if did not in allowed or did in locations:
            continue
        ranking.append(did)
        locations[did] = chunk
        if len(ranking) == 40:
            break
    return ranking, locations
