import json
import math
import os
import re
import threading
from typing import Any


from ..db import RequirementEmbedding, session_scope
from ..llm.client import get_embeddings


# NOTE: Optional cross-encoder reranking requires HYBRID_CROSS_ENCODER_MODEL
# (a HuggingFace model compatible with AutoModelForSequenceClassification).


_LOCK = threading.RLock()


class _RetrieverState:
    def __init__(self) -> None:
        self._bm25_ready = False
        self._documents: list[dict[str, Any]] = []
        self._vocabulary: set[str] = set()
        self._doc_freq: dict[str, int] = {}
        self._avg_doc_len = 0.0

    def reset(self) -> None:
        self._bm25_ready = False
        self._documents = []
        self._vocabulary = set()
        self._doc_freq = {}
        self._avg_doc_len = 0.0


_RETRIEVER_STATE = _RetrieverState()


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _build_bm25_index(documents: list[dict[str, Any]]) -> None:
    state = _RETRIEVER_STATE
    state.reset()
    state._documents = documents
    for doc in documents:
        tokens = _tokenize(doc.get("req_text", ""))
        for token in set(tokens):
            state._doc_freq[token] = state._doc_freq.get(token, 0) + 1
        state._vocabulary.update(tokens)
        state._avg_doc_len += len(tokens)
    if documents:
        state._avg_doc_len /= len(documents)
    state._bm25_ready = True


def _bm25_score(query: str, document: dict[str, Any]) -> float:
    state = _RETRIEVER_STATE
    if not state._bm25_ready:
        return 0.0

    query_tokens = _tokenize(query)
    if not query_tokens:
        return 0.0

    doc_tokens = _tokenize(document.get("req_text", ""))
    if not doc_tokens:
        return 0.0

    doc_len = len(doc_tokens)
    avg_doc_len = max(state._avg_doc_len, 1.0)
    k1 = 1.5
    b = 0.75
    score = 0.0
    term_freq = {}
    for token in doc_tokens:
        term_freq[token] = term_freq.get(token, 0) + 1

    for token in query_tokens:
        if token not in state._doc_freq:
            continue
        tf = term_freq.get(token, 0)
        doc_freq = state._doc_freq[token]
        idf = math.log((1 + (len(state._documents) - doc_freq + 0.5)) / (doc_freq + 0.5) + 1.0)
        normalized_tf = tf * (k1 + 1) / (tf + k1 * (1 - b + b * doc_len / avg_doc_len))
        score += idf * normalized_tf
    return score


def _coerce_embedding(value: Any, fallback_text: str) -> list[float]:
    if isinstance(value, (list, tuple)):
        try:
            return [float(item) for item in value]
        except Exception:
            pass
    if isinstance(value, str):
        try:
            payload = json.loads(value)
            if isinstance(payload, list):
                return [float(item) for item in payload]
        except Exception:
            pass
    return _fallback_embedding(fallback_text)


def _fallback_embedding(text: str) -> list[float]:
    tokens = _tokenize(text)
    vector = [0.0] * 1536
    for token in tokens:
        index = abs(hash(token)) % 1536
        vector[index] += 1.0
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    if len(left) != len(right):
        right = right[: len(left)] if len(right) > len(left) else right + [0.0] * (len(left) - len(right))
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (left_norm * right_norm)


def _fetch_requirements() -> list[dict[str, Any]]:
    # Important on SQLite/Windows: the SQLAlchemy session closes when we exit
    # session_scope(). We must materialize all ORM attributes *inside* the
    # active session to avoid DetachedInstanceError.
    with session_scope() as db:
        rows = db.query(RequirementEmbedding).all()
        documents = [
            {
                "req_id": row.req_id,
                "domain": row.domain,
                "req_text": row.req_text,
                "asil": row.asil,
                "reasoning": row.reasoning,
                "embedding": _coerce_embedding(getattr(row, "embedding", None), row.req_text),
            }
            for row in rows
        ]
    return documents



