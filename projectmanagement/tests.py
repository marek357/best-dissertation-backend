import io
import json
from django.test import Client, TestCase
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from annotators.models import PublicAnnotator
from projectmanagement.models import Category, MachineTranslationAdequacyProject, Project, TextClassificationProject, TextClassificationProjectEntry, TextClassificationProjectUnannotatedEntry


class ProjectTests(TestCase):
    def setUp(self):
        test_administrator = get_user_model().objects.create(
            username='test-administrator', email='administrator@ucl.ac.uk',
            password='admin-password'
        )
        mock_public_annotator_unauthenticated_contributor = get_user_model().objects.create(
            username='127.0.0.1', email='anon@ucl.ac.uk',
            password='test-password'
        )
        self.mock_public_annotator = PublicAnnotator.objects.create(
            contributor=mock_public_annotator_unauthenticated_contributor
        )
        text_classification_project = TextClassificationProject.objects.create(
            name='TCProject', description='Description TC', talk_markdown='Project Markdown'
        )
        machine_translation_adequacy_project = MachineTranslationAdequacyProject.objects.create(
            name='MTAdequacyProject', description='Description MTAdequacy', talk_markdown='Project Markdown'
        )
        unannotated = TextClassificationProjectUnannotatedEntry.objects.create(
            project=text_classification_project, text='test'
        )
        classification = Category.objects.create(
            project=text_classification_project, name='category1', description='category1'
        )
        TextClassificationProjectEntry.objects.create(
            project=text_classification_project,
            unannotated_source=unannotated,
            annotator=self.mock_public_annotator,
            classification=classification
        )

    def test_add_entry(self):
        from collections import namedtuple
        project = Project.objects.get(name='TCProject')
        self.assertEqual(project.entries.count(), 1)
        payload = namedtuple('payload', ['payload', 'unannotated_source'])
        project.add_entry(
            self.mock_public_annotator, payload(
                {
                    'category-name': 'category1'
                }, unannotated_source=1
            )
        )
        self.assertEqual(project.entries.count(), 2)

    def test_project_list(self):
        client = Client()
        project_list = client.get('/api/management/projects/list')
        self.assertEqual(project_list.status_code, 200)
        self.assertEqual(Project.objects.all().count(), 2)
        self.assertEqual(len(project_list.json()),
                         Project.objects.all().count())
        self.assertEqual(project_list.json()[0].get('name'), 'TCProject')
        self.assertEqual(project_list.json()[1].get(
            'name'), 'MTAdequacyProject')
        self.assertEqual(project_list.json()[0].get(
            'description'), 'Description TC')
        self.assertEqual(project_list.json()[1].get(
            'description'), 'Description MTAdequacy'
        )
        self.assertEqual(project_list.json()[0].get(
            'talk_markdown'), project_list.json()[1].get('talk_markdown')
        )

    def test_project_create_missing_parameters(self):
        client = Client()
        new_project = client.post(
            '/api/management/create/',
            json.dumps({}),
            content_type='application/json'
        )
        self.assertEqual(new_project.status_code, 422)

    def test_project_create(self):
        client = Client()
        self.assertEqual(Project.objects.all().count(), 2)
        new_project = client.post(
            '/api/management/create/',
            json.dumps({
                'project_type': 'Machine Translation Fluency',
                'name': 'MTFluencyProject',
                'description': 'Description MTAFluency',
                'talk_markdown': 'Project Markdown'
            }),
            content_type='application/json'
        )
        self.assertEqual(new_project.status_code, 200)
        self.assertEqual(new_project.json().get('name'), 'MTFluencyProject')
        self.assertEqual(Project.objects.all().count(), 3)

    def test_project_list_by_type(self):
        client = Client()
        projects_list = client.get(
            '/api/management/projects/list?project_type=Text%20Classification')
        self.assertEqual(projects_list.status_code, 200)
        self.assertEqual(len(projects_list.json()), 1)

    def test_export_annotated_entries(self):
        client = Client()
        # Text Classification Project
        url = str(Project.objects.get(name='TCProject').url)
        export_request = client.get(
            f'/api/management/projects/{url}/export?export_type=json')
        self.assertEqual(export_request.status_code, 200)
        # https://stackoverflow.com/questions/8244220/django-unit-test-for-testing-a-file-download
        exported_file = json.loads(io.BytesIO(export_request.content).read())
        self.assertEqual(len(exported_file), 1)
        self.assertEqual(exported_file[0].get('category'), 'category1')
        self.assertEqual(exported_file[0].get('text'), 'test')

    def test_import_unannotated_entries(self):
        client = Client()
        project = Project.objects.all().first()
        text_field = 'text_field=text'
        upload_text = 'text\ntext1\ntext2\ntext3\n'
        if project.project_type == 'Machine Translation Adequacy':
            text_field = 'text_field=source&mt_system_translation=target'
            upload_text = 'source,target\nsource1,target1\nsource2,target2\nsource3,target3'
        # https://stackoverflow.com/questions/11170425/how-to-unit-test-file-upload-in-django
        upload_text_file = SimpleUploadedFile(
            'upload.csv', bytes(upload_text, 'utf-8'), content_type='text/csv'
        )
        upload_request = client.post(
            f'/api/management/projects/{project.url}/import?{text_field}&csv_delimiter=%2C',
            {'unannotated_data_file': upload_text_file}
        )
        self.assertEqual(upload_request.status_code, 200)
        self.assertTrue('detail' in upload_request.json())
        self.assertEqual(
            'Succesfully created 3 unannotated entries',
            upload_request.json().get('detail')
        )
