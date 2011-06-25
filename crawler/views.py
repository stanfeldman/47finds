# -*- coding: utf-8 -*-
from django.shortcuts import *
from django.http import HttpResponseRedirect
import urllib2
from BeautifulSoup import *
from urlparse import urljoin
import re
from crawler.models import *
from django.contrib.auth.decorators import login_required

ignorewords = set(["the", "of", "to", "and", "a", "in", "is", "it", "о", "а", "в"])

def add_page(request):
	return render_to_response("crawler/templates/add_page.html", locals(), context_instance=RequestContext(request))

def add(request):
	pages = []
	page = request.POST["url"]
	if page[:7] != "http://":
		page = u"http://%s" % unicode(page)
	pages.append(page)
	crawl(pages)
	calculate_prs()
	return HttpResponseRedirect('/')

def crawl(pages, depth=3):
	for i in range(depth):
		newpages = set()
		for page in pages:
			try:
				c = urllib2.urlopen(page)
			except:
				continue
			try:
				soup = BeautifulSoup(c.read())
			except:
				continue
			add_to_index(page, soup)
			
			links = soup("a")
			for link in links:
				if "href" in dict(link.attrs):
					url = urljoin(page, link["href"])
					if url.find("'") != -1:
						continue
					#url = link["href"]
					url = url.split("#")[0]
					if url[:4] == "http":
						newpages.add(url)
					add_link(page, url)
		pages = newpages
		
def calculate_prs(iterations=10):
	for i in range(iterations):
		for page in Page.objects.all():
			pr_sum = 0
			for link in Link.objects.filter(to_page=page):
				count = Link.objects.filter(from_page=link.from_page).count()
				if count > 0:
					pr_sum += link.from_page.pr / count
			page.pr = 0.15 + 0.85 * pr_sum
			page.save()
			print page.pr
			
def add_to_index(url, soup):
	text = get_text(soup)
	words = separate_words(text)
	page = Page.objects.get_or_create(url=url)[0]
	page.title = unicode(soup.title.string)
	page.save()
	
	for i, word in enumerate(words):
		if word in ignorewords:
			continue
		word = Word.objects.get_or_create(value=word)[0]
		wl = WordInPage(location=i, word=word, page=page)
		wl.save()
		
def add_link(url1, url2):
	page = Page.objects.get_or_create(url=url1)[0]
	page2 = Page.objects.get_or_create(url=url2)[0]
	if Link.objects.filter(from_page=page, to_page=page2).count() == 0:
		link = Link(from_page=page, to_page=page2)
		link.save()
	
def get_text(soup):
	v = soup.string
	if v == None:
		c = soup.contents
		resulttext = ""
		for t in c:
			subtext = get_text(t)
			resulttext += subtext + "\n"
		return resulttext
	else:
		return unicode(v.strip())
		
def separate_words(text):
	splitter = re.compile("\\W*", re.U)
	return [s.lower() for s in splitter.split(text) if s != ""]
