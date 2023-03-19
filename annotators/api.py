import csv
import json
from uuid import uuid4
import pandas as pd
from typing import List, Optional, Union
from ninja import File, Router, UploadedFile
from django.forms.models import model_to_dict
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from annotators.helpers import send_annotator_welcome_email
from annotators.models import PrivateAnnotator
from annotators.schemas import CreatePrivateAnnotatorSchema, PrivateAnnotatorEntryCreateSchema, PrivateAnnotatorEntryPatchSchema, PrivateAnnotatorHiglightPatchSchema
from django.db.utils import IntegrityError

from projectmanagement.models import Project, ProjectEntry, TextHighlight

router = Router()


@router.post('/projects/{project_url}/annotators', response={200: dict, 401: dict, 404: dict, 400: dict}, tags=['Private Annotators'])
def invite_annotator(request, project_url: str, private_annotator_data: CreatePrivateAnnotatorSchema):
    try:
        project = Project.objects.get(url=project_url)
    except (Project.DoesNotExist, ValidationError):
        return 404, {'detail': f'Project with url {project_url} does not exist'}
    if not project.contributor_is_admin(request.user):
        return 401, {'detail': f'Contributor is not project adminstrator'}
    try:
        contributor = get_user_model().objects.get(
            username=private_annotator_data.username, email=private_annotator_data.email)
    except get_user_model().DoesNotExist:
        try:
            contributor = get_user_model().objects.create_user(
                username=private_annotator_data.username, email=private_annotator_data.email)
            contributor.set_unusable_password()
        except IntegrityError:
            return 404, {'detail': f'User with username {private_annotator_data.username} already exists'}
    if project.private_annotators.filter(contributor=contributor).exists():
        return 400, {'detail': f'Private Annotator {private_annotator_data.username} is already invited to the project'}
    annotator = PrivateAnnotator.objects.create(
        project=project, contributor=contributor, inviting_contributor=request.user, token=uuid4().hex
    )
    # if private_annotator_data.send_email:
    #     send_annotator_welcome_email(annotator, request.user, project)
    return 200, {
        **model_to_dict(annotator),
        'inviting_contributor': request.user.username,
        'contributor': annotator.contributor.username,
        'is_active': annotator.contributor.is_active,
        'completion': annotator.completion
    }


@router.get('/projects/{project_url}/annotators', response={200: list, 401: dict, 404: dict}, tags=['Private Annotators'])
def get_project_private_annotators(request, project_url: str):
    try:
        project = Project.objects.get(url=project_url)
    except (Project.DoesNotExist, ValidationError):
        return 404, {'detail': f'Project with url {project_url} does not exist'}
    if not project.contributor_is_admin(request.user):
        return 401, {'detail': f'Contributor is not project adminstrator'}
    return 200, [{
        **model_to_dict(annotator),
        'email': annotator.contributor.email,
        'inviting_contributor': request.user.username,
        'contributor': annotator.contributor.username,
        'is_active': annotator.contributor.is_active,
        'completion': annotator.completion
    } for annotator in project.private_annotators]


@router.get('/projects/annotator', response={200: dict, 401: dict, 404: dict}, tags=['Private Annotators'])
def get_project_private_annotator(request, private_annotator_token: str):
    try:
        private_annotator = PrivateAnnotator.objects.get(
            token=private_annotator_token
        )
    except PrivateAnnotator.DoesNotExist:
        return 404, {
            'detail': f'''
                Private Annotator with token {private_annotator_token} does not exist.\n
                Please contact your project administrator to ensure they provided you with the right token.\n
                Please also ensure that the link you recieved in an email matches the current browser URL\n\n
                See you soon!\n
                Annopedia Team
            '''
        }
    print(private_annotator.contributor.username,
          private_annotator.project.name, private_annotator.project.project_type)
    return 200, {
        **model_to_dict(private_annotator),
        'project_type': private_annotator.project.project_type,
        'email': private_annotator.contributor.email,
        'inviting_contributor': request.user.username,
        'contributor': private_annotator.contributor.username,
        'is_active': private_annotator.contributor.is_active,
        'completion': private_annotator.completion
    }


