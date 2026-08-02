"""
Standalone test for the safety assessment LLM node.
Reads sample_requirements.txt, extracts requirements, classifies safety relevance via LLM,
then runs safety ASIL assessment on safety-relevant items.

Usage:
    cd backend && python ../test_safety_node_local.py
"""
import json
import sys
import os
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from src.utils.parsers import extract_requirements
from src.llm.client import call_llm, call_llm_json, MODEL
from src.llm.prompts import CLASSIFY_SYSTEM_PROMPT, SAFETY_ASSESS_SYSTEM_PROMPT


def load_and_parse_sample():
    """Load sample_requirements.txt and parse into requirement dicts."""
    sample_path = Path(__file__).resolve().parent / "sample_requirements.txt"
    if not sample_path.exists():
        print(f"❌ File not found: {sample_path}")
        sys.exit(1)

    with open(sample_path, "r", encoding="utf-8") as f:
        raw_text = f.read()

    print(f"📄 Loaded: {sample_path.name} ({len(raw_text)} chars)")
    requirements = extract_requirements(raw_text)
    print(f"📋 Extracted {len(requirements)} requirements\n")
    return requirements


def classify_safety_relevance(requirements):
    """
    Send requirements to LLM classifier to flag safety-relevant ones.
    Returns classified list with safety_relevant and safety_reason fields.
    """
    print(f"{'='*70}")
    print("  STEP 1: CLASSIFY SAFETY RELEVANCE (LLM)")
    print(f"{'='*70}\n")

    req_list_json = json.dumps(requirements, indent=2)
    user = f"""Requirements (domains already extracted via regex):\n{req_list_json}

Classify ONLY safety relevance. Preserve existing domains. Return ONLY safety_relevant and safety_reason."""

    print("  📤 Sending to classifier LLM...")
    try:
        result = call_llm_json(CLASSIFY_SYSTEM_PROMPT, user, max_tokens=1000, schema_hint="classification output")
    except Exception as e:
        print(f"  ❌ LLM classification failed: {e}")
        # Fallback: mark domain=SAFETY as safety-relevant
        print("  ⚠️  Falling back: SAFETY domain items marked as safety-relevant\n")
        classified = []
        for r in requirements:
            is_safety = r.get("domain") == "SAFETY"
            classified.append({**r, "safety_relevant": is_safety, "safety_reason": "Domain: SAFETY" if is_safety else None})
        return classified

    # Merge LLM results with original requirements
    req_dict = {r["id"]: r for r in requirements}
    llm_classified = result.get("classified", [])
    classified = []

    for lc in llm_classified:
        req_id = lc.get("id")
        if req_id in req_dict:
            req = req_dict[req_id].copy()
            req["safety_relevant"] = lc.get("safety_relevant", False)
            req["safety_reason"] = lc.get("safety_reason")
            classified.append(req)
        else:
            print(f"  ⚠️  LLM returned unknown req ID: {req_id}")

    # Fallback for any missing
    for req_id, req in req_dict.items():
        if req_id not in {lc.get("id") for lc in llm_classified}:
            req["safety_relevant"] = False
            req["safety_reason"] = None
            classified.append(req)

    safety_count = sum(1 for r in classified if r.get("safety_relevant"))
    print(f"  ✅ Classification done! {safety_count} safety-relevant found\n")

    # Print summary
    for r in classified:
        flag = "⚠️ SAFETY" if r.get("safety_relevant") else "    OK"
        print(f"  {flag} | {r['id']:15s} | {r.get('domain', '?'):8s} | {r.get('text', '')[:70]}")

    print()
    return classified


