"""The paper check's settings on the site: levels per check and stage (CheckRule) and the limits
(CheckLimits), edited in the back office under Settings. checks.configuration() reads them."""

from __future__ import annotations

import json

from .checks import LIMITS, PRODUCTION, RULE_LABELS, default_rules


def load() -> tuple[dict, dict]:
    from .models import CheckLimits, CheckRule

    rules = {rule.code: {"review": rule.review, "camera_ready": rule.camera_ready, PRODUCTION: rule.production}
             for rule in CheckRule.objects.all()}
    limits = CheckLimits.load().as_dict() if CheckLimits.objects.exists() else {}
    return rules, limits


def sync_rules(**kwargs):
    """A row for every check in the code, with the code's defaults; existing rows keep their
    levels (after migrate)."""
    from .models import CheckRule

    defaults = default_rules()
    existing = {rule.code: rule for rule in CheckRule.objects.all()}
    for order, (code, label) in enumerate(RULE_LABELS.items()):
        rule = existing.get(code)
        if rule is None:
            CheckRule.objects.create(code=code, label=label, order=order, **defaults[code])
        elif (rule.label, rule.order) != (label, order):
            rule.label, rule.order = label, order
            rule.save(update_fields=["label", "order"])


def as_json() -> str:
    """The settings in force, for the authors' skill ZIP."""
    from .checks import configuration

    rules, limits = configuration()
    return json.dumps({"rules": rules, "limits": {**LIMITS, **limits}}, indent=1, sort_keys=True)
