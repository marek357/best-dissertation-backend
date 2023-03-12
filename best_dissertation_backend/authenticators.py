from django.http import HttpRequest
from annotators.models import PrivateAnnotator
from ninja.security import HttpBearer, APIKeyQuery
from django.contrib.auth import get_user_model
from firebase_admin import auth


class PublicAnnotatorAdminAndContributorAuth(HttpBearer):
    def authenticate(self, request: HttpRequest, token: str):
        try:
            print(f'trying to decode token: {token}')
            decoded_token = auth.verify_id_token(token)
            user_id = decoded_token['uid']
        except Exception as e:
            print(e)
            return False
        try:
            contributor = get_user_model().objects.get(username=user_id)
        except get_user_model().DoesNotExist:
            contributor = get_user_model().objects.create_user(
                username=user_id, email=decoded_token['email']
            )
            contributor.set_unusable_password()
        request.user = contributor
        return True


class PrivateAnnotatorAuth(APIKeyQuery):
    param_name = 'token'

    def authenticate(self, request: HttpRequest, token: str):
        try:
            annotator = PrivateAnnotator.objects.get(token=token)
        except PrivateAnnotator.DoesNotExist:
            return False
        if annotator.contributor.is_active:
            request.user = annotator.contributor
            return True
        return False


def fallback_auth(request: HttpRequest):
    try:
        print('fallback')
        # https://stackoverflow.com/questions/4581789/how-do-i-get-user-ip-address-in-django
        contributor = get_user_model().objects.get(
            username=request.META.get('REMOTE_ADDR')
        )
    except get_user_model().DoesNotExist:
        contributor = get_user_model().objects.create_user(
            username=request.META.get('REMOTE_ADDR'), email='anon@ucl.ac.uk'
        )
        contributor.set_unusable_password()
    request.user = contributor
    return True
