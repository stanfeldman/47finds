from django.core.management.base import BaseCommand, CommandError
from optparse import make_option
import settings
import os
import sys
import tornado.web
import tornadio
import tornadio.router
import tornadio.server
from os import path as op

ROOT = op.normpath(op.dirname(__file__))
 
class Command(BaseCommand):
    option_list = BaseCommand.option_list + (
        make_option('--reload', action='store_true',
            dest='use_reloader', default=False,
            help="Tells Tornado to use auto-reloader."),
        #make_option('--admin', action='store_true',
        #    dest='admin_media', default=False,
        #    help="Serve admin media."),
        #make_option('--adminmedia', dest='admin_media_path', default='',
        #    help="Specifies the directory from which to serve admin media."),
        make_option('--noxheaders', action='store_false',
            dest='xheaders', default=True,
            help="Tells Tornado to NOT override remote IP with X-Real-IP."),
        make_option('--nokeepalive', action='store_true',
            dest='no_keep_alive', default=False,
            help="Tells Tornado to NOT keep alive http connections."),
    )
    help = "Starts a Tornado Web."
    args = '[optional port number or ipaddr:port] (one or more, will start multiple servers)'

    # Validation is called explicitly each time the server is reloaded.
    requires_model_validation = False
 
    def handle(self, *addrport, **options):
        # reopen stdout/stderr file descriptor with write mode
        # and 0 as the buffer size (unbuffered).
        # XXX: why?
        sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0)
        sys.stderr = os.fdopen(sys.stderr.fileno(), 'w', 0)
 
        if len(addrport) == 0 :
            raise CommandError('Usage is runserver %s' % self.args)

        if len(addrport) == 1 :
            self.run_one(addrport[0], **options)
        else :
            from multiprocessing import Process

            plist = []
            for ap in addrport :
                p = Process(target=self.run_one, args=(ap,), kwargs=options)
                p.start()
                plist.append(p)

            # for p in plist : plist.terminate()

            while plist :
                if plist[0].exitcode is None :
                    plist.pop(0)
                else :
                    plist[0].join()
            

    def run_one(self, addrport, **options) :
        import django
        from django.core.handlers.wsgi import WSGIHandler
        from tornado import httpserver, wsgi, ioloop, web

        if not addrport:
            addr = ''
            port = '8000'
        else:
            try:
                addr, port = addrport.split(':')
            except ValueError:
                addr, port = '', addrport
        if not addr:
            addr = '127.0.0.1'
 
        if not port.isdigit():
            raise CommandError("%r is not a valid port number." % port)
 
        use_reloader = options.get('use_reloader', False)

        serve_admin_media = options.get('admin_media', False)
        admin_media_path = options.get('admin_media_path', '')

        xheaders = options.get('xheaders', True)
        no_keep_alive = options.get('no_keep_alive', False)

        shutdown_message = options.get('shutdown_message', '')
        quit_command = (sys.platform == 'win32') and 'CTRL-BREAK' or 'CONTROL-C'

        if settings.DEBUG :
            import logging
            logger = logging.getLogger()
            logger.setLevel(logging.DEBUG)
 
        def inner_run():
            from django.conf import settings
            from django.utils import translation
            print "Validating models..."
            self.validate(display_num_errors=True)
            print "\nDjango version %s, using settings %r" % (django.get_version(), settings.SETTINGS_MODULE)
            print "Server is running at http://%s:%s/" % (addr, port)
            print "Quit the server with %s." % quit_command

            # django.core.management.base forces the locate to en-us. We
            # should set it up correctly for the first request
            # (particularly important in the not "--reload" case).
            translation.activate(settings.LANGUAGE_CODE)

            try:
                application = tornado.web.Application(
                	[(r".*", DjangoHandler),],
                	socket_io_port = int(port)
                )
                http_server = tornadio.server.SocketServer(application)

                if hasattr(settings, 'TORNADO_STARTUP') :
                    from django.utils.importlib import import_module
                    for obj in settings.TORNADO_STARTUP :
                        # TODO - check to see if string or object
                        idx = obj.rindex('.')
                        func = getattr(import_module(obj[:idx]), obj[idx+1:])
                        func()

                ioloop.IOLoop.instance().start()
            except KeyboardInterrupt:
                if shutdown_message:
                    print shutdown_message
                sys.exit(0)
 
        if use_reloader:
            # Use tornado reload to handle IOLoop restarting.
            from tornado import autoreload
            autoreload.start()

        inner_run()

#
#  Modify copy of the base handeler with Tornado changes
#
from threading import Lock
from django.core.handlers import base
from django.core.urlresolvers import set_script_prefix
from django.core import signals

