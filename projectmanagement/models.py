from datetime import datetime
from django.db import models
from django.db.models import Avg
from simple_history.models import HistoricalRecords
from polymorphic.models import PolymorphicModel
from django.contrib.auth import get_user_model
from django.forms import model_to_dict
from uuid import uuid4

from annotators.models import PrivateAnnotator, PublicAnnotator


class Project(PolymorphicModel):
    name = models.CharField(max_length=255, verbose_name='Project Name')
    description = models.TextField(verbose_name='Project Description')
    url = models.UUIDField(
        unique=True, editable=False, default=uuid4, verbose_name='Project URL'
    )
    administrators = models.ManyToManyField(
        # A single project can have many administrators
        # A single administrator can admin many projects
        get_user_model(), blank=True, verbose_name='Project Administrators'
    )
    talk_markdown = models.TextField(
        null=True, blank=True, verbose_name='Project Talk Markdown'
    )
    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name='Project Created at'
    )
    updated_at = models.DateTimeField(
        auto_now=True, verbose_name='Project Created at'
    )

    @property
    def imported_texts(self):
        raise NotImplementedError

    @property
    def entries(self):
        raise NotImplementedError

    @property
    def project_type(self):
        raise NotImplementedError

    @property
    def value_fields(self):
        raise NotImplementedError

    @property
    def private_annotators(self):
        return PrivateAnnotator.objects.filter(project=self)

    def contributor_is_admin(self, contributor):
        return self.administrators.filter(id=contributor.id).exists()

    def get_imported_entry(self, entry_id):
        raise NotImplementedError

    def add_entry(self, contributor, entry_data):
        raise NotImplementedError

    def add_unannotated_entries(self, **kwargs):
        # All types of projects have different structure of
        #   preannotations and therefore, arguments cannot
        #   be described other than the generic **kwargs
        raise NotImplementedError

    def get_annotators_annotations(self, annotator):
        raise NotImplementedError

    def get_statistics(self):
        raise NotImplementedError


class ProjectEntry(PolymorphicModel):
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE,
        verbose_name='Project'
    )
    unannotated_source = models.ForeignKey(
        'UnannotatedProjectEntry', on_delete=models.CASCADE,
        verbose_name='Unannotated Source'
    )
    annotator = models.ForeignKey(
        'annotators.Annotator', on_delete=models.CASCADE,
        verbose_name='Annotator'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Project Entry Created at'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Project Entry Created at'
    )
    history = HistoricalRecords()

    @property
    def values(self):
        raise NotImplementedError

    def update_with_data(self, update_data):
        raise NotImplementedError


class UnannotatedProjectEntry(PolymorphicModel):
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE,
        verbose_name='Project'
    )
    text = models.TextField(verbose_name='Unannotated Text')
    context = models.TextField(null=True, blank=True, verbose_name='Context')
    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name='Unannotated Entry Created at'
    )
    updated_at = models.DateTimeField(
        auto_now=True, verbose_name='Unannotated Entry Created at'
    )

    @property
    def pre_annotations(self):
        raise NotImplementedError

    @property
    def parameters(self):
        raise NotImplementedError


class TextClassificationProjectEntry(ProjectEntry):
    classification = models.ForeignKey(
        'Category', on_delete=models.DO_NOTHING,
        verbose_name='Classification'
    )

    @property
    def values(self):
        return {'category': self.classification}

    def update_with_data(self, update_data):
        if not update_data.classification:
            return 400, {'detail': 'Missing classification in update data'}
        try:
            classification = Category.objects.get(
                name=update_data.classification, project=self.project
            )
        except Category.DoesNotExist:
            return 404, {'detail': f'Category {update_data.classification} does not exist in project {self.project.name}'}
        self.classification = classification
        self.updated_at = datetime.now()
        self.save()
        return 200, model_to_dict(self)


class MachineTranslationProjectEntry(ProjectEntry):
    fluency = models.FloatField(verbose_name='Fluency')
    adequacy = models.FloatField(verbose_name='Adequacy')

    @property
    def values(self):
        return {
            'fluency': self.fluency,
            'adequacy': self.adequacy
        }

    def update_with_data(self, update_data):
        if update_data.fluency:
            self.fluency = update_data.fluency
        if update_data.adequacy:
            self.adequacy = update_data.adequacy
        self.updated_at = datetime.now()
        self.save()
        return 200, model_to_dict(self)


