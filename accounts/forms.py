from django.contrib.auth.forms import UserChangeForm as DjangoUserChangeForm
from django.contrib.auth.forms import UserCreationForm as DjangoUserCreationForm
from .models import User

class UserCreationForm(DjangoUserCreationForm):
    username = None

    class Meta(DjangoUserCreationForm.Meta):
        model = User
        fields = ("email",)

class UserChangeForm(DjangoUserChangeForm):
    class Meta(DjangoUserChangeForm.Meta):
        model = User
        fields = "__all__"
