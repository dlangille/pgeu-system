from postgresqleu.util.backendviews import backend_list_editor, backend_process_form
from postgresqleu.confreg.util import get_authenticated_conference

from .models import Sponsor
from .backendforms import BackendSponsorForm
from .backendforms import BackendSponsorshipLevelForm
from .backendforms import BackendSponsorshipContractForm
from .backendforms import BackendShipmentAddressForm


def edit_sponsor(request, urlname, sponsorid):
    conference = get_authenticated_conference(request, urlname)
    sponsor = Sponsor.objects.get(conference=conference, pk=sponsorid)

    return backend_process_form(request,
                                urlname,
                                BackendSponsorForm,
                                sponsor.pk,
                                conference=conference,
                                allow_new=False,
                                allow_delete=not sponsor.invoice,
                                deleted_url='../../',
                                breadcrumbs=[
                                    ('/events/sponsor/admin/{0}/'.format(urlname), 'Sponsors'),
                                    ('/events/sponsor/admin/{0}/{1}/'.format(urlname, sponsor.pk), sponsor.name),
                                ])


def edit_sponsorship_levels(request, urlname, rest):
    return backend_list_editor(request,
                               urlname,
                               BackendSponsorshipLevelForm,
                               rest,
                               breadcrumbs=[('/events/sponsor/admin/{0}/'.format(urlname), 'Sponsors'), ])


def edit_sponsorship_contracts(request, urlname, rest):
    return backend_list_editor(request,
                               urlname,
                               BackendSponsorshipContractForm,
                               rest,
                               breadcrumbs=[('/events/sponsor/admin/{0}/'.format(urlname), 'Sponsors'), ])


def edit_shipment_addresses(request, urlname, rest):
    return backend_list_editor(request,
                               urlname,
                               BackendShipmentAddressForm,
                               rest,
                               breadcrumbs=[('/events/sponsor/admin/{0}/'.format(urlname), 'Sponsors'), ])
