import csv
import json
from django.http import HttpResponse
import pandas as pd
from typing import List, Optional, Union
from ninja import File, Router, UploadedFile
from django.forms.models import model_to_dict
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from annotators.models import PublicAnnotator
from projectmanagement.models import Category, MachineTranslationProject, Project, ProjectEntry, TextClassificationProject, UnannotatedProjectEntry

from projectmanagement.schemas import CategoryInSchema, CreateProjectSchema, EntrySchema, ProjectEntryPatchSchema, ProjectPatchSchema, ProjectSchema, TextClassificationOutSchema as TCOutSchema, MachineTranslationOutSchema as MTOutSchema

router = Router()


@router.post('/create/', response={200: dict, 404: dict}, tags=['Project Management'])
def create_project(request, project_data: CreateProjectSchema):
    if project_data.project_type in ['Text Classification', 'textclassification', 'text-classification', 'TextClassification', 'tc', 'TC']:
        project = TextClassificationProject.objects.create(
            name=project_data.name, description=project_data.description, talk_markdown=project_data.talk_markdown
        )
    elif project_data.project_type in ['Machine Translation', 'machinetranslation', 'machine-translation', 'MachineTranslation', 'mt', 'MT']:
        project = MachineTranslationProject.objects.create(
            name=project_data.name, description=project_data.description, talk_markdown=project_data.talk_markdown
        )
    else:
        return 404, {'detail', f'Project type {project_data.project_type} is not supported'}
    project.administrators.add(request.user)
    return {
        **model_to_dict(project),
        'type': project.project_type,
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
            'type': project.project_type,
            'url': str(project.url),
            'created_at': project.created_at.isoformat(),
            'updated_at': project.updated_at.isoformat(),
            'administrators': [admin.username for admin in project.administrators.all()]
        }
        for project in projects
    ], key=lambda x: x['id'])


@router.delete('/projects/{project_url}', response={200: dict, 401: dict, 404: dict}, tags=['Project Management'])
def delete_project(request, project_url: str):
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
        'type': project.project_type,
        'url': str(project.url),
        'created_at': project.created_at.isoformat(),
        'updated_at': project.updated_at.isoformat(),
        'administrators': [admin.username for admin in project.administrators.all()]
    }
    if project.project_type in ['Text Classification']:
        return_dict['categories'] = [
            {
                **model_to_dict(category),
                'project_url': str(project.url)
            } for category in project.categories
        ]
    print(return_dict)
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


@router.post('/classification/{project_url}/category', response={200: dict, 400: dict, 401: dict, 404: dict}, tags=['Project Management'])
def create_classification_category(request, project_url: str, category_data: CategoryInSchema):
    try:
        project = Project.objects.get(url=project_url)
    except (Project.DoesNotExist, ValidationError):
        return 404, {'detail': f'Project with url {project_url} does not exist'}
    if project.project_type not in ['Text Classification']:
        return 404, {'detail': 'Project does not have a category type'}
    try:
        category = Category.objects.create(
            project=project, name=category_data.name,
            description=category_data.description,
            key_binding=category_data.key_binding
        )
    except Exception as e:
        return 400, {'detail': f'Error: {e}'}
    return {
        **model_to_dict(category),
        'project_url': str(project.url)
    }


@router.delete('/classification/{project_url}/category', response={200: dict, 400: dict, 401: dict, 404: dict}, tags=['Project Management'])
def delete_classification_category(request, project_url: str, category_id: int):
    try:
        project = Project.objects.get(url=project_url)
    except (Project.DoesNotExist, ValidationError):
        return 404, {'detail': f'Project with url {project_url} does not exist'}
    if project.project_type not in ['Text Classification']:
        return 404, {'detail': 'Project does not have a category type'}

    # if not project.contributor_is_admin(request.user):
    #     return 401, {'detail': f'Contributor is not project adminstrator'}

    try:
        category = Category.objects.get(
            id=category_id, project=project
        )
    except Category.DoesNotExist:
        return 400, {'detail': f'Category with ID {category_id} is not found in the project {project.name}'}
    category.delete()
    return {
        **model_to_dict(category),
        'project_url': str(project.url),
        'category_id': category_id
    }


@router.post('/projects/{project_url}/entries', response={200: dict, 401: dict, 404: dict}, tags=['Project Entries'])
def create_entry(request, project_url: str, entry: EntrySchema):
    try:
        project = Project.objects.get(url=project_url)
    except (Project.DoesNotExist, ValidationError):
        return 404, {'detail', f'Project with url {project_url} does not exist'}
    try:
        annotator = PublicAnnotator.objects.get(
            contributor=request.user
        )
    except PublicAnnotator.DoesNotExist:
        annotator = PublicAnnotator.objects.create(
            contributor=request.user
        )
    return project.add_entry(annotator, entry)


