# This file is part account_invoice_in_credit module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
from trytond.tests.test_tryton import ModuleTestCase


class AccountInvoiceInCreditTestCase(ModuleTestCase):
    'Test Account Invoice In Credit module'
    module = 'purchase_separate_credit_invoice'

del ModuleTestCase
