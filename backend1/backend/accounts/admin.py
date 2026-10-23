from django.contrib import admin

from accounts.models import City, Class, District, Province, School, TeacherClass, User

admin.site.register([Province, City, District, School, Class, TeacherClass, User])
