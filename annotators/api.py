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
from annotators.schemas import PrivateAnnotatorEntryCreateSchema, PrivateAnnotatorEntryPatchSchema

from projectmanagement.models import Project, ProjectEntry

router = Router()


@router.post('/projects/{project_url}', response={200: dict, 401: dict, 404: dict}, tags=['Private Annotators'])
def invite_annotator(request, project_url: str, email: str, username: str, send_email: Optional[bool] = True):
    try:
        project = Project.objects.get(url=project_url)
    except (Project.DoesNotExist, ValidationError):
        return 404, {'detail', f'Project with url {project_url} does not exist'}
    if not project.contributor_is_admin(request.user):
        return 401, {'detail': f'Contributor is not project adminstrator'}
    try:
        contributor = get_user_model().objects.get(username=username, email=email)
    except get_user_model().DoesNotExist:
        contributor = get_user_model().objects.create_user(username=username, email=email)
        contributor.set_unusable_password()
    if project.private_annotators.filter(contributor=contributor).exists():
        return 400, {'detail': f'Private Annotator {username} is already invited to the project'}
    annotator = PrivateAnnotator.objects.create(
        project=project, contributor=contributor, inviting_contributor=request.user, token=uuid4().hex
    )
    if send_email:
        send_annotator_welcome_email(annotator, request.user, project)
    return 200, {
        **model_to_dict(annotator),
        'inviting_contributor': request.user.username,
        'contributor': annotator.contributor.username,
        'is_active': annotator.contributor.is_active,
        'completion': annotator.completion
    }


@router.get('/projects/{project_url}/disagreements', response={200: list, 401: dict, 404: dict}, tags=['Private Annotators'])
def get_project_private_annotators(request, project_url: str):
    try:
        project = Project.objects.get(url=project_url)
    except (Project.DoesNotExist, ValidationError):
        return 404, {'detail', f'Project with url {project_url} does not exist'}
    if not project.contributor_is_admin(request.user):
        return 401, {'detail': f'Contributor is not project adminstrator'}
    return 200, [{
        **model_to_dict(annotator),
        'inviting_contributor': request.user.username,
        'contributor': annotator.contributor.username,
        'is_active': annotator.contributor.is_active,
        'completion': annotator.completion
    } for annotator in project.private_annotators]


@router.get('/projects/{project_url}/resend-invite-email', response={200: dict, 401: dict, 404: dict}, tags=['Private Annotators'])
def resend_private_annotator_invitation(request, project_url: str, username: str, email: str):
    try:
        project = Project.objects.get(url=project_url)
    except (Project.DoesNotExist, ValidationError):
        return 404, {'detail', f'Project with url {project_url} does not exist'}
    if not project.contributor_is_admin(request.user):
        return 401, {'detail': f'Contributor is not project adminstrator'}
    try:
        contributor = get_user_model().objects.get(username=username, email=email)
    except get_user_model().DoesNotExist:
        return 404, {
            'detail': f'''
                Contributor with email {email} and username {username}
                has not been invited yet to the project {project.name}
            '''
        }
    if not project.private_annotators.filter(contributor=contributor).exists():
        return 404, {
            'detail': f'''
                Contributor with email {email} and username {username}
                has not been invited yet to the project {project.name}
            '''
        }
    if project.private_annotators.filter(contributor=contributor).count() != 1:
        return 404, {'detail': 'Data integrity error'}
    annotator = project.private_annotators.get(contributor=contributor)
    send_annotator_welcome_email(annotator, request.user, project)
    return 200, {'detail': f'Successfully sent email again to private annotator at email {email}'}


@router.get('/projects/{project_url}/{annotator_token}/toggle-annotator-status', response={200: dict, 401: dict, 404: dict}, tags=['Private Annotators'])
def toggle_annotator_status(request, project_url: str, annotator_token: str, annotator_status: bool):
    try:
        project = Project.objects.get(url=project_url)
    except (Project.DoesNotExist, ValidationError):
        return 404, {'detail', f'Project with url {project_url} does not exist'}
    if not project.contributor_is_admin(request.user):
        return 401, {'detail': f'Contributor is not project adminstrator'}
    try:
        annotator = PrivateAnnotator.objects.filter(
            project=project, token=annotator_token
        )
    except PrivateAnnotator.DoesNotExist:
        return 404, {'detail', f'Annotator with token {annotator_token} not found in project {project.name}'}
    annotator.contributor.is_active = annotator_status
    annotator.contributor.save()
    return 200, {
        **model_to_dict(annotator),
        'inviting_contributor': request.user.username,
        'contributor': annotator.contributor.username,
        'is_active': annotator.contributor.is_active,
        'completion': annotator.completion
    }


