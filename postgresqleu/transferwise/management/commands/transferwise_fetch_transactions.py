# Fetch transaction list from TransferWise
#
# Copyright (C) 2019, PostgreSQL Europe
#

from django.core.management.base import BaseCommand
from django.db import transaction
from django.conf import settings
from django.utils import timezone

from postgresqleu.util.time import today_global
from postgresqleu.accounting.util import create_accounting_entry
from postgresqleu.invoices.util import is_managed_bank_account
from postgresqleu.invoices.util import register_pending_bank_matcher, register_bank_transaction
from postgresqleu.invoices.util import InvoiceManager
from postgresqleu.invoices.models import InvoicePaymentMethod
from postgresqleu.transferwise.models import TransferwiseTransaction, TransferwiseRefund
from postgresqleu.transferwise.models import TransferwisePayout

from datetime import datetime, timedelta
import re


class Command(BaseCommand):
    help = 'Fetch TransferWise transactions'

    class ScheduledJob:
        scheduled_interval = timedelta(minutes=60)

        @classmethod
        def should_run(self):
            return InvoicePaymentMethod.objects.filter(active=True, classname='postgresqleu.util.payment.transferwise.Transferwise').exists()

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, help="Number of days back to get transactions for")

    @transaction.atomic
    def handle(self, *args, **options):
        if options['days']:
            startdate = today_global() - timedelta(days=options['days'])
        else:
            startdate = None

        for method in InvoicePaymentMethod.objects.filter(active=True, classname='postgresqleu.util.payment.transferwise.Transferwise'):
            self.handle_method(method, startdate=startdate)

    def handle_method(self, method, startdate):
        pm = method.get_implementation()

        api = pm.get_api()

        for t in api.get_transactions(startdate=startdate):
            # We will re-fetch most transactions, so only create them if they are not
            # already there.

            # Seems transactions come in as UNKNOWN and with no text first, and then we get
            # more details later. So if we see one of those, postpone it for up to 2 hours
            # (random magic value).
            if t['details']['type'] == 'UNKNOWN' and \
               t['details']['description'] in ('', 'No information') and \
               datetime.now() - api.parse_datetime(t['date']) < timedelta(hours=2):
                print("Skipping UNKNOWN transaction {}, no data and less than 2 hours old".format(t['referenceNumber']))
                continue

            trans, created = TransferwiseTransaction.objects.get_or_create(
                paymentmethod=method,
                twreference=t['referenceNumber'],
                defaults={
                    'datetime': api.parse_datetime(t['date']),
                    'amount': api.get_structured_amount(t['amount']),
                    'feeamount': api.get_structured_amount(t['totalFees']),
                    'transtype': t['details']['type'],
                    'paymentref': (t['details'].get('paymentReference', '') or '')[:200],
                    'fulldescription': t['details']['description'],
                }
            )
            if created:
                # Set optional fields
                trans.counterpart_name = t['details'].get('senderName', '') or ''
                trans.counterpart_account = t['details'].get('senderAccount', '').replace(' ', '')

                # Sometimes (newer entries?) transferwise adds both the BIC and the IBAN code,
                # and do so in the same field. This is undocumented and not even incuded in
                # their examples, but seems to be persistent enough to process.
                m = re.match(r'^\([A-Z0-9]{8,11}\)([A-Z0-9]+)$', trans.counterpart_account)
                if m:
                    trans.counterpart_account = m.group(1)

                # Weird stuff that sometimes shows up
                if trans.counterpart_account == 'Unknownbankaccount':
                    trans.counterpart_account = ''

                if trans.counterpart_account:
                    # If account is IBAN, then try to validate it!
                    trans.counterpart_valid_iban = api.validate_iban(trans.counterpart_account)
                trans.save()

                # If this is a refund transaction, process it as such
                if trans.transtype == 'TRANSFER' and trans.paymentref.startswith('{0} refund'.format(settings.ORG_SHORTNAME)):
                    # Yes, this is one of our refunds. Can we find the corresponding transaction?
                    m = re.match(r'^TRANSFER-(\d+)$', t['referenceNumber'])
                    if not m:
                        raise Exception("Could not find TRANSFER info in transfer reference {0}".format(t['referenceNumber']))
                    transferid = m.groups(1)[0]
                    try:
                        twrefund = TransferwiseRefund.objects.get(transferid=transferid)
                    except TransferwiseRefund.DoesNotExist:
                        print("Could not find transferwise refund for id {0}, registering as manual bank transaction".format(transferid))
                        register_bank_transaction(method, trans.id, trans.amount, trans.paymentref, trans.fulldescription, False)
                        continue

                    if twrefund.refundtransaction or twrefund.completedat:
                        raise Exception("Transferwise refund for id {0} has already been processed!".format(transferid))

                    # Flag this one as done!
                    twrefund.refundtransaction = trans
                    twrefund.completedat = timezone.now()
                    twrefund.save()

                    invoicemanager = InvoiceManager()
                    invoicemanager.complete_refund(
                        twrefund.refundid,
                        -(trans.amount + trans.feeamount),
                        -trans.feeamount,
                        pm.config('bankaccount'),
                        pm.config('feeaccount'),
                        [],  # urls
                        method,
                    )
                elif trans.transtype == 'TRANSFER' and trans.paymentref.startswith('{0} returned payment'.format(settings.ORG_SHORTNAME)):
                    # Returned payment. Nothing much to do, but we create an accounting record
                    # for it just to make things nice and clear. But first make sure we can
                    # actually find the original transaction.
                    try:
                        po = TransferwisePayout.objects.get(reference=trans.paymentref)
                    except TransferwisePayout.DoesNotExist:
                        raise Exception("Could not find transferwise payout object for {0}".format(trans.paymentref))

                    po.completedat = timezone.now()
                    po.completedtrans = trans
                    po.save()

                    m = re.match(r'^{0} returned payment (\d+)$'.format(settings.ORG_SHORTNAME), trans.paymentref)
                    if not m:
                        raise Exception("Could not find returned transaction id in reference '{0}'".format(trans.paymentref))
                    twtrans = TransferwiseTransaction.objects.get(pk=m.groups(1)[0])
                    if twtrans.amount != -trans.amount - trans.feeamount:
                        raise Exception("Original amount {0} does not match returned amount {1}".format(twtrans.amount, -trans.amount - trans.feeamount))

                    accountingtxt = "TransferWise returned payment {0}".format(trans.twreference)
                    accrows = [
                        (pm.config('bankaccount'), accountingtxt, trans.amount, None),
                        (pm.config('bankaccount'), accountingtxt, -(trans.amount + trans.feeamount), None),
                    ]
                    if trans.feeamount:
                        accrows.append(
                            (pm.config('feeaccount'), accountingtxt, trans.feeamount, None),
                        )
                    create_accounting_entry(accrows)
                elif trans.transtype == 'TRANSFER' and trans.paymentref.startswith('TW payout'):
                    # Payout. Create an appropriate accounting record and a pending matcher.
                    try:
                        po = TransferwisePayout.objects.get(reference=trans.paymentref)
                    except TransferwisePayout.DoesNotExist:
                        raise Exception("Could not find transferwise payout object for {0}".format(trans.paymentref))

                    refno = int(trans.paymentref[len("TW payout "):])

                    if po.amount != -(trans.amount + trans.feeamount):
                        raise Exception("Transferwise payout {0} returned transaction with amount {1} instead of {2}".format(refno, -(trans.amount + trans.feeamount), po.amount))

                    po.completedat = timezone.now()
                    po.completedtrans = trans
                    po.save()

                    # Payout exists at TW, so proceed to generate records. If the receiving account
                    # is a managed one, create a bank matcher. Otherwise just close the record
                    # immediately.
                    accrows = [
                        (pm.config('bankaccount'), trans.paymentref, trans.amount, None),
                        (pm.config('accounting_payout'), trans.paymentref, -(trans.amount + trans.feeamount), None),
                    ]
                    if trans.feeamount:
                        accrows.append(
                            (pm.config('feeaccount'), trans.paymentref, trans.feeamount, None),
                        )
                    if is_managed_bank_account(pm.config('accounting_payout')):
                        entry = create_accounting_entry(accrows, True)
                        register_pending_bank_matcher(pm.config('accounting_payout'),
                                                      '.*TW.*payout.*{0}.*'.format(refno),
                                                      -(trans.amount + trans.feeamount),
                                                      entry)
                    else:
                        create_accounting_entry(accrows)
                else:
                    # Else register a pending bank transaction. This may immediately match an invoice
                    # if it was an invoice payment, in which case the entire process will complete.
                    register_bank_transaction(method,
                                              trans.id,
                                              trans.amount,
                                              trans.paymentref,
                                              trans.fulldescription,
                                              trans.counterpart_valid_iban
                    )
