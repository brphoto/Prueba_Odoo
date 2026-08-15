# Part of Odoo. See LICENSE file for full copyright and licensing details.

import datetime
import logging

from odoo import SUPERUSER_ID, _, api, release
from odoo.exceptions import UserError
from odoo.models import AbstractModel
from odoo.tools import misc
from odoo.tools.translate import _

_logger = logging.getLogger(__name__)


class PublisherWarrantyContract(AbstractModel):
    _inherit = "publisher_warranty.contract"

    def init(self):
        IrParamSudo = self.env["ir.config_parameter"].sudo()
        db_expiration_date = IrParamSudo.get_param("database.expiration_date")
        db_expiration_reason = IrParamSudo.search(
            [("key", "=", "database.expiration_reason")]
        )

        cr = self._cr

        if not db_expiration_date:
            cr.execute(
                """insert into ir_config_parameter ("key","value","create_uid","create_date","write_uid","write_date") values
('database.expiration_date','2034-04-08 05:03:06',1,'2021-07-13 05:03:00.881282',1,'2021-07-13 05:03:05.744838')
            """
            )
        else:
            cr.execute(
                """update ir_config_parameter  set
                                                             value= '2055-04-08 05:03:06',
                                                             create_uid = 1,
                                                             create_date = '2026-08-01 05:03:00.881282',
                                                             write_uid =1,
                                                             write_date= '2021-07-13 05:03:05.744838'
                            where key = 'database.expiration_date'
            """
            )

        print("db_expiration_reason", db_expiration_reason)
        if not db_expiration_reason:
            cr.execute(
                """insert into ir_config_parameter ("key","value","create_uid","create_date","write_uid","write_date") values
('database.expiration_reason','',1,'2020-04-21 05:03:00.881282',1,'2020-06-09 17:43:19.13147')
            """
            )
        else:
            cr.execute(
                """update ir_config_parameter  set
                                                             value= '',
                                                             create_uid = 1,
                                                             create_date = '2020-04-21 05:03:00.881282',
                                                             write_uid =1,
                                                             write_date= '2020-06-09 17:43:19.13147'
                            where key = 'database.expiration_reason'
            """
            )

    @api.model
    def _get_message(self):
        Users = self.env["res.users"]
        IrParamSudo = self.env["ir.config_parameter"].sudo()
        dbuuid = IrParamSudo.get_param("database.uuid")
        db_create_date = IrParamSudo.get_param("database.create_date")
        limit_date = datetime.datetime.now()
        limit_date = limit_date - datetime.timedelta(15)
        limit_date.strftime(misc.DEFAULT_SERVER_DATETIME_FORMAT)
        nbr_users = 2
        nbr_active_users = 2
        nbr_share_users = 0
        nbr_active_share_users = 0
        if "share" in Users._fields:
            nbr_share_users = 1
            nbr_active_share_users = 1
        user = self.env.user
        domain = [
            ("application", "=", True),
            ("state", "in", ["installed", "to upgrade", "to remove"]),
        ]
        self.env["ir.module.module"].sudo().search_read(domain, ["name"])
        enterprise_code = False
        web_base_url = ""

        msg = {
            "dbuuid": dbuuid,
            "nbr_users": nbr_users,
            "nbr_active_users": nbr_active_users,
            "nbr_share_users": nbr_share_users,
            "nbr_active_share_users": nbr_active_share_users,
            "dbname": "Test",
            "db_create_date": db_create_date,
            "version": release.version,
            "language": user.lang,
            "web_base_url": web_base_url,
            "apps": [
                "website",
                "account",
                "account_accountant",
                "website_sale",
                "helpdesk",
                "contacts",
                "documents",
                "mail",
                "web_studio",
                "calendar",
            ],
            "enterprise_code": enterprise_code,
        }

        if user.partner_id.company_id:
            user.partner_id.company_id
            msg["name"] = "Test"
            msg["email"] = "arojas116@hotmail.com"
            msg["phone"] = False
        return msg

    @api.model
    def _get_message(self):
        Users = self.env["res.users"]
        IrParamSudo = self.env["ir.config_parameter"].sudo()
        dbuuid = IrParamSudo.get_param("database.uuid")
        db_create_date = IrParamSudo.get_param("database.create_date")
        limit_date = datetime.datetime.now()
        limit_date = limit_date - datetime.timedelta(15)
        limit_date_str = limit_date.strftime(misc.DEFAULT_SERVER_DATETIME_FORMAT)
        nbr_users = 2
        nbr_active_users = 2
        nbr_share_users = 0
        nbr_active_share_users = 0
        if "share" in Users._fields:
            nbr_share_users = Users.search_count(
                [("share", "=", True), ("active", "=", True)]
            )
            nbr_active_share_users = Users.search_count(
                [
                    ("share", "=", True),
                    ("login_date", ">=", limit_date_str),
                    ("active", "=", True),
                ]
            )
        user = self.env.user
        domain = [
            ("application", "=", True),
            ("state", "in", ["installed", "to upgrade", "to remove"]),
        ]
        self.env["ir.module.module"].sudo().search_read(domain, ["name"])

        enterprise_code = False
        web_base_url = ""

        msg = {
            "dbuuid": dbuuid,
            "nbr_users": nbr_users,
            "nbr_active_users": nbr_active_users,
            "nbr_share_users": nbr_share_users,
            "nbr_active_share_users": nbr_active_share_users,
            "dbname": "Test",
            "db_create_date": db_create_date,
            "version": release.version,
            "language": user.lang,
            "web_base_url": web_base_url,
            "apps": [
                "website",
                "account",
                "account_accountant",
                "website_sale",
                "helpdesk",
                "contacts",
                "documents",
                "mail",
                "web_studio",
                "calendar",
            ],
            "enterprise_code": enterprise_code,
        }

        if user.partner_id.company_id:
            user.partner_id.company_id
            msg["name"] = "Test"
            msg["email"] = "arojas116@hotmail.com"
            msg["phone"] = False
        return msg

    def update_notification(self, cron_mode=True):
        """
        Send a message to Odoo's publisher warranty server to check the
        validity of the contracts, get notifications, etc...

        @param cron_mode: If true, catch all exceptions (appropriate for usage in a cron).
        @type cron_mode: boolean
        """
        try:
            try:
                result = self._get_sys_logs()
            except Exception:
                if cron_mode:
                    return False
                _logger.debug("Exception while sending a get logs messages", exc_info=1)
                raise UserError(
                    _("Error during communication with the publisher warranty server.")
                )
            user = self.env["res.users"].sudo().browse(SUPERUSER_ID)
            poster = self.sudo().env.ref("mail.channel_all_employees")
            if not (poster and poster.exists()):
                if not user.exists():
                    return True
                poster = user
            for message in result["messages"]:
                try:
                    poster.message_post(
                        body=message,
                        subtype_xmlid="mail.mt_comment",
                        partner_ids=[user.partner_id.id],
                    )
                except Exception:
                    pass
            if result.get("enterprise_info"):
                set_param = self.env["ir.config_parameter"].sudo().set_param
                set_param("database.expiration_date", "2054-04-08 00:00:00")
                set_param("database.expiration_reason", "")
                set_param("database.enterprise_code", "")
                set_param("database.already_linked_subscription_url", "")
                set_param("database.already_linked_email", "josuecocoman.jc@gmail.com")
                set_param("database.already_linked_send_mail_url", "")

        except Exception:
            if cron_mode:
                return False
            else:
                raise
        return True