@router.get('/projects/{project_url}/resend-invite-email', response={200: dict, 401: dict, 404: dict}, tags=['Private Annotators'])
def resend_private_annotator_invitation(request, project_url: str, private_annotator_token: str):
    try:
        project = Project.objects.get(url=project_url)
    except (Project.DoesNotExist, ValidationError):
        return 404, {'detail': f'Project with url {project_url} does not exist'}
    if not project.contributor_is_admin(request.user):
        return 401, {'detail': f'Contributor is not project adminstrator'}
    try:
        private_annotator = PrivateAnnotator.objects.get(
            token=private_annotator_token)
    except PrivateAnnotator.DoesNotExist:
        return 404, {
            'detail': f'''
                Contributor with token {private_annotator_token}
                does not belong to the project {project.name}
            '''
        }
    if not project.private_annotators.filter(contributor=private_annotator.contributor).exists():
        return 404, {
            'detail': f'''
                Contributor with token {private_annotator_token}
                does not belong to the project {project.name}
            '''
        }
    if project.private_annotators.filter(contributor=private_annotator.contributor).count() != 1:
        return 404, {'detail': 'Data integrity error'}
    send_annotator_welcome_email(private_annotator, request.user, project)
    return 200, {'detail': f'Successfully sent email again to private annotator at email {private_annotator.contributor.email}'}


@router.get('/projects/{project_url}/{annotator_token}/toggle-annotator-status', response={200: dict, 401: dict, 404: dict}, tags=['Private Annotators'])
def toggle_annotator_status(request, project_url: str, annotator_token: str, annotator_status: bool):
    try:
        project = Project.objects.get(url=project_url)
    except (Project.DoesNotExist, ValidationError):
        return 404, {'detail': f'Project with url {project_url} does not exist'}
    if not project.contributor_is_admin(request.user):
        return 401, {'detail': f'Contributor is not project adminstrator'}
    try:
        annotator = PrivateAnnotator.objects.get(
            project=project, token=annotator_token
        )
    except PrivateAnnotator.DoesNotExist:
        return 404, {'detail': f'Annotator with token {annotator_token} not found in project {project.name}'}
    annotator.contributor.is_active = annotator_status
    annotator.contributor.save()
    return 200, {
        **model_to_dict(annotator),
        'inviting_contributor': request.user.username,
        'contributor': annotator.contributor.username,
        'is_active': annotator.contributor.is_active,
        'completion': annotator.completion
    }


@router.post('/projects/entry', response={200: dict, 401: dict, 404: dict, 400: dict}, tags=['Private Annotators'])
def create_private_annotators_entry(request, token: str, entry_data: PrivateAnnotatorEntryCreateSchema):
    try:
        annotator = PrivateAnnotator.objects.get(token=token)
    except PrivateAnnotator.DoesNotExist:
        return 404, {'detail': f'Annotator with token {token} not found'}
    project = annotator.project
    return project.add_entry(annotator, entry_data)


@router.get('/projects/remaining', response={200: list, 401: dict, 404: dict}, tags=['Private Annotators'])
def get_remaining_entries_for_annotation_private_annotator(request, token: str):
    try:
        annotator = PrivateAnnotator.objects.get(token=token)
    except (PrivateAnnotator.DoesNotExist, ValidationError):
        return 404, {'detail': f'Annotator with token {token} does not exist'}
    project = annotator.project
    # https://stackoverflow.com/questions/2354284/django-queries-how-to-filter-objects-to-exclude-id-which-is-in-a-list
    annotated = project.get_annotators_annotations(
        annotator).values('unannotated_source')
    remaining_to_be_annotated = project.imported_texts.exclude(
        id__in=annotated
    )
    return [{
        **model_to_dict(entry),
        'project': project.name,
        'project_url': str(project.url),
        'pre_annotations': entry.pre_annotations,
        'created_at': entry.created_at.isoformat(),
        'updated_at': entry.updated_at.isoformat(),
        'context': entry.context if entry.context is not None else 'No context'
    } for entry in remaining_to_be_annotated]


