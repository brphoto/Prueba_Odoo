## website_ausencias_19e

Base migration of `website_ausencias` for Odoo 19 Enterprise.

### Main adjustments

- Module renamed to `website_ausencias_19e`.
- Dependencies updated to migrated modules:
  - `l10n_ec_hr_payroll_19e`
  - `hr_initial_values_19e`
- Added explicit `hr_holidays` dependency.
- Replaced legacy XML `attrs=` modifiers with direct Odoo 19 modifiers.
- Removed legacy `@api.multi` usage.
- Replaced deprecated `track_visibility` with `tracking=True`.
- Updated internal XML ID and template references from `website_ausencias.*` to `website_ausencias_19e.*`.
- Updated inherited payroll leave form reference to `l10n_ec_hr_payroll_19e`.

### Remaining validation to do in Odoo 19

1. Install the module on a real Odoo 19 Enterprise database.
2. Validate website leave submission flow end to end.
3. Validate payslip portal rendering and PDF download.
4. Validate leave approval workflow and outgoing email delivery.
