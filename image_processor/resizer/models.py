from django.db import models


# Create your models here.
class Picture(models.Model):
    picture_name = models.CharField(max_length=256, blank=True)
    project_id = models.IntegerField(blank=True)
    state = models.IntegerField(blank=True, default=0)
    picture_data = models.BinaryField(blank=True)

    class Meta:
        db_table = 'picture'
        # app_label = 'fast_api'
