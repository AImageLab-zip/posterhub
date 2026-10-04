from django import forms
from .models import ResearchPoster


class PosterUploadForm(forms.ModelForm):
    ALLOWED_MIME_TYPES = {
        "image/jpeg", "image/png", "image/gif",
        "image/webp", "image/bmp", "image/tiff",
        "image/heic", "image/heif",
    }
    ALLOWED_EXTENSIONS = {
        "jpg", "jpeg", "png", "gif", "webp", "bmp", "tiff", "tif", "heic", "heif",
    }
    MAX_UPLOAD_SIZE = 20 * 1024 * 1024

    notes = forms.CharField(
        max_length=500,
        required=False,
        label="Notes",
        widget=forms.Textarea(attrs={
            "rows": 3,
            "placeholder": "Optional: personal notes about this paper…",
            "class": "form-control",
            "maxlength": "500",
        }),
    )
    tags = forms.CharField(
        max_length=200,
        required=False,
        label="Tags",
        help_text="Comma-separated — AI will match them to database categories",
        widget=forms.TextInput(attrs={
            "placeholder": "e.g. brain tumor, segmentation, 3D reconstruction…",
            "class": "form-control",
            "maxlength": "200",
        }),
    )

    class Meta:
        model = ResearchPoster
        fields = ["image", "notes", "tags"]

    def clean_image(self):
        image = self.cleaned_data.get("image")
        if not image:
            return image
        if image.size > self.MAX_UPLOAD_SIZE:
            raise forms.ValidationError("File troppo grande (massimo 20 MB).")
        mime = getattr(image, "content_type", "")
        name = getattr(image, "name", "")
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if mime not in self.ALLOWED_MIME_TYPES and ext not in self.ALLOWED_EXTENSIONS:
            raise forms.ValidationError(
                "Tipo di file non valido. Formati ammessi: JPG, PNG, GIF, WEBP, BMP, TIFF, HEIC."
            )
        return image


class SubfieldsMultipleWidget(forms.CheckboxSelectMultiple):
    template_name = "_subfields_grouped.html"

    def __init__(self, grouped_choices=None, *args, **kwargs):
        self.grouped_choices = grouped_choices or ResearchPoster.SUBFIELDS_GROUPED
        flat = [pair for _, _, items in self.grouped_choices for pair in items]
        super().__init__(*args, choices=flat, **kwargs)

    def get_context(self, name, value, attrs):
        ctx = super().get_context(name, value, attrs)
        ctx["widget"]["grouped_choices"] = self.grouped_choices
        ctx["widget"]["selected_values"] = value or []
        return ctx


class PosterEditForm(forms.ModelForm):
    subfields = forms.MultipleChoiceField(
        choices=ResearchPoster.SUBFIELD_CHOICES,
        widget=SubfieldsMultipleWidget(),
        required=False,
        label="Subfields",
    )

    publication_year = forms.IntegerField(
        required=False,
        label="Publication Year",
        widget=forms.NumberInput(attrs={"placeholder": "e.g. 2024", "min": "1900", "max": "2100"}),
    )

    class Meta:
        model = ResearchPoster
        fields = [
            "title", "authors", "institution", "paper_link", "github_link",
            "summary", "why_useful", "category", "subfields", "tags",
            "conference", "publication_year", "validation_status", "notes",
        ]
        widgets = {
            "institution": forms.TextInput(attrs={"maxlength": "500", "placeholder": "e.g. University of Modena and Reggio Emilia"}),
            "conference": forms.TextInput(attrs={
                "maxlength": "200", "list": "conferenceOptions", "autocomplete": "off",
                "placeholder": "e.g. MICCAI 2026",
            }),
            "summary": forms.Textarea(attrs={"rows": 4}),
            "why_useful": forms.Textarea(attrs={"rows": 3}),
            "notes": forms.Textarea(attrs={"rows": 4, "maxlength": "500"}),
            "tags": forms.TextInput(attrs={"maxlength": "200", "id": "id_tags"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.initial["subfields"] = self.instance.subfields_list

    def clean_subfields(self):
        return ",".join(self.cleaned_data.get("subfields") or [])
