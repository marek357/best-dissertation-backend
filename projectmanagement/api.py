import csv
import json
from django.http import HttpResponse
import pandas as pd
from typing import List, Optional, Union
from ninja import File, Router, UploadedFile
from django.forms.models import model_to_dict
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from annotators.models import PrivateAnnotator, PublicAnnotator
from projectmanagement.models import Category, MachineTranslationAdequacyProject, MachineTranslationFluencyProject, Project, ProjectEntry, TextClassificationProject, UnannotatedProjectEntry

from projectmanagement.schemas import CategoryInSchema, CreateProjectSchema, EntrySchema, ProjectAdministratorInSchema, ProjectEntryPatchSchema, ProjectPatchSchema, ProjectSchema, TextClassificationOutSchema as TCOutSchema, MachineTranslationOutSchema as MTOutSchema

router = Router()


@router.post('/create/', response={200: dict, 404: dict}, tags=['Project Management'])
def create_project(request, project_data: CreateProjectSchema):
    if project_data.project_type in ['Text Classification', 'textclassification', 'text-classification', 'TextClassification', 'tc', 'TC']:
        project = TextClassificationProject.objects.create(
            name=project_data.name, description=project_data.description, talk_markdown=project_data.talk_markdown
        )
    elif project_data.project_type in ['Machine Translation Adequacy', 'machinetranslationadequacy', 'machine-translation-adequacy', 'MachineTranslationAdequacy', 'mta', 'MTA']:
        project = MachineTranslationAdequacyProject.objects.create(
            name=project_data.name, description=project_data.description, talk_markdown=project_data.talk_markdown
        )
    elif project_data.project_type in ['Machine Translation Fluency', 'machinetranslationfluency', 'machine-translation-fluency', 'MachineTranslationFluency', 'mtf', 'MTF']:
        project = MachineTranslationFluencyProject.objects.create(
            name=project_data.name, description=project_data.description, talk_markdown=project_data.talk_markdown
        )
    else:
        return 404, {'detail': f'Project type {project_data.project_type} is not supported'}
    project.administrators.add(request.user)
    return {
        **model_to_dict(project),
        'type': project.project_type,
        'url': str(project.url),
        'created_at': project.created_at.isoformat(),
        'updated_at': project.updated_at.isoformat(),
        'administrators': [{'username': admin.username, 'email': admin.email} for admin in project.administrators.all()]
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
            'administrators': [{'username': admin.username, 'email': admin.email} for admin in project.administrators.all()]
        }
        for project in projects
    ], key=lambda x: x['id'])


@router.delete('/projects/{project_url}', response={200: dict, 401: dict, 404: dict}, tags=['Project Management'])
def delete_project(request, project_url: str):
    try:
        project = Project.objects.get(url=project_url)
    except (Project.DoesNotExist, ValidationError):
        return 404, {'detail': f'Project with url {project_url} does not exist'}
    if not project.contributor_is_admin(request.user):
        return 401, {'detail': f'Contributor is not project adminstrator'}
    project.delete()
    return 200, {'detail': f'Project {project.name} deleted'}


