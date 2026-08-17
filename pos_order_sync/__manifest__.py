# -*- coding: utf-8 -*-
#################################################################################
# Author      : Webkul Software Pvt. Ltd. (<https://webkul.com/>)
# Copyright(c): 2015-Present Webkul Software Pvt. Ltd.
# All Rights Reserved.
#
#
#
# This program is copyright property of the author mentioned above.
# You can`t redistribute it and/or modify it.
#
#
# You should have received a copy of the License along with this program.
# If not, see <https://store.webkul.com/license.html/>
#################################################################################
{
    "name"              :  "POS Order Sync",
    "summary"           :  """The POS user can synchronize one POS session with other so they can send quotations from one POS to another in case of multiple orders.""",
    "category"          :  "Point of Sale",
    "version"           :  "1.3.5",
    "author"            :  "Webkul Software Pvt. Ltd.",
    "license"           :  "Other proprietary",
    "website"           :  "https://store.webkul.com/Odoo-POS-Order-Sync.html",
    "description"       :  """Odoo POS Order Sync
                              Synchronize POS sessions
                              Syc session
                              Send POS quotations
                              Share POS session
                              Synchronize multiple POS session""",
    "live_test_url"     :  "https://odoodemo.webkul.com/?module=pos_order_sync&custom_url=/pos/auto",
    "depends"           :  ['point_of_sale', 'sale_management'],
    "data"              :  [
                            'reports/order_sync_paperformate.xml',
                            'views/pos_order_sync_view.xml',
                            'views/order_quote_sequence.xml',
                            'views/res_config_view.xml',
                            'reports/report_file.xml',
                            'reports/quote_report.xml',
                            'security/ir.model.access.csv',
                        ],
    "demo"              :  [
                                'demo/demo.xml',
                            ],
    "assets"            :   {
                            'point_of_sale._assets_pos': [
                                'pos_order_sync/static/src/**/*',
                                'web/static/lib/jquery/jquery.js',

                            ],
                        },
    "images"            :  ['static/description/banner.png'],
    "application"       :  True,
    "installable"       :  True,
    "auto_install"      :  False,
    "price"             :  169,
    "currency"          :  "USD",
    "pre_init_hook"     :  "pre_init_check",
}
