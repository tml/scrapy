import signal

from twisted.internet import reactor, defer

from scrapy.xlib.pydispatch import dispatcher
from scrapy.core.engine import ExecutionEngine
from scrapy.resolver import CachingThreadedResolver
from scrapy.extension import ExtensionManager
from scrapy.utils.ossignal import install_shutdown_handlers, signal_names
from scrapy.utils.misc import load_object
from scrapy import log, signals


class Crawler(object):

    def __init__(self, settings):
        self.configured = False
        self.settings = settings

    def install(self):
        import scrapy.project
        assert not hasattr(scrapy.project, 'crawler'), "crawler already installed"
        scrapy.project.crawler = self

    def uninstall(self):
        import scrapy.project
        assert hasattr(scrapy.project, 'crawler'), "crawler not installed"
        del scrapy.project.crawler

    def configure(self):
        if self.configured:
            return
        self.configured = True
        self.extensions = ExtensionManager.from_crawler(self)
        spman_cls = load_object(self.settings['SPIDER_MANAGER_CLASS'])
        self.spiders = spman_cls.from_settings(self.settings)
        self.engine = ExecutionEngine(self, self._spider_closed)

    def crawl(self, spider, requests=None):
        spider.set_crawler(self)
        if requests is None:
            requests = spider.start_requests()
        return self.engine.open_spider(spider, requests)

    def _spider_closed(self, spider=None):
        if not self.engine.open_spiders:
            self.stop()

    @defer.inlineCallbacks
    def start(self):
        yield defer.maybeDeferred(self.configure)
        yield defer.maybeDeferred(self.engine.start)

    @defer.inlineCallbacks
    def stop(self):
        if self.engine.running:
            yield defer.maybeDeferred(self.engine.stop)


class CrawlerProcess(Crawler):
    """A class to run a single Scrapy crawler in a process. It provides
    automatic control of the Twisted reactor and installs some convenient
    signals for shutting down the crawl.
    """

    def __init__(self, *a, **kw):
        super(CrawlerProcess, self).__init__(*a, **kw)
        dispatcher.connect(self.stop, signals.engine_stopped)
        install_shutdown_handlers(self._signal_shutdown)

    def start(self):
        super(CrawlerProcess, self).start()
        if self.settings.getbool('DNSCACHE_ENABLED'):
            reactor.installResolver(CachingThreadedResolver(reactor))
        reactor.addSystemEventTrigger('before', 'shutdown', self.stop)
        reactor.run(installSignalHandlers=False) # blocking call

    def stop(self):
        d = super(CrawlerProcess, self).stop()
        d.addBoth(self._stop_reactor)
        return d

    def _stop_reactor(self, _=None):
        try:
            reactor.stop()
        except RuntimeError: # raised if already stopped or in shutdown stage
            pass

    def _signal_shutdown(self, signum, _):
        install_shutdown_handlers(self._signal_kill)
        signame = signal_names[signum]
        log.msg("Received %s, shutting down gracefully. Send again to force " \
            "unclean shutdown" % signame, level=log.INFO)
        reactor.callFromThread(self.stop)

    def _signal_kill(self, signum, _):
        install_shutdown_handlers(signal.SIG_IGN)
        signame = signal_names[signum]
        log.msg('Received %s twice, forcing unclean shutdown' % signame, \
            level=log.INFO)
        reactor.callFromThread(self._stop_reactor)
