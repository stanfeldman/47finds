from django.conf.urls.defaults import *
from django.conf import *
import searcher.views
import crawler.views
from django.contrib import admin
admin.autodiscover()

urlpatterns = patterns('',
	(r"^$", searcher.views.search),
	(r"^add_page/$", crawler.views.add_page),
	(r"^add/$", crawler.views.add),
	(r'^admin/', include(admin.site.urls)),
)

if settings.DEBUG:
    urlpatterns += patterns('',
        url(r'^static/(?P<path>.*)$', 'django.views.static.serve', {
            'document_root': settings.MEDIA_ROOT
        }),
   )


