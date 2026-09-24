from django import forms

from .checks import STAGES

MAX_SIZE = 25 * 1024 * 1024


class PaperCheckForm(forms.Form):
    stage = forms.ChoiceField(label="What are you submitting?", choices=list(STAGES.items()),
                              initial="camera_ready", widget=forms.RadioSelect)
    paper = forms.FileField(label="Your paper (Word, .docx)")
    pdf = forms.FileField(label="The same paper as PDF, saved from Word (optional, to check the number of pages)",
                          required=False)

    def clean_paper(self):
        paper = self.cleaned_data["paper"]
        if not paper.name.lower().endswith(".docx"):
            raise forms.ValidationError("Please upload the paper as a Word file (.docx).")
        if paper.size > MAX_SIZE:
            raise forms.ValidationError("The file is larger than 25 MB.")
        return paper

    def clean_pdf(self):
        pdf = self.cleaned_data.get("pdf")
        if pdf and (not pdf.name.lower().endswith(".pdf") or pdf.size > MAX_SIZE):
            raise forms.ValidationError("Please upload a PDF of at most 25 MB.")
        return pdf
