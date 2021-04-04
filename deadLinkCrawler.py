from typing import Optional, Generator
import asyncio
import aiohttp
import ssl
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from time import time
import uvloop


asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())


class Link:
    """The Link class represents links.

    Example:

    >>> link = Link('https://domain.com')
    >>> isinstance(link, Link)
    True
    """

    def __init__(self,
                 relativeTarget: str,
                 foundOn: Optional[str] = None,
                 linkTitle: Optional[str] = None,
                 works: Optional[bool] = None,
                 targetBody: Optional[str] = None) -> None:
        self.relativeTarget = relativeTarget
        self.foundOn = foundOn
        self.linkTitle = linkTitle
        self.works = works
        self.targetBody = targetBody

    def __str__(self) -> str:
        return self.absoluteTarget

    @property
    def absoluteTarget(self) -> str:
        """Return absolute URL for the link.

        Example:

        >>> link = Link('about', foundOn='https://domain.com/home')
        >>> print(link.absoluteTarget)
        https://domain.com/about

        >>> link = Link('https://otherdomain.com', foundOn='https://domain.com/home')
        >>> print(link.absoluteTarget)
        https://otherdomain.com
        """

        if self.foundOn:
            return urljoin(self.foundOn, self.relativeTarget)
        else:
            return self.relativeTarget


def find_links(html: str) -> list:
    return [
        Link(relativeTarget=href, linkTitle=(aTag.text or '<untitled>'))
        for aTag in BeautifulSoup(html, features="html.parser").find_all('a')
        if (href := aTag.attrs.get('href')) is not None
    ]