@router.post('/projects/{project_url}/entry', response={200: dict, 401: dict, 404: dict}, tags=['Private Annotators'])
def create_private_annotators_entry(request, project_url: str, token: str, entry_data: PrivateAnnotatorEntryCreateSchema):
    try:
        project = Project.objects.get(url=project_url)
    except (Project.DoesNotExist, ValidationError):
        return 404, {'detail', f'Project with url {project_url} does not exist'}
    if not project.contributor_is_admin(request.user):
        return 401, {'detail': f'Contributor is not project adminstrator'}
    try:
        annotator = PrivateAnnotator.objects.filter(
            project=project, token=token
        )
    except PrivateAnnotator.DoesNotExist:
        return 404, {'detail', f'Annotator with token {token} not found in project {project.name}'}
    project.add_entry(annotator, entry_data)


@router.get('/projects/{project_url}/remaining', response={200: dict, 401: dict, 404: dict}, tags=['Private Annotators'])
def get_remaining_entries_for_annotation_private_annotator(request, project_url: str, token: str):
    try:
        project = Project.objects.get(url=project_url)
    except (Project.DoesNotExist, ValidationError):
        return 404, {'detail', f'Project with url {project_url} does not exist'}
    try:
        annotator = PrivateAnnotator.objects.get(project=project, token=token)
    except (PrivateAnnotator.DoesNotExist, ValidationError):
        return 404, {'detail', f'Annotator with token {token} does not exist in project {project.name}'}
    # https://stackoverflow.com/questions/2354284/django-queries-how-to-filter-objects-to-exclude-id-which-is-in-a-list
    annotated = project.get_annotators_annotations(annotator).value('id')
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


@router.get('/projects/{project_url}/remaining', response={200: dict, 401: dict, 404: dict}, tags=['Private Annotators'])
def get_entries__private_annotator(request, project_url: str, token: str):
    try:
        project = Project.objects.get(url=project_url)
    except (Project.DoesNotExist, ValidationError):
        return 404, {'detail', f'Project with url {project_url} does not exist'}
    try:
        annotator = PrivateAnnotator.objects.get(project=project, token=token)
    except (PrivateAnnotator.DoesNotExist, ValidationError):
        return 404, {'detail', f'Annotator with token {token} does not exist in project {project.name}'}
    return [{
        **model_to_dict(entry),
        'project': project.name,
        'project_url': str(project.url),
        'pre_annotations': entry.pre_annotations,
        'created_at': entry.created_at.isoformat(),
        'updated_at': entry.updated_at.isoformat(),
        'context': entry.context if entry.context is not None else 'No context'
    } for entry in project.get_annotators_annotations(annotator)]


@router.patch('/projects/{project_url}/entry', response={200: dict, 401: dict, 404: dict}, tags=['Private Annotators'])
def modify_annotators_entry(request, project_url: str, token: str, entry_id: int, patch_data: PrivateAnnotatorEntryPatchSchema):
    try:
        project = Project.objects.get(url=project_url)
    except (Project.DoesNotExist, ValidationError):
        return 404, {'detail', f'Project with url {project_url} does not exist'}
    try:
        annotator = PrivateAnnotator.objects.get(project=project, token=token)
    except (PrivateAnnotator.DoesNotExist, ValidationError):
        return 404, {'detail', f'Annotator with token {token} does not exist in project {project.name}'}
    try:
        entry = ProjectEntry.objects.get(
            id=entry_id, project=project, annotator=annotator
        )
    except (PrivateAnnotator.DoesNotExist, ValidationError):
        return 404, {'detail', f'Entry with ID {entry_id}, created by {annotator.contributor.username} does not exist in project {project.name}'}
    return entry.update_with_data(patch_data)
