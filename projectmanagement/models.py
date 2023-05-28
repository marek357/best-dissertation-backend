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
    character_level_selection = models.BooleanField(
        null=True, verbose_name='Character or Word level selection'
    )

    @property
    def imported_texts(self):
        return UnannotatedProjectEntry.objects.filter(project=self)

    @property
    def entries(self):
        return ProjectEntry.objects.filter(project=self)

    @property
    def unannotated_texts(self):
        annotated = self.entries.values('unannotated_source')
        return self.imported_texts.exclude(id__in=annotated)

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
        return UnannotatedProjectEntry.objects.get(id=entry_id, project=self)

    def add_entry(self, contributor, entry_data):
        raise NotImplementedError

    def add_unannotated_entries(self, **kwargs):
        # All types of projects have different structure of
        #   preannotations and therefore, arguments cannot
        #   be described other than the generic **kwargs
        raise NotImplementedError

    def get_annotators_annotations(self, annotator):
        return ProjectEntry.objects.filter(project=self, annotator=annotator)

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

    @property
    def non_standard_fix(self):
        # if a project entry contains a field that
        # is not JSON serialisable, it needs to be
        # serialised by overriding this property
        return {}

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


class TextHighlight(PolymorphicModel):
    mistranslation_source = models.ForeignKey(
        'TextHighlight', on_delete=models.CASCADE, null=True)
    span_start = models.IntegerField(verbose_name='Beginning of text span')
    span_end = models.IntegerField(verbose_name='End of text span')
    category = models.CharField(
        max_length=255, verbose_name='Text span category'
    )


class NERTextHighlight(PolymorphicModel):
    span_start = models.IntegerField(verbose_name='Beginning of text span')
    span_end = models.IntegerField(verbose_name='End of text span')
    category = models.ForeignKey('Category', on_delete=models.DO_NOTHING)


class NamedEntityRecognitionProjectEntry(ProjectEntry):
    ner_text_highlights = models.ManyToManyField(
        NERTextHighlight, blank=True, verbose_name='Named Entity Recognition Text Highlights'
    )

    @property
    def values(self):
        return {
            'ner_text_highlights': [
                (highlight.span_start, highlight.span_end, highlight.category.name)
                for highlight in self.ner_text_highlights.all()
            ]
        }

    @property
    def non_standard_fix(self):
        return {
            'ner_text_highlights': [
                (highlight.span_start, highlight.span_end, highlight.category.name)
                for highlight in self.ner_text_highlights.all()
            ],
        }


class TextClassificationProjectEntry(ProjectEntry):
    classification = models.ForeignKey(
        'Category', on_delete=models.DO_NOTHING,
        verbose_name='Classification'
    )

    @property
    def values(self):
        return {'category': self.classification.name}

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


class MachineTranslationAdequacyProjectEntry(ProjectEntry):
    annotator_comment = models.TextField(null=True, blank=True)
    adequacy = models.FloatField(verbose_name='Adequacy')
    source_text_highlights = models.ManyToManyField(
        TextHighlight, blank=True, verbose_name='Machine Translation Adequacy Source Text Highlights', related_name='adequacy_source_text'
    )
    target_text_highlights = models.ManyToManyField(
        TextHighlight, blank=True, verbose_name='Machine Translation Adequacy Target Text Highlights'
    )

    @property
    def values(self):
        return {
            'adequacy': self.adequacy
        }

    @property
    def non_standard_fix(self):
        text_source = self.unannotated_source.text
        text_target = self.unannotated_source.mt_system_translation
        return {
            'source_text_highlights': [
                (
                    f'{text_source[:highlight.span_start]}<s>{text_source[highlight.span_start:highlight.span_end+1]}</s>{text_source[highlight.span_end+1:]}',
                    highlight.span_start, highlight.span_end, highlight.category
                )
                # https://stackoverflow.com/questions/9003518/django-equivalent-of-sql-not-in
                for highlight in self.source_text_highlights.exclude(category__in=['Mistranslation'])
            ],
            'target_text_highlights': [
                (
                    f'{text_target[:highlight.span_start]}<s>{text_target[highlight.span_start:highlight.span_end+1]}</s>{text_target[highlight.span_end+1:]}',
                    f'''{text_source[:highlight.mistranslation_source.span_start]}<s>{text_source[highlight.mistranslation_source.span_start:highlight.mistranslation_source.span_end+1]}</s>{text_source[highlight.mistranslation_source.span_end+1:]}'''
                    if highlight.category == 'Mistranslation'
                    else 'Not mistranslation annotation',
                    highlight.span_start, highlight.span_end, highlight.category
                )
                for highlight in self.target_text_highlights.all()
            ],
        }

    def update_with_data(self, update_data):
        if update_data.adequacy:
            self.adequacy = update_data.adequacy
        self.updated_at = datetime.now()
        self.save()
        return 200, model_to_dict(self)


