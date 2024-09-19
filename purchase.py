from trytond.model import fields
from trytond.pool import Pool, PoolMeta
from trytond.modules.account_product.exceptions import AccountError
from trytond.i18n import gettext
from trytond.transaction import Transaction


class Party(metaclass=PoolMeta):
    __name__ = 'party.party'

    purchase_separate_credit_invoice = fields.Boolean('Separate Credit Invoice')

    @staticmethod
    def default_purchase_separate_credit_invoice():
        return False


class Purchase(metaclass=PoolMeta):
    __name__ = 'purchase.purchase'

    @classmethod
    def process(cls, purchases):
        super().process(purchases)
        for purchase in purchases:
            purchase.create_refund_invoice()


    def _get_grouped_invoice_domain(self, invoice):
        transaction = Transaction()
        context = transaction.context

        domain = super()._get_grouped_invoice_domain(invoice)
        if context.get('refund_invoice', False):
            domain.append(('payment_type.kind', '!=', 'payable'))
        return domain

    def create_refund_invoice(self):
        if self.shipment_state != 'received':
            return

        if not self.party.purchase_separate_credit_invoice:
            return

        with Transaction().set_context(refund_invoice=True):
            invoice = self._get_invoice_purchase()
        invoice_lines = []
        for line in self.lines:
            if line.type != 'line':
                continue
            line = line.get_refund_invoice_line()
            if line:
                invoice_lines.append(line)

        if invoice_lines:
            invoice.lines = invoice_lines
            invoice.save()


class PurchaseLine(metaclass=PoolMeta):
    __name__ = 'purchase.line'

    def _get_invoice_line_quantity(self):
        quantity = super()._get_invoice_line_quantity()
        if (not self.purchase.party.purchase_separate_credit_invoice or
                self.purchase.invoice_method == 'order'):
            return quantity

        if any([x.state == 'done' for x in self.moves]):
            return self.quantity
        else:
            return 0

    def _get_invoiced_quantity(self):
        invoiced_qty = super()._get_invoiced_quantity()
        if not self.purchase.party.purchase_separate_credit_invoice:
            return invoiced_qty

        invoiced_quantity = sum([x.quantity for x in self.invoice_lines
                if x.quantity >= 0])
        return invoiced_quantity

    def get_refund_invoice_line(self):
        pool = Pool()
        InvoiceLine = pool.get('account.invoice.line')
        AccountConfiguration = pool.get('account.configuration')
        Uom = pool.get('product.uom')
        account_config = AccountConfiguration(1)

        shipped_qty = 0
        for move in [x for  x in self.moves if x.state == 'done']:
            shipped_qty += Uom.compute_qty(move.unit, move.quantity, self.unit)

        refunded_quantity = sum([x.quantity for x in self.invoice_lines
                if x.quantity < 0])

        refund_qty = shipped_qty - self.quantity
        quantity = Uom.compute_qty(self.unit, refund_qty - refunded_quantity,
            self.unit)

        if quantity >= 0:
            return

        if self.unit:
            quantity = self.unit.round(quantity)

        invoice_line = InvoiceLine()
        invoice_line.type = self.type
        invoice_line.currency = self.currency
        invoice_line.company = self.company
        invoice_line.description = self.description
        invoice_line.note = self.note
        invoice_line.origin = self
        invoice_line.quantity = quantity
        invoice_line.unit = self.unit
        invoice_line.product = self.product
        invoice_line.unit_price = self.unit_price
        invoice_line.taxes = self.taxes
        if self.company.purchase_taxes_expense:
            invoice_line.taxes_deductible_rate = 0
        elif self.product:
            invoice_line.taxes_deductible_rate = (
                self.product.supplier_taxes_deductible_rate_used)
        invoice_line.invoice_type = 'in'
        if self.product:
            invoice_line.account = self.product.account_expense_used
            if not invoice_line.account:
                raise AccountError(
                    gettext('purchase'
                        '.msg_purchase_product_missing_account_expense',
                        purchase=self.purchase.rec_name,
                        product=self.product.rec_name))
        else:
            invoice_line.account = account_config.get_multivalue(
                'default_category_account_expense', company=self.company.id)
            if not invoice_line.account:
                raise AccountError(
                    gettext('purchase'
                        '.msg_purchase_missing_account_expense',
                        purchase=self.purchase.rec_name))
        invoice_line.stock_moves = self.moves_ignored
        return invoice_line
