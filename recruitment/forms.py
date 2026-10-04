from django import forms
from django.forms.models import BaseInlineFormSet, inlineformset_factory
from .models import Job, JobRequirement
from .services.scoring_service import canonical

class JobForm(forms.ModelForm):
    class Meta:
        model=Job
        fields=['title','description']
        widgets={'description':forms.Textarea(attrs={'rows':8,'placeholder':'Paste responsibilities, required skills and preferred qualifications…'}),'title':forms.TextInput(attrs={'placeholder':'e.g. Backend Developer Intern'})}
class RequirementForm(forms.ModelForm):
    category=forms.ChoiceField(choices=[(s,s.title()) for s in ['skills','projects','experience','education','expectations']])
    weight=forms.IntegerField(min_value=1,max_value=5)
    minimum_months=forms.IntegerField(min_value=1,required=False)
    minimum_count=forms.IntegerField(min_value=1,required=False)
    class Meta:
        model=JobRequirement
        fields=['label','canonical_key','category','essential','weight','minimum_months','minimum_count','jd_quote']
        widgets={'jd_quote':forms.HiddenInput()}
    def clean_canonical_key(self): return canonical(self.cleaned_data['canonical_key'])
    def clean(self):
        data=super().clean()
        if data.get('minimum_months') and data.get('category')!='experience': self.add_error('minimum_months','Months apply only to experience.')
        if data.get('minimum_count') and data.get('category')!='projects': self.add_error('minimum_count','Count applies only to projects.')
        return data
class RequirementFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors): return
        keys=[]
        for form in self.forms:
            if form.cleaned_data and not form.cleaned_data.get('DELETE'):
                key=form.cleaned_data.get('canonical_key')
                if key: keys.append(key)
        if not keys: raise forms.ValidationError('Add at least one requirement.')
        if len(set(keys))!=len(keys): raise forms.ValidationError('Canonical requirements must be unique; avoid double-counting a skill.')
RequirementSet=inlineformset_factory(Job,JobRequirement,form=RequirementForm,formset=RequirementFormSet,extra=1,max_num=15,validate_max=True,can_delete=True)
