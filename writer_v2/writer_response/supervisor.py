# Supervisor + post-fan-out node for the reviewer subgraph
from reviewer.checker import reviewer_produce_violations, reviewer_revalidate_fixes
from writer_response.state import ReviewerRouteState

# Ask the reviewer to find violations (each tagged with target_response_agent)
def run_reviewer(state: ReviewerRouteState) -> dict:
    violations = reviewer_produce_violations(state["section_content"])
    return {"violations": violations}


# Reviewer re-checks each fix (splices into content, reruns produce_violations); survivors become final list
def revalidate_and_filter(state: ReviewerRouteState) -> dict:
    fixes = state["response_suggestions"]
    violations = state["violations"]
    rejected = set(reviewer_revalidate_fixes(state["section_content"], fixes, violations))
    final_response_suggestions = [
        fix for index, fix in enumerate(fixes) if index not in rejected
    ]
    return {"final_response_suggestions": final_response_suggestions}
