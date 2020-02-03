import asyncio
import aiohttp
import ssl
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from time import time


class Link:

    def __init__(self, relativeTarget, foundOn=None, linkTitle=None, works=None, targetBody=None):
        self.relativeTarget = relativeTarget
        self.foundOn = foundOn
        self.linkTitle = linkTitle
        self.works = works
        self.targetBody = targetBody

    @property
    def absoluteTarget(self):
        if self.foundOn:
            return urljoin(self.foundOn, self.relativeTarget)
        else:
            return self.relativeTarget


class LinkScanner(HTMLParser):

    def __init__(self):
        super(LinkScanner, self).__init__(convert_charrefs=True)
        self.urls = []
        self.currentlyInATag = False

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.currentlyInATag = True
            for attr in attrs:
                if attr[0] == 'href':
                    newLink = Link(relativeTarget=attr[1])
                    self.urls.append(newLink)

    def handle_data(self, data):
        if self.currentlyInATag:
            self.urls[-1].linkTitle = data

    def handle_endtag(self, tag):
        if tag == 'a':
            self.currentlyInATag = False

    def popUrls(self):
        urls = self.urls
        self.urls = []
        return urls


class DeadLinkCrawler:

    def __init__(self):
        self.checkedLinks = []
        self._linkSkanner = LinkScanner()
        self._sslContext = ssl.SSLContext()
        self._queuedLinks = []
        self._domain = None
        self._parsableContentTypes = ('text/html', 'text/xml', 'application/xml', 'application/xhtml+xml')

    def startCrawl(self, url, maxSimultanousUrlFetches=10, errorText='Not Found', verbose=True):
        self._verbose = verbose
        self._maxSimultanousUrlFetches = maxSimultanousUrlFetches
        self._errorText = errorText
        self._domain = '.'.join(urlparse(url).netloc.split('.')[-2:])
        startLink = Link(relativeTarget=url, linkTitle='Initial URL')
        self._queuedLinks.append(startLink)
        self._loop = asyncio.get_event_loop()
        self._loop.run_until_complete(self._main())

    def printDeadLinks(self):
        sortedLinks = {}
        for link in self.deadLinks:
            if link.foundOn in sortedLinks:
                sortedLinks[link.foundOn].append(link)
            else:
                sortedLinks[link.foundOn] = [link]
        for foundOn, deadLinks in sortedLinks.items():
            print(f'On the page {foundOn}, the following links were dead:')
            for deadLink in deadLinks:
                print(f'  Link title: {deadLink.linkTitle}')
                print(f'  Link URL: {deadLink.absoluteTarget}')

    @property
    def deadLinks(self):
        return (link for link in self.checkedLinks if link.works is False)

    def _linkAlreadyChecked(self, link):
        return link.absoluteTarget in (checkedLink.absoluteTarget for checkedLink in self.checkedLinks)

    def _linkAlreadyQueued(self, link):
        return link.absoluteTarget in (queuedLink.absoluteTarget for queuedLink in self._queuedLinks)

    def _linkIsInternal(self, link):
        linkDomain = '.'.join(urlparse(link.absoluteTarget).netloc.split('.')[-2:])
        return linkDomain == self._domain

    async def _fetch(self, session, link):
        assert(isinstance(link, Link))
        try:
            async with session.head(link.absoluteTarget, ssl=self._sslContext) as response:
                if response.status >= 401:
                    link.works = False
                    return link
                contentType = response.headers.get('content-type').lower()
                parsable = any(t in contentType for t in self._parsableContentTypes)
                if parsable:
                    async with session.get(link.absoluteTarget, ssl=self._sslContext) as response:
                        body = await response.text()
                        if self._errorText in body:
                            link.works = False
                            return link
                        else:
                            link.targetBody = body
                            link.works = True
                            return link
                else:
                    link.works = True
                    return link
        except Exception as e:
            link.works = False
            return link

    async def _main(self):
        async with aiohttp.ClientSession() as session:
            tasks = []
            lastStatusPrintoutTime = time() - 9.0
            while True:
                completedTasks = [task for task in tasks if task.done()]
                tasks = [task for task in tasks if not task.done()]

                for task in completedTasks:
                    parentLink = task.result()
                    if self._verbose and parentLink.works is False:
                        print(f'Dead link with title "{parentLink.linkTitle}" and target {parentLink.absoluteTarget} found on {parentLink.foundOn}')
                    if parentLink.targetBody:
                        self._linkSkanner.feed(parentLink.targetBody)
                        childLinksFound = self._linkSkanner.popUrls()
                        self._linkSkanner.reset()
                        for childLink in childLinksFound:
                            childLink.foundOn = parentLink.absoluteTarget
                            if not self._linkAlreadyChecked(childLink) and not self._linkAlreadyQueued(childLink) and self._linkIsInternal(childLink):
                                self._queuedLinks.append(childLink)

                if len(tasks) < self._maxSimultanousUrlFetches and len(self._queuedLinks) > 0:
                    for i in range(self._maxSimultanousUrlFetches - len(tasks)):
                        if len(self._queuedLinks) > 0:
                            nextLink = self._queuedLinks.pop(0)
                            self.checkedLinks.append(nextLink)
                            newtask = asyncio.create_task(self._fetch(session, nextLink))
                            tasks.append(newtask)

                if time() - lastStatusPrintoutTime > 10:
                    lastStatusPrintoutTime = time()
                    print(f'Status: {len(self.checkedLinks)} links checked. {len([1 for link in crawler.checkedLinks if link.works is False])} dead.')
                    # Must use "is False" above, otherwise the default value None will evaluate as False for the ~ _maxSimultanousUrlFetches links that are currently being fetched.

                if len(tasks) == 0 and len(self._queuedLinks) == 0:
                    if self._verbose:
                        print(f'Crawl finished. URLs checked: {len(crawler.checkedLinks)}. Dead URLs found: {len([1 for link in crawler.checkedLinks if link.works is False])}')
                    break
                await asyncio.sleep(0.01)


if __name__ == '__main__':
    crawler = DeadLinkCrawler()
    crawler.startCrawl('https://mdg.no/', verbose=True)
    crawler.printDeadLinks()
    checkedLinks = crawler.checkedLinks
    deadLinks = list(crawler.deadLinks)
