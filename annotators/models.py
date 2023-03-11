from django.db import models
from django.contrib.auth import get_user_model
from polymorphic.models import PolymorphicModel


class Annotator(PolymorphicModel):
    # when contributor deletes their account
    # the annotator objects remain to preserve
    # accountability for the entries
    contributor = models.ForeignKey(
        get_user_model(), on_delete=models.DO_NOTHING
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Annotator Created at'
    )
    updated_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Annotator Updated at'
    )

    @property
    def type_verbose(self):
        raise NotImplementedError


class PrivateAnnotator(Annotator):
    # A single project can have many \textit{private} annotators
    # A single annotators can be assigned to a single project,
    #   as the PrivateAnnotator object is generated with
    #   a token which uniquely identifies the annotator
    #   and contains a 1-1 mapping with a project
    project = models.ForeignKey(
        'projectmanagement.Project', on_delete=models.CASCADE,
        verbose_name='Project'
    )
    inviting_contributor = models.ForeignKey(
        get_user_model(), on_delete=models.DO_NOTHING,
        verbose_name='Inviting Contributor'
    )
    token = models.CharField(max_length=100, verbose_name='Token')

    @property
    def completion(self):
        completed_annotations = self.project.get_annotators_annotations(self)
        annotations_total = self.project.imported_texts.count()
        if annotations_total == 0:
            return 100.0
        return round(float(completed_annotations) / float(annotations_total), 2) * 100

    @property
    def type_verbose(self):
        return 'Private Annotator'


class PublicAnnotator(Annotator):
    @property
    def type_verbose(self):
        return 'Public Annotator'
