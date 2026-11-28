"""What a FAIL says is wrong: one claim from a closed list (design section 6.1).

The baseline, the model and the oracle all use this list. A claim is a dict:
    {"claim": "wrong_balance", "observed_stock": 6}
    {"claim": "low_stock_warning_missing"}
    {"claim": "other", "text": "..."}
"""

CLAIMS = (
    "over_issue_accepted",           # an issue larger than the stock was accepted
    "negative_stock",                # a part has negative stock
    "wrong_balance",                 # the part's stock is not what the rules give; needs observed_stock
    "movement_log_wrong",            # movements do not match the accepted issues
    "low_stock_warning_missing",     # a low part shows no warning
    "low_stock_warning_unexpected",  # a part that is not low shows a warning
    "other",                         # anything else; needs text; never confirmed automatically
)

# Which claims count as finding each defect. Fixed before any run.
DEFECT_CLAIMS = {
    "DEF-01": ("over_issue_accepted", "negative_stock", "wrong_balance"),
    "DEF-02": ("low_stock_warning_missing",),
    "DEF-03": ("wrong_balance",),
}


class ClaimError(ValueError):
    pass


def validate_claim(claim: dict) -> dict:
    """Check a claim and return it in normal form. Raises ClaimError."""
    if not isinstance(claim, dict):
        raise ClaimError("a claim must be an object")
    name = claim.get("claim")
    if name not in CLAIMS:
        raise ClaimError(f"unknown claim {name!r}; allowed: {', '.join(CLAIMS)}")
    normal = {"claim": name}
    if name == "wrong_balance":
        observed = claim.get("observed_stock")
        if isinstance(observed, bool) or not isinstance(observed, int):
            raise ClaimError("wrong_balance needs observed_stock as a whole number")
        normal["observed_stock"] = observed
    if name == "other":
        text = str(claim.get("text") or "").strip()
        if not text:
            raise ClaimError("other needs a text")
        normal["text"] = text
    return normal


def counts_for(defect_id: str, claim: dict) -> bool:
    """True if this kind of claim counts as finding the defect (truth is checked separately)."""
    return claim.get("claim") in DEFECT_CLAIMS.get(defect_id, ())
