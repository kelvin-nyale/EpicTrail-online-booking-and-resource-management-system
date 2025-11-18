from django.apps import apps
from django.db import models

def show_model_structure(full_relationships=True):
    """
    Returns a structured string of all models and their fields,
    including ForeignKey, OneToOneField, and ManyToManyField if full_relationships=True.
    """
    output = []
    for model in apps.get_models():
        output.append(f"Model: {model.__name__}")
        for field in model._meta.get_fields():
            if isinstance(field, models.Field):
                field_name = field.name
                field_type = type(field).__name__
                pk_info = " (PK)" if getattr(field, 'primary_key', False) else ""
                
                relation_info = ""
                if full_relationships:
                    if isinstance(field, models.ForeignKey):
                        relation_info = f" -> FK to {field.related_model.__name__}"
                    elif isinstance(field, models.OneToOneField):
                        relation_info = f" -> O2O to {field.related_model.__name__}"
                    elif isinstance(field, models.ManyToManyField):
                        relation_info = f" -> M2M with {field.related_model.__name__}"

                output.append(f"  {field_name:15} {field_type}{pk_info}{relation_info}")
        output.append("")  # empty line between models
    return "\n".join(output)
