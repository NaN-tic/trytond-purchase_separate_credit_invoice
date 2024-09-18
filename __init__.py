# This file is part account_invoice_in_credit module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
from trytond.pool import Pool
from . import purchase

def register():
    Pool.register(
        purchase.Party,
        purchase.Purchase,
        purchase.PurchaseLine,
        module='purchase_separate_credit_invoice', type_='model')
