from . import models


def post_init_hook(env):
    env["l10n.co.payroll.rule.mapping"].sudo()._sync_default_dian_mappings()