class DjangoHandler(tornado.web.RequestHandler, base.BaseHandler) :
    initLock = Lock()

    def __init__(self, *args, **kwargs) :
        super(DjangoHandler, self).__init__(*args, **kwargs)

        # Set up middleware if needed. We couldn't do this earlier, because
        # settings weren't available.
        self._request_middleware = None
        self.initLock.acquire()
        # Check that middleware is still uninitialised.
        if self._request_middleware is None:
            self.load_middleware()
        self.initLock.release()
        self._auto_finish = False

    def head(self) :
        self.get()

    def get(self) :
        from tornado.wsgi import HTTPRequest, WSGIContainer
        from django.core.handlers.wsgi import WSGIRequest, STATUS_CODE_TEXT
        import urllib

        environ  = WSGIContainer.environ(self.request)
        environ['PATH_INFO'] = urllib.unquote(environ['PATH_INFO'])
        request  = WSGIRequest(environ)

        request._tornado_handler     = self

        set_script_prefix(base.get_script_name(environ))
        signals.request_started.send(sender=self.__class__)
        try:
            response = self.get_response(request)

            if not response :
                return 

            # Apply response middleware
            for middleware_method in self._response_middleware:
                response = middleware_method(request, response)
            response = self.apply_response_fixes(request, response)
        finally:
            signals.request_finished.send(sender=self.__class__)

        try:
            status_text = STATUS_CODE_TEXT[response.status_code]
        except KeyError:
            status_text = 'UNKNOWN STATUS CODE'
        status = '%s %s' % (response.status_code, status_text)

        self.set_status(response.status_code)
        for h in response.items() :
            self.set_header(h[0], h[1])

        if not hasattr(self, "_new_cookies"):
            self._new_cookies = []
        self._new_cookies.append(response.cookies)

        self.write(response.content)
        self.finish()

    def post(self) :
        self.get()

    
    #
    #
    #
    def get_response(self, request):
        "Returns an HttpResponse object for the given HttpRequest"
        from django import http
        from django.core import exceptions, urlresolvers
        from django.conf import settings

        try:
            try:
                # Setup default url resolver for this thread.
                urlconf = settings.ROOT_URLCONF
                urlresolvers.set_urlconf(urlconf)
                resolver = urlresolvers.RegexURLResolver(r'^/', urlconf)

                # Apply request middleware
                for middleware_method in self._request_middleware:
                    response = middleware_method(request)
                    if response:
                        return response

                if hasattr(request, "urlconf"):
                    # Reset url resolver with a custom urlconf.
                    urlconf = request.urlconf
                    urlresolvers.set_urlconf(urlconf)
                    resolver = urlresolvers.RegexURLResolver(r'^/', urlconf)

                callback, callback_args, callback_kwargs = resolver.resolve(
                        request.path_info)

                # Apply view middleware
                for middleware_method in self._view_middleware:
                    response = middleware_method(request, callback, callback_args, callback_kwargs)
                    if response:
                        return response

                from ...decorator import TornadoAsyncException

                try:
                    response = callback(request, *callback_args, **callback_kwargs)
                except TornadoAsyncException, e:
                    #
                    #  Running under Tornado, so a null return is ok... means that the 
                    #   data is not finished
                    #
                    return
                except Exception, e:
                    # If the view raised an exception, run it through exception
                    # middleware, and if the exception middleware returns a
                    # response, use that. Otherwise, reraise the exception.
                    for middleware_method in self._exception_middleware:
                        response = middleware_method(request, e)
                        if response:
                            return response
                    raise

                # Complain if the view returned None (a common error).
                if response is None:
                    try:
                        view_name = callback.func_name # If it's a function
                    except AttributeError:
                        view_name = callback.__class__.__name__ + '.__call__' # If it's a class
                    raise ValueError("The view %s.%s didn't return an HttpResponse object." % (callback.__module__, view_name))

                return response
            except http.Http404, e:
                if settings.DEBUG:
                    from django.views import debug
                    return debug.technical_404_response(request, e)
                else:
                    try:
                        callback, param_dict = resolver.resolve404()
                        return callback(request, **param_dict)
                    except:
                        try:
                            return self.handle_uncaught_exception(request, resolver, sys.exc_info())
                        finally:
                            receivers = signals.got_request_exception.send(sender=self.__class__, request=request)
            except exceptions.PermissionDenied:
                return http.HttpResponseForbidden('<h1>Permission denied</h1>')
            except SystemExit:
                # Allow sys.exit() to actually exit. See tickets #1023 and #4701
                raise
            except Exception, e: # Handle everything else, including SuspiciousOperation, etc.
                # Get the exception info now, in case another exception is thrown later.
                exc_info = sys.exc_info()
                receivers = signals.got_request_exception.send(sender=self.__class__, request=request)
                return self.handle_uncaught_exception(request, resolver, exc_info)
        finally:
            # Reset URLconf for this thread on the way out for complete
            # isolation of request.urlconf
            urlresolvers.set_urlconf(None)
