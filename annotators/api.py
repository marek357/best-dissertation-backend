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

from projectmanagement.models import Project

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
        'contributor': annotator.contributor.username
    }


@router.get('/projects/{project_url}/disagreements', response={200: dict, 401: dict, 404: dict}, tags=['Private Annotators'])
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
        'contributor': annotator.contributor.username
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