class MachineTranslationFluencyProjectEntry(ProjectEntry):
    annotator_comment = models.TextField(null=True, blank=True)
    target_text_highlights = models.ManyToManyField(
        TextHighlight, blank=True, verbose_name='Machine Translation Fluency Highlights', related_name='fluency_source_text'
    )
    fluency = models.FloatField(verbose_name='Fluency')

    @property
    def values(self):
        return {
            'fluency': self.fluency,
        }

    @property
    def non_standard_fix(self):
        text_target = self.unannotated_source.mt_system_translation
        return {
            'target_text_highlights': [
                (
                    f'{text_target[:highlight.span_start]}<s>{text_target[highlight.span_start:highlight.span_end+1]}</s>{text_target[highlight.span_end+1:]}',
                    highlight.span_start, highlight.span_end, highlight.category
                )
                for highlight in self.target_text_highlights.all()
            ],
        }

    def update_with_data(self, update_data):
        if update_data.fluency:
            self.fluency = update_data.fluency
        self.updated_at = datetime.now()
        self.save()
        return 200, model_to_dict(self)


class TextClassificationProject(Project):
    @property
    def project_type(self):
        return 'Text Classification'

    @property
    def categories(self):
        return Category.objects.filter(project=self)

    @property
    def value_fields(self):
        return ['classification']

    def add_entry(self, annotator, entry_data):
        try:
            category = Category.objects.get(
                project=self, name=entry_data.payload['category-name'])
        except KeyError:
            return 404, {'detail': f'Missing category name in payload'}
        except Category.DoesNotExist:
            return 404, {'detail': f'Category {entry_data.payload["category-name"]} does not exist in project {self.name}'}
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


