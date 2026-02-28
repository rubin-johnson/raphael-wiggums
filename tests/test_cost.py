from execute.cost import parse_escalation, model_for_attempt, total_max_retries


def test_parse_single_tier():
    tiers = parse_escalation("sonnet:3")
    assert len(tiers) == 1
    assert tiers[0].model == "sonnet"
    assert tiers[0].max_attempts == 3


def test_parse_two_tiers():
    tiers = parse_escalation("sonnet:3,opus:2")
    assert len(tiers) == 2
    assert tiers[0].model == "sonnet"
    assert tiers[0].max_attempts == 3
    assert tiers[1].model == "opus"
    assert tiers[1].max_attempts == 2


def test_model_for_attempt_first_tier():
    tiers = parse_escalation("sonnet:3,opus:2")
    assert model_for_attempt(tiers, 1) == "sonnet"
    assert model_for_attempt(tiers, 2) == "sonnet"
    assert model_for_attempt(tiers, 3) == "sonnet"


def test_model_for_attempt_escalates():
    tiers = parse_escalation("sonnet:3,opus:2")
    assert model_for_attempt(tiers, 4) == "opus"
    assert model_for_attempt(tiers, 5) == "opus"


def test_model_for_attempt_beyond_tiers_uses_last():
    tiers = parse_escalation("sonnet:3,opus:2")
    assert model_for_attempt(tiers, 99) == "opus"


def test_total_max_retries():
    tiers = parse_escalation("sonnet:3,opus:2")
    assert total_max_retries(tiers) == 4  # 5 total attempts - 1


def test_parse_with_spaces():
    tiers = parse_escalation("sonnet: 3, opus: 2")
    assert tiers[0].model == "sonnet"
    assert tiers[1].model == "opus"
