# -*- coding: utf-8 -*-
from django.db.models import *

class Page(Model):
	title = CharField(max_length=200, null=True, blank=True)
	url = URLField(verify_exists=False, unique=True)
	pr = FloatField(default=0.5)
	
class Link(Model):
	from_page = ForeignKey(Page, related_name="from_page")
	to_page = ForeignKey(Page, related_name="to_page")
	
class Word(Model):
	value = CharField(max_length=100, unique=True)
	
class WordInPage(Model):
	location = IntegerField()
	page = ForeignKey(Page)
	word = ForeignKey(Word)