def assess_safety_levels(classified, retrieved_context=None):
    """
    Send each safety-relevant requirement to LLM for ASIL assessment.
    Uses the same prompt as the safety node in the pipeline.
    """
    safety_reqs = [r for r in classified if r.get("safety_relevant")]
    if not safety_reqs:
        print("  ℹ️  No safety-relevant requirements to assess.\n")
        return []

    print(f"{'='*70}")
    print(f"  STEP 2: SAFETY ASIL ASSESSMENT (LLM)")
    print(f"  {len(safety_reqs)} requirements to assess")
    print(f"{'='*70}\n")

    if retrieved_context is None:
        retrieved_context = {}

    assessments = []
    for req in safety_reqs:
        print(f"{'─'*70}")
        print(f"  📋 {req['id']} | {req['domain']}")
        print(f"     {req['text'][:100]}")
        print(f"     Reason: {req.get('safety_reason', 'N/A')}")
        print(f"{'─'*70}")

        # Build historical context block (replicates safety.py logic)
        context_items = retrieved_context.get(req.get("id"), [])
        if context_items:
            lines = []
            for item in context_items:
                lines.append(
                    f"- {item.get('req_id')} | {item.get('domain', 'UNKNOWN')} | {item.get('req_text')} | score={item.get('score', 0)}"
                )
            historical_block = "Historical context for this requirement:\n" + "\n".join(lines)
        else:
            historical_block = "No historical context available."

        system = SAFETY_ASSESS_SYSTEM_PROMPT.format(historical_context_block=historical_block)
        user = f"Assess this safety requirement:\n{json.dumps(req, indent=2)}"

        print(f"\n  📤 Sending to LLM (model: {MODEL})...")

        try:
            system_with_json = (
                system
                + "\n\nIMPORTANT: Respond ONLY with valid JSON. "
                "No markdown, no explanation, no code blocks. "
                "Start your response directly with { and end with }."
            )
            raw_output = call_llm(system_with_json, user, max_tokens=800)

            print(f"\n  📥 RAW LLM OUTPUT:")
            print(f"  {raw_output}")

            # Parse JSON
            try:
                parsed = json.loads(raw_output)
            except json.JSONDecodeError:
                import re
                match = re.search(r'\{.*\}', raw_output, re.DOTALL)
                if match:
                    parsed = json.loads(match.group())
                else:
                    raise

            assessment = parsed.get("assessments", [{}])[0] if parsed.get("assessments") else {}
            assessment["id"] = req.get("id")
            assessments.append(assessment)

            # Extract values with null-safe fallback
            asil = assessment.get("suggested_asil")
            sev = assessment.get("severity")
            exp = assessment.get("exposure")
            cont = assessment.get("controllability")
            rat = assessment.get("rationale", "")[:100] if assessment.get("rationale") else ""
            hr = assessment.get("human_review_required")

            print(f"\n  ✅ ASSESSMENT:")
            print(f"     suggested_asil:       {asil or '⚠️ None → QM (fallback)'}")
            print(f"     severity:             {sev or '⚠️ None → S0 (fallback)'}")
            print(f"     exposure:             {exp or '⚠️ None → E0 (fallback)'}")
            print(f"     controllability:      {cont or '⚠️ None → C0 (fallback)'}")
            print(f"     rationale:            {rat or '⚠️ None → Not assessed (fallback)'}")
            print(f"     human_review_required: {hr}")

            # Determine field ordering compliance
            if assessment:
                keys = list(assessment.keys())
                expected_prefix = ["id", "suggested_asil", "severity", "exposure", "controllability", "rationale", "human_review_required"]
                matches = sum(1 for i, k in enumerate(keys) if i < len(expected_prefix) and k == expected_prefix[i])
                print(f"     field_order_match:    {matches}/{len(expected_prefix)}")

        except Exception as e:
            print(f"  ❌ ERROR: {e}")
            # Still record with null defaults
            assessments.append({
                "id": req.get("id"),
                "suggested_asil": None,
                "severity": None,
                "exposure": None,
                "controllability": None,
                "rationale": None,
            })

        print()

    print(f"{'='*70}")
    print(f"  ASSESSMENT SUMMARY:")
    print(f"{'='*70}")
    for a in assessments:
        asil = a.get("suggested_asil") or "QM (fallback)"
        sev = a.get("severity") or "S0"
        exp = a.get("exposure") or "E0"
        cont = a.get("controllability") or "C0"
        print(f"  {a.get('id'):15s} | ASIL-{asil:4s} | S:{sev} E:{exp} C:{cont}")

    return assessments


if __name__ == "__main__":
    print(f"{'='*70}")
    print(f"  SAFETY NODE END-TO-END TEST")
    print(f"  Model: {MODEL}")
    print(f"  Source: sample_requirements.txt")
    print(f"{'='*70}\n")

    # Step 0: Load and parse sample requirements
    requirements = load_and_parse_sample()

    # Step 1: Classify safety relevance via LLM
    classified = classify_safety_relevance(requirements)

    # Step 2: Assess safety levels via LLM
    assessments = assess_safety_levels(classified)

    print(f"\n{'='*70}")
    print(f"  TEST COMPLETE")
    print(f"  Total requirements:  {len(requirements)}")
    print(f"  Safety-relevant:     {sum(1 for r in classified if r.get('safety_relevant'))}")
    print(f"  Assessments made:    {len(assessments)}")
    print(f"{'='*70}")