class NamedEntityRecognitionProject(Project):
    @property
    def project_type(self):
        return 'Named Entity Recognition'

    @property
    def categories(self):
        return Category.objects.filter(project=self)

    @property
    def value_fields(self):
        return ['ner_text_highlights']

    def add_entry(self, annotator, entry_data):
        if entry_data.payload.get('ner_text_highlights', None) is None:
            return 400, {'details': f'Missing ner_text_highlights data in request'}
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
        new_entry_dict = {
            'project': self,
            'unannotated_source': unannotated_source,
            'annotator': annotator
        }

        # Data integrity check
        if entry_data.payload.get('ner_text_highlights', None) is not None:
            for highlight in entry_data.payload.get('ner_text_highlights'):
                beginning = highlight.get('beginning', None)
                end = highlight.get('end', None)
                category = highlight.get('category', None)
                if None in [beginning, end, category]:
                    return 400, {'detail': 'Missing data'}
                try:
                    Category.objects.get(project=self, name=category)
                except Category.DoesNotExist:
                    return 404, {'detail': f'Category {category} not found in project {self.name}'}

        new_entry = NamedEntityRecognitionProjectEntry.objects.create(
            **new_entry_dict)

        if entry_data.payload.get('ner_text_highlights', None) is not None:
            for highlight in entry_data.payload.get('ner_text_highlights'):
                beginning = highlight.get('beginning')
                end = highlight.get('end')
                category = highlight.get('category')
                category = Category.objects.get(project=self, name=category)
                highlight = NERTextHighlight.objects.create(
                    span_start=beginning, span_end=end, category=category
                )
                new_entry.ner_text_highlights.add(highlight)

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
            'context': new_entry.unannotated_source.context if new_entry.unannotated_source.context is not None else 'No context',
            'ner_text_highlights': [
                (highlight.span_start, highlight.span_end, highlight.category.name)
                for highlight in new_entry.ner_text_highlights.all()
            ]
        }

    def add_unannotated_entries(self, unannotated_data, text_field, value_field, context_field):
        # start by running data integrity checks
        # on the uploaded data to ensure that
        # if preannotations are present, all categories
        # exist and that data is well formated
        for index, entry in enumerate(unannotated_data):
            if type(entry) != dict:
                return 400, {'detail': f'Uploaded data is not in a list of dictionaries format'}
            if context_field is not None and context_field not in entry:
                return 400, {'detail': f'Context field provided, but row with index {index} is missing context value'}
            if text_field not in entry:
                return 400, {'detail': f'Text field missing from row with index {index}'}

        # data has been checked for integrity violations
        # and now can be added to the database
        for entry in unannotated_data:
            context = entry.get(context_field, None)
            NamedEntityRecognitionProjectUnannotatedEntry.objects.create(
                project=self, text=entry[text_field],
                context=context
            )

        return 200, {'detail': f'Succesfully created {len(unannotated_data)} unannotated entries'}

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
    def machine_translation_variation(self):
        raise NotImplementedError

    @property
    def project_type(self):
        raise NotImplementedError

    @property
    def value_fields(self):
        return [self.machine_translation_variation]

    @property
    def annotated_entry_class(self):
        raise NotImplementedError

    def add_entry(self, annotator, entry_data):
        if entry_data.payload.get(self.machine_translation_variation, None) is None:
            return 400, {'details': f'Missing {self.machine_translation_variation} data in request'}
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
        new_entry_dict = {
            'project': self,
            self.machine_translation_variation: entry_data.payload.get(
                self.machine_translation_variation, None
            ),
            'unannotated_source': unannotated_source,
            'annotator': annotator
        }

        if entry_data.payload.get('annotator_comment', None) is not None:
            new_entry_dict['annotator_comment'] = entry_data.payload.get(
                'annotator_comment', None
            )

        new_entry = self.annotated_entry_class.objects.create(**new_entry_dict)

        if entry_data.payload.get('target_text_highlights', None) is not None:
            for highlight in entry_data.payload.get('target_text_highlights'):
                beginning = highlight.get('beginning', None)
                end = highlight.get('end', None)
                category = highlight.get('category', None)
                mistranslation_source = highlight.get(
                    'mistranslation_source', None)
                mistranslation_source_object = None
                if None in [beginning, end, category]:
                    pass
                if category == 'Mistranslation' and mistranslation_source is None:
                    pass
                if category == 'Mistranslation' and mistranslation_source is not None:
                    mistranslation_source_object = TextHighlight.objects.create(
                        span_start=mistranslation_source.get('start'),
                        span_end=mistranslation_source.get('end'),
                        category="mistranslation-reference"
                    )
                highlight = TextHighlight.objects.create(
                    span_start=beginning, span_end=end, category=category,
                    mistranslation_source=mistranslation_source_object
                )
                new_entry.target_text_highlights.add(highlight)

        if self.machine_translation_variation == 'adequacy':
            if entry_data.payload.get('source_text_highlights', None) is not None:
                for highlight in entry_data.payload.get('source_text_highlights'):
                    beginning = highlight.get('beginning', None)
                    end = highlight.get('end', None)
                    category = highlight.get('category', None)
                    if None in [beginning, end, category]:
                        pass
                    highlight = TextHighlight.objects.create(
                        span_start=beginning, span_end=end, category=category)
                    new_entry.source_text_highlights.add(highlight)

        return_dict = {
            **model_to_dict(new_entry),
            'project': self.name,
            'project_type': self.project_type,
            'project_url': str(self.url),
            'unannotated_source': model_to_dict(new_entry.unannotated_source),
            'value_fields': self.value_fields,
            'pre_annotations': new_entry.unannotated_source.pre_annotations,
            'created_at': new_entry.created_at.isoformat(),
            'updated_at': new_entry.updated_at.isoformat(),
            'context': new_entry.unannotated_source.context if new_entry.unannotated_source.context is not None else 'No context',
            'target_text_highlights': [
                (highlight.span_start, highlight.span_end, highlight.category)
                for highlight in new_entry.target_text_highlights.all()
            ]
        }

        if self.machine_translation_variation == 'adequacy':
            return_dict['source_text_highlights'] = [
                (highlight.span_start, highlight.span_end, highlight.category)
                for highlight in new_entry.source_text_highlights.all()
            ]

        return return_dict

    def get_statistics(self):
        # https://stackoverflow.com/questions/28607727/how-to-calculate-average-in-django/50087144#50087144
        aggregated_value = self.entries.values(
            self.machine_translation_variation)
        return {
            'averages': {
                self.machine_translation_variation: aggregated_value.aggregate(
                    avg_fluency=Avg(self.machine_translation_variation)
                )
            }
        }


class MachineTranslationFluencyProject(MachineTranslationProject):
    @property
    def machine_translation_variation(self):
        return 'fluency'

    @property
    def project_type(self):
        return 'Machine Translation Fluency'

    @property
    def annotated_entry_class(self):
        return MachineTranslationFluencyProjectEntry

    def add_unannotated_entries(self, unannotated_data, text_field, context_field, **kwargs):
        # start by running data integrity checks
        # on the uploaded data to ensure that
        # data is well formated
        machine_translation_system_translation_field = text_field['mt_system_translation']

        for index, entry in enumerate(unannotated_data):
            if type(entry) != dict:
                return 400, {'detail': f'Uploaded data is not in a list of dictionaries format'}
            # if context_field is not None and context_field not in entry:
            #     return 400, {'detail': f'Context field provided, but row with index {index} is missing context value'}
            if machine_translation_system_translation_field not in entry:
                return 400, {'detail': f'Reference translation field missing from row with index {index}'}

        # data has been checked for integrity violations
        # and now can be added to the database
        for entry in unannotated_data:
            context = entry.get(context_field, None)
            MachineTranslationFluencyProjectUnannotatedEntry.objects.create(
                project=self, text=entry[machine_translation_system_translation_field],
                context=context
            )

        return 200, {'detail': f'Succesfully created {len(unannotated_data)} unannotated entries'}


