# Process reports from Adyen. This includes downloading them for storage,
# as well as processing the contents.
#
# Copyright (C) 2013, PostgreSQL Europe
#
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.conf import settings

import re
import csv
import io
import os
import sys
import traceback

import requests
from requests.auth import HTTPBasicAuth
from datetime import timedelta
from decimal import Decimal

from postgresqleu.adyen.models import AdyenLog, Report, TransactionStatus
from postgresqleu.mailqueue.util import send_simple_mail
from postgresqleu.accounting.util import create_accounting_entry
from postgresqleu.invoices.util import is_managed_bank_account
from postgresqleu.invoices.util import register_pending_bank_matcher


class Command(BaseCommand):
    help = 'Download and/or process reports from Adyen'

    class ScheduledJob:
        scheduled_interval = timedelta(minutes=30)

        @classmethod
        def should_run(self):
            return Report.objects.filter(Q(downloadedat__isnull=True) | Q(processedat__isnull=True)).exists()

    def add_arguments(self, parser):
        parser.add_argument('--only', choices=('download', 'process'))
        parser.add_argument('-q', '--quiet', action='store_true')

    def handle(self, *args, **options):
        self.verbose = not options['quiet']

        if options['only'] in (None, 'download'):
            self.download_reports()

        if options['only'] in (None, 'process'):
            self.process_reports()

    def download_reports(self):
        # Download all currently pending reports (that we can)
        for report in Report.objects.filter(downloadedat=None).order_by('receivedat'):
            pm = report.paymentmethod.get_implementation()
            if not report.url.endswith('.csv'):
                with transaction.atomic():
                    report.downloadedat = timezone.now()
                    report.processedat = timezone.now()
                    report.save()
                    if report.url.endswith('.pdf') or report.url.endswith('.xlsx'):
                        # For known file-types, just log it and not as an error.
                        AdyenLog(message="Report {} is not of type csv, ignoring but flagging as downloaded and processed".format(report.url), error=False, paymentmethod=report.paymentmethod).save()
                    else:
                        # For unknown types, log as an error in case this is something broken.
                        AdyenLog(message="Report {} is of unknown type, ignoring but flagging as downloaded and processed".format(report.url), error=True, paymentmethod=report.paymentmethod).save()
                continue

            # Now that we know it's a CSV, download the contents of the report
            try:
                with transaction.atomic():
                    if self.verbose:
                        self.stdout.write("Downloading {0}".format(report.url))
                    resp = requests.get(report.url,
                                        auth=HTTPBasicAuth(pm.config('report_user'), pm.config('report_password')))
                    if resp.status_code != 200:
                        self.stderr.write("Downloaded report {0} and got status code {1}. Not storing, will try again.".format(report.url, resp.status_code))
                    elif len(resp.text) == 0:
                        self.stderr.write("Downloaded report {0} and got zero bytes (no header). Not storing, will try again.".format(report.url))
                    else:
                        report.downloadedat = timezone.now()
                        report.contents = resp.text
                        report.save()
                        AdyenLog(message='Downloaded report {0}'.format(report.url), error=False, paymentmethod=report.paymentmethod).save()
            except Exception as ex:
                self.stderr.write("Failed to download report {0}: {1}".format(report.url, ex))
                # This might fail again if we had a db problem, but it should be OK as long as it
                # was just a download issue which is most likely.
                AdyenLog(message='Failed to download report %s: %s' % (report.url, ex), error=True, paymentmethod=report.paymentmethod).save()

    def process_payment_accounting_report(self, report):
        method = report.paymentmethod
        pm = method.get_implementation()

        sio = io.StringIO(report.contents)
        reader = csv.DictReader(sio, delimiter=',')
        for line in reader:
            # SentForSettle is what we call capture, so we track that
            # Settled is when we actually receive the money
            # Changes in Sep 2015 means Settled is sometimes SettledBulk
            # Everything else we ignore
            if line['Record Type'] == 'SentForSettle' or line['Record Type'] == 'Settled' or line['Record Type'] == 'SettledBulk':
                # Find the actual payment
                pspref = line['Psp Reference']
                bookdate = line['Booking Date']
                try:
                    trans = TransactionStatus.objects.get(pspReference=pspref, paymentmethod=method)
                except TransactionStatus.DoesNotExist:
                    # Yes, for now we rollback the whole processing of this one
                    raise Exception('Transaction %s not found!' % pspref)
                if line['Record Type'] == 'SentForSettle':
                    # If this is a POS transaction, it typically received a
                    # separate CAPTURE notification, in which case the capture
                    # date is already set. But if not, we'll set it to the
                    # sent for settle date.
                    if not trans.capturedat:
                        trans.capturedat = bookdate
                        trans.method = line['Payment Method']
                        trans.save()
                        AdyenLog(message='Transaction %s captured at %s' % (pspref, bookdate), error=False, paymentmethod=method).save()
                        if self.verbose:
                            self.stdout.write("Sent for settle on {0}".format(pspref))
                elif line['Record Type'] in ('Settled', 'SettledBulk'):
                    if trans.settledat is not None:
                        # Transaction already settled. But we might be reprocessing
                        # the report, so verify if the previously settled one is
                        # *identical*.
                        if trans.settledamount == Decimal(line['Main Amount']).quantize(Decimal('0.01')):
                            self.stderr.write("Transaction {0} already settled at {1}, ignoring (NOT creating accounting record)!".format(pspref, trans.settledat))
                            continue
                        else:
                            raise CommandError('Transaction {0} settled more than once with a different amount?!'.format(pspref))
                    if not trans.capturedat:
                        trans.capturedat = bookdate

                    trans.settledat = bookdate
                    trans.settledamount = Decimal(line['Main Amount']).quantize(Decimal('0.01'))
                    trans.save()
                    if self.verbose:
                        self.stdout.write("Settled {0}, total amount {1}".format(pspref, trans.settledamount))
                    AdyenLog(message='Transaction %s settled at %s' % (pspref, bookdate), error=False, paymentmethod=method).save()

                    # Settled transactions create a booking entry
                    accstr = "Adyen settlement %s" % pspref
                    accrows = [
                        (pm.config('accounting_authorized'), accstr, -trans.amount, None),
                        (pm.config('accounting_payable'), accstr, trans.settledamount, None),
                        (pm.config('accounting_fee'), accstr, trans.amount - trans.settledamount, trans.accounting_object),
                        ]
                    create_accounting_entry(accrows, False)

    def process_received_payments_report(self, report):
        # We don't currently do anything with this report, but we store the contents
        # of them in case we might need them in the future.
        pass

    def process_settlement_detail_report_batch(self, report):
        # Summarize the settlement detail report in an email to to treasurer@, so they
        # can keep track of what's going on.
        method = report.paymentmethod
        pm = method.get_implementation()

        # Get the batch number from the url
        batchnum = re.search(r'settlement_detail_report_batch_(\d+).csv$', report.url).groups(1)[0]

        # Now summarize the contents
        sio = io.StringIO(report.contents)
        reader = csv.DictReader(sio, delimiter=',')
        types = {}
        for line in reader:
            t = line['Type']
            if t == 'Balancetransfer':
                # Balance transfer is special -- we can have two of them that evens out,
                # but we need to separate in and out
                if Decimal(line['Net Debit (NC)'] or 0) > 0:
                    t = "Balancetransfer2"

            lamount = Decimal(line['Net Credit (NC)'] or 0) - Decimal(line['Net Debit (NC)'] or 0)
            if t in types:
                types[t] += lamount
            else:
                types[t] = lamount

        def sort_types(a):
            # Special sort method that just ensures that Settled always ends up at the top
            # and the rest is just alphabetically sorted. (And yes, this is ugly code :P)
            if a[0] == 'Settled' or a[0] == 'SettledBulk':
                return 'AAA'
            return a[0]

        msg = "\n".join(["%-20s: %s" % (k, v) for k, v in sorted(iter(types.items()), key=sort_types)])
        acct = report.notification.merchantAccountCode

        # Generate an accounting record, iff we know what every row on the
        # statement actually is.
        acctrows = []
        accstr = "Adyen settlement batch %s for %s" % (batchnum, acct)
        payout_amount = 0
        for t, amount in list(types.items()):
            if t == 'Settled' or t == 'SettledBulk':
                # Settled means we took it out of the payable balance
                acctrows.append((pm.config('accounting_payable'), accstr, -amount, None))
            elif t == 'MerchantPayout':
                # Amount directly into our checking account
                acctrows.append((pm.config('accounting_payout'), accstr, -amount, None))
                # Payouts show up as negative, so we have to reverse the sign
                payout_amount -= amount
            elif t in ('DepositCorrection', 'Balancetransfer', 'Balancetransfer2', 'ReserveAdjustment'):
                # Modification of our deposit account - in either direction!
                acctrows.append((pm.config('accounting_merchant'), accstr, -amount, None))
            elif t == 'InvoiceDeduction':
                # Adjustment of the invoiced costs. So adjust the payment fees!
                acctrows.append((pm.config('accounting_fee'), accstr, -amount, None))
            elif t == 'Refunded' or t == 'RefundedBulk':
                # Refunded - should already be booked against the refunding account
                acctrows.append((pm.config('accounting_refunds'), accstr, -amount, None))
            else:
                # Other rows that we don't know about will generate an open accounting entry
                # for manual fixing.
                pass
        if len(acctrows) == len(types):
            # If all entries were processed, the accounting entry should
            # automatically be balanced by now, so we can safely just complete it.
            # If payout is to a managed bank account (and there is a payout), we register
            # the payout for processing there and leave the entry open. If not, then we
            # just close it right away.
            is_managed = is_managed_bank_account(pm.config('accounting_payout'))
            if is_managed and payout_amount > 0:
                entry = create_accounting_entry(acctrows, True)

                # Register a pending bank transfer using the syntax that Adyen are
                # currently using. We only match the most important keywords, just
                # but it should still be safe against most other possibilities.
                register_pending_bank_matcher(pm.config('accounting_payout'),
                                              '.*ADYEN.*BATCH {0}[ ,].*'.format(batchnum),
                                              payout_amount,
                                              entry)
                msg = "A settlement batch with Adyen has completed for merchant account %s. A summary of the entries are:\n\n%s\n\nAccounting entry %s was created and will automatically be closed once the payout has arrived." % (acct, msg, entry)
            else:
                # Close immediately
                create_accounting_entry(acctrows, False)

                msg = "A settlement batch with Adyen has completed for merchant account %s. A summary of the entries are:\n\n%s\n\n" % (acct, msg)
        else:
            # All entries were not processed, so we write what we know to the
            # db, and then just leave the entry open.
            create_accounting_entry(acctrows, True)

            msg = "A settlement batch with Adyen has completed for merchant account %s. At least one entry in this was UNKNOWN, and therefor the accounting record has been left open, and needs to be adjusted manually!\nA summary of the entries are:\n\n%s\n\n" % (acct, msg)

        send_simple_mail(settings.INVOICE_SENDER_EMAIL,
                         pm.config('notification_receiver'),
                         'Adyen settlement batch %s completed' % batchnum,
                         msg
                         )

    def process_reports(self):
        # Process all downloaded but unprocessed reports

        for report in Report.objects.filter(downloadedat__isnull=False, processedat=None).order_by('downloadedat'):
            try:
                with transaction.atomic():
                    if self.verbose:
                        self.stdout.write("Processing {0}".format(report.url))

                    # To know what to do, we look at the filename of the report URL
                    filename = report.url.split('/')[-1]
                    if filename.startswith('payments_accounting_report_'):
                        self.process_payment_accounting_report(report)
                    elif filename.startswith('received_payments_report'):
                        self.process_received_payments_report(report)
                    elif filename.startswith('settlement_detail_report_batch_'):
                        self.process_settlement_detail_report_batch(report)
                    else:
                        raise CommandError('Unknown report type in file "{0}"'.format(filename))

                    # If successful, flag as processed and add the log
                    report.processedat = timezone.now()
                    report.save()
                    AdyenLog(message='Processed report %s' % report.url, error=False, paymentmethod=report.paymentmethod).save()
            except Exception as ex:
                exc_type, exc_obj, exc_tb = sys.exc_info()
                self.stderr.write("Failed to process report {0}: {1} at line {2} of {3}".format(report.url, ex, exc_tb.tb_lineno, os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]))
                self.stderr.write(traceback.format_exc())
                AdyenLog(message='Failed to process report %s: %s' % (report.url, ex), error=True, paymentmethod=report.paymentmethod).save()
