import csv
import json
from django.http import HttpResponse
import pandas as pd
from typing import List, Optional, Union
from ninja import File, Router, UploadedFile
from django.forms.models import model_to_dict
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from projectmanagement.models import Category, Project, ProjectEntry, TextClassificationProject, UnannotatedProjectEntry

from projectmanagement.schemas import EntrySchema, ProjectEntryPatchSchema, ProjectPatchSchema, ProjectSchema, TextClassificationOutSchema as TCOutSchema, MachineTranslationOutSchema as MTOutSchema

router = Router()


@router.post('/create/', response={200: ProjectSchema, 404: dict}, tags=['Project Management'])
def create_project(request, project_type: str, name: str, description: str, talk_markdown: str):
    if project_type in ['textclassification', 'text-classification', 'TextClassification', 'tc', 'TC']:
        project = TextClassificationProject.objects.create(
            name=name, description=description, talk_markdown=talk_markdown
        )
    elif project_type in ['machinetranslation', 'machine-translation', 'MachineTranslation', 'mt', 'MT']:
        project = TextClassificationProject.objects.create(
            name=name, description=description, talk_markdown=talk_markdown
        )
    else:
        return 404, {'detail', f'Project type {project_type} is not supported'}
    project.administrators.add(request.user)
    return {
        **model_to_dict(project),
        'project_type': project.project_type,
        'url': str(project.url),
        'created_at': project.created_at.isoformat(),
        'updated_at': project.updated_at.isoformat(),
        'administrators': [admin.username for admin in project.administrators.all()]
    }


@router.get('/projects/list', response=List[ProjectSchema], tags=['Project Management'])
def list_projects(request, project_type: Optional[str] = None):
    projects = Project.objects.all()
    if project_type is not None:
        projects = list(
            filter(lambda x: x.project_type == project_type, projects)
        )
    return sorted([
        {
            **model_to_dict(project),
            'project_type': project.project_type,
            'url': str(project.url),
            'created_at': project.created_at.isoformat(),
            'updated_at': project.updated_at.isoformat(),
            'administrators': [admin.username for admin in project.administrators.all()]
        }
        for project in projects
    ], key=lambda x: x['id'])


@router.delete('/projects/{project_url}', response={200: dict, 401: dict, 404: dict}, tags=['Project Management'])
def delete_dataset(request, project_url: str):
    try:
        project = Project.objects.get(url=project_url)
    except (Project.DoesNotExist, ValidationError):
        return 404, {'detail', f'Project with url {project_url} does not exist'}
    if not project.contributor_is_admin(request.user):
        return 401, {'detail': f'Contributor is not project adminstrator'}
    project.delete()
    return 200, {'detail': f'Project {project.name} deleted'}


@router.get('/projects/{project_url}', response={200: Union[TCOutSchema, MTOutSchema], 404: dict}, tags=['Project Management'])
def get_project(request, project_url: str):
    try:
        project = Project.objects.get(url=project_url)
    except (Project.DoesNotExist, ValidationError):
        return 404, {'detail', f'Project with url {project_url} does not exist'}
    return_dict = {
        **model_to_dict(project),
        'project_type': project.project_type,
        'url': str(project.url),
        'created_at': project.created_at.isoformat(),
        'updated_at': project.updated_at.isoformat(),
        'administrators': [admin.username for admin in project.administrators.all()]
    }
    if project.project_type in ['Text Classification']:
        return_dict['categories'] = [
            category.name for category in project.categories
        ]
    return return_dict


@router.post('/projects/{project_url}/administrators', response={200: dict, 401: dict, 404: dict}, tags=['Project Management'])
def add_administrator(request, project_url: str, username: str, email: str):
    try:
        project = Project.objects.get(url=project_url)
    except (Project.DoesNotExist, ValidationError):
        return 404, {'detail', f'Project with url {project_url} does not exist'}
    if not project.contributor_is_admin(request.user):
        return 401, {'detail': f'Contributor is not project adminstrator'}

    try:
        new_administrator = get_user_model().objects.get(username=username, email=email)
    except get_user_model().DoesNotExist:
        return 404, {'detail': f'Contributor with username {username}, and email {email} does not exist'}

    project.administrators.add(new_administrator)
    return 200, {'detail': f'Administrator {username} added to project {project.name}'}


@router.post('/classification/{project_url}/category', response={200: dict, 401: dict, 404: dict}, tags=['Project Management'])
def create_classification_category(request, project_url: str, name: str, description: str, key_binding: str):
    try:
        project = Project.objects.get(url=project_url)
    except (Project.DoesNotExist, ValidationError):
        return 404, {'detail', f'Project with url {project_url} does not exist'}
    category = Category.objects.create(
        project=project, name=name, description=description, key_binding=key_binding
    )
    return {
        **model_to_dict(category),
        'project_url': project.url
    }


