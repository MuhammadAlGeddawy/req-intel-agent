from ...utils.retriever import hybrid_search_and_rerank
from ...utils.normalization import normalize_asil

# Number of most-similar knowledge-base requirements to surface for each safety
# requirement (used in the report output as `safety.retrieved_requirements`).
RETRIEVAL_LIMIT = 5


def retrieve_context_node(state):
    print("\n[Node retrieve_context] Retrieving relevant historical context...")
    requirements = state.get("classified", [])
    retrieved_context = {}

    for requirement in requirements:
        req_id = requirement.get("id")
        if not req_id:
            continue
        query = requirement.get("text") or requirement.get("req_text") or ""
        results = hybrid_search_and_rerank(query, limit=RETRIEVAL_LIMIT)
        retrieved_context[req_id] = [
            {
                "req_id": item.get("req_id"),
                "req_text": item.get("req_text"),
                "domain": item.get("domain"),
                "asil": item.get("asil"),
                "reasoning": item.get("reasoning"),
                "score": item.get("score"),
            }
            for item in results
            if item.get("req_id") != req_id
        ]

    return {**state, "retrieved_context": retrieved_context}
