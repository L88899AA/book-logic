import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from book_logic import books, semantic
from book_logic.store import Error, Library, initialize


class Tokenizer:
    def __call__(self, text, **kwargs):
        return {"offset_mapping": [(i, i + 1) for i in range(len(text))], "input_ids": list(range(len(text) + 2))}

    def num_special_tokens_to_add(self):
        return 2


class Model:
    max_seq_length = 128
    tokenizer = Tokenizer()

    def get_sentence_embedding_dimension(self):
        return 3

    def encode(self, texts, **kwargs):
        import numpy as np
        return np.array([[1.0, 0.0, 0.0] for _ in texts], dtype="float32")


@unittest.skipUnless(importlib.util.find_spec("numpy"), "Optional numpy not installed")
class SemanticTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="book-logic-semantic-")
        self.root = Path(self.tmp.name)
        self.model = self.root / "model"
        self.model.mkdir()
        (self.model / "weights.safetensors").write_bytes(b"fixture only")
        (self.model / "config.json").write_text("{}")
        initialize(self.root / "library", str(self.model))
        self.lib = Library(self.root / "library", writable=True)
        source = self.root / "book.txt"
        source.write_text("capacity " * 60)
        books.add(self.lib, source)
        self.loader = patch.object(semantic, "load_model", return_value=Model())
        self.loader.start()

    def tearDown(self):
        self.loader.stop()
        self.lib.close()
        self.tmp.cleanup()

    def test_resume_and_query(self):
        first = semantic.build(self.lib)
        self.assertEqual(first, semantic.build(self.lib))
        self.assertGreater(first["chunks"], 1)
        from book_logic.retrieval import search
        self.assertTrue(search(self.lib, "capacity", mode="hybrid")["hits"])

    def test_model_and_source_invalidation(self):
        semantic.build(self.lib)
        (self.model / "config.json").write_text('{"changed":true}')
        self.assertEqual(semantic.index_status(self.lib)["state"], "stale")
        semantic.build(self.lib)
        other = self.root / "other.txt"
        other.write_text("another source")
        books.add(self.lib, other)
        self.assertEqual(semantic.index_status(self.lib)["state"], "stale")

    def test_vector_corruption_and_query_budget(self):
        result = semantic.build(self.lib)
        from book_logic.retrieval import search
        with self.assertRaises(Error):
            search(self.lib, "q" * 200, mode="semantic")
        (self.lib.root / "indexes" / result["generation"] / "vectors.npy").write_bytes(b"corrupt")
        with self.assertRaises(Error) as caught:
            search(self.lib, "capacity", mode="semantic")
        self.assertEqual(caught.exception.code, "corrupt_index")

    def test_single_writer_lock(self):
        import fcntl
        with (self.lib.root / "index-writer.lock").open("a") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(Error) as caught:
                semantic.build(self.lib)
            self.assertEqual(caught.exception.code, "busy")