@router.post('/projects/{project_url}/entries', response={200: dict, 401: dict, 404: dict}, tags=['Project Entries'])
def create_entry(request, project_url: str, entry: EntrySchema):
    try:
        project = Project.objects.get(url=project_url)
    except (Project.DoesNotExist, ValidationError):
        return 404, {'detail', f'Project with url {project_url} does not exist'}
    project.add_entry(request.user, entry)


@router.get('/projects/{project_url}/entries', response={200: dict, 401: dict, 404: dict}, tags=['Project Entries'])
def get_project_entries(request, project_url: str):
    try:
        project = Project.objects.get(url=project_url)
    except (Project.DoesNotExist, ValidationError):
        return 404, {'detail', f'Project with url {project_url} does not exist'}
    return [{
        **model_to_dict(entry),
        **entry.values,
        'project': entry.project.name,
        'project_url': str(entry.project.url),
        'created_at': entry.created_at.isoformat(),
        'updated_at': entry.updated_at.isoformat(),
        'text': entry.unannotated_source.text,
        'annotator': entry.annotator.contributor.username
    } for entry in project.entries]


@router.delete('/projects/{project_url}/entries/{entry_id}', response={200: dict, 401: dict, 404: dict}, tags=['Project Entries'])
def delete_project_entry(request, project_url: str, entry_id: int):
    try:
        project = Project.objects.get(url=project_url)
    except (Project.DoesNotExist, ValidationError):
        return 404, {'detail', f'Project with url {project_url} does not exist'}
    if not project.contributor_is_admin(request.user):
        return 401, {'detail': f'Contributor is not project adminstrator'}
    try:
        entry = ProjectEntry.objects.get(id=entry_id, project=project)
    except (ProjectEntry.DoesNotExist, ValidationError, ValueError):
        return 404, {'detail': f'Entry with ID: {entry_id} not found'}
    entry.delete()
    return 200, {'detail', f'Successfully deleted entry {entry_id}'}


@router.patch('/projects/{project_url}/entries/{entry_id}', response={200: dict, 401: dict, 404: dict}, tags=['Project Entries'])
def update_project_entry(request, project_url: str, entry_id: int, update_data: ProjectEntryPatchSchema):
    try:
        project = Project.objects.get(url=project_url)
    except (Project.DoesNotExist, ValidationError):
        return 404, {'detail', f'Project with url {project_url} does not exist'}
    if not project.contributor_is_admin(request.user):
        return 401, {'detail': f'Contributor is not project adminstrator'}
    try:
        entry = ProjectEntry.objects.get(id=entry_id, project=project)
    except (ProjectEntry.DoesNotExist, ValidationError, ValueError):
        return 404, {'detail': f'Entry with ID: {entry_id} not found'}
    return entry.update_with_data(update_data)


@router.patch('/projects/{project_url}', response={200: dict, 401: dict, 404: dict}, tags=['Project Entries'])
def update_project(request, project_url: str, entry_id: int, update_data: ProjectPatchSchema):
    try:
        project = Project.objects.get(url=project_url)
    except (Project.DoesNotExist, ValidationError):
        return 404, {'detail', f'Project with url {project_url} does not exist'}
    if not project.contributor_is_admin(request.user):
        return 401, {'detail': f'Contributor is not project adminstrator'}
    if update_data.name:
        project.name = update_data.name
    if update_data.description:
        project.description = update_data.description
    if update_data.talk_markdown:
        project.description = update_data.description
    project.save()
    return {
        **model_to_dict(project),
        'project_type': project.project_type,
        'url': str(project.url),
        'created_at': project.created_at.isoformat(),
        'updated_at': project.updated_at.isoformat(),
        'administrators': [admin.username for admin in project.administrators.all()]
    }


@router.get('/projects/{project_url}/statistics', tags=['Project Management'])
def get_project_statistics(request, project_url: str):
    try:
        project = Project.objects.get(url=project_url)
    except (Project.DoesNotExist, ValidationError):
        return 404, {'detail', f'Project with url {project_url} does not exist'}
    return {
        'total_entries': project.entries.count(),
        'total_imported_texts': project.imported_texts.count(),
        **project.get_statistsics()
    }


