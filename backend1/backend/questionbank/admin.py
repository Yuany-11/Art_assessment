from django.contrib import admin

from questionbank.models import Chapter, Course, Question, QuestionOption, QuestionResource

admin.site.register([Course, Chapter, Question, QuestionOption, QuestionResource])
