import logging
from django.http import HttpResponseRedirect
from django.shortcuts import render

from allauth.account import app_settings as account_settings
from allauth.account.adapter import get_adapter as get_account_adapter
from allauth.account.utils import perform_login
from allauth.core.exceptions import (
    ImmediateHttpResponse,
    SignupClosedException,
)
from allauth.socialaccount import app_settings, signals
from allauth.socialaccount.adapter import get_adapter
from allauth.socialaccount.internal.flows.connect import connect, do_connect
from allauth.socialaccount.internal.flows.signup import (
    clear_pending_signup,
    process_signup,
)
from allauth.socialaccount.models import SocialLogin
from allauth.socialaccount.providers.base import AuthProcess

logger = logging.getLogger(__name__)

def _login(request, sociallogin):
    logger.error("In allauth/socialaccount/internal/flows/login.py - _login")
    sociallogin._accept_login(request)
    record_authentication(request, sociallogin)
    return perform_login(
        request,
        sociallogin.user,
        email_verification=app_settings.EMAIL_VERIFICATION,
        redirect_url=sociallogin.get_redirect_url(request),
        signal_kwargs={"sociallogin": sociallogin},
    )


def pre_social_login(request, sociallogin):
    logger.error("In allauth/socialaccount/internal/flows/login.py - pre_social_login")
    clear_pending_signup(request)
    assert not sociallogin.is_existing  # nosec
    sociallogin.lookup()
    get_adapter().pre_social_login(request, sociallogin)
    signals.pre_social_login.send(
        sender=SocialLogin, request=request, sociallogin=sociallogin
    )


def complete_login(request, sociallogin, raises=False):
    logger.error("In allauth/socialaccount/internal/flows/login.py - complete_login")
    try:
        pre_social_login(request, sociallogin)
        process = sociallogin.state.get("process")
        if process == AuthProcess.REDIRECT:
            return _redirect(request, sociallogin)
        elif process == AuthProcess.CONNECT:
            if raises:
                do_connect(request, sociallogin)
            else:
                return connect(request, sociallogin)
        else:
            return _authenticate(request, sociallogin)
    except SignupClosedException:
        logger.error("Signup is closed")
        if raises:
            raise
        return render(
            request,
            "account/signup_closed." + account_settings.TEMPLATE_EXTENSION,
        )
    except ImmediateHttpResponse as e:
        logger.error("ImmediateHttpResponse")
        if raises:
            raise
        return e.response


def _redirect(request, sociallogin):
    next_url = sociallogin.get_redirect_url(request) or "/"
    return HttpResponseRedirect(next_url)


def _authenticate(request, sociallogin):
    logger.error("In allauth/socialaccount/internal/flows/login.py - _authenticate")
    logger.error(f"""
        Social Login: {sociallogin}
        User: {request.user}
        Social token: {sociallogin.token}
        Social email: {sociallogin.email_addresses}
        Login state: {sociallogin.state}
        Did auth by email: {sociallogin._did_authenticate_by_email}

        """)
    if request.user.is_authenticated:
        logger.error("User is authenticated")
        get_account_adapter(request).logout(request)
    if sociallogin.is_existing:
        # Login existing user
        logger.error("Login existing user")
        ret = _login(request, sociallogin)
    else:
        logger.error("New social user")
        # New social user
        ret = process_signup(request, sociallogin)
    logger.error("Authentication completed")
    return ret


def record_authentication(request, sociallogin):
    logger.error("In allauth/socialaccount/internal/flows/login.py - record_authentication")
    from allauth.account.internal.flows.login import record_authentication

    record_authentication(
        request,
        "socialaccount",
        **{
            "provider": sociallogin.account.provider,
            "uid": sociallogin.account.uid,
        }
    )
