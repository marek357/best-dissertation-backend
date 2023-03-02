from ninja import NinjaAPI
from annotators.api import router as annotators_router
from projectmanagement.api import router as project_management_router
from best_dissertation_backend.authenticators import (
    PublicAnnotatorAdminAndContributorAuth,
    PrivateAnnotatorAuth, fallback_auth
)

api = NinjaAPI(auth=[
    PublicAnnotatorAdminAndContributorAuth(),
    PrivateAnnotatorAuth(), fallback_auth
])

api.add_router('/management/', project_management_router)
api.add_router('/annotate/', annotators_router)
