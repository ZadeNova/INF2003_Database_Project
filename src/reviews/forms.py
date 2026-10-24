from django import forms


class ReviewForm(forms.Form):
    score = forms.TypedChoiceField(choices=[(score, str(score)) for score in range(1, 6)], coerce=int)
    title = forms.CharField(max_length=200, required=False)
    text = forms.CharField(max_length=5000, required=False, widget=forms.Textarea(attrs={"rows": 5}))


class ModerationForm(forms.Form):
    action = forms.ChoiceField(choices=[("takedown", "Take down"), ("restore", "Restore")])
    reason = forms.CharField(max_length=500, widget=forms.Textarea(attrs={"rows": 2}))
