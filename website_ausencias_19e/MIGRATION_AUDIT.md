# Migration Audit Snapshot

Generated during the Odoo 19 Enterprise migration pass.

## Mechanical status

- `@api.multi`: 0
- `track_visibility`: 0
- XML `attrs=` in module views: 0
- `self.pool.get(...)`: 0
- legacy report abstractions (`report.abstract_report`, `report_sxw`, `rml_parse`): 0
- old-style `.post()` calls: 0

## Runtime areas to validate

- Website routes and QWeb template rendering
- Leave request creation against Odoo 19 `hr.leave`
- Email notifications and mail queue behavior
- Leave approval buttons and inherited leave views
- Portal payslip report rendering
