import logging
from typing import Optional, Type

from django.utils.decorators import classonlymethod

from allauth.account.stages import LoginStage, LoginStageController
from allauth.core.exceptions import ReauthenticationRequired
from allauth.headless.base import response
from allauth.headless.constants import Client
from allauth.headless.internal import decorators
from allauth.headless.internal.restkit.views import RESTView


logger = logging.getLogger(__name__)


class APIView(RESTView):
    client = None

    @classonlymethod
    def as_api_view(cls, **initkwargs):
        view_func = cls.as_view(**initkwargs)
        if initkwargs["client"] == Client.APP:
            view_func = decorators.app_view(view_func)
        else:
            view_func = decorators.browser_view(view_func)
        return view_func

    def dispatch(self, request, *args, **kwargs):
        try:
            return super().dispatch(request, *args, **kwargs)
        except ReauthenticationRequired:
            return response.ReauthenticationResponse(self.request)


class AuthenticationStageAPIView(APIView):
    stage_class: Optional[Type[LoginStage]] = None

    def handle(self, request, *args, **kwargs):
        self.stage = LoginStageController.enter(request, self.stage_class.key)
        if not self.stage:
            logger.error(
                f"""
                In handle
                Request: {request.POST}
                User: {request.user}
                Stage: {self.stage_class}

                """
            )
            return response.UnauthorizedResponse(request)
        return super().handle(request, *args, **kwargs)

    def respond_stage_error(self):
        logger.error(
            f"""
            In response_stage_error
            Request: {self.request.POST}
            User: {self.request.user}
            Stage: {self.stage_class}
            """
        )
        return response.UnauthorizedResponse(self.request)

    def respond_next_stage(self):
        self.stage.exit()
        return response.AuthenticationResponse(self.request)


class AuthenticatedAPIView(APIView):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return response.AuthenticationResponse(request)
        return super().dispatch(request, *args, **kwargs)


class ConfigView(APIView):
    def get(self, request, *args, **kwargs):
        """
        The frontend queries (GET) this endpoint, expecting to receive
        either a 401 if no user is authenticated, or user information.
        """
        return response.ConfigResponse(request)
