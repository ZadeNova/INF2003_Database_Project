from django.contrib import messages
from .forms import CustomerCreationForm
from django.urls import reverse_lazy
from django.views.generic.edit import CreateView
from django.conf import settings
from django.shortcuts import redirect
from django.db import transaction
from .models import CustomerProfile

class RegisterView(CreateView):
    form_class = CustomerCreationForm
    template_name = "accounts/register.html"
    success_url = reverse_lazy("accounts:login")

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect(settings.LOGIN_REDIRECT_URL)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        with transaction.atomic():
            response = super().form_valid(form)
            CustomerProfile.objects.create(user=self.object)
        messages.success(self.request, "Account created. You can now log in.")
        return response
