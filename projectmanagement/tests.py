import json
from django.test import Client, TestCase
from django.contrib.auth import get_user_model

from projectmanagement.models import MachineTranslationAdequacyProject, Project, TextClassificationProject


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
        text_classification_project = TextClassificationProject.objects.create(
            name='TCProject', description='Description TC', talk_markdown='Project Markdown'
        )
        machine_translation_adequacy_project = MachineTranslationAdequacyProject.objects.create(
            name='MTAdequacyProject', description='Description MTAdequacy', talk_markdown='Project Markdown'
        )

    def test_project_list(self):
        client = Client()
        project_list = client.get('/api/management/projects/list')
        self.assertEqual(project_list.status_code, 200)
        self.assertEqual(Project.objects.all().count(), 2)
        self.assertEqual(len(project_list), Project.objects.all().count())
        self.assertEqual(project_list[0].get('name'), 'TCProject')
        self.assertEqual(project_list[1].get('name'), 'MTAdequacyProject')
        self.assertEqual(project_list[0].get('description'), 'Description TC')
        self.assertEqual(project_list[1].get(
            'description'), 'Description MTAdequacy'
        )
        self.assertEqual(project_list[0].get(
            'talk_markdown'), project_list[1].get('talk_markdown')
        )

    def test_project_create_fail(self):
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
        self.assertEqual(new_project.get('name'), 'MTFluencyProject')
        self.assertEqual(Project.objects.all().count(), 3)

    def test_project_list_by_type(self):
        client = Client()
        projects_list = client.get(
            '/api/management/list?project_type=Text%20Classification')
        self.assertEqual(projects_list.status_code, 200)
        self.assertEqual(len(projects_list), 1)