def _get_query_embedding(query: str) -> list[float]:
    try:
        embeddings = get_embeddings([query])
        if embeddings:
            return [float(value) for value in embeddings[0]]
    except Exception:
        pass
    return _fallback_embedding(query)


def hybrid_search_and_rerank(query: str, limit: int = 4) -> list[dict[str, Any]]:
    """Perform dense+sparse retrieval and rerank results using RRF.

    Note: A cross-encoder reranker can be enabled via HYBRID_CROSS_ENCODER_MODEL.
    If it's unavailable, the function falls back to RRF only.
    """

    documents = _fetch_requirements()
    if not documents:
        return []

    with _LOCK:
        _build_bm25_index(documents)
        query_embedding = _get_query_embedding(query)

        dense_scores = []
        for index, document in enumerate(documents):
            dense_scores.append((index, _cosine_similarity(query_embedding, document["embedding"])))

        sparse_scores = []
        for index, document in enumerate(documents):
            sparse_scores.append((index, _bm25_score(query, document)))

        dense_scores.sort(key=lambda item: item[1], reverse=True)
        sparse_scores.sort(key=lambda item: item[1], reverse=True)

        ranked: list[tuple[float, int]] = []
        for dense_rank, (index, _) in enumerate(dense_scores, start=1):
            sparse_rank = next((rank for rank, (candidate_index, _) in enumerate(sparse_scores, start=1) if candidate_index == index), len(documents))
            rrf_score = 1.0 / (60 + dense_rank) + 1.0 / (60 + sparse_rank)
            ranked.append((rrf_score, index))

        ranked.sort(key=lambda item: item[0], reverse=True)

        # Build baseline ranking (RRF) with clean scores.
        candidates: list[tuple[float, int]] = ranked[: max(limit, 20)]
        final_results = []
        for rrf_score, index in candidates:
            document = documents[index]
            final_results.append(
                {
                    "req_id": document["req_id"],
                    "domain": document["domain"],
                    "req_text": document["req_text"],
                    "asil": document.get("asil"),
                    "reasoning": document.get("reasoning"),
                    "score": round(float(rrf_score), 4),
                    "retrieval_sources": ["dense", "sparse"],
                }
            )

        # Optional cross-encoder reranking
        try:
            cross_encoder_model = os.getenv("HYBRID_CROSS_ENCODER_MODEL")
            if cross_encoder_model and final_results:
                from transformers import AutoModelForSequenceClassification, AutoTokenizer
                import torch

                tokenizer = AutoTokenizer.from_pretrained(cross_encoder_model)
                model = AutoModelForSequenceClassification.from_pretrained(cross_encoder_model)
                model.eval()

                def _score_pairs(q: str, docs: list[dict[str, Any]]) -> list[float]:
                    scores: list[float] = []
                    # Score in small batches for memory safety.
                    batch_size = 8
                    for start in range(0, len(docs), batch_size):
                        batch = docs[start : start + batch_size]
                        pairs = [(q, d["req_text"]) for d in batch]
                        inputs = tokenizer(
                            [p[0] for p in pairs],
                            [p[1] for p in pairs],
                            padding=True,
                            truncation=True,
                            return_tensors="pt",
                        )
                        with torch.no_grad():
                            out = model(**inputs)
                            logits = out.logits
                            # If shape is (bs, 1) reduce to (bs,)
                            if logits.dim() > 1:
                                logits = logits.squeeze(-1)
                            scores.extend(logits.detach().cpu().tolist())
                    return [float(s) for s in scores]

                query_scores = _score_pairs(query, final_results)
                reranked = sorted(
                    zip(query_scores, final_results),
                    key=lambda t: t[0],
                    reverse=True,
                )

                # Replace score with reranker score (keeping RRF as retrieval baseline)
                reranked_final = []
                for s, item in reranked[:limit]:
                    item = dict(item)
                    item["reranker_score"] = round(float(s), 6)
                    item["retrieval_sources"] = ["dense", "sparse", "cross_encoder"]
                    reranked_final.append(item)

                return reranked_final
        except Exception:
            # Cross-encoder is optional; ignore failures and return RRF results.
            pass

        return final_results[:limit]

