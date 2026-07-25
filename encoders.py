"""
Pluggable text-embedding backends for embedding_filter.py.

LocalEncoder: the original free, local sentence-transformers model
(all-MiniLM-L6-v2) -- no API call, no cost, runs on your own machine.

VoyageEncoder: Anthropic's own recommended embeddings provider (Anthropic
doesn't offer a first-party embedding model -- see
platform.claude.com/docs/en/build-with-claude/embeddings). voyage-4 is
their current balanced/recommended model. Requires VOYAGE_API_KEY in .env.
Free up to 200M tokens/month, then $0.06/million tokens -- for a
short-message classifier like this one, realistic usage stays inside the
free tier (see README.md).

Both backends expose the same encode(texts) -> np.ndarray interface so
embedding_filter.py doesn't need to know which one it's using. Both return
L2-normalized vectors, so similarity is a plain dot product either way --
no dependency on sentence_transformers' util.cos_sim, which only works
with its own tensor type.
"""
import numpy as np
from dotenv import load_dotenv

load_dotenv()


class LocalEncoder:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(model_name)

    def encode(self, texts: list[str]) -> np.ndarray:
        embeddings = self.model.encode(texts, normalize_embeddings=True)
        return np.asarray(embeddings)


class VoyageEncoder:
    def __init__(self, model_name: str = "voyage-4"):
        import voyageai
        self.client = voyageai.Client()
        self.model_name = model_name

    def encode(self, texts: list[str], input_type: str = "document") -> np.ndarray:
        result = self.client.embed(texts, model=self.model_name, input_type=input_type)
        return np.asarray(result.embeddings)