class TextClassificationProject(Project):
    @property
    def imported_texts(self):
        return TextClassificationProjectUnannotatedEntry.objects.filter(project=self)

    @property
    def project_type(self):
        return 'Text Classification'

    @property
    def categories(self):
        return Category.objects.filter(project=self)

    @property
    def entries(self):
        return TextClassificationProjectEntry.objects.filter(project=self)

    @property
    def value_fields(self):
        return ['classification']

    def get_imported_entry(self, entry_id):
        return TextClassificationProjectUnannotatedEntry.objects.get(id=entry_id, project=self)

    def add_entry(self, annotator, entry_data):
        try:
            category = Category.objects.get(
                project=self, name=entry_data.payload['category-name'])
        except KeyError:
            return 404, {'detail': f'Missing category name in payload'}
        except Category.DoesNotExist:
            return 404, {'detail': f'Category {entry_data["category-name"]} does not exist in project {self.name}'}
        try:
            unannotated_source = UnannotatedProjectEntry.objects.get(
                id=entry_data.unannotated_source, project=self
            )
        except UnannotatedProjectEntry.DoesNotExist:
            return 404, {
                'detail': f'''
                    Unannotated source with ID: {entry_data.unannotated_source} 
                    does not exist in project {self.name}
                '''
            }
        new_entry = TextClassificationProjectEntry.objects.create(
            project=self, classification=category,
            unannotated_source=unannotated_source,
            annotator=annotator
        )
        return {
            **model_to_dict(new_entry),
            'project': self.name,
            'project_type': self.project_type,
            'project_url': str(self.url),
            'unannotated_source': model_to_dict(new_entry.unannotated_source),
            'value_fields': self.value_fields,
            'pre_annotations': new_entry.unannotated_source.pre_annotations,
            'created_at': new_entry.created_at.isoformat(),
            'updated_at': new_entry.updated_at.isoformat(),
            'context': new_entry.unannotated_source.context if new_entry.unannotated_source.context is not None else 'No context'
        }

    def add_unannotated_entries(self, unannotated_data, text_field, value_field, context_field):
        # start by running data integrity checks
        # on the uploaded data to ensure that
        # if preannotations are present, all categories
        # exist and that data is well formated
        for index, entry in enumerate(unannotated_data):
            if type(entry) != dict:
                return 400, {'detail': f'Uploaded data is not in a list of dictionaries format'}
            if value_field is not None:
                try:
                    Category.objects.get(project=self, name=entry[value_field])
                except Category.DoesNotExist:
                    return 400, {
                        'detail': f'''
                            Uploaded data contains category {entry[value_field]}, 
                            that does not exist in project {self.name}
                        '''
                    }
            if context_field is not None and context_field not in entry:
                return 400, {'detail': f'Context field provided, but row with index {index} is missing context value'}
            if text_field not in entry:
                return 400, {'detail': f'Text field missing from row with index {index}'}

        # data has been checked for integrity violations
        # and now can be added to the database
        for entry in unannotated_data:
            pre_annotation = None
            context = entry.get(context_field, None)
            if value_field is not None:
                pre_annotation = Category.objects.get(
                    project=self, name=entry[value_field]
                )
            TextClassificationProjectUnannotatedEntry.objects.create(
                project=self, text=entry[text_field],
                context=context, pre_annotation=pre_annotation
            )

        return 200, {'detail': f'Succesfully created {len(unannotated_data)} unannotated entries'}

    def get_annotators_annotations(self, annotator):
        return TextClassificationProjectEntry.objects.filter(project=self, annotator=annotator)

    def get_statistics(self):
        return {
            'categories': [
                {
                    'name': category.name,
                    'total_entries': self.entries.filter(classification=category).count()
                }
                for category in self.categories
            ]
        }


