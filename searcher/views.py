# -*- coding: utf-8 -*-
from django.shortcuts import *
from django.http import HttpResponseRedirect
from crawler.models import *

def search(request):
	if "query" in request.POST:
		q = request.POST["query"]
		pages = query(q)
		is_searched = True
	return render_to_response("searcher/templates/search.html", locals(), context_instance=RequestContext(request))
	
def query(q):
	rows = get_match_rows(q)
	if len(rows) == 0:
		return
	scores = get_scored_list(rows)
	return sorted(scores, key = lambda item: item.rank, reverse=True)[:10]

def get_match_rows(query):
	words = unicode(query).split(" ")
	pages = Page.objects.filter(wordinpage__word__value__in=words).distinct()
	for page in pages:
		page.wips = WordInPage.objects.filter(page=page, word__value__in=words) 
		page.rank = 0
	return pages
	
def get_scored_list(rows):
	weights = [(1.5, location_score(rows)), (1.0, frequency_score(rows)), (0.5, pr_score(rows))]
	for (weight, scores) in weights:
		for row in rows:
			row.rank += weight*scores[row]
	return rows
	
def normalize_scores(scores):
	maxscore = max(scores.values())
	if maxscore == 0:
		maxscore = 0.000001
	return dict([(key, float(value)/maxscore) for (key, value) in scores.items()])

def pr_score(rows):
	max_pr = max(map(lambda r: r.pr, rows))
	print "max_pr: %s" % max_pr
	results = dict([(row, row.pr / max_pr) for row in rows])
	return results
		
def frequency_score(rows):
	results = dict([(row, len(row.wips) / WordInPage.objects.filter(page=row).count()) for row in rows])
	return normalize_scores(results)
	
def location_score(rows):
	results = dict()
	for row in rows:
		results[row] = 100000 - min(map(lambda wip: wip.location, row.wips))
	return normalize_scores(results)