class DeadLinkCrawler:
    """Looks for dead (broken) links on a domain.

    Example:

    >>> crawler = DeadLinkCrawler()
    >>> crawler.startCrawl('http://danielhjertholm.me', verbose=False)
    >>> crawler.printDeadLinks()
    No dead links have been found.
    >>> len(crawler.checkedLinks)
    2
    >>> len(list(crawler.deadLinks))
    0
    """

    def __init__(self) -> None:
        self.checkedLinks = []
        self._sslContext = ssl.SSLContext()
        self._queuedLinks = []
        self._domain = None
        self._parsableContentTypes = ('text/html', 'text/xml', 'application/xml', 'application/xhtml+xml')

    def startCrawl(self,
                   url: str,
                   maxConcurrentRequests: int = 10,
                   errorText: str = 'Not Found',
                   verbose: bool = True) -> None:
        """Start scanning for dead links on the given URL."""

        self._verbose = verbose
        self._maxConcurrentRequests = maxConcurrentRequests
        self._errorText = errorText
        self._domain = '.'.join(urlparse(url).netloc.split('.')[-2:])
        startLink = Link(relativeTarget=url, linkTitle='Initial URL')
        self._queuedLinks.append(startLink)
        self._loop = asyncio.get_event_loop()
        self._loop.run_until_complete(self._main())

    def printDeadLinks(self) -> None:
        """Print out a summary of all dead links that have been found."""

        groupedLinks = {}
        for link in self.deadLinks:
            if link.foundOn in groupedLinks:
                groupedLinks[link.foundOn].append(link)
            else:
                groupedLinks[link.foundOn] = [link]
        if len(groupedLinks) > 0:
            for foundOn, deadLinks in groupedLinks.items():
                print(f'On the page {foundOn}, the following links were dead:')
                for deadLink in deadLinks:
                    print(f'  Link title: {deadLink.linkTitle}')
                    print(f'  Link URL: {deadLink.absoluteTarget}')
        else:
            print('No dead links have been found.')

    @property
    def deadLinks(self) -> Generator:
        return (link for link in self.checkedLinks if link.works is False)

    def _linkAlreadyChecked(self, link: Link) -> bool:
        return link.absoluteTarget in (checkedLink.absoluteTarget for checkedLink in self.checkedLinks)

    def _linkAlreadyQueued(self, link: Link) -> bool:
        return link.absoluteTarget in (queuedLink.absoluteTarget for queuedLink in self._queuedLinks)

    def _linkIsInternal(self, link: Link) -> bool:
        linkDomain = '.'.join(urlparse(link.absoluteTarget).netloc.split('.')[-2:])
        return linkDomain == self._domain

    def _allWorkIsDone(self):
        return len(self._tasks) == 0 and len(self._queuedLinks) == 0

    def _parseAndDiscardCompletedTasks(self):
        completedTasks = [task for task in self._tasks if task.done()]
        self._tasks = [task for task in self._tasks if not task.done()]

        for task in completedTasks:
            parentLink = task.result()
            if self._verbose and parentLink.works is False:
                print(f'Dead link with title "{parentLink.linkTitle}" and target {parentLink.absoluteTarget} found on {parentLink.foundOn}')
            if parentLink.targetBody:
                childLinksFound = find_links(parentLink.targetBody)
                for childLink in childLinksFound:
                    childLink.foundOn = parentLink.absoluteTarget
                    if not self._linkAlreadyChecked(childLink) and not self._linkAlreadyQueued(childLink) and self._linkIsInternal(childLink):
                        self._queuedLinks.append(childLink)

    def _startAdditionalTasksFromQueue(self, session: aiohttp.ClientSession):
        if len(self._tasks) < self._maxConcurrentRequests and len(self._queuedLinks) > 0:
            for i in range(self._maxConcurrentRequests - len(self._tasks)):
                if len(self._queuedLinks) > 0:
                    nextLink = self._queuedLinks.pop(0)
                    self.checkedLinks.append(nextLink)
                    newtask = asyncio.create_task(self._fetch(session, nextLink))
                    self._tasks.append(newtask)

    def _printStatus(self):
        try:
            if time() - self._lastStatusPrintoutTime > 10.0:
                print(f'Status: {len(self.checkedLinks)} links checked. {len([1 for link in self.checkedLinks if link.works is False])} dead.')
                # Must use "is False" above, otherwise the default value None will evaluate as False for the ~ _maxConcurrentRequests links that are currently being fetched.
                self._lastStatusPrintoutTime = time()
        except AttributeError:
            # If self does not have the attribute _lastStatusPrintoutTime, this is method's first run
            self._lastStatusPrintoutTime = time()

    async def _fetch(self, session: aiohttp.ClientSession, link: Link) -> Link:
        try:
            async with session.head(link.absoluteTarget, ssl=self._sslContext) as response:
                if response.status >= 401:
                    link.works = False
                    return link

                try:
                    contentType = response.headers['content-type'].lower()
                except AttributeError:  # contentType is None
                    parsable = True
                else:  # ContentType is not None
                    parsable = any(t in contentType for t in self._parsableContentTypes)

                if not parsable:
                    link.works = True
                    return link

                async with session.get(link.absoluteTarget, ssl=self._sslContext) as response:
                    body = await response.text()
                    if self._errorText in body:
                        link.works = False
                        return link
                    link.targetBody = body
                    link.works = True
                    return link
        except Exception:
            link.works = False
            return link

    async def _main(self) -> None:
        async with aiohttp.ClientSession() as session:
            self._tasks = []

            while not self._allWorkIsDone():
                self._parseAndDiscardCompletedTasks()
                self._startAdditionalTasksFromQueue(session)
                self._printStatus()
                await asyncio.sleep(0.01)

            if self._verbose:
                print(f'Crawl finished. Links checked: {len(self.checkedLinks)}. Dead links found: {len([1 for link in self.checkedLinks if link.works is False])}')


if __name__ == '__main__':
    import doctest
    doctest.testmod(verbose=True)

    crawler = DeadLinkCrawler()
    crawler.startCrawl('http://danielhjertholm.me/prosjekter.htm', verbose=True)
    crawler.printDeadLinks()
    checkedLinks = crawler.checkedLinks
    deadLinks = list(crawler.deadLinks)
