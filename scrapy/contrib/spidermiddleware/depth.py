"""
Depth Spider Middleware

See documentation in docs/topics/spider-middleware.rst
"""

import warnings

from scrapy import log
from scrapy.http import Request
from scrapy.exceptions import ScrapyDeprecationWarning

class DepthMiddleware(object):

    def __init__(self, maxdepth, stats=None, verbose_stats=False, prio=1):
        self.maxdepth = maxdepth
        self.stats = stats
        self.verbose_stats = verbose_stats
        self.prio = prio

    @classmethod
    def from_settings(cls, settings):
        maxdepth = settings.getint('DEPTH_LIMIT')
        usestats = settings.getbool('DEPTH_STATS')
        verbose = settings.getbool('DEPTH_STATS_VERBOSE')
        sorder = settings['SCHEDULER_ORDER']
        if sorder:
            # XXX: backwards compatibility with old SCHEDULER_ORDER setting
            # will be removed on Scrapy 0.15
            warnings.warn("SCHEDULER_ORDER setting is deprecated, " \
                "use DEPTH_PRIORITY instead", ScrapyDeprecationWarning)
            if sorder == 'BFO':
                prio = 1
            elif sorder == 'DFO':
                prio = -1
        else:
            prio = settings.getint('DEPTH_PRIORITY')
        if usestats:
            from scrapy.stats import stats
        else:
            stats = None
        return cls(maxdepth, stats, verbose, prio)

    def process_spider_output(self, response, result, spider):
        def _filter(request):
            if isinstance(request, Request):
                depth = response.request.meta['depth'] + 1
                request.meta['depth'] = depth
                if self.prio:
                    request.priority += depth * self.prio
                if self.maxdepth and depth > self.maxdepth:
                    log.msg("Ignoring link (depth > %d): %s " % (self.maxdepth, request.url), \
                        level=log.DEBUG, spider=spider)
                    return False
                elif self.stats:
                    if self.verbose_stats:
                        self.stats.inc_value('request_depth_count/%s' % depth, spider=spider)
                    self.stats.max_value('request_depth_max', depth, spider=spider)
            return True

        # base case (depth=0)
        if self.stats and 'depth' not in response.request.meta: 
            response.request.meta['depth'] = 0
            if self.verbose_stats:
                self.stats.inc_value('request_depth_count/0', spider=spider)

        return (r for r in result or () if _filter(r))
