import logging

from django.core.exceptions import ValidationError

from allauth.core import context
from allauth.headless.adapter import get_adapter
from allauth.headless.internal.restkit import inputs
from allauth.socialaccount.adapter import (
    get_adapter as get_socialaccount_adapter,
)
from allauth.socialaccount.forms import SignupForm
from allauth.socialaccount.internal.flows.connect import validate_disconnect
from allauth.socialaccount.models import SocialAccount, SocialApp
from allauth.socialaccount.providers import registry
from allauth.socialaccount.providers.base.constants import AuthProcess

logger = logging.getLogger('allauth')
logger.setLevel(logging.DEBUG)

class SignupInput(SignupForm, inputs.Input):
    pass


class DeleteProviderAccountInput(inputs.Input):
    provider = inputs.CharField()
    account = inputs.CharField()

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user")
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        uid = cleaned_data.get("account")
        provider_id = cleaned_data.get("provider")
        if uid and provider_id:
            accounts = SocialAccount.objects.filter(user=self.user)
            account = accounts.filter(
                uid=uid,
                provider=provider_id,
            ).first()
            if not account:
                raise get_adapter().validation_error("account_not_found")
            validate_disconnect(context.request, account)
            self.cleaned_data["account"] = account
        return cleaned_data


class ProviderTokenInput(inputs.Input):
    provider = inputs.CharField()
    process = inputs.ChoiceField(
        choices=[
            (AuthProcess.LOGIN, AuthProcess.LOGIN),
            (AuthProcess.CONNECT, AuthProcess.CONNECT),
        ]
    )
    token = inputs.Field()

    def clean(self):
        cleaned_data = super().clean()
        print(f"Cleaned Data: {cleaned_data}")
        token = self.data.get("token")
        adapter = get_adapter()
        if not isinstance(token, dict):
            print(f"Token is not a dictionary: {token}")
            logger.error(f"Token is not a dictionary: {token}")
            self.add_error("token", adapter.validation_error("invalid_token"))
            token = None

        provider_id = cleaned_data.get("provider")
        print(f"Provider ID: {provider_id}")
        provider = None
        if provider_id and token:
            provider_class = registry.get_class(provider_id)
            # If `provider_id` is a sub provider ID we won't find it by class.
            client_id_required = provider_class is None or provider_class.uses_apps
            client_id = token.get("client_id")
            if client_id_required and not isinstance(client_id, str):
                self.add_error("token", adapter.validation_error("client_id_required"))
            else:
                try:
                    provider = get_socialaccount_adapter().get_provider(
                        context.request, provider_id, client_id=client_id
                    )
                except SocialApp.DoesNotExist:
                    social_apps = get_socialaccount_adapter().list_apps(context.request)
                    for app in social_apps:
                        print(app)
                    logger.error(f"SocialApp not found for provider ID: {provider_id}\nClient ID: {client_id}\nRequest: {context.request}")
                    self.add_error("token", adapter.validation_error("invalid_token"))
                else:
                    if not provider.supports_token_authentication:
                        self.add_error(
                            "provider",
                            adapter.validation_error(
                                "token_authentication_not_supported"
                            ),
                        )
                    elif (
                        provider.uses_apps
                        and client_id
                        and provider.app.client_id != client_id
                    ):
                        self.add_error(
                            "token", adapter.validation_error("client_id_mismatch")
                        )
                    else:
                        id_token = token.get("id_token")
                        access_token = token.get("access_token")
                        if (
                            (id_token is not None and not isinstance(id_token, str))
                            or (
                                access_token is not None
                                and not isinstance(access_token, str)
                            )
                            or (not id_token and not access_token)
                        ):
                            self.add_error(
                                "token", adapter.validation_error("token_required")
                            )
        if not self.errors:
            cleaned_data["provider"] = provider
            try:
                login = provider.verify_token(context.request, token)
                login.state["process"] = cleaned_data["process"]
                cleaned_data["sociallogin"] = login
            except ValidationError as e:
                print(f"Token verification failed: {e}")
                self.add_error("token", e)
        return cleaned_data
