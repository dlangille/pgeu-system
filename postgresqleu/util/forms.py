from django import forms
from django.forms import ValidationError
from django.core.signing import Signer, BadSignature
from django.contrib.postgres.fields import ArrayField
from django.forms.widgets import FILE_INPUT_CONTRADICTION

import pickle
import base64
from itertools import groupby

from .widgets import InlineImageUploadWidget, InlinePdfUploadWidget


class _ValidatorField(forms.Field):
    required = True
    widget = forms.HiddenInput


class ConcurrentProtectedModelForm(forms.ModelForm):
    _validator = _ValidatorField()
    exclude_fields_from_validation = []

    def _filter_initial(self):
        # self.initial will include things given in the URL after ?, so filter it to
        # only include items that are actually form fields.
        return {k: v for k, v in list(self.initial.items()) if k in list(self.fields.keys()) and k not in self.exclude_fields_from_validation}

    def update_protected_fields(self):
        self.fields['_validator'].initial = Signer().sign(base64.urlsafe_b64encode(pickle.dumps(self._filter_initial(), -1)))

    def __init__(self, *args, **kwargs):
        r = super(ConcurrentProtectedModelForm, self).__init__(*args, **kwargs)
        self.update_protected_fields()
        return r

    def clean(self):
        # Process the form itself
        data = super(ConcurrentProtectedModelForm, self).clean()

        if not self.instance.pk:
            # No primary key, means instance was not previously saved, so there can be
            # no concurrent edit.
            return data

        # Fetch the list of values from the currernt object in the db
        i = self._filter_initial()
        try:
            s = Signer().unsign(self.cleaned_data['_validator'])
            b = base64.urlsafe_b64decode(s.encode('utf8'))
            d = pickle.loads(b)
            for k, v in list(d.items()):
                if i[k] != v:
                    raise ValidationError("Concurrent modification of field {0}. Please reload the form and try again.".format(k))
        except BadSignature:
            raise ValidationError("Form has been tampered with!")
        except TypeError:
            raise ValidationError("Bad serialized form state")
        except pickle.UnpicklingError:
            raise ValidationError("Bad serialized python form state")

        return data


class ChoiceArrayField(ArrayField):
    def formfield(self, **kwargs):
        defaults = {
            'form_class': forms.MultipleChoiceField,
            'choices': self.base_field.choices,
        }
        defaults.update(kwargs)
        return super(ArrayField, self).formfield(**defaults)


class GroupedIterator(forms.models.ModelChoiceIterator):
    def __iter__(self):
        for group, choices in groupby(self.queryset.all().order_by(self.field.groupfield, *self.field.orderby),
                                      key=lambda x: getattr(x, self.field.groupfield)):
            yield (group,
                   [self.choice(c) for c in choices])


class Grouped(object):
    def __init__(self, groupfield, queryset, *args, **kwargs):
        self.orderby = queryset.query.order_by
        super(Grouped, self).__init__(*args, queryset=queryset, **kwargs)
        self.groupfield = groupfield

    def _get_choices(self):
        return GroupedIterator(self)


class GroupedModelMultipleChoiceField(Grouped, forms.ModelMultipleChoiceField):
    choices = property(Grouped._get_choices, forms.ModelMultipleChoiceField._set_choices)


class IntegerBooleanField(forms.BooleanField):
    def to_python(self, value):
        return value and 1 or 0

    def prepare_value(self, value):
        return value and True or False


class CharToArrayField(forms.CharField):
    def to_python(self, value):
        return [x.strip() for x in value.split(',') if x.strip()]

    def prepare_value(self, value):
        if isinstance(value, list):
            return ", ".join(value)
        else:
            return value


class ImageBinaryFormField(forms.Field):
    widget = InlineImageUploadWidget

    def to_python(self, value):
        if value is False:
            # Value gets set to False if the clear checkbox is marked
            return None
        if value == FILE_INPUT_CONTRADICTION:
            # This gets set if the user *both* uploads a new file *and* marks the clear checkbox
            return None
        if value is None:
            return None
        return value.read()

    def prepare_value(self, value):
        return value

    def clean(self, data, initial=None):
        if data is False:
            if not self.required:
                return False
            data = None
        if not data and initial:
            return initial
        return super(ImageBinaryFormField, self).clean(data)


class PdfBinaryFormField(ImageBinaryFormField):
    widget = InlinePdfUploadWidget
