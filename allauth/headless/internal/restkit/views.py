import json
import logging
from typing import Dict, Optional, Type, Union

from django.http import HttpResponseBadRequest
from django.views.generic import View

from allauth.core.exceptions import ImmediateHttpResponse
from allauth.headless.internal.restkit.inputs import Input
from allauth.headless.internal.restkit.response import ErrorResponse

logger = logging.getLogger(__name__)

class RESTView(View):
    input_class: Union[Optional[Dict[str, Type[Input]]], Type[Input]] = None
    handle_json_input = True

    def dispatch(self, request, *args, **kwargs):
        return self.handle(request, *args, **kwargs)

    def handle(self, request, *args, **kwargs):
        logger.error("In allauth/headless/internal/restkit/views.py:RESTView:handle")
        if self.handle_json_input and request.method != "GET":
            self.data = self._parse_json(request)
            response = self.handle_input(self.data)
            if response:
                return response
        return super().dispatch(request, *args, **kwargs)

    def get_input_class(self):
        logger.error("In allauth/headless/internal/restkit/views.py:RESTView:get_input_class")
        input_class = self.input_class
        if isinstance(input_class, dict):
            input_class = input_class.get(self.request.method)

        logger.info(f"Using input class: {input_class}")

        return input_class

    def get_input_kwargs(self):
        return {}

    def handle_input(self, data):
        logger.error("In allauth/headless/internal/restkit/views.py:RESTView:handle_input")
        input_class = self.get_input_class()
        if not input_class:
            return
        input_kwargs = self.get_input_kwargs()
        if data is None:
            # Make form bound on empty POST
            data = {}
        self.input = input_class(data=data, **input_kwargs)
        if not self.input.is_valid():
            print("In handle invalid input")
            return self.handle_invalid_input(self.input)

    def handle_invalid_input(self, input):
        logger.error("In allauth/headless/internal/restkit/views.py:RESTView:handle_invalid_input")
        return ErrorResponse(self.request, input=input)

    def _parse_json(self, request):
        logger.error("In allauth/headless/internal/restkit/views.py:RESTView:_parse_json")
        if request.method == "GET" or not request.body:
            return
        try:
            data = json.loads(request.body.decode("utf8"))
            print(f"Parsed json: {data}")
            return data
        except (UnicodeDecodeError, json.JSONDecodeError):
            logger.error(f"""
                Error parsing JSON
                request: {request.body.decode("utf8")}
            """)
            raise ImmediateHttpResponse(response=HttpResponseBadRequest())