@router.post('/projects/{project_url}/import', response={200: dict, 401: dict, 404: dict}, tags=['Unannotated Entries'])
def import_unannotated(request, project_url: str, text_field: str, csv_delimiter: Optional[str] = None,
                       value_field: Optional[str] = None, context_field: Optional[str] = None,
                       unannotated_data_file: UploadedFile = File(...)):
    try:
        project = Project.objects.get(url=project_url)
    except (Project.DoesNotExist, ValidationError):
        return 404, {'detail', f'Project with url {project_url} does not exist'}

    if csv_delimiter == r'\t':
        csv_delimiter = '\t'

    if unannotated_data_file.content_type == 'application/json':
        unannotated_data = json.loads(
            unannotated_data_file.file.read().decode('utf-8')
        )
    elif unannotated_data_file.content_type == 'text/csv':
        unannotated_data_df = pd.read_csv(
            unannotated_data_file.file.read().decode('utf-8'),
            delimiter=csv_delimiter
        )
        unannotated_data = unannotated_data_df.to_json(orient='records')
    else:
        return 400, {'detail': f'Uploaded data type {unannotated_data_file.content_type} is not supported'}

    if type(unannotated_data) != list:
        return 400, {'detail': f'Uploaded data is not in a list of records format'}

    return project.add_unannotated_entries(unannotated_data, text_field, value_field, context_field)


@router.get('/projects/{project_url}/import', response={200: dict, 401: dict, 404: dict}, tags=['Unannotated Entries'])
def get_imported_entries(request, project_url: str):
    try:
        project = Project.objects.get(url=project_url)
    except (Project.DoesNotExist, ValidationError):
        return 404, {'detail', f'Project with url {project_url} does not exist'}

    return [{
        **model_to_dict(entry),
        'pre_annotations': entry.pre_annotations,
        'created_at': entry.created_at.isoformat(),
        'updated_at': entry.updated_at.isoformat(),
        'context': entry.context if entry.context is not None else 'No context'
    } for entry in project.imported_texts]


@router.delete('/projects/{project_url}/import/{entry_id}', response={200: dict, 401: dict, 404: dict}, tags=['Unannotated Entries'])
def delete_project_entry(request, project_url: str, entry_id: int):
    try:
        project = Project.objects.get(url=project_url)
    except (Project.DoesNotExist, ValidationError):
        return 404, {'detail', f'Project with url {project_url} does not exist'}
    if not project.contributor_is_admin(request.user):
        return 401, {'detail': f'Contributor is not project adminstrator'}
    try:
        entry = project.get_imported_entry(entry_id)
    except UnannotatedProjectEntry.DoesNotExist:
        return 404, {'detail': f'Unannotated entry with ID: {entry_id} not found'}
    entry.delete()
    return 200, {'detail', f'Successfully deleted unannotated entry {entry_id}'}


@router.get('/projects/{project_url}/export', tags=['Project Management'])
def export_dataset(request, project_url: str, export_type: str):
    try:
        project = Project.objects.get(url=project_url)
    except (Project.DoesNotExist, ValidationError):
        return 404, {'detail', f'Project with url {project_url} does not exist'}

    if export_type == 'csv':
        # https://docs.djangoproject.com/en/4.1/howto/outputting-csv/
        value_fields = sorted(project.value_fields)
        response = HttpResponse(content_type='text/csv', headers={
            'Content-Disposition': f'attachment; filename="{project.name}.csv"'
        })
        writer = csv.writer(response)
        # write header row
        writer.writerow([
            'id', 'imported_text_source_id', 'text', *value_fields,
            *[f'preannotation_{field}' for field in value_fields],
            'created_at', 'updated_at'
        ])
        for entry in project.entries:
            preannotations = entry.unannotated_source.pre_annotations
            values = entry.values
            writer.writerow([
                entry.id, entry.unannotated_source.id, entry.text,
                *[values[value_field] for value_field in value_fields],
                *[preannotations[value_field] for value_field in value_fields],
                entry.created_at.isoformat(), entry.updated_at.isoformat()
            ])
    elif export_type == 'json':
        response = HttpResponse(content_type='application/json', headers={
            'Content-Disposition': f'attachment; filename="{project.name}.json"'
        })
        export_data = []
        for entry in project.entries:
            preannotations = entry.unannotated_source.pre_annotations
            export_data.append({
                'id': entry.id,
                'imported_text_source_id': entry.unannotated_source.id,
                'text': entry.unannotated_source.text,
                **entry.values, **preannotations,
                'created_at': entry.created_at.isoformat(),
                'updated_at': entry.updated_at.isoformat(),
            })
        response.write(json.dumps(export_data))
    else:
        return 400, {'detail': f'Requested export type {export_type} is not supported'}
    return 200, response