@router.get('/projects/{project_url}', response={200: Union[TCOutSchema, MTOutSchema], 404: dict}, tags=['Project Management'])
def get_project(request, project_url: str):
    try:
        project = Project.objects.get(url=project_url)
    except (Project.DoesNotExist, ValidationError):
        return 404, {'detail': f'Project with url {project_url} does not exist'}
    return_dict = {
        **model_to_dict(project),
        'type': project.project_type,
        'url': str(project.url),
        'created_at': project.created_at.isoformat(),
        'updated_at': project.updated_at.isoformat(),
        'administrators': [{'username': admin.username, 'email': admin.email} for admin in project.administrators.all()]
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
def add_administrator(request, project_url: str, new_administrator: ProjectAdministratorInSchema):
    try:
        project = Project.objects.get(url=project_url)
    except (Project.DoesNotExist, ValidationError):
        return 404, {'detail': f'Project with url {project_url} does not exist'}
    if not project.contributor_is_admin(request.user):
        return 401, {'detail': f'Contributor is not project adminstrator'}

    try:
        new_administrator = get_user_model().objects.get(email=new_administrator.email)
    except get_user_model().DoesNotExist:
        return 404, {'detail': f'Contributor with email {new_administrator.email} does not exist'}

    project.administrators.add(new_administrator)
    return 200, {'detail': f'Administrator {new_administrator.username} added to project {project.name}'}


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
        return 404, {'detail': f'Project with url {project_url} does not exist'}
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
        return 404, {'detail': f'Project with url {project_url} does not exist'}
    return_list = [{
        **model_to_dict(entry),
        'value': entry.values,
        'project': entry.project.name,
        'project_url': str(entry.project.url),
        'created_at': entry.created_at.isoformat(),
        'updated_at': entry.updated_at.isoformat(),
        'text': entry.unannotated_source.text,
        'annotator': entry.annotator.contributor.username
    } for entry in project.entries]

    if project.project_type in ['Machine Translation Fluency', 'Machine Translation Adequacy']:
        for return_entry, entry in zip(return_list, project.entries):
            return_entry['target_text_highlights'] = [
                (highlight.span_start, highlight.span_end, highlight.category)
                for highlight in entry.target_text_highlights.all()
            ]

            if project.machine_translation_variation == 'adequacy':
                return_entry['source_text_highlights'] = [
                    (highlight.span_start, highlight.span_end, highlight.category)
                    for highlight in entry.source_text_highlights.all()
                ]

    return 200, return_list


@router.delete('/projects/{project_url}/entries/{entry_id}', response={200: dict, 401: dict, 404: dict}, tags=['Project Entries'])
def delete_project_entry(request, project_url: str, entry_id: int):
    try:
        project = Project.objects.get(url=project_url)
    except (Project.DoesNotExist, ValidationError):
        return 404, {'detail': f'Project with url {project_url} does not exist'}
    if not project.contributor_is_admin(request.user):
        return 401, {'detail': f'Contributor is not project adminstrator'}
    try:
        entry = ProjectEntry.objects.get(id=entry_id, project=project)
    except (ProjectEntry.DoesNotExist, ValidationError, ValueError):
        return 404, {'detail': f'Entry with ID: {entry_id} not found'}
    entry.delete()
    return 200, {'detail': f'Successfully deleted entry {entry_id}'}


@router.patch('/projects/{project_url}/entries/{entry_id}', response={200: dict, 401: dict, 404: dict}, tags=['Project Entries'])
def update_project_entry(request, project_url: str, entry_id: int, update_data: ProjectEntryPatchSchema):
    try:
        project = Project.objects.get(url=project_url)
    except (Project.DoesNotExist, ValidationError):
        return 404, {'detail': f'Project with url {project_url} does not exist'}
    if not project.contributor_is_admin(request.user):
        return 401, {'detail': f'Contributor is not project adminstrator'}
    try:
        entry = ProjectEntry.objects.get(id=entry_id, project=project)
    except (ProjectEntry.DoesNotExist, ValidationError, ValueError):
        return 404, {'detail': f'Entry with ID: {entry_id} not found'}
    return entry.update_with_data(update_data)


@router.patch('/projects/{project_url}', response={200: dict, 401: dict, 404: dict}, tags=['Project Entries'])
def update_project(request, project_url: str, update_data: ProjectPatchSchema):
    try:
        project = Project.objects.get(url=project_url)
    except (Project.DoesNotExist, ValidationError):
        return 404, {'detail': f'Project with url {project_url} does not exist'}
    if not project.contributor_is_admin(request.user):
        return 401, {'detail': f'Contributor is not project adminstrator'}
    if update_data.name is not None:
        project.name = update_data.name
    if update_data.description is not None:
        project.description = update_data.description
    if update_data.talk_markdown is not None:
        project.talk_markdown = update_data.talk_markdown
    project.save()
    return {
        **model_to_dict(project),
        'type': project.project_type,
        'url': str(project.url),
        'created_at': project.created_at.isoformat(),
        'updated_at': project.updated_at.isoformat(),
        'administrators': [{'username': admin.username, 'email': admin.email} for admin in project.administrators.all()]
    }


@router.get('/projects/{project_url}/statistics', tags=['Project Management'])
def get_project_statistics(request, project_url: str):
    try:
        project = Project.objects.get(url=project_url)
    except (Project.DoesNotExist, ValidationError):
        return 404, {'detail': f'Project with url {project_url} does not exist'}
    return {
        'total_entries': project.entries.count(),
        'total_imported_texts': project.imported_texts.count(),
        **project.get_statistics()
    }


@router.post('/projects/{project_url}/import', response={200: dict, 401: dict, 404: dict, 400: dict}, tags=['Unannotated Entries'])
def import_unannotated(request, project_url: str, text_field: str, csv_delimiter: Optional[str] = None,
                       value_field: Optional[str] = None, context_field: Optional[str] = None, mt_system_translation: Optional[str] = None,
                       unannotated_data_file: UploadedFile = File(...)):
    try:
        project = Project.objects.get(url=project_url)
    except (Project.DoesNotExist, ValidationError):
        return 404, {'detail': f'Project with url {project_url} does not exist'}

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

    if project.project_type == 'Machine Translation Adequacy':
        text_field = {
            'reference_field': text_field,
            'mt_system_translation': mt_system_translation
        }
    elif project.project_type == 'Machine Translation Fluency':
        text_field = {
            'mt_system_translation': text_field
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
        return 404, {'detail': f'Project with url {project_url} does not exist'}
    return 200, [{
        **model_to_dict(entry),
        'project': project.name,
        'project_url': str(project.url),
        'pre_annotations': entry.pre_annotations,
        'created_at': entry.created_at.isoformat(),
        'updated_at': entry.updated_at.isoformat(),
        'context': entry.context if entry.context is not None else 'No context'
    } for entry in project.imported_texts]


@router.get('/projects/{project_url}/unannotated', response={200: list, 401: dict, 404: dict}, tags=['Unannotated Entries'])
def get_unannotated_entries(request, project_url: str):
    try:
        project = Project.objects.get(url=project_url)
    except (Project.DoesNotExist, ValidationError):
        return 404, {'detail': f'Project with url {project_url} does not exist'}
    return 200, [{
        **model_to_dict(entry),
        'project': project.name,
        'project_url': str(project.url),
        'pre_annotations': entry.pre_annotations,
        'created_at': entry.created_at.isoformat(),
        'updated_at': entry.updated_at.isoformat(),
        'context': entry.context if entry.context is not None else 'No context'
    } for entry in project.unannotated_texts]


@router.delete('/projects/{project_url}/import/{entry_id}', response={200: dict, 401: dict, 404: dict}, tags=['Unannotated Entries'])
def delete_unannotated_project_entry(request, project_url: str, entry_id: int):
    try:
        project = Project.objects.get(url=project_url)
    except (Project.DoesNotExist, ValidationError):
        return 404, {'detail': f'Project with url {project_url} does not exist'}
    if not project.contributor_is_admin(request.user):
        return 401, {'detail': f'Contributor is not project adminstrator'}
    try:
        entry = project.get_imported_entry(entry_id)
    except UnannotatedProjectEntry.DoesNotExist:
        return 404, {'detail': f'Unannotated entry with ID: {entry_id} not found'}
    entry.delete()
    return 200, {'detail': f'Successfully deleted unannotated entry {entry_id}'}


@router.get('/projects/{project_url}/export-disagreements')
def export_annotator_disagreements(request, project_url: str, annotator1: str, annotator2: str):
    try:
        project = Project.objects.get(url=project_url)
    except (Project.DoesNotExist, ValidationError):
        return 404, {'detail': f'Project with url {project_url} does not exist'}

    try:
        annotator1_user = PrivateAnnotator.objects.get(
            project=project, contributor__username=annotator1)
    except PrivateAnnotator.DoesNotExist:
        return 404, {'detail': f'Private Annotator with username {annotator1} does not exist'}

    try:
        annotator2_user = PrivateAnnotator.objects.get(
            project=project, contributor__username=annotator2)
    except PrivateAnnotator.DoesNotExist:
        return 404, {'detail': f'Private Annotator with username {annotator2} does not exist'}

    annotator1_entries = project.get_annotators_annotations(annotator1_user)
    annotator1_entries_source_id = [
        entry.unannotated_source.id for entry in annotator1_entries
    ]

    annotator2_entries = project.get_annotators_annotations(annotator2_user)
    annotator2_entries_source_id = [
        entry.unannotated_source.id for entry in annotator2_entries
    ]

    common_ids = [
        entry_id.unannotated_source.id
        for entry_id in [*annotator1_entries, *annotator2_entries]
        if entry_id.unannotated_source.id in annotator1_entries_source_id and entry_id.unannotated_source.id in annotator2_entries_source_id]

    disagreements = []
    for entry_id in common_ids:
        entry1 = annotator1_entries.get(unannotated_source__id=entry_id)
        entry2 = annotator2_entries.get(unannotated_source__id=entry_id)
        if entry1.values != entry2.values:
            disagreements.append(
                {
                    annotator1: entry1.values,
                    annotator2: entry2.values,
                    'text': entry1.unannotated_source.text
                }
            )

    # https://stackoverflow.com/questions/1156246/having-django-serve-downloadable-files
    response = HttpResponse(content_type='application/force-download', headers={
        'Content-Disposition': f'attachment; filename="disagreements-{annotator1}-{annotator2}.json"'
    })

    response.write(json.dumps(disagreements))

    return response


@router.get('/projects/{project_url}/export', tags=['Project Management'])
def export_project(request, project_url: str, export_type: str):
    try:
        project = Project.objects.get(url=project_url)
    except (Project.DoesNotExist, ValidationError):
        return 404, {'detail': f'Project with url {project_url} does not exist'}

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