class MachineTranslationAdequacyProject(MachineTranslationProject):
    @property
    def machine_translation_variation(self):
        return 'adequacy'

    @property
    def project_type(self):
        return 'Machine Translation Adequacy'

    @property
    def annotated_entry_class(self):
        return MachineTranslationAdequacyProjectEntry

    def add_unannotated_entries(self, unannotated_data, text_field, context_field, **kwargs):
        # start by running data integrity checks
        # on the uploaded data to ensure that
        # data is well formated
        reference_translation_field = text_field['reference_field']
        machine_translation_system_translation_field = text_field['mt_system_translation']

        for index, entry in enumerate(unannotated_data):
            if type(entry) != dict:
                return 400, {'detail': f'Uploaded data is not in a list of dictionaries format'}
            # if context_field is not None and context_field not in entry:
            #     return 400, {'detail': f'Context field provided, but row with index {index} is missing context value'}
            if reference_translation_field not in entry:
                return 400, {'detail': f'Reference translation field missing from row with index {index}'}
            if machine_translation_system_translation_field not in entry:
                return 400, {'detail': f'Reference translation field missing from row with index {index}'}

        # data has been checked for integrity violations
        # and now can be added to the database
        for entry in unannotated_data:
            context = entry.get(context_field, None)
            MachineTranslationAdequacyProjectUnannotatedEntry.objects.create(
                project=self, text=entry[reference_translation_field],
                mt_system_translation=entry[machine_translation_system_translation_field],
                context=context
            )

        return 200, {'detail': f'Succesfully created {len(unannotated_data)} unannotated entries'}


class Category(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    name = models.CharField(max_length=255, verbose_name='Category Name')
    description = models.CharField(
        max_length=255, verbose_name='Category Description'
    )
    # It is more convinient for contributors to annotate
    # when the category is associated with a keybinding,
    # which is saved as a string and processed on frontend
    # NULL only when the project is NER
    key_binding = models.CharField(
        max_length=255, null=True, verbose_name='Key Bindnig')
    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name='Category Created at'
    )
    updated_at = models.DateTimeField(
        auto_now=True, verbose_name='Category Created at'
    )

    class Meta:
        unique_together = (('project', 'name', 'description'),
                           ('project', 'name'), ('project', 'key_binding'))


class TextClassificationProjectUnannotatedEntry(UnannotatedProjectEntry):
    pre_annotation = models.ForeignKey(
        'Category', on_delete=models.DO_NOTHING,
        null=True, blank=True,
        verbose_name='Pre-annotation classification'
    )

    @property
    def pre_annotations(self):
        return {
            'category': (self.pre_annotation.name
                         if self.pre_annotation is not None
                         else 'No preannotation')
        }

    @property
    def parameters(self):
        return {'text': self.text}


class NamedEntityRecognitionProjectUnannotatedEntry(UnannotatedProjectEntry):
    @property
    def pre_annotations(self):
        return {}

    @property
    def parameters(self):
        return {'text': self.text}


class MachineTranslationAdequacyProjectUnannotatedEntry(UnannotatedProjectEntry):
    mt_system_translation = models.TextField(
        verbose_name='Reference Translation'
    )

    pre_annotation_adequacy = models.FloatField(
        null=True, blank=True,
        verbose_name='Pre-annotation adequacy'
    )

    @property
    def pre_annotations(self):
        return_dict = {
            'adequacy': 'No annotation',
        }

        if self.pre_annotation_adequacy:
            return_dict['adequacy'] = self.pre_annotation_adequacy

        return return_dict

    @property
    def parameters(self):
        return {'reference_translation': self.text, 'mt_system_translation': self.mt_system_translation}


class MachineTranslationFluencyProjectUnannotatedEntry(UnannotatedProjectEntry):
    pre_annotation_fluency = models.FloatField(
        null=True, blank=True,
        verbose_name='Pre-annotation fluency'
    )

    @property
    def pre_annotations(self):
        return_dict = {
            'fluency': 'No annotation',
        }

        if self.pre_annotation_fluency:
            return_dict['fluency'] = self.pre_annotation_fluency

        return return_dict

    @property
    def parameters(self):
        return {'mt_system_translation': self.text}
