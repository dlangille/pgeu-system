from collections import OrderedDict
from django.utils.text import Truncator

from postgresqleu.util.backendforms import BackendForm
from postgresqleu.elections.models import Election, Candidate


class BackendCandidateForm(BackendForm):
    helplink = 'elections#candidate'
    markdown_fields = ['presentation', ]

    class Meta:
        model = Candidate
        fields = ['name', 'email', 'presentation', ]


class ElectionCandidateManager(object):
    helplink = 'elections'
    title = 'Candidates'
    singular = 'candidate'
    can_add = True

    def get_list(self, instance):
        if instance.pk:
            return [(c.id, c.name, Truncator(c.presentation).words(30)) for c in instance.candidate_set.all()]

    def get_form(self, obj, POST):
        return BackendCandidateForm

    def get_object(self, masterobj, subjid):
        try:
            return Candidate.objects.get(election=masterobj, pk=subjid)
        except Candidate.DoesNotExist:
            return None

    def get_instancemaker(self, masterobj):
        return lambda: Candidate(election=masterobj)


class BackendElectionForm(BackendForm):
    helplink = 'elections#election'
    list_fields = ['name', 'startdate', 'enddate', 'isactive', 'resultspublic']
    linked_objects = OrderedDict({
        'candidates': ElectionCandidateManager(),
    })
    markdown_fields = ['intro', ]

    class Meta:
        model = Election
        fields = ['name', 'startdate', 'enddate', 'slots', 'intro', 'isactive', 'resultspublic', ]