@router.get('/projects/{project_url}/entries', response={200: list, 401: dict, 404: dict}, tags=['Project Entries'])
def get_project_entries(request, project_url: str):
    try:
        project = Project.objects.get(url=project_url)
    except (Project.DoesNotExist, ValidationError):
        return 404, {'detail', f'Project with url {project_url} does not exist'}
    return 200, [{
        **model_to_dict(entry),
        'value': entry.values,
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
        'type': project.project_type,
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
        **project.get_statistics()
    }


@router.post('/projects/{project_url}/import', response={200: dict, 401: dict, 404: dict}, tags=['Unannotated Entries'])
def import_unannotated(request, project_url: str, text_field: str, csv_delimiter: Optional[str] = None,
                       value_field: Optional[str] = None, context_field: Optional[str] = None, mt_system_translation: Optional[str] = None,
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

    if project.project_type == 'Machine Translation':
        text_field = {
            'reference_field': text_field,
            'mt_system_translation': mt_system_translation
        }

    return project.add_unannotated_entries(
        unannotated_data=unannotated_data,
        text_field=text_field,
        value_field=value_field,
        context_field=context_field
    )


@router.get('/projects/{project_url}/import', response={200: list, 401: dict, 404: dict}, tags=['Unannotated Entries'])
def get_imported_entries(request, project_url: str):
    try:
        project = Project.objects.get(url=project_url)
    except (Project.DoesNotExist, ValidationError):
        return 404, {'detail', f'Project with url {project_url} does not exist'}
    return 200, [{
        **model_to_dict(entry),
        'project': project.name,
        'project_url': str(project.url),
        'pre_annotations': entry.pre_annotations,
        'created_at': entry.created_at.isoformat(),
        'updated_at': entry.updated_at.isoformat(),
        'context': entry.context if entry.context is not None else 'No context'
    } for entry in project.imported_texts]


@router.delete('/projects/{project_url}/import/{entry_id}', response={200: dict, 401: dict, 404: dict}, tags=['Unannotated Entries'])
def delete_unannotated_project_entry(request, project_url: str, entry_id: int):
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
def export_project(request, project_url: str, export_type: str):
    try:
        project = Project.objects.get(url=project_url)
    except (Project.DoesNotExist, ValidationError):
        return 404, {'detail', f'Project with url {project_url} does not exist'}

    if export_type == 'csv':
        # https://docs.djangoproject.com/en/4.1/howto/outputting-csv/
        value_fields = sorted(project.value_fields)
        # https://stackoverflow.com/questions/1156246/having-django-serve-downloadable-files
        response = HttpResponse(content_type='application/force-download', headers={
            'Content-Disposition': f'attachment; filename="{project.name}.csv"'
        })
        writer = csv.writer(response)
        header_row_written = False
        for entry in project.entries:
            parameters = entry.unannotated_source.parameters
            if not header_row_written:
                # write header row
                writer.writerow([
                    'id', 'imported_text_source_id', *parameters.keys(), *
                    value_fields,
                    *[f'preannotation_{field}' for field in value_fields],
                    'created_at', 'updated_at'
                ])
                header_row_written = True
            preannotations = entry.unannotated_source.pre_annotations
            values = entry.values
            writer.writerow([
                entry.id, entry.unannotated_source.id,
                *[parameter_value for _, parameter_value in parameters.items()],
                *[values[value_field] for value_field in value_fields],
                *[preannotations[value_field] for value_field in value_fields],
                entry.created_at.isoformat(), entry.updated_at.isoformat()
            ])
        if not header_row_written:
            # write header row
            writer.writerow([
                'id', 'imported_text_source_id', 'text', *
                value_fields,
                *[f'preannotation_{field}' for field in value_fields],
                'created_at', 'updated_at'
            ])

    elif export_type == 'json':
        # https://stackoverflow.com/questions/1156246/having-django-serve-downloadable-files
        response = HttpResponse(content_type="application/force-download", headers={
            'Content-Disposition': f'attachment; filename="{project.name}.json"'
        })
        export_data = []
        for entry in project.entries:
            preannotations = {f'preannotation_{k}': v for k,
                              v in entry.unannotated_source.pre_annotations.items()}
            export_data.append({
                'id': entry.id,
                'imported_text_source_id': entry.unannotated_source.id,
                **entry.unannotated_source.parameters,
                **entry.values, **preannotations,
                'created_at': entry.created_at.isoformat(),
                'updated_at': entry.updated_at.isoformat(),
            })
        response.write(json.dumps(export_data))
    else:
        return 400, {'detail': f'Requested export type {export_type} is not supported'}
    return response
