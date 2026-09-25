from django import forms

from .models import ProcessedImage, TargetImage, VirtualObject

FILTER_CHOICES = [
    ("original", "Original"),
    ("clarity", "AI-style clarity (CLAHE + sharpen)"),
    ("denoise", "Noise reduction"),
    ("grayscale", "Grayscale"),
    ("edges", "Edge detection (Canny)"),
    ("neon", "Neon edge glow"),
    ("nightvision", "Night vision"),
    ("scan", "Document scanner"),
    ("cartoon", "Cartoon"),
    ("sketch", "Pencil sketch"),
    ("thermal", "Thermal heatmap"),
    ("negative", "Negative"),
    ("blur", "Gaussian blur"),
]


class ARUploadForm(forms.Form):
    """Upload a photo + choose an AR mode + optional overlay and filter."""

    MODE_CHOICES = [
        ("aruco", "Marker-based AR — detect ArUco markers & pin a virtual object"),
        ("orb", "Feature-based AR — match against a target image (ORB + homography)"),
        ("filter", "Image-processing filter only"),
    ]

    image = forms.ImageField(
        label="Scene photo",
        help_text="JPG/PNG. Contains an ArUco marker (ArUco mode) or your target (ORB mode).",
    )
    mode = forms.ChoiceField(choices=MODE_CHOICES, widget=forms.RadioSelect,
                             initial="aruco")
    overlay = forms.ModelChoiceField(
        queryset=VirtualObject.objects.all(), required=False,
        help_text="Virtual object to augment onto the scene (optional).",
    )
    target = forms.ModelChoiceField(
        queryset=TargetImage.objects.all(), required=False,
        help_text="Reference image to find (ORB mode).",
    )
    image_filter = forms.ChoiceField(choices=FILTER_CHOICES, required=False,
                                     initial="original")
    alpha = forms.IntegerField(
        min_value=0, max_value=100, initial=90,
        label="Overlay opacity %",
        widget=forms.NumberInput(attrs={"type": "range", "min": 0, "max": 100, "step": 5}),
    )

    def clean_alpha(self):
        return self.cleaned_data["alpha"] / 100.0


class TargetUploadForm(forms.ModelForm):
    class Meta:
        model = TargetImage
        fields = ["name", "image"]


class OverlayUploadForm(forms.ModelForm):
    class Meta:
        model = VirtualObject
        fields = ["name", "image"]


class ProcessedImageForm(forms.ModelForm):
    class Meta:
        model = ProcessedImage
        fields = ["title"]
