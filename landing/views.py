"""
:copyright: (c) 2014 Building Energy Inc
:license: see LICENSE for more details.
"""
from annoying.decorators import render_to
from django.contrib import auth
from django.contrib.auth import authenticate, login
from django.conf import settings
from django.core.urlresolvers import reverse
from django.forms.util import ErrorList
from django.forms.forms import NON_FIELD_ERRORS
from django.http import HttpResponseRedirect

from landing.forms import LoginForm, SetStrongPasswordForm

import logging
logger = logging.getLogger(__name__)


@render_to('landing/home.html')
def landing_page(request):
    if request.user.is_authenticated():
        return HttpResponseRedirect(reverse('seed:home'))
    login_form = LoginForm()
    return locals()


def _login_view(request):
    """Standard Django login plus lowercases the login email(username)"""
    if request.method == "POST":
        redirect_to = request.REQUEST.get('next', False)

        form = LoginForm(request.POST)
        if form.is_valid():
            new_user = authenticate(
                username=form.cleaned_data['email'].lower(),
                password=form.cleaned_data['password']
            )
            if new_user and new_user.is_active:
                login(request, new_user)
                if redirect_to:
                    return HttpResponseRedirect(redirect_to)
                else:
                    return HttpResponseRedirect(reverse("seed:home"))
            else:
                errors = ErrorList()
                errors = form._errors.setdefault(NON_FIELD_ERRORS, errors)
                errors.append('Username and/or password were invalid.')
    else:
        form = LoginForm()

    return locals()
login_view = render_to('landing/login.html')(_login_view)


def password_set(request, uidb64=None, token=None):
    return auth.views.password_reset_confirm(
        request,
        uidb64=uidb64,
        token=token,
        template_name='landing/password_set.html',
        post_reset_redirect=reverse('landing:password_set_complete')
    )


def password_reset(request):
    return auth.views.password_reset(
        request, template_name='landing/password_reset.html',
        subject_template_name='landing/password_reset_subject.txt',
        email_template_name='landing/password_reset_email.html',
        post_reset_redirect=reverse('landing:password_reset_done'),
        from_email=settings.PASSWORD_RESET_EMAIL
    )


def password_reset_done(request):
    return auth.views.password_reset_done(
        request,
        template_name='landing/password_reset_done.html'
    )


def password_reset_confirm(request, uidb64=None, token=None):
    return auth.views.password_reset_confirm(
        request,
        uidb64=uidb64,
        token=token,
        template_name='landing/password_reset_confirm.html',
        set_password_form=SetStrongPasswordForm,
        post_reset_redirect=reverse('landing:password_reset_complete')
    )


@render_to("landing/password_reset_complete.html")
def password_reset_complete(request):
    return locals()


def signup(request, uidb64=None, token=None):
    return auth.views.password_reset_confirm(
        request,
        uidb64=uidb64,
        token=token,
        template_name='landing/signup.html',
        set_password_form=SetStrongPasswordForm,
        post_reset_redirect=reverse('landing:landing_page') + "?setup_complete"
    )
