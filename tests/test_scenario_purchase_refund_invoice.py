import unittest
from decimal import Decimal

from proteus import Model
from trytond.modules.account.tests.tools import (create_chart,
                                                 create_fiscalyear, create_tax,
                                                 get_accounts)
from trytond.modules.account_invoice.tests.tools import (
    create_payment_term, set_fiscalyear_invoice_sequences)
from trytond.modules.company.tests.tools import create_company, get_company
from trytond.tests.test_tryton import drop_db
from trytond.tests.tools import activate_modules, set_user


class Test(unittest.TestCase):

    def setUp(self):
        drop_db()
        super().setUp()

    def tearDown(self):
        drop_db()
        super().tearDown()

    def test(self):

        # Activate modules
        config = activate_modules('purchase_separate_credit_invoice')

        # Create company
        _ = create_company()
        company = get_company()

        User = Model.get('res.user')
        Group = Model.get('res.group')

        # Set employee
        User = Model.get('res.user')
        Party = Model.get('party.party')
        Employee = Model.get('company.employee')
        employee_party = Party(name="Employee")
        employee_party.save()
        employee = Employee(party=employee_party)
        employee.save()
        user = User(config.user)
        user.employees.append(employee)
        user.employee = employee
        user.save()

        #Create stock user::
        stock_user = User()
        stock_user.name = 'Stock'
        stock_user.login = 'stock'
        purchase_group, = Group.find([('name', '=', 'Purchase')])
        stock_user.groups.append(purchase_group)
        stock_group, = Group.find([('name', '=', 'Stock')])
        stock_force_group, = Group.find([
            ('name', '=', 'Stock Force Assignment')])
        product_admin_group, = Group.find([
            ('name', '=', "Product Administration")])
        stock_user.groups.append(stock_group)
        stock_user.groups.append(stock_force_group)
        stock_user.groups.append(product_admin_group)
        stock_user.save()

        # Create fiscal year
        fiscalyear = set_fiscalyear_invoice_sequences(
            create_fiscalyear(company))
        fiscalyear.click('create_period')

        # Create chart of accounts
        _ = create_chart(company)
        accounts = get_accounts(company)
        revenue = accounts['revenue']
        expense = accounts['expense']
        cash = accounts['cash']
        Journal = Model.get('account.journal')
        PaymentMethod = Model.get('account.invoice.payment.method')
        cash_journal, = Journal.find([('type', '=', 'cash')])
        cash_journal.save()
        payment_method = PaymentMethod()
        payment_method.name = 'Cash'
        payment_method.journal = cash_journal
        payment_method.credit_account = cash
        payment_method.debit_account = cash
        payment_method.save()

        # Create tax
        tax = create_tax(Decimal('.10'))
        tax.save()

        # Create parties
        Party = Model.get('party.party')
        supplier = Party(name='Supplier')
        supplier.customer_code = '1234'
        supplier.save()
        separate_invoice_supplier = Party(name='Separate Invoice Supplier')
        separate_invoice_supplier.customer_code = 'safe'
        separate_invoice_supplier.purchase_separate_credit_invoice = True
        separate_invoice_supplier.save()

        # Create account categories
        ProductCategory = Model.get('product.category')
        account_category = ProductCategory(name="Account Category")
        account_category.accounting = True
        account_category.account_expense = expense
        account_category.account_revenue = revenue
        account_category.save()
        account_category_tax, = account_category.duplicate()
        account_category_tax.supplier_taxes.append(tax)
        account_category_tax.save()

        # Create product
        ProductUom = Model.get('product.uom')
        unit, = ProductUom.find([('name', '=', 'Unit')])
        ProductTemplate = Model.get('product.template')
        template = ProductTemplate()
        template.name = 'product'
        template.default_uom = unit
        template.type = 'goods'
        template.purchasable = True
        template.list_price = Decimal('10')
        template.cost_price_method = 'fixed'
        template.account_category = account_category_tax
        template.purchasable = True
        product, = template.products
        product.active = True

        product.cost_price = Decimal('5')
        template.save()
        product, = template.products

        # Create payment term
        payment_term = create_payment_term()
        payment_term.save()


        set_user(stock_user.id)

        # Purchase 2 products with an invoice method 'on shipment'
        Purchase = Model.get('purchase.purchase')
        PurchaseLine = Model.get('purchase.line')
        purchase = Purchase()
        purchase.party = supplier
        purchase.payment_term = payment_term
        purchase.invoice_method = 'shipment'
        purchase_line = PurchaseLine()
        purchase.lines.append(purchase_line)
        purchase_line.product = product
        purchase_line.quantity = 2.0
        purchase.save()
        purchase.click('quote')
        purchase.click('confirm')

        self.assertEqual(purchase.state, 'processing')
        self.assertEqual(purchase.shipment_state, 'waiting')
        self.assertEqual(purchase.invoice_state, 'none')
        self.assertEqual(len(purchase.moves), 1)
        self.assertEqual(len(purchase.shipment_returns), 0)
        self.assertEqual(len(purchase.invoices), 0)


        # Validate Shipments
        Move = Model.get('stock.move')
        ShipmentIn = Model.get('stock.shipment.in')
        shipment = ShipmentIn()
        shipment.supplier = supplier
        for move in purchase.moves:
            incoming_move = Move(id=move.id)
            incoming_move.quantity = 1.0
            shipment.incoming_moves.append(incoming_move)
        shipment.save()
        self.assertEqual(shipment.origins, purchase.rec_name)
        shipment.click('receive')
        shipment.click('done')
        purchase.reload()
        self.assertEqual(purchase.shipment_state, 'partially shipped')
        self.assertEqual(len(purchase.shipments), 1)
        self.assertEqual(len(purchase.shipment_returns), 0)
        self.assertEqual(len(purchase.invoices), 1)

        # Purchase 2 products with an invoice method 'on shipment'
        Purchase = Model.get('purchase.purchase')
        PurchaseLine = Model.get('purchase.line')
        purchase = Purchase()
        purchase.party = separate_invoice_supplier
        purchase.payment_term = payment_term
        purchase.invoice_method = 'shipment'
        purchase_line = purchase.lines.new()
        purchase_line.product = product
        purchase_line.quantity = 2.0
        purchase_line = purchase.lines.new()
        purchase_line.product = product
        purchase_line.quantity = 3.0
        purchase.click('quote')
        purchase.click('confirm')
        self.assertEqual(purchase.state, 'processing')
        self.assertEqual(purchase.shipment_state, 'waiting')
        self.assertEqual(purchase.invoice_state, 'none')
        self.assertEqual(len(purchase.moves), 2)
        self.assertEqual(len(purchase.shipment_returns), 0)
        self.assertEqual(len(purchase.invoices), 0)


        # Validate Shipments
        Move = Model.get('stock.move')
        ShipmentIn = Model.get('stock.shipment.in')
        shipment = ShipmentIn()
        shipment.supplier = supplier
        for move in purchase.moves:
            incoming_move = Move(id=move.id)
            incoming_move.quantity = 1.0
            shipment.incoming_moves.append(incoming_move)
        shipment.save()
        self.assertEqual(shipment.origins, purchase.rec_name)
        shipment.click('receive')
        shipment.click('done')
        purchase.reload()
        self.assertEqual(purchase.shipment_state, 'partially shipped')
        self.assertEqual(len(purchase.shipments), 1)
        self.assertEqual(len(purchase.shipment_returns), 0)
        self.assertEqual(len(purchase.invoices), 1)

        # Create and Cancel shipment
        shipment = ShipmentIn()
        shipment.supplier = supplier
        for move in purchase.moves:
            if move.state == 'done':
                continue
            incoming_move = Move(id=move.id)
            shipment.incoming_moves.append(incoming_move)
        shipment.save()

        set_user(stock_user.id)
        shipment.click('cancel')
        self.assertEqual(shipment.state, 'cancelled')
        purchase.reload()
        self.assertEqual(purchase.shipment_state, 'exception')
        self.assertEqual(len(purchase.shipments), 2)
        self.assertEqual(len(purchase.invoices), 1)

        # handle shipment exception
        handle_exception = purchase.click('handle_shipment_exception')
        handle_exception.form.recreate_moves.clear()

        handle_exception.execute('handle')
        purchase.reload()
        self.assertEqual(purchase.shipment_state, 'received')
        self.assertEqual(len(purchase.shipments), 2)
        self.assertEqual(len(purchase.invoices), 2)

        # check invoices
        invoice, credit_invoice = purchase.invoices
        self.assertEqual(invoice.untaxed_amount, Decimal('10'))
        self.assertEqual(credit_invoice.untaxed_amount, Decimal('-15'))
