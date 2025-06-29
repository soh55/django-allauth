import logging

from django.contrib.auth.decorators import login_required
from django.contrib.sites.shortcuts import get_current_site
from django.http import HttpResponseRedirect
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.views.generic.base import TemplateView
from django.views.generic.edit import FormView

from allauth.account.internal.decorators import login_not_required
from allauth.socialaccount.forms import DisconnectForm, SignupForm
from allauth.socialaccount.internal import flows
from allauth.socialaccount.models import SocialAccount

from ..account import app_settings as account_settings
from ..account.views import (
    AjaxCapableProcessFormViewMixin,
    CloseableSignupMixin,
    RedirectAuthenticatedUserMixin,
)
from ..utils import get_form_class
from . import app_settings
from .adapter import get_adapter

logger = logging.getLogger(__name__)

class SignupView(
    RedirectAuthenticatedUserMixin,
    CloseableSignupMixin,
    AjaxCapableProcessFormViewMixin,
    FormView,
):
    form_class = SignupForm
    template_name = "socialaccount/signup." + account_settings.TEMPLATE_EXTENSION

    def get_form_class(self):
        logger.info(f"allauth/socialaccount/views.py:SignupView:get_form_class: Getting form class for request: {self.request} SocialLogin: {self.sociallogin} Form: {type(self.form_class)}")
        form = get_form_class(app_settings.FORMS, "signup", self.form_class)
        logger.info(f"Found form: {type(form)}")
        return get_form_class(app_settings.FORMS, "signup", self.form_class)

    @method_decorator(login_not_required)
    def dispatch(self, request, *args, **kwargs):
        logger.info(f"allauth/socialaccount/views.py:SignupView:dispatch: Dispatching request: {request}")
        self.sociallogin = flows.signup.get_pending_signup(request)
        if not self.sociallogin:
            return HttpResponseRedirect(reverse("account_login"))
        return super(SignupView, self).dispatch(request, *args, **kwargs)

    def is_open(self):
        return get_adapter(self.request).is_open_for_signup(
            self.request, self.sociallogin
        )

    def get_form_kwargs(self):
        ret = super(SignupView, self).get_form_kwargs()
        ret["sociallogin"] = self.sociallogin
        return ret

    def form_valid(self, form):
        logger.info(f"allauth/socialaccount/views.py:SignupView:form_valid: Signing up by form for request: {self.request} SocialLogin: {self.sociallogin} Form: {type(form)}")
        return flows.signup.signup_by_form(self.request, self.sociallogin, form)

    def get_context_data(self, **kwargs):
        ret = super(SignupView, self).get_context_data(**kwargs)
        ret.update(
            dict(
                site=get_current_site(self.request),
                account=self.sociallogin.account,
            )
        )
        return ret

    def get_authenticated_redirect_url(self):
        return reverse("socialaccount_connections")


signup = SignupView.as_view()


@method_decorator(login_not_required, name="dispatch")
class LoginCancelledView(TemplateView):
    template_name = (
        "socialaccount/login_cancelled." + account_settings.TEMPLATE_EXTENSION
    )


login_cancelled = LoginCancelledView.as_view()


class LoginErrorView(TemplateView):
    template_name = (
        "socialaccount/authentication_error." + account_settings.TEMPLATE_EXTENSION
    )


login_error = LoginErrorView.as_view()


@method_decorator(login_required, name="dispatch")
class ConnectionsView(AjaxCapableProcessFormViewMixin, FormView):
    template_name = "socialaccount/connections." + account_settings.TEMPLATE_EXTENSION
    form_class = DisconnectForm
    success_url = reverse_lazy("socialaccount_connections")

    def get_form_class(self):
        return get_form_class(app_settings.FORMS, "disconnect", self.form_class)

    def get_form_kwargs(self):
        kwargs = super(ConnectionsView, self).get_form_kwargs()
        kwargs["request"] = self.request
        return kwargs

    def form_valid(self, form):
        form.save()
        return super(ConnectionsView, self).form_valid(form)

    def get_ajax_data(self):
        account_data = []
        for account in SocialAccount.objects.filter(user=self.request.user):
            provider_account = account.get_provider_account()
            account_data.append(
                {
                    "id": account.pk,
                    "provider": account.provider,
                    "name": provider_account.to_str(),
                }
            )
        return {"socialaccounts": account_data}


connections = ConnectionsView.as_view()
