from django.db import models


class TsVectorField(models.Field):
    def db_type(self, connection):
        return 'tsvector'
