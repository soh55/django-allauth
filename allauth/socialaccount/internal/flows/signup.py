import logging

from django.forms import ValidationError

from allauth.account import app_settings as account_settings
from allauth.account.adapter import get_adapter as get_account_adapter
from allauth.account.internal.flows.manage_email import assess_unique_email
from allauth.account.internal.flows.signup import (
    complete_signup,
    prevent_enumeration,
)
from allauth.account.utils import user_username
from allauth.core.exceptions import SignupClosedException
from allauth.core.internal.httpkit import headed_redirect_response
from allauth.socialaccount import app_settings
from allauth.socialaccount.adapter import get_adapter
from allauth.socialaccount.models import SocialLogin

logger = logging.getLogger(__name__)

def get_pending_signup(request):
    logger.info(f"allauth/socialaccount/internal/flows/signup.py:get_pending_signup: Retrieving pending signup for request: {request}")
    data = request.session.get("socialaccount_sociallogin")
    if data:
        return SocialLogin.deserialize(data)


def redirect_to_signup(request, sociallogin):
    logger.info(f"allauth/socialaccount/internal/flows/signup.py:redirect_to_signup: Redirecting to signup for request: {request}")
    request.session["socialaccount_sociallogin"] = sociallogin.serialize()
    return headed_redirect_response("socialaccount_signup")


def clear_pending_signup(request):
    logger.info(f"allauth/socialaccount/internal/flows/signup.py:clear_pending_signup: Clearing pending signup for request: {request}")
    request.session.pop("socialaccount_sociallogin", None)


def signup_by_form(request, sociallogin, form):
    logger.info(f"allauth/socialaccount/internal/flows/signup.py:signup_by_form: Signing up by form for request: {request} SocialLogin: {sociallogin} Form: {type(form)}")
    clear_pending_signup(request)
    user, resp = form.try_save(request)
    if not resp:
        resp = complete_social_signup(request, sociallogin)
    return resp


def process_auto_signup(request, sociallogin):
    logger.info(f"allauth/socialaccount/internal/flows/signup.py:process_auto_signup: Processing auto signup for request: {request} SocialLogin: {sociallogin}")
    auto_signup = get_adapter().is_auto_signup_allowed(request, sociallogin)
    if not auto_signup:
        return False, None
    email = None
    if sociallogin.email_addresses:
        email = sociallogin.email_addresses[0].email
    # Let's check if auto_signup is really possible...
    if email:
        assessment = assess_unique_email(email)
        if assessment is True:
            logger.info(f"allauth/socialaccount/internal/flows/signup.py:process_auto_signup: Auto signup is fine for email: {email}")
            # Auto signup is fine.
            pass
        elif assessment is False:
            logger.info(f"allauth/socialaccount/internal/flows/signup.py:process_auto_signup: Another user already has this email: {email}")
            # Oops, another user already has this address.  We cannot simply
            # connect this social account to the existing user. Reason is
            # that the email address may not be verified, meaning, the user
            # may be a hacker that has added your email address to their
            # account in the hope that you fall in their trap.  We cannot
            # check on 'email_address.verified' either, because
            # 'email_address' is not guaranteed to be verified.
            auto_signup = False
            # TODO: We redirect to signup form -- user will see email
            # address conflict only after posting whereas we detected it
            # here already.
        else:
            logger.info(f"allauth/socialaccount/internal/flows/signup.py:process_auto_signup: Auto signup is fine for email: {email}")
            assert assessment is None  # nosec
            # Prevent enumeration is properly turned on, meaning, we cannot
            # show the signup form to allow the user to input another email
            # address. Instead, we're going to send the user an email that
            # the account already exists, and on the outside make it appear
            # as if an email verification mail was sent.
            resp = prevent_enumeration(request, email=email)
            return False, resp
    elif app_settings.EMAIL_REQUIRED:
        logger.info(f"allauth/socialaccount/internal/flows/signup.py:process_auto_signup: Email is required for email: {email}")
        # Nope, email is required and we don't have it yet...
        auto_signup = False
    return auto_signup, None


def process_signup(request, sociallogin):
    logger.error("In allauth/socialaccount/internal/flows/signup.py - process_signup")
    if not get_adapter().is_open_for_signup(request, sociallogin):
        raise SignupClosedException()
    auto_signup, resp = process_auto_signup(request, sociallogin)
    if resp:
        return resp
    if not auto_signup:
        logger.error("Redirecting to signup page")
        resp = redirect_to_signup(request, sociallogin)
    else:
        # Ok, auto signup it is, at least the email address is ok.
        # We still need to check the username though...
        if account_settings.USER_MODEL_USERNAME_FIELD:
            username = user_username(sociallogin.user)
            try:
                get_account_adapter(request).clean_username(username)
            except ValidationError:
                logger.error("Invalid username")
                # This username is no good ...
                user_username(sociallogin.user, "")
        # TODO: This part contains a lot of duplication of logic
        # ("closed" rendering, create user, send email, in active
        # etc..)
        get_adapter().save_user(request, sociallogin, form=None)
        resp = complete_social_signup(request, sociallogin)
    return resp


def complete_social_signup(request, sociallogin):
    logger.info(f"allauth/socialaccount/internal/flows/signup.py:complete_social_signup: Auto signup is fine for email: {sociallogin.user.email}")
    return complete_signup(
        request,
        user=sociallogin.user,
        email_verification=app_settings.EMAIL_VERIFICATION,
        redirect_url=sociallogin.get_redirect_url(request),
        signal_kwargs={"sociallogin": sociallogin},
    )