@router.get('/projects/annotated', response={200: list, 401: dict, 404: dict}, tags=['Private Annotators'])
def get_entries__private_annotator(request, token: str):
    try:
        annotator = PrivateAnnotator.objects.get(token=token)
    except (PrivateAnnotator.DoesNotExist, ValidationError):
        return 404, {'detail': f'Annotator with token {token} does not exist'}
    project = annotator.project
    return [{
        **model_to_dict(entry),
        'project': project.name,
        'project_type': project.project_type,
        'project_url': str(project.url),
        'unannotated_source': model_to_dict(entry.unannotated_source),
        'value_fields': project.value_fields,
        'pre_annotations': entry.unannotated_source.pre_annotations,
        'created_at': entry.created_at.isoformat(),
        'updated_at': entry.updated_at.isoformat(),
        'context': entry.unannotated_source.context if entry.unannotated_source.context is not None else 'No context',
        **entry.non_standard_fix
    } for entry in project.get_annotators_annotations(annotator)]


@router.get('/projects/categories', response={200: list, 401: dict, 404: dict}, tags=['Private Annotators'])
def get_categories_private_annotator(request, token: str):
    try:
        annotator = PrivateAnnotator.objects.get(token=token)
    except (PrivateAnnotator.DoesNotExist, ValidationError):
        return 404, {'detail': f'Annotator with token {token} does not exist'}
    project = annotator.project
    if project.project_type not in ['Text Classification', 'Named Entity Recognition']:
        return 404, {'detail': 'Project does not have a category type'}
    return [
        {
            **model_to_dict(category),
            'project_url': str(project.url)
        } for category in project.categories
    ]


@router.patch('/projects/entry', response={200: dict, 401: dict, 404: dict}, tags=['Private Annotators'])
def modify_annotators_entry(request, token: str, entry_id: int, patch_data: PrivateAnnotatorEntryPatchSchema):
    try:
        annotator = PrivateAnnotator.objects.get(token=token)
    except (PrivateAnnotator.DoesNotExist, ValidationError):
        return 404, {'detail': f'Annotator with token {token} does not exist'}
    project = annotator.project
    try:
        entry = ProjectEntry.objects.get(
            id=entry_id, project=project, annotator=annotator
        )
    except (PrivateAnnotator.DoesNotExist, ValidationError):
        return 404, {'detail': f'Entry with ID {entry_id}, created by {annotator.contributor.username} does not exist in project {project.name}'}
    return entry.update_with_data(patch_data)


@router.patch('/projects/', response={200: dict, 401: dict, 404: dict}, tags=['Private Annotators'])
def modify_annotators_highlight(request, token: str, patch_data: PrivateAnnotatorHiglightPatchSchema):
    try:
        annotator = PrivateAnnotator.objects.get(token=token)
    except (PrivateAnnotator.DoesNotExist, ValidationError):
        return 404, {'detail': f'Annotator with token {token} does not exist'}
    try:
        higlight = TextHighlight.objects.get(
            id=patch_data.highlight_id
        )
    except (TextHighlight.DoesNotExist, ValidationError):
        return 404, {'detail': f'Higlight with ID {patch_data.highlight_id}, created by {annotator.contributor.username} does not exist in project {annotator.project.name}'}
    try:
        entry = higlight.project_entry_set.first()
    except ProjectEntry.DoesNotExist:
        return 404, {'detail': f'Integrity Error'}
    if annotator != entry.annotator:
        return 401, {'detail': f'Annotator is not annotator'}
    higlight.classification = patch_data.classification
    higlight.save()
    return 200, model_to_dict(higlight)


@router.delete('/projects/', response={200: dict, 401: dict, 404: dict}, tags=['Private Annotators'])
def delete_annotators_highlight(request, token: str, highlight_id: int):
    try:
        annotator = PrivateAnnotator.objects.get(token=token)
    except (PrivateAnnotator.DoesNotExist, ValidationError):
        return 404, {'detail': f'Annotator with token {token} does not exist'}
    try:
        higlight = TextHighlight.objects.get(
            id=highlight_id
        )
    except (TextHighlight.DoesNotExist, ValidationError):
        return 404, {'detail': f'Higlight with ID {highlight_id}, created by {annotator.contributor.username} does not exist in project {annotator.project.name}'}
    try:
        entry = higlight.project_entry_set.first()
    except ProjectEntry.DoesNotExist:
        return 404, {'detail': f'Integrity Error'}
    if annotator != entry.annotator:
        return 401, {'detail': f'Annotator is not annotator'}
    higlight.delete()
    return 200, {
        **model_to_dict(higlight),
        'higlight_id': highlight_id
    }
