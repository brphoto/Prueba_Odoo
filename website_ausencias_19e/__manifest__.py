# -*- coding: utf-8 -*-
{
    'name': "website_ausencias_19e",

    'summary': """
        Módulo de registro de ausencias Ecuador""",

    

    'author': "Bryan Cando",
    'website': "http://www.yourcompany.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/12.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Uncategorized',
    'version': '19.0.1.0.0',
    'license': 'LGPL-3',

    # any module necessary for this one to work correctly
    'depends': ['base', 'website', 'contacts', 'hr', 'hr_holidays', 'l10n_ec_hr_payroll_19e'],#'hr_initial_values_19e'
    'installable': True,
    'auto_install': False,
    

    # always loaded
    'data': [

        'data/group.xml',
         "security/ir.model.access.csv",
        'views/portal_layout.xml',
        'views/portal_home.xml',
        'views/website_form.xml',
        'views/payslip_form.xml',
       'views/hr_departments.xml',
        'views/hr_leave.xml',
        'views/res_user.xml',
        'views/historyc_leave_user.xml',
        'views/form_employee_data.xml',
        'views/employee_documents.xml',
        'views/employee_cargas_familiares.xml',
        'views/loan_request.xml',
        'views/notifications.xml'



    ]
   
  
}