class MachineTranslationProject(Project):
    @property
    def imported_texts(self):
        return MachineTranslationProjectUnannotatedEntry.objects.filter(project=self)

    @property
    def project_type(self):
        return 'Machine Translation'

    @property
    def entries(self):
        return MachineTranslationProjectEntry.objects.filter(project=self)

    @property
    def value_fields(self):
        return ['fluency', 'adequacy']

    def get_imported_entry(self, entry_id):
        return MachineTranslationProjectUnannotatedEntry.objects.get(id=entry_id, project=self)

    def add_entry(self, annotator, entry_data):
        if None in [entry_data.payload.get('adequacy', None), entry_data.payload.get('fluency', None)]:
            return 400, {'details': 'Missing data in request'}
        try:
            unannotated_source = UnannotatedProjectEntry.objects.get(
                id=entry_data.unannotated_source, project=self
            )
        except UnannotatedProjectEntry.DoesNotExist:
            return 404, {
                'detail': f'''
                    Unannotated source with ID: {entry_data.unannotated_source} 
                    does not exist in project {self.name}
                '''
            }
        new_entry = MachineTranslationProjectEntry.objects.create(
            project=self, adequacy=entry_data.payload.get('adequacy', None),
            fluency=entry_data.payload.get('fluency', None),
            unannotated_source=unannotated_source,
            annotator=annotator
        )
        return {
            **model_to_dict(new_entry),
            'project': self.name,
            'project_type': self.project_type,
            'project_url': str(self.url),
            'unannotated_source': model_to_dict(new_entry.unannotated_source),
            'value_fields': self.value_fields,
            'pre_annotations': new_entry.unannotated_source.pre_annotations,
            'created_at': new_entry.created_at.isoformat(),
            'updated_at': new_entry.updated_at.isoformat(),
            'context': new_entry.unannotated_source.context if new_entry.unannotated_source.context is not None else 'No context'
        }

    def add_unannotated_entries(self, unannotated_data, text_field, context_field, **kwargs):
        # start by running data integrity checks
        # on the uploaded data to ensure that
        # data is well formated
        reference_translation_field = text_field['reference_field']
        machine_translation_system_translation_field = text_field['mt_system_translation']

        for index, entry in enumerate(unannotated_data):
            if type(entry) != dict:
                return 400, {'detail': f'Uploaded data is not in a list of dictionaries format'}
            if context_field is not None and context_field not in entry:
                return 400, {'detail': f'Context field provided, but row with index {index} is missing context value'}
            if reference_translation_field not in entry:
                return 400, {'detail': f'Reference translation field missing from row with index {index}'}
            if machine_translation_system_translation_field not in entry:
                return 400, {'detail': f'Reference translation field missing from row with index {index}'}

        # data has been checked for integrity violations
        # and now can be added to the database
        for entry in unannotated_data:
            context = entry.get(context_field, None)
            MachineTranslationProjectUnannotatedEntry.objects.create(
                project=self, text=entry[reference_translation_field],
                mt_system_translation=entry[machine_translation_system_translation_field],
                context=context
            )

        return 200, {'detail': f'Succesfully created {len(unannotated_data)} unannotated entries'}

    def get_annotators_annotations(self, annotator):
        return MachineTranslationProjectEntry.objects.filter(project=self, annotator=annotator)

    def get_statistics(self):
        # https://stackoverflow.com/questions/28607727/how-to-calculate-average-in-django/50087144#50087144
        fluency = self.entries.values('fluency')
        adequacy = self.entries.values('adequacy')
        return {
            'averages': {
                'fluency': fluency.aggregate(avg_fluency=Avg('fluency')),
                'adequacy': adequacy.aggregate(avg_adequacy=Avg('adequacy'))
            }
        }


class Category(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    name = models.CharField(max_length=255, verbose_name='Category Name')
    description = models.CharField(
        max_length=255, verbose_name='Category Description'
    )
    # It is more convinient for contributors to annotate
    # when the category is associated with a keybinding,
    # which is saved as a string and processed on frontend
    key_binding = models.CharField(max_length=255, verbose_name='Key Bindnig')
    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name='Category Created at'
    )
    updated_at = models.DateTimeField(
        auto_now=True, verbose_name='Category Created at'
    )


class TextClassificationProjectUnannotatedEntry(UnannotatedProjectEntry):
    pre_annotation = models.ForeignKey(
        'Category', on_delete=models.DO_NOTHING,
        null=True, blank=True,
        verbose_name='Pre-annotation classification'
    )

    @property
    def pre_annotations(self):
        return {
            'category': self.pre_annotation
            if self.pre_annotation is not None
            else 'No preannotation'
        }

    @property
    def parameters(self):
        return {'text': self.text}


class MachineTranslationProjectUnannotatedEntry(UnannotatedProjectEntry):
    mt_system_translation = models.TextField(
        verbose_name='Reference Translation'
    )

    pre_annotation_adequacy = models.FloatField(
        null=True, blank=True,
        verbose_name='Pre-annotation adequacy'
    )
    pre_annotation_fluency = models.FloatField(
        null=True, blank=True,
        verbose_name='Pre-annotation fluency'
    )

    @property
    def pre_annotations(self):
        return_dict = {
            'adequacy': 'No annotation',
            'fluency': 'No annotation'
        }

        if self.pre_annotation_adequacy:
            return_dict['adequacy'] = self.pre_annotation_adequacy

        if self.pre_annotation_fluency:
            return_dict['fluency'] = self.pre_annotation_fluency

        return return_dict

    @property
    def parameters(self):
        return {'reference_translation': self.text, 'mt_system_translation': self.mt_system_translation}
